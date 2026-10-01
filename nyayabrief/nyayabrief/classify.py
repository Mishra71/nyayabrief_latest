"""Stage 4 (LLM, batched): is this article useful for judiciary/APO/BPSC prep? Input = headline + first 700 chars."""
from __future__ import annotations

from .config import get_settings
from .llm import call_structured
from .schemas import ClassifyBatch, ClassifyItem

SYSTEM = """You are a strict content curator for Indian competitive exams: Judicial Services (Judiciary/Magistrate),
APO (Assistant Public Prosecutor), BPSC and similar state/civil-service exams.

For EACH numbered newspaper article (headline + opening text) decide whether it can be useful for exam preparation.

RELEVANT: Supreme Court / High Court judgments and orders; constitutional questions; new laws, bills, amendments,
rules (BNS, BNSS, BSA etc.); legal institutions and appointments (judges, collegium, Law Commission, tribunals);
government policy/schemes with a legal or administrative angle; international law/treaties/organisations;
Bihar-specific governance and policy (for BPSC).
NOT RELEVANT: crime reports with no legal principle, sports, entertainment, routine business/market news,
opinion pieces without legal/policy substance, ads.

category must be one of: judgment, constitutional, statute_bill, legal_institutional, policy_governance, intl_law, bihar_state, other.
exam_tags: any of judiciary, apo, bpsc, general.
score: 0..1 (how useful). When unsure use 0.4-0.6: a missed relevant article is worse than a false positive.
reason: one short sentence.
Return one item for EVERY id given, using the same id."""


def classify_batch(batch: list[dict]) -> dict[int, ClassifyItem]:
    parts = [f"[{i}] HEADLINE: {r['headline']}\nTEXT: {r['body'][:700]}" for i, r in enumerate(batch)]
    out, _ = call_structured(SYSTEM, "\n\n".join(parts), ClassifyBatch, chain=get_settings().classify_chain or None)
    return {it.id: it for it in out.items}
