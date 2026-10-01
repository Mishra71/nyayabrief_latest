"""Stage 6 (deterministic): every checkable claim must be traceable to the article text.

Verified by code: evidence quotes, provisions, case/court/bench names, dates, numbers in summary/key points.
NOT verifiable by code: the free-text meaning of the summary -> we bound it (quotes + number check) and label it.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .schemas import Extraction

_NUM = re.compile(r"\d[\d,]*\.?\d*")


def norm(s: str) -> str:
    """Lowercase, drop punctuation/quote styles/hyphenation noise -> robust to curly quotes & OCR spacing."""
    s = unicodedata.normalize("NFKC", s).lower()
    return re.sub(r"[^0-9a-z\u0900-\u097f]+", " ", s).strip()


def present(needle: str, hay_norm: str, threshold: int = 88) -> bool:
    n = norm(needle)
    if not n:
        return False
    if n in hay_norm:
        return True
    return len(n) >= 6 and fuzz.partial_ratio(n, hay_norm) >= threshold  # tolerates small OCR errors


def _numbers(s: str) -> set[str]:
    return {x.replace(",", "").rstrip(".") for x in _NUM.findall(s)}


@dataclass
class Validation:
    status: str  # verified | partial | needs_review
    warnings: list[str] = field(default_factory=list)
    data: Extraction | None = None


def validate(ex: Extraction, body: str) -> Validation:
    hay = norm(body)
    warnings: list[str] = []

    good_ev = [e for e in ex.evidence if present(e.quote, hay, 90)]
    if len(good_ev) < len(ex.evidence):
        warnings.append(f"dropped {len(ex.evidence) - len(good_ev)} ungrounded quote(s)")

    provs = [p for p in ex.provisions if present(p.name, hay)]
    if len(provs) < len(ex.provisions):
        warnings.append("dropped provision(s) not found in article: " + ", ".join(p.name for p in ex.provisions if p not in provs))

    case = ex.case
    if case:
        upd = {}
        if case.case_name and not present(case.case_name, hay):
            warnings.append(f"case_name not in article: {case.case_name}"); upd["case_name"] = None
        if case.court and not present(case.court, hay):
            warnings.append(f"court not in article: {case.court}"); upd["court"] = None
        bench = [b for b in case.bench if present(b, hay)]
        if len(bench) < len(case.bench):
            warnings.append("dropped bench name(s) not in article"); upd["bench"] = bench
        if upd:
            case = case.model_copy(update=upd)

    ev_date = ex.event_date
    if ev_date and not (str(ev_date.year) in body or ev_date.strftime("%B").lower() in body.lower()):
        warnings.append(f"event_date {ev_date} not supported by text"); ev_date = None

    claimed = _numbers(ex.summary + " " + " ".join(ex.key_points))
    unknown = claimed - _numbers(body)
    if unknown:
        warnings.append("numbers in summary not found in article: " + ", ".join(sorted(unknown)))

    cleaned = ex.model_copy(update={"evidence": good_ev, "provisions": provs, "case": case, "event_date": ev_date})
    status = "needs_review" if not good_ev else ("partial" if warnings else "verified")
    return Validation(status, warnings, cleaned)


def search_text(headline: str, ex: Extraction) -> str:
    parts = [headline, ex.summary, *ex.key_points, ex.exam_relevance, *[p.name for p in ex.provisions]]
    if ex.case:
        parts += [x for x in (ex.case.case_name, ex.case.court, ex.case.holding) if x]
    return "\n".join(parts)
