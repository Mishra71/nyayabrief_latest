# NyayaBrief AI

Upload the daily *The Hindu* PDF -> get exam-relevant notes (Judiciary / APO / BPSC) with page numbers and verbatim evidence quotes.

```
PDF -> PyMuPDF blocks -> segment articles (geometry) -> stitch "continued on page N"
    -> keyword prefilter -> LLM classify (batched) -> LLM extract (relevant only)
    -> grounding validator (code) -> Postgres (rows + tsvector + pgvector) -> Streamlit
```
No agent: ingestion is a fixed, resumable batch pipeline; search is RAG (filters + keyword + vector + RRF).

## 1. Local setup
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # add GEMINI_API_KEY (and GROQ_API_KEY), set ADMIN_PASSWORD
docker compose up -d                                   # local Postgres + pgvector
python scripts/init_db.py
pytest -q                                              # 10 tests should pass
```

## 2. FIRST: calibrate segmentation on a real Hindu PDF (most important step)
```bash
python scripts/inspect_pdf.py data/pdfs/day1.pdf 6     # 6 = page number -> writes data/debug.png
```
Check: text layer present? body/headline font sizes sensible? In debug.png red = headline, blue = body.
Tune `SegConfig`, `SECTION_LABELS`, `CONT_TO/CONT_FROM` in `nyayabrief/segment.py` until ~85% of articles look right.
Typical fixes: body columns missing -> raise `x_slack`; headlines missed -> lower `headline_ratio`.

## 3. Process a paper
```bash
python scripts/run_issue.py data/pdfs/day1.pdf         # date auto-detected, or --date 2026-09-30
streamlit run streamlit_app.py                         # Upload tab appears because ADMIN_PASSWORD is set
```
Re-running the same PDF only does the missing work (quota ran out? just run again later).

## 4. Evaluate (do this before tuning prompts)
```bash
python eval/labeling.py export 2026-09-30              # fill the `human` column with 1/0 for every row
python eval/labeling.py score eval/label_2026-09-30.csv
```
Targets: prefilter recall >= 0.95, then classifier F1. Label 5+ issues.

## 5. Deploy free, share a link with Shruti
1. **DB**: create a free Neon (or Supabase) Postgres. Set `DATABASE_URL` (Neon needs `?sslmode=require`) in your `.env`, run `python scripts/init_db.py` once against it.
2. **You process papers on your laptop** (same `.env`) -> notes land in the cloud DB.
3. Push this repo to GitHub (private is fine; `.env` is git-ignored).
4. **Streamlit Community Cloud** -> New app -> main file `streamlit_app.py` -> Secrets:
   ```toml
   DATABASE_URL = "postgresql://...sslmode=require"
   # optional: GEMINI_API_KEY = "..."  -> enables semantic search + "Answer with citations"
   ```
   Do NOT set `ADMIN_PASSWORD` there -> Shruti sees only Daily Brief + Search.
5. Share the app link (in the app's Share settings you can restrict it to invited emails).

## Notes / limits
- Verify model names & free quotas in `.env` (Gemini 2.5 models are scheduled to shut down 16 Oct 2026; free limits are no longer published - see AI Studio).
- Not in MVP: OCR for scanned pages (reported, not processed), cross-day story clustering, embedding-similarity prefilter, LLM-as-judge for summaries.
- Small ads directly under an article may get attached to it (nearest headline above wins).
