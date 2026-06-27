from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import re

from breadcrumbs.models import LearnedPreference, Suggestion, new_id


HEDGING_PATTERNS = [
    r"\bjust\b",
    r"\bmaybe\b",
    r"\bkind of\b",
    r"\bsort of\b",
    r"\bi think\b",
    r"\bi was wondering if\b",
    r"\bif possible\b",
]

VERBOSE_PHRASES = {
    "I wanted to reach out to see if": "Could",
    "I am writing to ask whether": "Could",
    "At this point in time": "Now",
    "Due to the fact that": "Because",
    "In order to": "To",
}

WARM_SIGNOFF_RE = re.compile(r"\b(thanks|thank you|best|warmly|appreciate it)\b", re.IGNORECASE)


@dataclass(frozen=True)
class TargetDocument:
    app: str
    target_id: str
    text: str


class PreferenceEngine:
    """Local-first preference inference with deterministic fallbacks.

    This can later call Gemini with sanitized before/after snippets, but the
    default path is intentionally local so tests and privacy guarantees do not
    depend on an external provider.
    """

    def infer(
        self,
        session_id: str,
        before_text: str,
        after_text: str,
        evidence_event_ids: Iterable[str] = (),
        app: str | None = None,
    ) -> LearnedPreference:
        before = before_text.strip()
        after = after_text.strip()
        tags: list[str] = []
        reasons: list[str] = []

        if before and len(after) <= max(1, int(len(before) * 0.82)):
            tags.append("concise")
            reasons.append("made the text shorter")

        if WARM_SIGNOFF_RE.search(after) and not WARM_SIGNOFF_RE.search(before):
            tags.append("warm")
            reasons.append("added a warmer closing or tone")

        before_hedges = self._hedge_count(before)
        after_hedges = self._hedge_count(after)
        if after_hedges < before_hedges:
            tags.append("direct")
            reasons.append("removed hedging language")

        if app == "vscode" or self._looks_like_code(before + after):
            if len(after.splitlines()) <= len(before.splitlines()) and after != before:
                tags.append("code_style")
                reasons.append("tightened code or comments")

        if not tags:
            tags.append("style_match")
            reasons.append("changed wording or structure")

        summary = "User prefers to " + ", ".join(dict.fromkeys(reasons)) + "."
        applies_when = self._applies_when(app, tags)
        suggested_rule = self._rule_for_tags(tags)
        confidence = 0.55 + min(0.35, len(set(tags)) * 0.1)

        return LearnedPreference(
            id=new_id("pref"),
            session_id=session_id,
            summary=summary,
            applies_when=applies_when,
            suggested_rule=suggested_rule,
            confidence=round(confidence, 2),
            evidence_event_ids=list(evidence_event_ids),
            tags=list(dict.fromkeys(tags)),
        )

    def suggest_for_documents(
        self,
        session_id: str,
        preference: LearnedPreference,
        documents: Iterable[TargetDocument | dict],
    ) -> list[Suggestion]:
        suggestions: list[Suggestion] = []
        for document in documents:
            target = self._coerce_target(document)
            revised = self.rewrite(target.text, preference.tags)
            if revised.strip() == target.text.strip():
                continue
            suggestions.append(
                Suggestion(
                    id=new_id("sug"),
                    session_id=session_id,
                    preference_id=preference.id,
                    app=target.app,
                    target_id=target.target_id,
                    before_text=target.text,
                    after_text=revised,
                    reason=preference.summary,
                    confidence=preference.confidence,
                )
            )
        return suggestions

    def rewrite(self, text: str, tags: Iterable[str]) -> str:
        revised = text.strip()
        tag_set = set(tags)
        if "direct" in tag_set or "concise" in tag_set:
            revised = self._make_direct(revised)
        if "concise" in tag_set:
            revised = self._make_concise(revised)
        if "warm" in tag_set:
            revised = self._make_warm(revised)
        return revised

    def _make_direct(self, text: str) -> str:
        revised = text
        for pattern in HEDGING_PATTERNS:
            revised = re.sub(pattern, "", revised, flags=re.IGNORECASE)
        return re.sub(r"\s{2,}", " ", revised).strip()

    def _make_concise(self, text: str) -> str:
        revised = text
        for verbose, concise in VERBOSE_PHRASES.items():
            revised = revised.replace(verbose, concise)
        sentences = re.split(r"(?<=[.!?])\s+", revised)
        if len(sentences) > 3:
            revised = " ".join(sentence for sentence in sentences[:3] if sentence)
        return revised.strip()

    def _make_warm(self, text: str) -> str:
        if WARM_SIGNOFF_RE.search(text):
            return text
        if "\n" in text:
            return f"{text.rstrip()}\n\nThanks,"
        return f"{text.rstrip()} Thanks."

    def _hedge_count(self, text: str) -> int:
        return sum(len(re.findall(pattern, text, re.IGNORECASE)) for pattern in HEDGING_PATTERNS)

    def _looks_like_code(self, text: str) -> bool:
        return any(marker in text for marker in ("def ", "function ", "const ", "class ", "=>", "{", "}"))

    def _applies_when(self, app: str | None, tags: list[str]) -> str:
        surface = "similar writing or editing tasks"
        if app == "gmail":
            surface = "email drafts with a similar goal"
        elif app == "slack":
            surface = "Slack messages in similar conversations"
        elif app == "vscode":
            surface = "code or comment edits in similar files"
        return f"Apply to {surface} when the same {', '.join(tags)} preference is relevant."

    def _rule_for_tags(self, tags: list[str]) -> str:
        rules = {
            "concise": "shorten verbose phrasing",
            "direct": "remove hedging and make the ask clearer",
            "warm": "keep a friendly closing",
            "code_style": "match the user's tighter code/comment style",
            "style_match": "mirror the user's revised wording style",
        }
        return "; ".join(rules[tag] for tag in tags if tag in rules)

    def _coerce_target(self, document: TargetDocument | dict) -> TargetDocument:
        if isinstance(document, TargetDocument):
            return document
        return TargetDocument(
            app=str(document["app"]),
            target_id=str(document["target_id"]),
            text=str(document.get("text", "")),
        )
