from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime
from pathlib import Path

from src.models import FeedbackEntry

logger = logging.getLogger(__name__)


class FeedbackLoop:
    """Records user feedback and drives confidence-weight updates in the knowledge base.

    The loop is *triggered*, not scheduled — run ``process()`` manually or via
    ``python cli/main.py --process-feedback`` to apply accumulated feedback to
    the vector store.
    """

    def __init__(
        self,
        feedback_log_path: str = "data/feedback_log.json",
        knowledge_base_path: str = "data/knowledge_base.json",
        vector_store=None,
    ) -> None:
        self.log_path = Path(feedback_log_path)
        self.kb_path = Path(knowledge_base_path)
        self.vector_store = vector_store  # optional; used for rebuild after processing
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text("[]")

    # ─── Recording ───────────────────────────────────────────────────────────

    def record(
        self,
        query: str,
        case_id: str | None,
        suggestion: str,
        feedback: str,
        ab_variant: str = "A",
        note: str | None = None,
    ) -> FeedbackEntry:
        """Append one feedback entry to the log.

        Args:
            feedback: ``"positive"`` | ``"negative"`` | ``"skipped"``
        """
        entry = FeedbackEntry(
            id=f"fb_{uuid.uuid4().hex[:6]}",
            timestamp=datetime.now().isoformat(),
            query=query,
            case_retrieved=case_id,
            ab_variant=ab_variant,
            suggestion_given=suggestion,
            feedback=feedback,
            user_note=note,
        )
        log = self._load_log()
        log.append(entry.model_dump())
        self.log_path.write_text(json.dumps(log, indent=2))
        logger.debug("Recorded feedback %s for case %s", feedback, case_id)
        return entry

    # ─── Processing ──────────────────────────────────────────────────────────

    def process(self) -> dict:
        """Read the feedback log, update ``confidence_weight`` in the knowledge
        base, optionally rebuild the vector store, and return a summary."""
        log = self._load_log()
        if not log:
            return {"updated": [], "flagged": [], "processed": 0, "message": "No feedback to process"}

        # Group entries by case_id
        by_case: dict[str, list[dict]] = {}
        for entry in log:
            cid = entry.get("case_retrieved")
            if cid:
                by_case.setdefault(cid, []).append(entry)

        kb = self._load_kb()
        updated: list[str] = []
        flagged: list[dict] = []

        for case_id, entries in by_case.items():
            total = len(entries)
            positives = sum(1 for e in entries if e["feedback"] == "positive")
            win_rate = round(positives / total, 3)

            for case in kb:
                if case["case_id"] == case_id:
                    case["confidence_weight"] = win_rate
                    updated.append(case_id)
                    if win_rate < 0.4 and total >= 5:
                        flagged.append(
                            {"case_id": case_id, "win_rate": win_rate, "total": total}
                        )
                    break

        self.kb_path.write_text(json.dumps(kb, indent=2))

        if self.vector_store and updated:
            self.vector_store.rebuild(kb)
            logger.info("Rebuilt vector store after feedback processing.")

        return {"updated": updated, "flagged": flagged, "processed": len(log)}

    # ─── Stats ───────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        log = self._load_log()
        if not log:
            return {"total": 0, "positive_rate": 0.0, "cases_flagged": 0, "flagged_cases": []}
        total = len(log)
        positives = sum(1 for e in log if e["feedback"] == "positive")

        by_case: dict[str, list[dict]] = {}
        for e in log:
            cid = e.get("case_retrieved")
            if cid:
                by_case.setdefault(cid, []).append(e)

        flagged = [
            cid
            for cid, entries in by_case.items()
            if len(entries) >= 5
            and sum(1 for e in entries if e["feedback"] == "positive") / len(entries) < 0.4
        ]
        return {
            "total": total,
            "positive_rate": round(positives / total, 3),
            "cases_flagged": len(flagged),
            "flagged_cases": flagged,
        }

    # ─── Internals ───────────────────────────────────────────────────────────

    def _load_log(self) -> list[dict]:
        try:
            return json.loads(self.log_path.read_text())
        except Exception:
            return []

    def _load_kb(self) -> list[dict]:
        return json.loads(self.kb_path.read_text())
