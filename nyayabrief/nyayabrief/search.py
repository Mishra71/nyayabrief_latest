"""Query side = RAG with a fixed workflow (filters -> keyword + vector -> RRF -> cited answer). Not an agent."""
from __future__ import annotations

from . import db
from .llm import call_text, embed

ANSWER_SYSTEM = """You answer questions for an Indian judiciary/APO/BPSC aspirant using ONLY the numbered notes provided.
Cite sources like [1], [2] after each claim. If the notes do not contain the answer, say so plainly. Be concise."""


def hybrid_search(q: str, k: int = 8, **filters) -> list[dict]:
    """Reciprocal Rank Fusion of Postgres full-text and pgvector cosine results."""
    rankings = [db.fts_ids(q, **filters)]
    vecs = embed([q])
    if vecs:
        rankings.append(db.vec_ids(vecs[0], **filters))
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, aid in enumerate(ranking):
            scores[aid] = scores.get(aid, 0.0) + 1.0 / (60 + rank)
    top = sorted(scores, key=scores.get, reverse=True)[:k]
    return db.cards_by_ids(top)


def answer(q: str, hits: list[dict]) -> str:
    if not hits:
        return "No matching notes found."
    notes = []
    for i, h in enumerate(hits[:6], 1):
        d = h["data"]
        notes.append(f"[{i}] ({h['issue_date']}, p.{h['page_no']}) {h['headline']}\n{d['summary']}\n- " + "\n- ".join(d["key_points"]))
    return call_text(ANSWER_SYSTEM, f"QUESTION: {q}\n\nNOTES:\n" + "\n\n".join(notes))
