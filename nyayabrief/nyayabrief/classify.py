"""Stage 4 (LLM, batched): is this article useful for judiciary/APO/BPSC prep? Input = headline + first 700 chars."""
from __future__ import annotations

from .config import get_settings
from .llm import call_structured
from .schemas import ClassifyBatch, ClassifyItem

SYSTEM = """You are a strict content curator for Indian competitive exams: Judicial Services (Judiciary/Magistrate),
APO (Assistant Public Prosecutor), UPSC, BPSC and similar state/civil-service exams. These exams test LAW and also
CURRENT AFFAIRS (general studies).

For EACH numbered newspaper article (headline + opening text) decide whether it can be useful for exam preparation.

RELEVANT (law): Supreme Court / High Court judgments and orders; constitutional questions; new laws, bills,
amendments, rules (BNS, BNSS, BSA etc.); legal institutions and appointments (judges, collegium, Law Commission, tribunals).
RELEVANT (current affairs a UPSC/APO/BPSC paper could ask): economy and banking (RBI, GDP, inflation, trade, tariffs,
budget, schemes with money data); environment, disasters, climate, science and technology; international relations
(treaties, summits, bilateral issues, other countries' elections or conflicts that involve India); internal security and
defence; government schemes, reports, indices and surveys; social issues; awards and key appointments; Bihar-specific
governance and policy (for BPSC); awards, key appointments, obituaries, major sports results, books, reports.
NOT RELEVANT: local crime or accident reports with no legal/policy point, festival and event listings, weather tables,
sports (unless a major national/international policy or award), entertainment, crosswords/puzzles, ads, routine
price or stock-market ticks, opinion pieces without substance.

category must be one of:
- judgment: ONLY if a court/tribunal has actually delivered a ruling, order, verdict, bail/stay decision or direction reported in the article
- constitutional: constitutional provisions/questions, fundamental rights, Governor/Speaker/federal issues, pending constitutional cases
- statute_bill: new laws, bills, amendments, ordinances, rules
- legal_institutional: judiciary/legal institutions, appointments, commissions, tribunals, reports on the justice system, bar/police-court matters
- intl_law: treaties and international courts as LAW
- policy_governance: government schemes, administration, regulators, elections and political-process news
- economy: economy, banking, trade, finance, industry data
- environment_science: environment, climate, disasters, science and technology, health research
- intl_relations: foreign policy, other countries, international organisations, summits
- security_defence: internal security, defence, terrorism, border issues
- social_issues: education, health, welfare, gender, caste/religion-related social matters, human rights, reports/indices
- awards_misc: awards and prizes, key appointments, obituaries, major sports results, books, days/anniversaries, exam GK
- bihar_state: Bihar-specific governance/policy
- other
exam_tags (any of): judiciary, apo, bpsc, upsc, general. EVERY exam tests current affairs, so a current-affairs article gets ALL of judiciary, apo, bpsc, upsc. Law articles get judiciary and apo (add upsc/bpsc if they are also general-awareness material).
score: 0..1 (how useful). When unsure use 0.4-0.6: a missed relevant article is worse than a false positive.
reason: one short sentence.
Return one item for EVERY id given, using the same id."""


def classify_batch(batch: list[dict]) -> dict[int, ClassifyItem]:
    parts = [f"[{i}] HEADLINE: {r['headline']}\nTEXT: {r['body'][:700]}" for i, r in enumerate(batch)]
    out, _ = call_structured(SYSTEM, "\n\n".join(parts), ClassifyBatch, chain=get_settings().classify_chain or None)
    return {it.id: it for it in out.items}
