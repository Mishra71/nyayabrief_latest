"""Near-duplicate grouping for display (same story printed on two pages, e.g. a page-1 summary + the full page-13 report).

Thresholds were measured on a real issue: true duplicates scored >= 85 on BOTH headline and opening text, the
highest false pair scored 59 / 52. So 80 / 80 leaves a wide safety margin. We LINK duplicates ("also on p.X"),
we never delete them, because a false merge (two different stories become one) is worse than a missed merge.
"""
from __future__ import annotations

from rapidfuzz import fuzz

HEADLINE_SIM = 80
BODY_SIM = 80
HEAD_CHARS = 300


def group_duplicates(rows: list[dict]) -> list[dict]:
    """Keep the longest version of each story; list the other pages in row['also_on_pages']. Order preserved."""
    by_len = sorted(range(len(rows)), key=lambda i: -len(rows[i].get("body") or ""))
    kept: list[int] = []
    also: dict[int, list[int]] = {}
    for i in by_len:
        r = rows[i]
        for k in kept:
            kr = rows[k]
            if r.get("issue_date") != kr.get("issue_date"):
                continue
            if (fuzz.token_set_ratio(r["headline"], kr["headline"]) >= HEADLINE_SIM
                    and fuzz.token_set_ratio((r.get("body") or "")[:HEAD_CHARS], (kr.get("body") or "")[:HEAD_CHARS]) >= BODY_SIM):
                also.setdefault(k, []).append(r["page_no"])
                break
        else:
            kept.append(i)
    out = []
    for i in sorted(kept):
        row = dict(rows[i])
        row["also_on_pages"] = sorted(also.get(i, []))
        out.append(row)
    return out
