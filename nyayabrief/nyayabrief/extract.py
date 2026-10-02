"""Stage 5 (LLM, one call per RELEVANT article): structured notes, grounded in the article text."""
from __future__ import annotations

from .llm import call_structured
from .schemas import Extraction

SYSTEM = """You extract exam-preparation notes from ONE newspaper article for Indian Judiciary/APO/BPSC aspirants.

HARD RULES
- Use ONLY facts stated in the article text. Do NOT add outside knowledge: no extra case citations, section numbers,
  dates, names or numbers that are not in the text.
- If something is not stated, use null (or an empty list). Never guess.
- evidence: 1-4 VERBATIM quotes (15-300 characters each) copied exactly from the article that support your summary.
- summary: max 600 characters, plain and factual. key_points: max 6 short bullets.
- provisions: only constitutional articles / Acts / sections that are explicitly mentioned in the article.
- case: fill only if the article reports a court case/order.
- For current-affairs articles (economy, environment, international relations, security, schemes), make key_points the
  FACTS an exam could ask: who/what/where/when, numbers, names of schemes/reports/organisations/places, as stated.
- exam_relevance: ONE sentence on why this matters for the exam (e.g. concept tested, static-GK link)."""


def extract_article(headline: str, body: str, issue_date) -> tuple[Extraction, str]:
    user = f"ISSUE DATE: {issue_date}\nHEADLINE: {headline}\n\nARTICLE TEXT:\n{body[:12000]}"
    ex, model = call_structured(SYSTEM, user, Extraction)
    return ex, model  # type: ignore[return-value]
