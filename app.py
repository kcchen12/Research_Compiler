from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from config import DB_PATH, JOURNALS, ensure_data_dir, load_config
from database import PaperDatabase
from digest import build_digest_markdown, markdown_to_html
from paper_fetcher import PaperFetcherError, fetch_papers
from relevance import rank_papers
from summarizer import INSUFFICIENT_TEXT_SUMMARY, PaperSummarizer, SummarizationError


st.set_page_config(page_title="Research Paper Digest", layout="wide")

ensure_data_dir()
config = load_config()
db = PaperDatabase(DB_PATH)


if "new_papers" not in st.session_state:
    st.session_state.new_papers = []
if "seen_papers" not in st.session_state:
    st.session_state.seen_papers = []
if "ranked_papers" not in st.session_state:
    st.session_state.ranked_papers = []
if "date_range" not in st.session_state:
    st.session_state.date_range = (date.today() - timedelta(days=7), date.today())
if "digest_markdown" not in st.session_state:
    st.session_state.digest_markdown = ""


st.title("Research Paper Digest")
st.caption("Monitor newly published papers and generate weekly/biweekly digests.")

with st.sidebar:
    st.subheader("History")
    st.metric("Tracked in digest history", db.count_seen())

    if st.button("View History"):
        history = db.get_history(limit=500)
        if history:
            st.dataframe(pd.DataFrame(history), use_container_width=True)
        else:
            st.info("No digest history yet.")

    if st.button("Reset History"):
        db.reset_history()
        st.success("Digest history and cached summaries reset.")

journal = st.selectbox("Journal", list(JOURNALS.keys()), index=0)

preset = st.selectbox("Date Range", ["Past 7 days", "Past 14 days", "Past 30 days", "Custom"])
if preset == "Past 7 days":
    start_date, end_date = date.today() - timedelta(days=7), date.today()
elif preset == "Past 14 days":
    start_date, end_date = date.today() - timedelta(days=14), date.today()
elif preset == "Past 30 days":
    start_date, end_date = date.today() - timedelta(days=30), date.today()
else:
    custom = st.date_input(
        "Custom date range",
        value=(date.today() - timedelta(days=7), date.today()),
    )
    if isinstance(custom, tuple) and len(custom) == 2:
        start_date, end_date = custom
    else:
        start_date, end_date = date.today() - timedelta(days=7), date.today()

interests = st.text_area(
    "Research interests (comma separated)",
    value="vortex shedding, oscillating cylinder, wake flow, drag, lift, CFD",
)

if st.button("Find New Papers"):
    with st.spinner("Fetching papers..."):
        try:
            papers, warnings = fetch_papers(journal, start_date, end_date)
        except PaperFetcherError as exc:
            st.error(f"Failed to fetch papers: {exc}")
            papers, warnings = [], []

    for warning in warnings:
        st.warning(warning)

    ranked = rank_papers(papers, interests)
    new_papers, seen_papers = db.split_new_and_seen(ranked)

    st.session_state.new_papers = new_papers
    st.session_state.seen_papers = seen_papers
    st.session_state.ranked_papers = ranked
    st.session_state.date_range = (start_date, end_date)
    st.session_state.digest_markdown = ""

if st.session_state.ranked_papers:
    st.write(
        f"Found **{len(st.session_state.ranked_papers)}** papers: "
        f"**{len(st.session_state.new_papers)}** new, "
        f"**{len(st.session_state.seen_papers)}** previously seen"
    )

for paper in st.session_state.ranked_papers:
    badge = "NEW" if paper in st.session_state.new_papers else "SEEN"
    with st.expander(
        f"[{badge}] {paper.get('title')} (score: {paper.get('relevance_score', 0):.3f})"
    ):
        st.write(f"**Journal:** {paper.get('journal')}")
        st.write(f"**Published:** {paper.get('publication_date')}")
        st.write(f"**DOI:** {paper.get('doi') or 'N/A'}")
        st.write(f"**URL:** {paper.get('url') or 'N/A'}")
        st.write(f"**Authors:** {', '.join(paper.get('authors') or []) or 'N/A'}")
        st.write(f"**Abstract:** {paper.get('abstract') or 'N/A'}")

if st.button("Generate Digest"):
    new_papers = st.session_state.new_papers
    if not new_papers:
        st.info("No unseen papers available for digest generation.")
    else:
        summarizer = PaperSummarizer(
            db=db,
            provider=config.ai_provider,
            model=config.default_model,
            openai_key=config.openai_api_key,
            gemini_key=config.gemini_api_key,
        )

        summarized = []
        with st.spinner("Generating paper summaries..."):
            for paper in new_papers:
                paper_with_summary = dict(paper)
                try:
                    paper_with_summary["summary"] = summarizer.summarize_paper(paper, interests)
                except SummarizationError as exc:
                    st.warning(f"Summary failed for '{paper.get('title')}': {exc}")
                    paper_with_summary["summary"] = INSUFFICIENT_TEXT_SUMMARY
                summarized.append(paper_with_summary)

        md = build_digest_markdown(summarized, st.session_state.date_range[0], st.session_state.date_range[1], interests)
        html = markdown_to_html(md)
        db.mark_digest_papers(summarized)

        st.session_state.digest_markdown = md
        st.success("Digest generated. New papers were added to digest history.")
        st.download_button("Download Markdown", md, file_name="research_digest.md", mime="text/markdown")
        st.download_button("Download HTML", html, file_name="research_digest.html", mime="text/html")

if st.session_state.digest_markdown:
    st.markdown("---")
    st.subheader("Digest Preview")
    st.markdown(st.session_state.digest_markdown)
