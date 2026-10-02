"""Pydantic contracts for everything an LLM returns. The LLM never fills provenance (page, date, hash, model)."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

Category = Literal[
    # legal
    "judgment", "constitutional", "statute_bill", "legal_institutional", "intl_law",
    # current affairs (UPSC / APO / BPSC general studies)
    "policy_governance", "economy", "environment_science", "intl_relations", "security_defence",
    "social_issues", "awards_misc", "bihar_state", "other",
]
ExamTag = Literal["judiciary", "apo", "bpsc", "upsc", "general"]


# ---- classification ----
class ClassifyItem(BaseModel):
    id: int
    relevant: bool
    category: Category
    exam_tags: list[ExamTag] = []
    score: float = Field(ge=0, le=1)
    reason: str = Field(max_length=300)


class ClassifyBatch(BaseModel):
    items: list[ClassifyItem]


# ---- extraction ----
class Evidence(BaseModel):
    quote: str = Field(min_length=15, max_length=400)  # must be VERBATIM from the article


class CaseInfo(BaseModel):
    case_name: Optional[str] = None
    court: Optional[str] = None
    bench: list[str] = []
    holding: Optional[str] = None  # what the court decided, as stated in the article


class LegalProvision(BaseModel):
    name: str  # e.g. "Article 21", "Section 480 BNSS"
    kind: Literal["constitution", "act", "section", "bill", "rule"]


class Extraction(BaseModel):
    summary: str = Field(max_length=800)
    key_points: list[str] = Field(max_length=6)
    case: Optional[CaseInfo] = None
    provisions: list[LegalProvision] = []
    exam_relevance: str = Field(max_length=400)
    event_date: Optional[date] = None
    evidence: list[Evidence] = Field(min_length=1, max_length=5)
