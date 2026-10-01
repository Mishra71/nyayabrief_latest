"""Stage 2 (deterministic): text blocks -> individual articles.

Idea: headline = block(s) whose font is clearly bigger than body text.
Body = blocks lying BELOW a headline, horizontally under it (same columns), nearest headline above wins.
Then stitch "Continued on page N" fragments. Everything is geometry + regex -> testable, no LLM.
All thresholds live in SegConfig / the regex lists so you can tune them from scripts/inspect_pdf.py output.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass

from rapidfuzz import fuzz

from .parse import Block, Page, extract_pages

# Tune these after looking at real Hindu PDFs (inspect_pdf.py prints what it finds).
# The Hindu prints an arrow glyph that extracts as a stray letter: "CONTINUED ON A PAGE 12" -> allow 0-2 junk chars.
CONT_FROM = [re.compile(r"continued\s+from\s*\S{0,2}\s*page\s*(\d+)", re.I)]
CONT_TO = [re.compile(r"continued\s+on\s*\S{0,2}\s*page\s*(\d+)", re.I)]
# Cross-references ("MORE REPORTS ON A PAGE 13") are NOT continuations: strip them from the text, don't stitch.
XREF = re.compile(r"(?:more\s+reports|details)\s+on\s*\S{0,2}\s*page\s*\d+|see\s+also\s*\S{0,2}\s*page\s*\d+", re.I)
SECTION_LABELS = [
    "CITY", "NORTH", "EAST", "WEST", "SOUTH", "NATION", "WORLD", "NEWS", "EDITORIAL", "OPED", "SPORT",
    "BUSINESS", "ENTERTAINMENT", "EDUCATION", "SCIENCE",
]
_SECTION_RX = re.compile(r"\b(" + "|".join(SECTION_LABELS) + r")\b")


@dataclass
class SegConfig:
    headline_ratio: float = 1.35   # headline if font >= body_size * ratio
    min_words: int = 20            # drop tiny fragments/ads
    header_frac: float = 0.03      # ignore running header/footer bands
    footer_frac: float = 0.03
    max_headline_chars: int = 220
    min_headline_words: int = 2    # one-word big text ("ELSEWHERE", "LETTERS") is a column label, not an article
    deck_ratio: float = 1.15       # a smaller heading under a >=15% bigger one is its sub-headline (deck)
    deck_gap: float = 2.5          # ...if the vertical gap is under deck_gap * its font size
    deck_max_body_mult: float = 1.8  # ...and its font is at most 1.8x body size (decks ~14pt, side headlines >=17pt)
    min_overlap: float = 0.5       # body block counts as "under" a headline if >= this share of its width overlaps it...
    x_slack: float = 5.0           # ...or its LEFT edge lies within [headline.x0 - slack, headline.x1 + slack].
                                   # Raise x_slack if body columns to the right of a short headline get dropped.


@dataclass
class Article:
    page: int
    headline: str
    body: str
    section: str | None = None
    continues_on: int | None = None
    continued_from: int | None = None
    incomplete: bool = False


_BAD_CATEGORIES = {"Cc", "Co", "Cn", "Cs"}  # control, private-use (broken ligatures), unassigned, surrogates


def _strip_bad_chars(t: str) -> str:
    """PDF fonts often emit NUL / private-use glyphs for ligatures (fi, ff, rupee). Postgres rejects NUL, UI shows boxes."""
    return "".join(
        ch for ch in t
        if ch in "\n\t" or (unicodedata.category(ch) not in _BAD_CATEGORIES and ch not in "\ufffd\u00ad")
    )


def clean_text(t: str) -> str:
    t = re.sub(r"\u00ad\s*\n\s*", "", t)   # soft hyphen at a line end = typesetter's break -> join the word
    t = t.replace("\u00ad", "-")            # soft hyphen mid-line is a REAL hyphen in this PDF ("Ex-officers")
    t = unicodedata.normalize("NFKC", t)    # ligatures fi/fl/ffi -> letters, NBSP -> space (needed for search)
    t = _strip_bad_chars(t)
    t = re.sub(r"(?<=[a-z])-\n(?=[a-z])", "", t)  # de-hyphenate line-break splits
    t = re.sub(r"\s*\n\s*", " ", t)
    return re.sub(r"\s{2,}", " ", t).strip()


def _pop_marker(text: str, patterns) -> tuple[int | None, str]:
    for p in patterns:
        m = p.search(text)
        if m:
            return int(m.group(1)), (text[: m.start()] + " " + text[m.end():]).strip()
    return None, text


def calibrate_body_size(pages: list[Page]) -> float:
    """Body font = the size that carries the most characters in the whole issue."""
    c: Counter[float] = Counter()
    for p in pages:
        for b in p.blocks:
            c[round(b.size * 2) / 2] += b.nchars
    return c.most_common(1)[0][0] if c else 9.0


def detect_section(page: Page) -> str | None:
    top = " ".join(b.text for b in page.blocks if b.bbox[3] < page.height * 0.08).upper()
    m = _SECTION_RX.search(top)
    return m.group(1) if m else None


def _is_under(block_bbox, head_bbox, cfg: "SegConfig") -> bool:
    """Headline text often ends mid-page-width, so overlap alone loses right-hand columns; also accept left-edge match."""
    w = max(0.0, min(block_bbox[2], head_bbox[2]) - max(block_bbox[0], head_bbox[0]))
    if w / max(1e-6, block_bbox[2] - block_bbox[0]) >= cfg.min_overlap:
        return True
    return head_bbox[0] - cfg.x_slack <= block_bbox[0] <= head_bbox[2] + cfg.x_slack


def _merge_heads(heads: list[Block]) -> list[dict]:
    """Multi-line headlines can arrive as several blocks: glue vertically adjacent, same-size ones."""
    merged: list[dict] = []
    for h in sorted(heads, key=lambda b: (b.bbox[1], b.bbox[0])):
        text = h.text
        for m in merged:
            gap = h.bbox[1] - m["bbox"][3]
            narrower = min(h.bbox[2] - h.bbox[0], m["bbox"][2] - m["bbox"][0])
            overlap = max(0.0, min(h.bbox[2], m["bbox"][2]) - max(h.bbox[0], m["bbox"][0])) / max(narrower, 1e-6)
            if -2 <= gap < 1.2 * h.size and overlap > 0.5 and abs(h.size - m["size"]) < 1.5:
                m["text"] += "\n" + text
                b = m["bbox"]
                m["bbox"] = (min(b[0], h.bbox[0]), b[1], max(b[2], h.bbox[2]), max(b[3], h.bbox[3]))
                break
        else:
            merged.append({"bbox": h.bbox, "text": text, "size": h.size})
    return merged


def _absorb_decks(heads: list[dict], cfg: "SegConfig", body_size: float) -> list[dict]:
    """A newspaper headline is often followed by a smaller sub-headline (deck). Without this step the deck wins the
    'nearest headline above' race, steals the body, and the real headline ends up with no body (article dropped)."""
    kept: list[dict] = []
    for h in sorted(heads, key=lambda d: (d["bbox"][1], d["bbox"][0])):
        parent = None
        for p in kept:
            gap = h["bbox"][1] - p["bbox"][3]
            narrower = min(h["bbox"][2] - h["bbox"][0], p["bbox"][2] - p["bbox"][0])
            overlap = max(0.0, min(h["bbox"][2], p["bbox"][2]) - max(h["bbox"][0], p["bbox"][0])) / max(narrower, 1e-6)
            # Decks are set in a fixed small display size (~1.6x body text); real side-story headlines are bigger (>=2x).
            if (p["size"] >= h["size"] * cfg.deck_ratio and h["size"] <= cfg.deck_max_body_mult * body_size
                    and -2 <= gap < cfg.deck_gap * h["size"] and overlap > 0.3):
                parent = p
        if parent is None:
            kept.append({**h, "deck": []})
        else:
            parent["deck"].append(h["text"])
            b, hb = parent["bbox"], h["bbox"]
            parent["bbox"] = (min(b[0], hb[0]), b[1], max(b[2], hb[2]), max(b[3], hb[3]))
    return kept


def _assemble(blocks: list[Block]) -> str:
    """Reading order inside one article: column by column (cluster x0), top to bottom."""
    xs = sorted({round(b.bbox[0]) for b in blocks})
    col_of, col, prev = {}, 0, None
    for x in xs:
        if prev is not None and x - prev > 15:
            col += 1
        col_of[x], prev = col, x
    ordered = sorted(blocks, key=lambda b: (col_of[round(b.bbox[0])], b.bbox[1]))
    return "\n".join(b.text for b in ordered)


def segment_page(page: Page, body_size: float, cfg: SegConfig) -> list[Article]:
    thr = body_size * cfg.headline_ratio
    top, bot = page.height * cfg.header_frac, page.height * (1 - cfg.footer_frac)
    blocks = [b for b in page.blocks if b.bbox[1] >= top and b.bbox[3] <= bot]
    heads_raw = [
        b for b in blocks
        if b.size >= thr and 8 <= len(b.text) <= cfg.max_headline_chars and not b.text.strip().isdigit()
    ]
    raw_ids = {id(b) for b in heads_raw}
    heads = _absorb_decks(_merge_heads(heads_raw), cfg, body_size)

    groups: dict[int, list[Block]] = defaultdict(list)
    for b in blocks:
        if id(b) in raw_ids:
            continue
        cands = [
            (i, h) for i, h in enumerate(heads)
            if h["bbox"][3] <= b.bbox[1] + 3 and _is_under(b.bbox, h["bbox"], cfg)
        ]
        if cands:  # nearest headline above wins; blocks with no headline above = ads/furniture -> dropped
            groups[max(cands, key=lambda ih: ih[1]["bbox"][3])[0]].append(b)

    section = detect_section(page)
    out: list[Article] = []
    for i, h in enumerate(heads):
        if not groups.get(i) or len(h["text"].split()) < cfg.min_headline_words:
            continue
        body = clean_text("\n".join(h["deck"]) + "\n" + _assemble(groups[i]))
        cf, body = _pop_marker(body, CONT_FROM)
        ct, body = _pop_marker(body, CONT_TO)
        body = XREF.sub(" ", body)
        out.append(Article(page.number, clean_text(h["text"]), body, section, continues_on=ct, continued_from=cf))
    return out


def stitch(articles: list[Article]) -> list[Article]:
    """Join 'continued on page N' fragments. Unmatched fragments are kept but flagged incomplete."""
    by_page: dict[int, list[Article]] = defaultdict(list)
    for a in articles:
        by_page[a.page].append(a)
    absorbed: set[int] = set()
    for a in articles:
        if not a.continues_on or a.continues_on == a.page:
            continue
        cands = [c for c in by_page.get(a.continues_on, []) if id(c) not in absorbed and c.continued_from in (a.page, None)]
        best, best_score = None, 0.0
        for c in cands:
            score = fuzz.token_set_ratio(a.headline, c.headline) + (40 if c.continued_from == a.page else 0)
            if score > best_score:
                best, best_score = c, score
        if best and best_score >= 50:
            a.body = f"{a.body} {best.body}".strip()
            a.continues_on = None
            absorbed.add(id(best))
        else:
            a.incomplete = True
    out = [a for a in articles if id(a) not in absorbed]
    for a in out:
        if a.continued_from:  # orphan continuation (parent not found)
            a.incomplete = True
    return out


def segment_pdf(pdf_path, cfg: SegConfig | None = None) -> tuple[list[Article], dict]:
    cfg = cfg or SegConfig()
    pages = extract_pages(pdf_path)
    body_size = calibrate_body_size(pages)
    arts: list[Article] = []
    for p in pages:
        arts += segment_page(p, body_size, cfg)
    arts = stitch(arts)
    arts = [a for a in arts if len(a.body.split()) >= cfg.min_words]
    report = {
        "pages": len(pages),
        "scanned_pages": [p.number for p in pages if p.chars < 200],  # no text layer -> needs OCR (not in MVP)
        "body_size": body_size,
        "articles": len(arts),
        "incomplete": sum(a.incomplete for a in arts),
    }
    return arts, report
