"""Orchestrator: plain, resumable, idempotent batch pipeline. No agent - fixed steps, state lives in Postgres.

Re-running the same PDF only does the missing work (pending classify / pending extract / missing embeddings),
so quota exhaustion mid-run just means: run again later.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import fitz

from . import db
from .classify import classify_batch
from .config import get_settings
from .extract import extract_article
from .grounding import search_text, validate
from .llm import LLMFailure, QuotaExhausted, embed
from .prefilter import prefilter
from .segment import segment_pdf

log = logging.getLogger(__name__)
Progress = Callable[[str, int, int], None]

_DATE_RE = re.compile(
    r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)[,\s]+([a-z]+)\s+(\d{1,2}),?\s+(20\d{2})", re.I
)


def detect_issue_date(pdf_path) -> date | None:
    doc = fitz.open(pdf_path)
    for i in range(min(2, len(doc))):
        m = _DATE_RE.search(doc[i].get_text())
        if m:
            try:
                return datetime.strptime(f"{m[1]} {m[2]} {m[3]}", "%B %d %Y").date()
            except ValueError:
                pass
    m = re.search(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", Path(pdf_path).name)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            pass
    return None


def _hash(headline: str, body: str) -> str:
    return hashlib.sha1(f"{headline}|{body}".encode()).hexdigest()


def process_pdf(pdf_path, issue_date: date | None = None, progress: Progress | None = None) -> dict:
    progress = progress or (lambda *_: None)
    s = get_settings()
    pdf_path = Path(pdf_path)
    issue_date = issue_date or detect_issue_date(pdf_path)
    if not issue_date:
        raise ValueError("Could not detect issue date - pass it explicitly.")
    sha = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    issue_id = db.upsert_issue(issue_date, pdf_path.name, sha)
    notes: list[str] = []

    # 1-2. parse + segment (deterministic)
    arts, report = segment_pdf(pdf_path)
    log.info("segmentation: %s", report)
    if report["scanned_pages"]:
        notes.append(f"{len(report['scanned_pages'])} page(s) have no text layer (OCR not enabled): {report['scanned_pages'][:10]}")
    db.insert_articles(issue_id, [
        {"page_no": a.page, "section": a.section, "headline": a.headline, "body": a.body,
         "content_hash": _hash(a.headline, a.body), "incomplete": a.incomplete}
        for a in arts
    ])
    progress("segmented", 1, 1)

    # 3. prefilter (deterministic)
    todo = db.articles_needing_prefilter(issue_id)
    for n, r in enumerate(todo, 1):
        res = prefilter(r["headline"], r["body"], r["section"])
        db.set_prefilter(r["id"], res.passed, res.score)
        progress("prefilter", n, len(todo))

    status = "done"
    try:
        _classify(issue_id, progress)
        _extract(issue_id, issue_date, progress)
        _embed(issue_id, progress)
    except QuotaExhausted:
        status = "partial"
        notes.append("LLM quota exhausted - run the same PDF again later to resume (nothing is lost).")

    db.finish_issue(issue_id, status, "; ".join(notes))
    deleted = db.prune_old_issues(s.keep_issues, protect_issue_id=issue_id)
    if deleted:
        log.info("retention: deleted old issues %s", deleted)
    return {**db.issue_stats(issue_date), "issue_date": issue_date, "status": status, "note": "; ".join(notes)}


def _classify(issue_id: int, progress: Progress) -> None:
    todo = db.pending_classify(issue_id)
    bs, done = get_settings().classify_batch_size, 0
    for i in range(0, len(todo), bs):
        batch = todo[i:i + bs]
        try:
            results = classify_batch(batch)
        except LLMFailure as e:
            log.error("classify batch failed: %s", e)
            for r in batch:
                db.set_classify_failed(r["id"])
            continue
        for idx, r in enumerate(batch):
            it = results.get(idx)
            if it is None:
                db.set_classify_failed(r["id"])
                continue
            db.set_classification(r["id"], it.relevant and it.score >= 0.4, it.category, it.exam_tags, it.score, it.reason)
        done += len(batch)
        progress("classify", done, len(todo))


def _extract(issue_id: int, issue_date, progress: Progress) -> None:
    s = get_settings()
    todo = db.pending_extract(issue_id, s.prompt_version)[: s.max_notes_per_run]
    for n, r in enumerate(todo, 1):
        try:
            ex, model = extract_article(r["headline"], r["body"], issue_date)
        except LLMFailure as e:
            log.error("extract failed for article %s: %s", r["id"], e)
            continue
        v = validate(ex, r["body"])
        db.save_extraction(
            r["id"], v.data.model_dump(mode="json"), v.status, v.warnings, model, s.prompt_version,
            search_text(r["headline"], v.data),
        )
        progress("extract", n, len(todo))


def _embed(issue_id: int, progress: Progress) -> None:
    todo = db.needing_embedding(issue_id)
    for i in range(0, len(todo), 16):
        chunk = todo[i:i + 16]
        vecs = embed([r["search_text"] for r in chunk])
        if not vecs:
            return  # keyword search still works
        for r, v in zip(chunk, vecs):
            db.set_embedding(r["article_id"], v)
        progress("embed", min(i + 16, len(todo)), len(todo))
