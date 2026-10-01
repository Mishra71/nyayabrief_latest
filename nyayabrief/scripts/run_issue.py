import pathlib, sys; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))  # run from anywhere
"""CLI: process one newspaper PDF end to end.
    python scripts/run_issue.py data/pdfs/hindu.pdf [--date 2026-09-30]
"""
import argparse
import logging
from datetime import date

from nyayabrief.pipeline import process_pdf

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
ap = argparse.ArgumentParser()
ap.add_argument("pdf")
ap.add_argument("--date", type=date.fromisoformat, default=None)
args = ap.parse_args()

result = process_pdf(args.pdf, args.date, progress=lambda stage, done, total: print(f"  {stage}: {done}/{total}"))
print(result)
