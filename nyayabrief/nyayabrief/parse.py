"""Stage 1 (deterministic): PDF -> pages -> text blocks with geometry + font info."""
from __future__ import annotations

from dataclasses import dataclass, field

import fitz  # PyMuPDF

SPLIT_RATIO = 1.25  # consecutive lines whose font sizes differ by more than this ratio start a new block


@dataclass
class Block:
    page: int
    bbox: tuple[float, float, float, float]
    text: str
    size: float   # char-weighted mean font size (robust to drop-caps)
    bold: bool
    nchars: int


@dataclass
class Page:
    number: int   # 1-based PDF page index = source of truth (printed page numbers are unreliable)
    width: float
    height: float
    blocks: list[Block] = field(default_factory=list)

    @property
    def chars(self) -> int:
        return sum(b.nchars for b in self.blocks)


def _lines(raw_block: dict) -> list[dict]:
    out = []
    for ln in raw_block["lines"]:
        text = "".join(s["text"] for s in ln["spans"]).strip()
        n = weighted = bold = 0
        for s in ln["spans"]:
            k = len(s["text"].strip())
            if not k:
                continue
            weighted += s["size"] * k
            n += k
            if (s["flags"] & 16) or "bold" in s["font"].lower():
                bold += k
        if text and n:
            out.append({"text": text, "size": weighted / n, "n": n, "bold": bold, "bbox": ln["bbox"], "w": weighted})
    return out


def _to_block(page_no: int, group: list[dict]) -> Block:
    n = sum(l["n"] for l in group)
    x0 = min(l["bbox"][0] for l in group); y0 = min(l["bbox"][1] for l in group)
    x1 = max(l["bbox"][2] for l in group); y1 = max(l["bbox"][3] for l in group)
    return Block(page_no, (x0, y0, x1, y1), "\n".join(l["text"] for l in group),
                 sum(l["w"] for l in group) / n, sum(l["bold"] for l in group) / n > 0.6, n)


def extract_pages(pdf_path) -> list[Page]:
    doc = fitz.open(pdf_path)
    pages: list[Page] = []
    for i, pg in enumerate(doc, start=1):
        page = Page(number=i, width=pg.rect.width, height=pg.rect.height)
        for b in pg.get_text("dict")["blocks"]:
            if b["type"] != 0:  # 0 = text, 1 = image
                continue
            group: list[dict] = []
            for ln in _lines(b):
                if group:
                    ref = sum(l["w"] for l in group) / sum(l["n"] for l in group)
                    if max(ln["size"], ref) / max(min(ln["size"], ref), 1e-6) > SPLIT_RATIO:
                        page.blocks.append(_to_block(i, group))
                        group = []
                group.append(ln)
            if group:
                page.blocks.append(_to_block(i, group))
        pages.append(page)
    return pages
