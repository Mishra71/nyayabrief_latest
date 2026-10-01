"""One app, two modes. Viewer (Shruti): Daily Brief + Search. Admin (you): + Upload tab, only if ADMIN_PASSWORD is set."""
import tempfile
from datetime import date
from pathlib import Path

import streamlit as st

from nyayabrief import db, search
from nyayabrief.config import get_settings
from nyayabrief.pipeline import detect_issue_date, process_pdf

st.set_page_config(page_title="NyayaBrief AI", page_icon="⚖️", layout="wide")
cfg = get_settings()

CATEGORIES = {
    "judgment": "Court judgments", "constitutional": "Constitutional", "statute_bill": "Laws / Bills",
    "legal_institutional": "Legal institutions", "policy_governance": "Policy & governance",
    "intl_law": "International law", "bihar_state": "Bihar / State", "other": "Other",
}
BADGE = {"verified": "✅ verified", "partial": "⚠️ partly verified", "needs_review": "❗ needs review"}


@st.cache_data(ttl=120)
def _dates():
    return db.list_issue_dates()


@st.cache_data(ttl=120)
def _brief(d):
    return db.brief(d)


@st.cache_data(ttl=120)
def _stats(d):
    return db.issue_stats(d)


def card(row: dict) -> None:
    d = row["data"]
    title = f"{row['headline']}  ·  p.{row['page_no']}  ·  {CATEGORIES.get(row['category'], row['category'])}"
    with st.expander(title):
        st.caption(
            f"{row['issue_date']} · {BADGE.get(row['validation_status'], '')} · tags: {', '.join(row['exam_tags']) or '-'}"
            f" · relevance {(row['relevance_score'] or 0):.2f}" + (" · ⚠️ article continues elsewhere (incomplete)" if row["incomplete"] else "")
        )
        st.write(d["summary"])
        for p in d["key_points"]:
            st.markdown(f"- {p}")
        case = d.get("case")
        if case and any(case.get(k) for k in ("case_name", "court", "holding")):
            st.markdown(
                f"**Case:** {case.get('case_name') or '-'}  \n**Court:** {case.get('court') or '-'}"
                + (f"  \n**Bench:** {', '.join(case['bench'])}" if case.get("bench") else "")
                + (f"  \n**Held:** {case['holding']}" if case.get("holding") else "")
            )
        if d.get("provisions"):
            st.markdown("**Provisions:** " + ", ".join(p["name"] for p in d["provisions"]))
        st.info(d["exam_relevance"])
        for e in d["evidence"]:
            st.markdown(f"> {e['quote']}")
        if row["warnings"]:
            st.caption("Validation notes: " + "; ".join(row["warnings"]))


def brief_tab() -> None:
    dates = _dates()
    if not dates:
        st.info("No newspaper processed yet.")
        return
    c1, c2, c3 = st.columns([1, 2, 1])
    d = c1.selectbox("Date", dates, format_func=lambda x: x.strftime("%d %b %Y"))
    cats = c2.multiselect("Category", list(CATEGORIES), format_func=CATEGORIES.get)
    tag = c3.selectbox("Exam", ["all", "judiciary", "apo", "bpsc", "general"])
    stats = _stats(d)
    if stats.get("status") == "partial":
        st.warning("This issue is partially processed (API quota ran out). More notes will appear after the next run.")
    st.caption(f"{stats.get('articles', 0)} articles scanned → {stats.get('relevant', 0)} relevant → {stats.get('extracted', 0)} notes")
    rows = [r for r in _brief(d) if (not cats or r["category"] in cats) and (tag == "all" or tag in r["exam_tags"])]
    for r in rows:
        card(r)
    if not rows:
        st.write("Nothing for these filters.")


def search_tab() -> None:
    q = st.text_input("Search notes (e.g. bail, Article 21, POCSO, Collegium)")
    c1, c2 = st.columns(2)
    cat = c1.selectbox("Category", [None, *CATEGORIES], format_func=lambda x: "all" if x is None else CATEGORIES[x])
    tag = c2.selectbox("Exam ", [None, "judiciary", "apo", "bpsc", "general"], format_func=lambda x: "all" if x is None else x)
    if not q:
        return
    hits = search.hybrid_search(q, category=cat, tag=tag)
    if not hits:
        st.write("No results.")
        return
    if st.button("Answer with citations"):
        with st.spinner("Thinking..."):
            try:
                st.markdown(search.answer(q, hits))
            except Exception as e:  # quota/outage: search results below still work
                st.warning(f"Answer unavailable right now ({type(e).__name__}). Results are below.")
    for i, h in enumerate(hits, 1):
        st.caption(f"[{i}]")
        card(h)


def admin_tab() -> None:
    if st.text_input("Admin password", type="password") != cfg.admin_password:
        st.info("Enter admin password to upload a newspaper.")
        return
    up = st.file_uploader("The Hindu PDF", type="pdf")
    if not up:
        return
    tmp = Path(tempfile.gettempdir()) / up.name
    tmp.write_bytes(up.getvalue())
    d = st.date_input("Issue date", value=detect_issue_date(tmp) or date.today())
    if st.button("Process newspaper", type="primary"):
        bar = st.progress(0.0, text="Starting...")

        def cb(stage: str, done: int, total: int) -> None:
            bar.progress(min(done / max(total, 1), 1.0), text=f"{stage}: {done}/{total}")

        result = process_pdf(tmp, d, progress=cb)
        st.cache_data.clear()
        (st.success if result["status"] == "done" else st.warning)(
            f"{result['status']}: {result.get('articles', 0)} articles, {result.get('relevant', 0)} relevant, "
            f"{result.get('extracted', 0)} notes. {result.get('note') or ''}"
        )


st.title("⚖️ NyayaBrief AI")
tabs = ["📰 Daily Brief", "🔎 Search"] + (["⬆️ Upload (admin)"] if cfg.admin_password else [])
for t, fn in zip(st.tabs(tabs), [brief_tab, search_tab, admin_tab]):
    with t:
        fn()
