"""One app, two modes. Viewer (Shruti): Daily Brief + Search. Admin (you): + Upload tab, only if ADMIN_PASSWORD is set."""
import tempfile
from datetime import date
from pathlib import Path

import streamlit as st

from nyayabrief import db, search
from nyayabrief.config import get_settings
from nyayabrief.dedup import group_duplicates
from nyayabrief.pipeline import detect_issue_date, process_pdf

st.set_page_config(page_title="NyayaBrief AI", page_icon="⚖️", layout="centered")
cfg = get_settings()

st.markdown("""<style>
.block-container{padding-top:1.4rem;max-width:760px}
.chip{display:inline-block;padding:1px 9px;margin:0 6px 5px 0;border-radius:999px;font-size:.76rem;border:1px solid rgba(128,128,128,.5)}
.chip.ok{border-color:#16a34a;color:#16a34a}.chip.warn{border-color:#d97706;color:#d97706}.chip.bad{border-color:#dc2626;color:#dc2626}
.chip.tag{border-color:#0f766e;color:#0f766e}
</style>""", unsafe_allow_html=True)

CATEGORIES = {
    "judgment": "Court judgments", "constitutional": "Constitutional", "statute_bill": "Laws / Bills",
    "legal_institutional": "Legal institutions", "intl_law": "International law",
    "policy_governance": "Policy & governance", "economy": "Economy", "environment_science": "Environment & Science",
    "intl_relations": "International relations", "security_defence": "Security & defence",
    "social_issues": "Social issues & schemes", "awards_misc": "Awards, people & misc", "bihar_state": "Bihar / State", "other": "Other",
}
ICON = {"judgment": "⚖️", "constitutional": "📜", "statute_bill": "🏛️", "legal_institutional": "🧑‍⚖️", "intl_law": "🌐",
        "policy_governance": "📋", "economy": "💰", "environment_science": "🌿", "intl_relations": "🌍",
        "security_defence": "🛡️", "social_issues": "🤝", "awards_misc": "🏅", "bihar_state": "📍", "other": "📰"}
LEGAL = ["judgment", "constitutional", "statute_bill", "legal_institutional", "intl_law"]
CURRENT = ["policy_governance", "economy", "environment_science", "intl_relations", "security_defence",
           "social_issues", "awards_misc", "bihar_state", "other"]
EXAMS = ["all", "judiciary", "apo", "bpsc", "upsc", "general"]
STATUS = {"verified": ("ok", "✅ Verified against article"), "partial": ("warn", "⚠️ Partly verified"),
          "needs_review": ("bad", "❗ Unverified")}


@st.cache_data(ttl=120)
def _dates():
    return db.list_issue_dates()


@st.cache_data(ttl=120)
def _brief(d):
    return db.brief(d)


@st.cache_data(ttl=120)
def _stats(d):
    return db.issue_stats(d)


def chips(row: dict) -> str:
    cls, label = STATUS.get(row["validation_status"], ("warn", row["validation_status"]))
    out = [f'<span class="chip {cls}">{label}</span>', f'<span class="chip">p.{int(row["page_no"])}</span>']
    out += [f'<span class="chip tag">{t}</span>' for t in row["exam_tags"] if t in ("judiciary", "apo", "bpsc", "upsc", "general")]
    if row.get("incomplete"):
        out.append('<span class="chip warn">may be incomplete</span>')
    return "".join(out)


def feedback_buttons(row: dict, ctx: str) -> None:
    c1, c2, _ = st.columns([1, 1, 3])
    for col, vote, label in ((c1, 1, "👍 Sahi"), (c2, -1, "👎 Galat")):
        if col.button(label, key=f"fb-{ctx}-{row['id']}-{vote}"):
            try:
                db.save_feedback(row["id"], vote)
                st.toast("Thanks! Feedback saved." if vote == 1 else "Thanks, we'll review this note.")
            except Exception:
                st.toast("Could not save feedback right now.")


def card(row: dict, ctx: str, quick: bool = False) -> None:
    d = row["data"]
    title = f"{ICON.get(row['category'], '📰')} {row['headline']}"
    with st.expander(title):
        st.markdown(chips(row), unsafe_allow_html=True)
        if row.get("also_on_pages"):
            st.caption("Same story also printed on page " + ", ".join(str(p) for p in row["also_on_pages"]))
        if not quick:
            st.write(d["summary"])
        for p in d["key_points"]:
            st.markdown(f"- {p}")
        if quick:
            return
        case = d.get("case")
        if case and any(case.get(k) for k in ("case_name", "court", "holding")):
            st.markdown(
                f"**Case:** {case.get('case_name') or '-'}  \n**Court:** {case.get('court') or '-'}"
                + (f"  \n**Bench:** {', '.join(case['bench'])}" if case.get("bench") else "")
                + (f"  \n**Held:** {case['holding']}" if case.get("holding") else "")
            )
        if d.get("provisions"):
            st.markdown("**Provisions:** " + ", ".join(p["name"] for p in d["provisions"]))
        st.info("💡 **Exam angle (AI note):** " + d["exam_relevance"])
        for e in d["evidence"]:
            st.markdown(f"> {e['quote']}")
        if row.get("warnings"):
            st.caption("Validation notes: " + "; ".join(row["warnings"]))
        if st.checkbox("📄 Show original article text (to check)", key=f"orig-{ctx}-{row['id']}"):
            st.caption(row.get("body") or "")
        feedback_buttons(row, ctx)


def brief_markdown(rows: list[dict], d) -> str:
    """One-click revision sheet: the filtered brief as a Markdown file."""
    out = [f"# NyayaBrief - {d:%d %b %Y}", ""]
    for r in rows:
        x = r["data"]
        out += [f"## {r['headline']}  (p.{r['page_no']} | {CATEGORIES.get(r['category'], r['category'])})", x["summary"], ""]
        out += [f"- {k}" for k in x["key_points"]]
        if x.get("provisions"):
            out.append("**Provisions:** " + ", ".join(p["name"] for p in x["provisions"]))
        out += ["", f"_Exam angle (AI note): {x['exam_relevance']}_", ""]
    return "\n".join(out)


def brief_tab(group: list[str], ns: str, exam_filter: bool = True) -> None:
    dates = _dates()
    if not dates:
        st.info("No newspaper processed yet. Please check back later.")
        return
    d = st.selectbox("Date", dates, format_func=lambda x: x.strftime("%A, %d %b %Y"), key=f"{ns}-date")
    c1, c2 = st.columns(2)
    cats = c1.multiselect("Category", group, format_func=lambda c: f"{ICON[c]} {CATEGORIES[c]}", key=f"{ns}-cats")
    tag = c2.selectbox("Exam", EXAMS, key=f"{ns}-exam") if exam_filter else "all"  # current affairs counts for every exam
    if not exam_filter:
        c2.caption("Current affairs: relevant for every exam")
    t1, t2 = st.columns(2)
    quick = t1.toggle("Quick view (key points only)", key=f"{ns}-quick")
    show_unverified = t2.toggle("Show unverified notes", key=f"{ns}-unv",
                                help="Notes whose quotes could not be matched to the article text.")

    stats = _stats(d)
    m1, m2, m3 = st.columns(3)
    m1.metric("Articles scanned", stats.get("articles", 0))
    m2.metric("Relevant", stats.get("relevant", 0))
    m3.metric("Notes", stats.get("extracted", 0))
    if stats.get("status") == "partial":
        st.warning("This issue is partially processed (API quota ran out). More notes will appear after the next run.")

    rows_all = [r for r in _brief(d) if r["category"] in (cats or group) and (tag == "all" or tag in r["exam_tags"])]
    hidden = [r for r in rows_all if r["validation_status"] == "needs_review"]
    rows = rows_all if show_unverified else [r for r in rows_all if r["validation_status"] != "needs_review"]
    if hidden and not show_unverified:
        st.caption(f"{len(hidden)} note(s) hidden: their quotes could not be verified against the article.")
    rows = group_duplicates(rows)
    if not rows:
        st.write("Nothing here for this date and filters yet.")
        return
    st.download_button("⬇️ Download as Markdown (for revision)", brief_markdown(rows, d),
                       file_name=f"nyayabrief_{ns}_{d}.md", key=f"{ns}-dl")

    st.subheader("⭐ Top picks")
    for r in rows[:5]:
        card(r, f"{ns}-top", quick)
    rest = rows[5:]
    if rest:
        st.subheader("All other notes, by category")
        for cat in group:
            in_cat = [r for r in rest if r["category"] == cat]
            if in_cat:
                st.markdown(f"**{ICON[cat]} {CATEGORIES[cat]} ({len(in_cat)})**")
                for r in in_cat:
                    card(r, f"{ns}-cat-{cat}", quick)


def search_tab() -> None:
    q = st.text_input("Search notes", placeholder="e.g. bail, Article 21, POCSO, Collegium, Section 144")
    c1, c2 = st.columns(2)
    cat = c1.selectbox("Category", [None, *CATEGORIES], format_func=lambda x: "all" if x is None else f"{ICON[x]} {CATEGORIES[x]}")
    tag = c2.selectbox("Exam ", [None, *EXAMS[1:]], format_func=lambda x: "all" if x is None else x)
    if not q:
        st.caption("Searches the notes from the last few days (keyword + meaning).")
        return
    hits = group_duplicates(search.hybrid_search(q, category=cat, tag=tag))
    if not hits:
        st.write("No results.")
        return
    if st.button("Answer with citations"):
        with st.spinner("Thinking..."):
            try:
                st.markdown(search.answer(q, hits))
            except Exception as e:  # quota/outage: search results below still work
                st.warning(f"Answer unavailable right now ({type(e).__name__}). Results are below.")
    for r in hits:
        card(r, "search")


def admin_tab() -> None:
    if st.text_input("Admin password", type="password") != cfg.admin_password:
        st.info("Enter admin password to upload a newspaper.")
        return
    up = st.file_uploader("The Hindu PDF", type="pdf")
    if up:
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
    st.subheader("Viewer feedback")
    fb = db.feedback_summary()
    if fb:
        st.dataframe(fb, use_container_width=True)
        st.caption("Notes with 👎 are your best material for fixing prompts and growing the eval set.")
    else:
        st.caption("No feedback yet.")


st.title("⚖️ NyayaBrief AI")
st.caption("Exam-relevant news from Newpapers like (TH,IEX,HT,TOI): law for Judiciary / APO, plus current affairs for UPSC / APO / BPSC. AI-generated notes: verify with the original before relying on them.")
tabs = ["🌍 Current Affairs", "⚖️ Legal Brief", "🔎 Search"] + (["⬆️ Upload (admin)"] if cfg.admin_password else [])
pages = [lambda: brief_tab(CURRENT, "ca", exam_filter=False), lambda: brief_tab(LEGAL, "legal"), search_tab, admin_tab]
for t, fn in zip(st.tabs(tabs), pages):
    with t:
        fn()
