import fitz

from nyayabrief.segment import Article, segment_pdf, stitch

BODY1 = "ALPHA " + "The Supreme Court on Tuesday heard a petition about bail and personal liberty under Article 21. " * 6
BODY2 = "BETA " + "The bench observed that prolonged incarceration without trial violates fundamental rights of the accused. " * 6
BODY3 = "GAMMA " + "Parliament passed the amendment after a long debate and the Bill now awaits assent from the President. " * 6


def make_pdf(path):
    doc = fitz.open()
    pg = doc.new_page(width=595, height=842)
    pg.insert_textbox(fitz.Rect(40, 60, 555, 110), "SC grants bail to undertrial after long delay", fontsize=20)
    pg.insert_textbox(fitz.Rect(40, 120, 285, 400), BODY1, fontsize=9)
    pg.insert_textbox(fitz.Rect(305, 120, 555, 400), BODY2, fontsize=9)
    pg.insert_textbox(fitz.Rect(40, 450, 555, 500), "Parliament passes constitutional amendment Bill", fontsize=20)
    pg.insert_textbox(fitz.Rect(40, 510, 555, 700), BODY3, fontsize=9)
    pg.insert_textbox(fitz.Rect(40, 720, 555, 780), "Buy one get one free! Limited offer.", fontsize=9)
    doc.save(path)


def test_two_articles_two_columns(tmp_path):
    p = tmp_path / "t.pdf"
    make_pdf(p)
    arts, report = segment_pdf(p)
    assert report["pages"] == 1 and report["scanned_pages"] == []
    assert len(arts) == 2
    a1, a2 = arts
    assert "bail" in a1.headline.lower() and "amendment" in a2.headline.lower()
    assert a1.body.index("ALPHA") < a1.body.index("BETA")  # column 1 read before column 2
    assert "GAMMA" not in a1.body and "ALPHA" not in a2.body  # no bleeding across articles


def test_stitch_continued_article():
    a = Article(1, "Verdict in landmark case", "first part " * 20, continues_on=9)
    b = Article(9, "Verdict in landmark case", "second part " * 20, continued_from=1)
    out = stitch([a, b])
    assert len(out) == 1 and "second part" in out[0].body and not out[0].incomplete


def test_stitch_missing_target_flags_incomplete():
    a = Article(1, "Some story", "text " * 30, continues_on=9)
    out = stitch([a])
    assert len(out) == 1 and out[0].incomplete


def _page_pdf(path, items):
    doc = fitz.open()
    pg = doc.new_page(width=595, height=842)
    for rect, text, size in items:
        pg.insert_textbox(fitz.Rect(*rect), text, fontsize=size)
    doc.save(path)


def test_deck_is_merged_into_headline_not_used_as_headline(tmp_path):
    """Headline (22pt) + deck/sub-headline (13pt) + body (9pt): headline must be the BIG one."""
    p = tmp_path / "deck.pdf"
    _page_pdf(p, [
        ((40, 60, 555, 100), "Supreme Court verdict on bail expected today", 22),
        ((40, 105, 555, 140), "Bench says prolonged delay violates personal liberty of undertrials", 13),
        ((40, 150, 555, 400), BODY1, 9),
        ((40, 420, 555, 520), BODY2, 9),  # filler so 9pt is clearly the body size
    ])
    arts, _ = segment_pdf(p)
    assert len(arts) == 1
    assert "verdict" in arts[0].headline.lower()
    assert "prolonged delay" in arts[0].body  # deck kept as the first line of the body


def test_single_word_column_label_is_not_an_article(tmp_path):
    p = tmp_path / "label.pdf"
    _page_pdf(p, [
        ((40, 60, 555, 100), "ELSEWHERE", 20),
        ((40, 100, 555, 300), BODY1, 9),
    ])
    arts, _ = segment_pdf(p)
    assert arts == []


def test_private_use_and_control_chars_removed():
    from nyayabrief.segment import clean_text
    assert clean_text("offi\ue000ce and A\x00B \ufffdok \u00adx") == "office and AB ok -x"


def test_small_brief_with_dateline_becomes_article_but_inline_subhead_does_not(tmp_path):
    p = tmp_path / "brief.pdf"
    doc = fitz.open()
    pg = doc.new_page(width=595, height=842)
    big = fitz.Rect
    pg.insert_textbox(big(40, 50, 555, 100), "Supreme Court verdict on bail expected today", fontsize=22)
    pg.insert_textbox(big(40, 110, 555, 150), "Title suits and later developments", fontsize=9.6, fontname="hebo")   # inline subhead
    pg.insert_textbox(big(40, 160, 555, 330), BODY1, fontsize=9)
    pg.insert_textbox(big(40, 400, 280, 418), "ICC jails warlord for 30 years", fontsize=9.6, fontname="hebo")      # brief headline
    pg.insert_textbox(big(40, 420, 120, 430), "THE HAGUE", fontsize=5.5)                                             # dateline
    pg.insert_textbox(big(40, 434, 555, 560), BODY2, fontsize=9)
    doc.save(p)
    arts, _ = segment_pdf(p)
    heads = [a.headline for a in arts]
    assert any("ICC jails warlord" in h for h in heads), heads
    assert not any(h.startswith("Title suits") for h in heads), heads   # subhead stays inside its article
    assert len(arts) == 2
