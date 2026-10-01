import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a Postgres DATABASE_URL")


def test_prune_keeps_newest_three():
    from datetime import date, timedelta

    from nyayabrief import db

    base = date(2031, 1, 1)  # far-future dates so real data is never touched
    ids = [db.upsert_issue(base + timedelta(days=i), f"t{i}.pdf", f"sha{i}") for i in range(5)]
    deleted = db.prune_old_issues(3, protect_issue_id=ids[-1])
    remaining = db.list_issue_dates()
    assert base + timedelta(days=4) in remaining and base + timedelta(days=0) not in remaining
    assert len(deleted) >= 2
    with db.get_conn() as c:  # cleanup
        c.execute("DELETE FROM issues WHERE issue_date >= %s", (base,))
