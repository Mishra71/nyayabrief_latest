"""All SQL lives here. One short-lived connection per call (fine at this scale)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .config import get_settings


def get_conn() -> psycopg.Connection:
    return psycopg.connect(get_settings().database_url, row_factory=dict_row, autocommit=True)


def init_schema() -> None:
    sql = (Path(__file__).resolve().parent.parent / "schema.sql").read_text()
    with get_conn() as c:
        c.execute(sql)


# ---------- write side (pipeline) ----------
def upsert_issue(issue_date, filename: str, sha: str) -> int:
    with get_conn() as c:
        row = c.execute("SELECT id, pdf_sha256 FROM issues WHERE issue_date=%s", (issue_date,)).fetchone()
        if row:
            if row["pdf_sha256"] != sha:  # different PDF for same date -> start clean
                c.execute("DELETE FROM articles WHERE issue_id=%s", (row["id"],))
            c.execute(
                "UPDATE issues SET filename=%s, pdf_sha256=%s, status='processing', note=NULL WHERE id=%s",
                (filename, sha, row["id"]),
            )
            return row["id"]
        return c.execute(
            "INSERT INTO issues(issue_date, filename, pdf_sha256) VALUES (%s,%s,%s) RETURNING id",
            (issue_date, filename, sha),
        ).fetchone()["id"]


def insert_articles(issue_id: int, rows: list[dict]) -> None:
    sql = """INSERT INTO articles(issue_id,page_no,section,headline,body,content_hash,incomplete)
             VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (issue_id, content_hash) DO NOTHING"""
    with get_conn() as c, c.cursor() as cur:
        cur.executemany(
            sql,
            [(issue_id, r["page_no"], r["section"], r["headline"], r["body"], r["content_hash"], r["incomplete"]) for r in rows],
        )


def articles_needing_prefilter(issue_id: int) -> list[dict]:
    with get_conn() as c:
        return c.execute(
            "SELECT id, headline, body, section FROM articles WHERE issue_id=%s AND prefilter_passed IS NULL ORDER BY id",
            (issue_id,),
        ).fetchall()


def set_prefilter(article_id: int, passed: bool, score: float) -> None:
    with get_conn() as c:
        c.execute(
            "UPDATE articles SET prefilter_passed=%s, prefilter_score=%s, classify_status=%s WHERE id=%s",
            (passed, score, "pending" if passed else "skipped", article_id),
        )


def pending_classify(issue_id: int) -> list[dict]:
    with get_conn() as c:
        return c.execute(
            """SELECT id, headline, body FROM articles
               WHERE issue_id=%s AND prefilter_passed AND classify_status IN ('pending','failed') ORDER BY id""",
            (issue_id,),
        ).fetchall()


def set_classification(article_id, relevant, category, tags, score, reason) -> None:
    with get_conn() as c:
        c.execute(
            """UPDATE articles SET classify_status='done', relevant=%s, category=%s, exam_tags=%s,
               relevance_score=%s, reason=%s WHERE id=%s""",
            (relevant, category, list(tags), score, reason, article_id),
        )


def set_classify_failed(article_id: int) -> None:
    with get_conn() as c:
        c.execute("UPDATE articles SET classify_status='failed' WHERE id=%s", (article_id,))


def pending_extract(issue_id: int, prompt_version: str) -> list[dict]:
    with get_conn() as c:
        return c.execute(
            """SELECT a.id, a.headline, a.body FROM articles a
               LEFT JOIN extractions e ON e.article_id=a.id
               WHERE a.issue_id=%s AND a.relevant AND (e.article_id IS NULL OR e.prompt_version <> %s)
               ORDER BY a.relevance_score DESC NULLS LAST, a.id""",
            (issue_id, prompt_version),
        ).fetchall()


def save_extraction(article_id, data, status, warnings, model, prompt_version, search_text) -> None:
    with get_conn() as c:
        c.execute(
            """INSERT INTO extractions(article_id,data,validation_status,warnings,model,prompt_version,search_text)
               VALUES (%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (article_id) DO UPDATE SET data=EXCLUDED.data, validation_status=EXCLUDED.validation_status,
                 warnings=EXCLUDED.warnings, model=EXCLUDED.model, prompt_version=EXCLUDED.prompt_version,
                 search_text=EXCLUDED.search_text, embedding=NULL""",
            (article_id, json.dumps(data), status, json.dumps(warnings), model, prompt_version, search_text),
        )


def needing_embedding(issue_id: int) -> list[dict]:
    with get_conn() as c:
        return c.execute(
            """SELECT e.article_id, e.search_text FROM extractions e JOIN articles a ON a.id=e.article_id
               WHERE a.issue_id=%s AND e.embedding IS NULL""",
            (issue_id,),
        ).fetchall()


def set_embedding(article_id: int, vec: list[float]) -> None:
    literal = "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
    with get_conn() as c:
        c.execute("UPDATE extractions SET embedding=%s::vector WHERE article_id=%s", (literal, article_id))


def prune_old_issues(keep: int, protect_issue_id: int | None = None) -> list:
    """Retention: keep the newest `keep` issues (by issue date, so skipped days don't matter).
    ON DELETE CASCADE removes their articles + extractions too. Returns the deleted dates."""
    with get_conn() as c:
        rows = c.execute(
            """DELETE FROM issues WHERE id NOT IN (SELECT id FROM issues ORDER BY issue_date DESC LIMIT %s)
               AND id IS DISTINCT FROM %s RETURNING issue_date""",
            (keep, protect_issue_id),
        ).fetchall()
    return [r["issue_date"] for r in rows]


def finish_issue(issue_id: int, status: str, note: str) -> None:
    with get_conn() as c:
        c.execute("UPDATE issues SET status=%s, note=%s WHERE id=%s", (status, note or None, issue_id))


# ---------- read side (UI / search) ----------
_CARD_COLS = """a.id, a.page_no, a.headline, a.body, a.category, a.exam_tags, a.relevance_score, a.incomplete,
                i.issue_date, e.data, e.validation_status, e.warnings"""
_CARD_FROM = """FROM articles a JOIN issues i ON i.id=a.issue_id JOIN extractions e ON e.article_id=a.id"""


def list_issue_dates() -> list:
    with get_conn() as c:
        return [r["issue_date"] for r in c.execute("SELECT issue_date FROM issues ORDER BY issue_date DESC")]


def brief(issue_date) -> list[dict]:
    with get_conn() as c:
        return c.execute(
            f"SELECT {_CARD_COLS} {_CARD_FROM} WHERE i.issue_date=%s ORDER BY a.relevance_score DESC NULLS LAST, a.page_no",
            (issue_date,),
        ).fetchall()


def issue_stats(issue_date) -> dict:
    with get_conn() as c:
        return c.execute(
            """SELECT i.status, i.note, COUNT(a.id) AS articles,
                      COUNT(*) FILTER (WHERE a.prefilter_passed) AS passed_prefilter,
                      COUNT(*) FILTER (WHERE a.relevant) AS relevant,
                      COUNT(e.article_id) AS extracted
               FROM issues i LEFT JOIN articles a ON a.issue_id=i.id LEFT JOIN extractions e ON e.article_id=a.id
               WHERE i.issue_date=%s GROUP BY i.id""",
            (issue_date,),
        ).fetchone() or {}


def _filters(date_from=None, date_to=None, category=None, tag=None) -> tuple[str, dict]:
    where, params = [], {}
    if date_from:
        where.append("i.issue_date >= %(df)s"); params["df"] = date_from
    if date_to:
        where.append("i.issue_date <= %(dt)s"); params["dt"] = date_to
    if category:
        where.append("a.category = %(cat)s"); params["cat"] = category
    if tag:
        where.append("%(tag)s = ANY(a.exam_tags)"); params["tag"] = tag
    return ("".join(f" AND {w}" for w in where), params)


def fts_ids(q: str, limit: int = 30, **filters) -> list[int]:
    words = re.findall(r"\w+", q)
    if not words:
        return []
    where, params = _filters(**filters)
    params.update(q=" or ".join(words), lim=limit)  # OR semantics: natural-language queries rarely match with AND
    sql = f"""SELECT e.article_id {_CARD_FROM}
              WHERE e.tsv @@ websearch_to_tsquery('english', %(q)s){where}
              ORDER BY ts_rank_cd(e.tsv, websearch_to_tsquery('english', %(q)s)) DESC LIMIT %(lim)s"""
    with get_conn() as c:
        return [r["article_id"] for r in c.execute(sql, params)]


def vec_ids(vec: list[float], limit: int = 30, **filters) -> list[int]:
    where, params = _filters(**filters)
    params.update(v="[" + ",".join(f"{x:.6f}" for x in vec) + "]", lim=limit)
    sql = f"""SELECT e.article_id {_CARD_FROM}
              WHERE e.embedding IS NOT NULL{where}
              ORDER BY e.embedding <=> %(v)s::vector LIMIT %(lim)s"""
    with get_conn() as c:
        return [r["article_id"] for r in c.execute(sql, params)]


def cards_by_ids(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    with get_conn() as c:
        rows = c.execute(f"SELECT {_CARD_COLS} {_CARD_FROM} WHERE a.id = ANY(%s)", (ids,)).fetchall()
    order = {i: n for n, i in enumerate(ids)}
    return sorted(rows, key=lambda r: order[r["id"]])


# ---------- human feedback loop (viewer marks a note right / wrong) ----------
_FEEDBACK_DDL = """CREATE TABLE IF NOT EXISTS feedback (
  id SERIAL PRIMARY KEY,
  article_id INT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
  vote SMALLINT NOT NULL CHECK (vote IN (-1, 1)),
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now())"""


def save_feedback(article_id: int, vote: int, note: str | None = None) -> None:
    with get_conn() as c:
        c.execute(_FEEDBACK_DDL)  # self-creating: no manual migration on Neon needed
        c.execute("INSERT INTO feedback(article_id, vote, note) VALUES (%s,%s,%s)", (article_id, vote, note))


def feedback_summary() -> list[dict]:
    with get_conn() as c:
        c.execute(_FEEDBACK_DDL)
        return c.execute(
            """SELECT a.headline, a.page_no, i.issue_date,
                      SUM((f.vote = 1)::int) AS up, SUM((f.vote = -1)::int) AS down, MAX(f.created_at) AS last
               FROM feedback f JOIN articles a ON a.id=f.article_id JOIN issues i ON i.id=a.issue_id
               GROUP BY a.id, i.issue_date ORDER BY down DESC, last DESC LIMIT 100"""
        ).fetchall()
