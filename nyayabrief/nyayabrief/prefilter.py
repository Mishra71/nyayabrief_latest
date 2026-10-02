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
# Current affairs (UPSC / APO / BPSC general studies). Weak signals: two distinct hits are needed to pass.
WEAK += [
    r"\bGDP\b", r"inflation", r"repo rate", r"fiscal", r"\bbudget\b", r"\bFDI\b", r"tariff", r"trade (?:deal|war|agreement)",
    r"demonetis", r"\bUPI\b", r"\bbank(?:s|ing)?\b", r"\bIMF\b", r"world bank", r"cyclone", r"pollution", r"air quality",
    r"biodiversity", r"wildlife", r"satellite", r"vaccine", r"united nations", r"bilateral", r"nuclear", r"sanctions?",
    r"foreign minister", r"external affairs", r"\bMEA\b", r"\bNATO\b", r"\bASEAN\b", r"\bFATF\b", r"terror", r"\bArmy\b",
    r"\bborder\b", r"\bCRPF\b", r"maoist|naxal", r"\byojana\b", r"ayushman", r"\bsurvey\b", r"\bindex\b", r"\bprize\b",
    r"\baward\b", r"\bcensus\b", r"\bcensorship\b", r"\bpresident\b", r"election", r"\bpenetration\b", r"\bTRAI\b",
    r"\bprivacy\b", r"data protection", r"cyclon", r"flood", r"earthquake", r"disaster", r"\bNDRF\b",
    r"pakistan", r"\bchina\b", r"\bnepal\b", r"bangladesh", r"sri lanka", r"afghanistan", r"\biran\b", r"\bpilgrim",
]
SKIP_SECTIONS = {"SPORT", "ENTERTAINMENT"}  # BUSINESS stays: economy is current affairs
JUNK = re.compile(r"\b(crossword|sudoku|horoscope|weather watch|delhi today|tender notice|classifieds?)\b", re.I)
_S = [re.compile(p, re.I) for p in STRONG]
_W = [re.compile(p, re.I) for p in WEAK]


@dataclass
class PrefilterResult:
    passed: bool
    score: float
    hits: list[str]


def prefilter(headline: str, body: str, section: str | None = None, min_score: float | None = None) -> PrefilterResult:
    """Cheap gate before the LLM. Default: reject only obvious junk (puzzles, listings, weather tables, sports/entertainment
    pages) and let the batched LLM classifier decide the rest: classification costs ~1 call per 8 articles, while a missed
    current-affairs article is lost for good. Set PREFILTER_MIN_SCORE=1 or 2 to be stricter."""
    if min_score is None:
        from .config import get_settings
        min_score = get_settings().prefilter_min_score
    if JUNK.search(headline):
        return PrefilterResult(False, 0.0, [])
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
    return PrefilterResult(score >= min_score, score, hits)
