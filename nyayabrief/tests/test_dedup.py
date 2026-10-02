from datetime import date

from nyayabrief.dedup import group_duplicates

D = date(2019, 11, 8)
SHORT = "The Union government on Thursday night announced that it would revoke the Overseas Citizen of India card of author Aatish Taseer"
FULL = SHORT + " over what it said was his attempt to conceal information that his father Salman Taseer was of Pakistani origin."


def row(h, body, page):
    return {"headline": h, "body": body, "page_no": page, "issue_date": D}


def test_same_story_two_pages_is_linked_and_longest_kept():
    rows = [row("Govt. to revoke Aatish Taseer's OCI card", SHORT, 1), row("Centre to revoke Taseer's OCI card", FULL, 13)]
    out = group_duplicates(rows)
    assert len(out) == 1 and out[0]["page_no"] == 13 and out[0]["also_on_pages"] == [1]


def test_different_stories_not_merged():
    rows = [row("JNU asks students to end protest against hostel manual", "The Jawaharlal Nehru University administration on Thursday appealed to students", 4),
            row("JEE: TMC to protest against Centre's bias", "Escalating her fight with the Centre over alleged bias against regional languages", 9)]
    assert len(group_duplicates(rows)) == 2


def test_different_dates_never_merged():
    a, b = row("Same headline here", "same body text " * 20, 1), row("Same headline here", "same body text " * 20, 2)
    b["issue_date"] = date(2019, 11, 9)
    assert len(group_duplicates([a, b])) == 2
