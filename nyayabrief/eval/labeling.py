import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # run from anywhere
"""Tiny evaluation harness (your gold set).
    python eval/labeling.py export 2026-09-30        -> eval/label_2026-09-30.csv  (fill the 'human' column with 1 or 0)
    python eval/labeling.py score eval/label_*.csv   -> prefilter recall + classifier precision/recall/F1
"""
import csv
import sys
from datetime import date

from nyayabrief import db


def export(d: date) -> None:
    with db.get_conn() as c:
        rows = c.execute(
            """SELECT a.content_hash, a.page_no, a.headline, left(a.body, 250) AS snippet
               FROM articles a JOIN issues i ON i.id=a.issue_id WHERE i.issue_date=%s ORDER BY a.page_no""",
            (d,),
        ).fetchall()
    out = f"eval/label_{d}.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["content_hash", "page_no", "headline", "snippet", "human"])
        for r in rows:
            w.writerow([r["content_hash"], r["page_no"], r["headline"], r["snippet"], ""])
    print(f"wrote {out} ({len(rows)} rows) - label ALL rows: 1 = relevant for exam prep, 0 = not")


def score(files: list[str]) -> None:
    gold: dict[str, int] = {}
    for fn in files:
        for r in csv.DictReader(open(fn, encoding="utf-8")):
            if r["human"].strip() in ("0", "1"):
                gold[r["content_hash"]] = int(r["human"])
    with db.get_conn() as c:
        rows = c.execute("SELECT content_hash, prefilter_passed, relevant FROM articles WHERE content_hash = ANY(%s)", (list(gold),)).fetchall()
    pos = [r for r in rows if gold[r["content_hash"]] == 1]
    pf_recall = sum(1 for r in pos if r["prefilter_passed"]) / max(len(pos), 1)
    tp = sum(1 for r in rows if r["relevant"] and gold[r["content_hash"]] == 1)
    fp = sum(1 for r in rows if r["relevant"] and gold[r["content_hash"]] == 0)
    fn_ = sum(1 for r in rows if not r["relevant"] and gold[r["content_hash"]] == 1)
    p, rc = tp / max(tp + fp, 1), tp / max(tp + fn_, 1)
    f1 = 2 * p * rc / max(p + rc, 1e-9)
    print(f"labelled={len(rows)} positives={len(pos)}")
    print(f"PREFILTER recall = {pf_recall:.2f}   (target >= 0.95; if lower, add keywords)")
    print(f"CLASSIFIER precision={p:.2f} recall={rc:.2f} F1={f1:.2f}")


if __name__ == "__main__":
    cmd = sys.argv[1]
    export(date.fromisoformat(sys.argv[2])) if cmd == "export" else score(sys.argv[2:])
