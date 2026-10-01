"""Stage 3 (deterministic, free): cheap keyword scoring. Tuned for RECALL - the LLM adds precision later."""
from __future__ import annotations

import re
from dataclasses import dataclass

STRONG = [
    r"supreme court", r"high court", r"collegium", r"constitution bench", r"\barticle\s+\d+", r"\bBNSS?\b", r"\bBSA\b",
    r"bharatiya nyay", r"nagarik suraksha", r"bharatiya sakshya", r"\bIPC\b", r"\bCrPC\b", r"\bPOCSO\b", r"\bbail\b",
    r"\bPIL\b", r"habeas corpus", r"contempt of court", r"law commission", r"\btribunal\b", r"chief justice",
    r"\bjudges?\b", r"\bmagistrate\b", r"\bverdict\b", r"fundamental rights?", r"\bordinance\b", r"\bjudiciary\b",
    r"\bsection\s+\d+", r"constitutional", r"\bacquitt", r"\bconvict", r"\bFIR\b", r"\bwrit\b", r"\bsuo motu\b", r"overseas citizen", r"\bOCI\b", r"citizenship",
]
WEAK = [
    r"parliament", r"\bbill\b", r"amendment", r"\bpolice\b", r"\barrest", r"petition", r"election commission",
    r"\bact\b", r"governor", r"\bscheme\b", r"ministry", r"\bpolicy\b", r"\btreaty\b", r"\bUN\b", r"human rights",
    r"\bBihar\b", r"\bPatna\b", r"\bRBI\b", r"\bISRO\b", r"\bclimate\b", r"\bsummit\b", r"\bcommission\b",
]
SKIP_SECTIONS = {"SPORT", "BUSINESS", "ENTERTAINMENT"}
_S = [re.compile(p, re.I) for p in STRONG]
_W = [re.compile(p, re.I) for p in WEAK]


@dataclass
class PrefilterResult:
    passed: bool
    score: float
    hits: list[str]


def prefilter(headline: str, body: str, section: str | None = None) -> PrefilterResult:
    head, text = headline, f"{headline}\n{body}"
    hits, score = [], 0.0
    for rx in _S:
        if rx.search(text):
            hits.append(rx.pattern)
            score += 2.0 + (1.0 if rx.search(head) else 0.0)
    for rx in _W:
        if rx.search(text):
            hits.append(rx.pattern)
            score += 1.0 + (0.5 if rx.search(head) else 0.0)
    strong_hits = sum(1 for rx in _S if rx.search(text))
    if section and section.upper() in SKIP_SECTIONS and strong_hits < 2:
        return PrefilterResult(False, score, hits)
    return PrefilterResult(score >= 2.0, score, hits)
