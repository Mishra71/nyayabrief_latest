import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # run from anywhere
"""Calibration + debugging tool (your Step 2/3). Usage:
    python scripts/inspect_pdf.py data/pdfs/day1.pdf [page_no]

Prints: chars per page (text layer check), font-size histogram, auto-detected body size / headline threshold,
segmentation summary. With a page number it also writes data/debug.png:
red = headline, blue = body assigned to an article, gray = dropped (ads / furniture).
"""
import sys
from collections import Counter

import fitz

from nyayabrief.parse import extract_pages
from nyayabrief.segment import SegConfig, calibrate_body_size, segment_page, segment_pdf

path = sys.argv[1]
pages = extract_pages(path)
print(f"pages: {len(pages)}")
print("chars per page:", [p.chars for p in pages])
print("pages with no text layer (<200 chars):", [p.number for p in pages if p.chars < 200])

hist: Counter = Counter()
for p in pages:
    for b in p.blocks:
        hist[round(b.size * 2) / 2] += b.nchars
print("\nfont size -> chars (top 8):")
for size, n in sorted(hist.items(), key=lambda kv: kv[1], reverse=True)[:8]:
    print(f"  {size:>5}: {n}")

cfg = SegConfig()
body = calibrate_body_size(pages)
print(f"\nauto body size = {body}; headline threshold = {body * cfg.headline_ratio:.1f}")
arts, report = segment_pdf(path, cfg)
print("segmentation:", report)
for a in arts[:15]:
    print(f"  p{a.page} [{a.section}] {a.headline[:70]!r} ({len(a.body.split())} words){' INCOMPLETE' if a.incomplete else ''}")

if len(sys.argv) > 2:
    n = int(sys.argv[2])
    page = pages[n - 1]
    doc = fitz.open(path)
    pg = doc[n - 1]
    thr = body * cfg.headline_ratio
    used = {a.headline for a in segment_page(page, body, cfg)}
    for b in page.blocks:
        color = (1, 0, 0) if b.size >= thr else (0, 0, 1)
        pg.draw_rect(fitz.Rect(b.bbox), color=color, width=0.8)
    pg.get_pixmap(dpi=110).save("data/debug.png")
    print(f"\nwrote data/debug.png for page {n} ({len(used)} articles found on this page)")
