from __future__ import annotations
import re

INTENT_TEMPLATES: dict[str, list[str]] = {
    "query_analysis": [
        "why is this query slow",
        "what is wrong with this query",
        "explain the performance issue",
        "why does this take so long",
        "what causes this slowness",
        "why is it slow",
        "analyze this query",
        "diagnose",
        "what is the problem",
    ],
    "optimization": [
        "how can i optimize",
        "how to optimize",
        "make this faster",
        "improve performance",
        "suggest improvements",
        "how to speed up",
        "optimize this",
        "how do i fix",
        "how to fix",
        "rewrite",
    ],
    "anomaly_detection": [
        "is this an anomaly",
        "detect anomaly",
        "latency spike",
        "sudden increase",
        "unusual behavior",
        "something wrong",
        "spike",
        "degradation",
        "performance drop",
    ],
    "system_design": [
        "what would you change",
        "system design",
        "architectural changes",
        "how to design for scale",
        "design improvement",
        "production design",
        "scale this",
    ],
    "general": [
        "tell me about",
        "what is",
        "explain",
        "how does",
        "describe",
    ],
}

# Keyword → intent (fast path, checked first)
_KEYWORD_MAP: dict[str, str] = {
    "slow": "query_analysis",
    "slowness": "query_analysis",
    "performance": "query_analysis",
    "diagnose": "query_analysis",
    "analyze": "query_analysis",
    "optimize": "optimization",
    "faster": "optimization",
    "rewrite": "optimization",
    "fix": "optimization",
    "improve": "optimization",
    "anomaly": "anomaly_detection",
    "spike": "anomaly_detection",
    "latency": "anomaly_detection",
    "degradation": "anomaly_detection",
    "design": "system_design",
    "scale": "system_design",
    "architect": "system_design",
}


def classify_intent(query: str) -> str:
    """Classify user query into one of five intent categories.

    Uses keyword matching (fast path) with template-based fallback.
    Returns one of: query_analysis, optimization, anomaly_detection,
                    system_design, general.
    """
    if not query:
        return "general"

    q_lower = query.lower()

    # Fast path: keyword matching
    for kw, intent in _KEYWORD_MAP.items():
        if kw in q_lower:
            return intent

    # Template matching: score against intent example phrases
    best_intent = "general"
    best_score = 0
    for intent, templates in INTENT_TEMPLATES.items():
        score = sum(1 for t in templates if t in q_lower)
        if score > best_score:
            best_score = score
            best_intent = intent

    return best_intent
