from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.models import AnalysisResponse, Finding, AnomalyResult, RewriteResult
from src.agent.tools import TOOL_SCHEMAS

logger = logging.getLogger(__name__)

AGENT_SYSTEM_PROMPT = """You are a senior database performance analyst for an insurance \
Policy Administration System (PAS). You diagnose SQL performance issues, detect anomalies, \
and suggest specific fixes.

You have tools available. Use them to gather evidence before answering:
1. search_cases  — ALWAYS call this first to find similar past incidents
2. analyze_sql   — call when the user provides or mentions a SQL query
3. detect_anomaly— call when the user mentions latency spikes or unusual behavior
4. rewrite_query — call to produce corrected SQL with index suggestions
5. get_schema    — call when you need column names or table structure

Rules:
- Base your answer on tool results, not general knowledge
- Call multiple tools if relevant — call them all before answering
- Provide specific fixes (CREATE INDEX statements, rewritten SQL)
- Rate confidence: high (rule match + RAG match), medium (one source), low (general reasoning)
- Insurance context: policy_data has 50M rows, claims_data 8M rows — performance is critical
- Respond ONLY as valid JSON:
  {"problem":"...","root_cause":"...","suggestion":["..."],"confidence":0.95,"category":"...","severity":"critical|high|medium|low"}"""


class AgentOrchestrator:
    """Central orchestrator: ReAct agent loop (online) + fixed pipeline (offline).

    All three interfaces (CLI, REST API, MCP server) call ``process()`` and
    receive an ``AnalysisResponse``.  The orchestrator is the single point of
    truth — no business logic exists in the interfaces.
    """

    def __init__(
        self,
        retriever,
        rule_engine,
        anomaly_detector,
        rewriter,
        schemas: dict,
        cache,
        settings,
    ) -> None:
        self.retriever = retriever
        self.rule_engine = rule_engine
        self.anomaly_detector = anomaly_detector
        self.rewriter = rewriter
        self.schemas = schemas
        self.cache = cache
        self.settings = settings

    # ─── Public API ──────────────────────────────────────────────────────────

    def process(self, user_query: str, sql: str | None = None) -> AnalysisResponse:
        """Main entry point. Returns a structured AnalysisResponse."""
        start = time.time()

        # Cache check (skip processing entirely on hit)
        cache_key = user_query + (f" SQL:{sql}" if sql else "")
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        chain: list[dict] = []

        if self.settings.llm_available:
            result = self._agent_loop(user_query, sql, chain)
        else:
            result = self._fixed_pipeline(user_query, sql, chain)

        result.metadata["processing_time_ms"] = int((time.time() - start) * 1000)
        result.metadata["mode"] = "online" if self.settings.llm_available else "offline"
        result.explanation_chain = chain

        self.cache.put(cache_key, result)
        return result

    # ─── Agent loop (online) ─────────────────────────────────────────────────

    def _agent_loop(
        self, user_query: str, sql: str | None, chain: list[dict]
    ) -> AnalysisResponse:
        """ReAct loop: LLM decides which tools to call each step."""
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=self.settings.llm_api_key,
                base_url=self.settings.llm_base_url or None,
            )
        except Exception as exc:
            logger.warning(
                "OpenAI client init failed (%s) — falling back to fixed pipeline", exc
            )
            return self._fixed_pipeline(user_query, sql, chain)

        messages: list[dict] = [
            {"role": "system", "content": AGENT_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": user_query + (f"\n\nSQL: {sql}" if sql else ""),
            },
        ]
        tool_results: dict[str, Any] = {}

        for step in range(self.settings.agent_max_steps):
            try:
                response = client.chat.completions.create(
                    model=self.settings.llm_model,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                )
            except Exception as exc:
                logger.warning(
                    "LLM call failed at step %d (%s) — falling back", step, exc
                )
                return self._fixed_pipeline(user_query, sql, chain)

            choice = response.choices[0]
            chain.append({"step": step + 1, "finish_reason": choice.finish_reason})

            if choice.finish_reason == "tool_calls":
                messages.append(choice.message)
                for call in choice.message.tool_calls:
                    args = json.loads(call.function.arguments)
                    tool_result = self._dispatch_tool(call.function.name, args)
                    tool_results[call.function.name] = tool_result
                    chain[-1]["tool"] = call.function.name
                    chain[-1]["args_keys"] = list(args.keys())
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": json.dumps(tool_result, default=str),
                        }
                    )
            else:
                # LLM produced a final answer
                return self._parse_llm_response(
                    choice.message.content or "", tool_results, user_query, sql
                )

        # Hit max steps — synthesize from tool results
        return self._fixed_pipeline(user_query, sql, chain)

    # ─── Fixed pipeline (offline) ─────────────────────────────────────────────

    def _fixed_pipeline(
        self, user_query: str, sql: str | None, chain: list[dict]
    ) -> AnalysisResponse:
        """Deterministic pipeline — same tools, fixed order, no LLM."""
        from src.analyzer.intent import classify_intent
        from src.analyzer.sql_parser import extract_sql

        step = len(chain)

        # Step 1: intent
        intent = classify_intent(user_query)
        chain.append({"step": step + 1, "action": "classify_intent", "result": intent})
        step += 1

        # Step 2: extract SQL if not provided
        if not sql:
            sql = extract_sql(user_query)
        if sql:
            chain.append(
                {"step": step + 1, "action": "sql_extracted", "result": sql[:80]}
            )
            step += 1

        # Step 3: RAG retrieval
        rag_results = self.retriever.retrieve(
            user_query, top_k=self.settings.rag_top_k_rerank
        )
        chain.append(
            {"step": step + 1, "action": "rag_retrieval", "matches": len(rag_results)}
        )
        step += 1

        # Step 4: rule engine
        rule_findings: list[Finding] = self.rule_engine.analyze(sql) if sql else []
        chain.append(
            {"step": step + 1, "action": "rule_engine", "findings": len(rule_findings)}
        )
        step += 1

        # Step 5: rewriter
        rewrite: RewriteResult | None = self.rewriter.rewrite(sql) if sql else None
        if rewrite and rewrite.changes:
            chain.append(
                {
                    "step": step + 1,
                    "action": "rewrite_query",
                    "changes": len(rewrite.changes),
                }
            )
            step += 1

        confidence = self._calculate_confidence(
            rule_findings, rag_results, llm_used=False
        )
        return self._template_response(
            intent, rule_findings, rag_results, rewrite, confidence, sql,
            user_query=user_query,
        )

    # ─── Tool dispatcher ─────────────────────────────────────────────────────

    def _dispatch_tool(self, tool_name: str, args: dict) -> Any:
        if tool_name == "analyze_sql":
            findings = self.rule_engine.analyze(args.get("sql", ""))
            return [f.model_dump() for f in findings]
        if tool_name == "search_cases":
            return self.retriever.retrieve(
                args.get("query", ""), top_k=args.get("top_k", 3)
            )
        if tool_name == "detect_anomaly":
            return self.anomaly_detector.detect(args.get("metrics", [])).model_dump()
        if tool_name == "rewrite_query":
            return self.rewriter.rewrite(args.get("sql", "")).model_dump()
        if tool_name == "get_schema":
            return self.schemas.get(args.get("table_name", "").lower(), {})
        return {"error": f"Unknown tool: {tool_name}"}

    # ─── Response parsing ─────────────────────────────────────────────────────

    def _parse_llm_response(
        self,
        content: str,
        tool_results: dict,
        user_query: str,
        sql: str | None,
    ) -> AnalysisResponse:
        """Parse LLM JSON response into AnalysisResponse.

        Handles output from any model type:
        - Standard instruct models  → plain JSON or markdown-fenced JSON
        - Thinking models (Qwen3,   → <think>...</think> block before JSON
          DeepSeek-R1, o1/o3, etc.)
        """
        import re as _re

        try:
            clean = content.strip()

            # ── Step 1: strip <think>...</think> blocks ────────────────────
            # Thinking models (qwen3-thinking, deepseek-r1, o1, etc.) emit an
            # internal reasoning block before the final answer.  Safe no-op
            # when the model doesn't produce thinking blocks.
            clean = _re.sub(
                r"<think>[\s\S]*?</think>",
                "",
                clean,
                flags=_re.IGNORECASE,
            ).strip()

            # ── Step 2: strip markdown code fences ────────────────────────
            if clean.startswith("```"):
                clean = "\n".join(clean.split("\n")[1:])
            if clean.endswith("```"):
                clean = clean[: clean.rfind("```")]

            data = json.loads(clean.strip())
        except Exception:
            # Fallback: surface raw content so the caller has something
            data = {"problem": content[:200], "root_cause": content[:400]}

        rag_cases = tool_results.get("search_cases", [])
        rule_findings_raw = tool_results.get("analyze_sql", [])
        rule_findings = [Finding(**f) for f in rule_findings_raw if isinstance(f, dict)]
        rewrite_raw = tool_results.get("rewrite_query")
        rewrite = RewriteResult(**rewrite_raw) if rewrite_raw else None
        anomaly_raw = tool_results.get("detect_anomaly")
        anomaly = AnomalyResult(**anomaly_raw) if anomaly_raw else None

        suggestion = data.get("suggestion", [])
        if isinstance(suggestion, str):
            suggestion = [suggestion]

        return AnalysisResponse(
            problem=data.get("problem", "Performance issue detected"),
            root_cause=data.get("root_cause", ""),
            suggestion=suggestion,
            confidence=float(data.get("confidence", 0.7)),
            category=data.get("category", "general"),
            severity=data.get("severity", "medium"),
            similar_cases=[c.get("case_id", "") for c in rag_cases[:3]],
            sql_analyzed=sql,
            rule_findings=rule_findings,
            anomaly_info=anomaly,
            rewritten_sql=rewrite,
            metadata={
                "model": self.settings.llm_model,
                "rag_cases": [
                    {
                        "case_id": c.get("case_id"),
                        "title": c.get("title"),
                        "category": c.get("category"),
                        "severity": c.get("severity"),
                        "root_cause": c.get("root_cause", ""),
                        "problem": c.get("problem", ""),
                        "_rerank_score": c.get("_rerank_score"),
                        "_distance": c.get("_distance"),
                    }
                    for c in rag_cases[:3]
                ],
            },
        )

    def _template_response(
        self,
        intent: str,
        rule_findings: list[Finding],
        rag_cases: list[dict],
        rewrite: RewriteResult | None,
        confidence: float,
        sql: str | None,
        user_query: str = "",
    ) -> AnalysisResponse:
        """Build a response from rules + RAG without LLM."""
        top_case = rag_cases[0] if rag_cases else {}

        # Derive problem + root_cause
        if rule_findings:
            problem = rule_findings[0].message
            root_cause = top_case.get("root_cause", "") or ". ".join(
                f.message for f in rule_findings
            )
        else:
            problem = top_case.get("problem", "Performance issue detected")
            root_cause = top_case.get(
                "root_cause", "Unable to determine root cause without more context"
            )

        # Build suggestions
        suggestions: list[str] = []
        for f in rule_findings:
            suggestions.append(f.fix)
        for s in top_case.get("suggestions", []):
            if s not in suggestions:
                suggestions.append(s)
        if rewrite and rewrite.changes:
            suggestions.append(f"Rewritten SQL available — see rewritten_sql field")

        # ── A/B testing integration ──
        from src.ab_testing.ab_engine import ABTestingEngine
        ab = ABTestingEngine()
        variant = ab.get_variant(user_query or "")
        tables = [top_case.get("context", {}).get("table", "policy_data")] if top_case else ["unknown"]
        context = {
            "table": tables[0] if tables else "unknown",
            "is_select_star": any(f.rule == "SELECT_STAR" for f in rule_findings),
            "no_where": any(f.rule == "NO_WHERE_CLAUSE" for f in rule_findings),
            "no_limit": any(f.rule == "NO_LIMIT" for f in rule_findings),
            "uses_json_extract": any(f.rule == "JSON_EXTRACT_IN_WHERE" for f in rule_findings),
            "missing_index": bool(rule_findings),
            "join_count": top_case.get("context", {}).get("join_count", 0),
            "frequency": top_case.get("frequency", ""),
            "table_size_rows": top_case.get("context", {}).get("table_size_rows", 0),
            "schema_columns": [],
        }
        ab_extras = ab.generate_suggestions(context, variant)
        for s in ab_extras:
            if s not in suggestions:
                suggestions.append(s)

        # Severity
        severity_map = {"critical": "critical", "high": "high", "warning": "medium"}
        severity = "medium"
        if rule_findings:
            severity = severity_map.get(rule_findings[0].severity, "medium")
        elif top_case.get("severity"):
            severity = top_case["severity"]

        metadata = {
            "mode": "offline",
            "ab_variant": variant,
            "rag_cases": [
                {
                    "case_id": c.get("case_id"),
                    "title": c.get("title"),
                    "category": c.get("category"),
                    "severity": c.get("severity"),
                    "root_cause": c.get("root_cause", ""),
                    "problem": c.get("problem", ""),
                    "_rerank_score": c.get("_rerank_score"),
                    "_distance": c.get("_distance"),
                }
                for c in rag_cases[:3]
            ],
        }

        return AnalysisResponse(
            problem=problem,
            root_cause=root_cause,
            suggestion=suggestions or ["Review query execution plan with EXPLAIN"],
            confidence=confidence,
            category=top_case.get("category", "general"),
            severity=severity,
            similar_cases=[c.get("case_id", "") for c in rag_cases[:3]],
            sql_analyzed=sql,
            rule_findings=rule_findings,
            rewritten_sql=rewrite,
            metadata=metadata,
        )

    def _calculate_confidence(
        self,
        rule_findings: list[Finding],
        rag_results: list[dict],
        llm_used: bool,
    ) -> float:
        """Calculate a calibrated confidence score 0.0–1.0."""
        score = 0.0
        # Rule matches: up to 0.4
        if rule_findings:
            score += 0.4 * min(len(rule_findings) / 3.0, 1.0)
        # RAG rerank score: up to 0.4
        if rag_results:
            rerank = rag_results[0].get("_rerank_score")
            if rerank is not None:
                # rerank scores are logits; sigmoid → 0-1
                import math

                score += 0.4 * (1 / (1 + math.exp(-rerank)))
            else:
                dist = rag_results[0].get("_distance", 1.0)
                score += 0.4 * max(0.0, 1.0 - dist)
        # LLM reasoning: +0.2
        if llm_used:
            score += 0.2
        return round(min(score, 1.0), 3)
