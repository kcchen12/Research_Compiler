from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import subprocess
import sys
import time

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit.runtime.scriptrunner import get_script_run_ctx

from audio_reader import build_audio_reader_html, digest_to_speech_text
from config import (
    DB_PATH,
    JOURNALS,
    enabled_gemini_models,
    ensure_data_dir,
    format_quota_updated_date,
    gemini_request_spacing_seconds,
    get_gemini_model_config,
    load_config,
    recommended_gemini_model,
)
from database import PaperDatabase
from digest import build_digest_markdown, markdown_to_html
from paper_fetcher import PaperFetcherError, fetch_papers, search_journals
from relevance import rank_papers
from summarizer import INSUFFICIENT_TEXT_SUMMARY, PaperSummarizer, SummarizationError


def _launch_with_streamlit_when_run_directly() -> None:
    if __name__ == "__main__" and get_script_run_ctx() is None:
        script_path = Path(__file__).resolve()
        raise SystemExit(
            subprocess.call(
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    str(script_path),
                    "--server.headless",
                    "true",
                    "--browser.gatherUsageStats",
                    "false",
                ]
            )
        )


_launch_with_streamlit_when_run_directly()

st.set_page_config(page_title="Research Paper Digest", layout="wide")
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding-top: 0.25rem;
    }
    [data-testid="stSidebarCollapseButton"] {
        margin-top: 0.25rem;
    }
    [data-testid="stSidebarCollapseButton"] button {
        height: 2rem;
        width: 2rem;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: 0.45rem;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:first-child {
        padding-top: 0;
    }
    [data-testid="stSidebar"] hr {
        margin: 0.55rem 0;
    }
    [data-testid="stSidebar"] h3 {
        padding-top: 0.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

ensure_data_dir()
config = load_config()
db = PaperDatabase(DB_PATH)
custom_journals = db.get_custom_journals()
available_journals = {**JOURNALS, **custom_journals}


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
if "digest_html" not in st.session_state:
    st.session_state.digest_html = ""
if "last_ai_request_at" not in st.session_state:
    st.session_state.last_ai_request_at = 0.0
if "gemini_token_window" not in st.session_state:
    st.session_state.gemini_token_window = []
if "journal_search_results" not in st.session_state:
    st.session_state.journal_search_results = []


def _prune_gemini_token_window(model_id: str) -> None:
    now = time.monotonic()
    st.session_state.gemini_token_window = [
        entry
        for entry in st.session_state.gemini_token_window
        if entry["model"] == model_id and now - entry["at"] < 60
    ]


def _gemini_tokens_in_window(model_id: str) -> int:
    _prune_gemini_token_window(model_id)
    return sum(entry["tokens"] for entry in st.session_state.gemini_token_window)


def _track_gemini_tokens(model_id: str, token_count: int) -> None:
    _prune_gemini_token_window(model_id)
    st.session_state.gemini_token_window.append(
        {"model": model_id, "tokens": token_count, "at": time.monotonic()}
    )


def _wait_for_gemini_request_slot(model_config, estimated_tokens: int) -> None:
    spacing = gemini_request_spacing_seconds(model_config)
    elapsed = time.monotonic() - st.session_state.last_ai_request_at
    if elapsed < spacing:
        time.sleep(spacing - elapsed)

    while _gemini_tokens_in_window(model_config.api_model_id) + estimated_tokens > model_config.tpm:
        oldest = min(st.session_state.gemini_token_window, key=lambda item: item["at"])
        wait_seconds = max(1.0, 60 - (time.monotonic() - oldest["at"]))
        time.sleep(wait_seconds)
        _prune_gemini_token_window(model_config.api_model_id)


def _paper_identity(paper: dict) -> tuple:
    return (
        (paper.get("doi") or "").strip().lower(),
        (paper.get("title") or "").strip().lower(),
        (paper.get("publication_date") or "").strip(),
        (paper.get("url") or "").strip().lower(),
    )


def _paper_choice_label(paper: dict) -> str:
    title = paper.get("title") or "Untitled"
    published = paper.get("publication_date") or "unknown date"
    score = paper.get("relevance_score", 0)
    return f"{score:.3f} | {published} | {title}"


st.title("Research Paper Digest")
st.caption("Monitor newly published papers and generate weekly/biweekly digests.")

with st.sidebar:
    st.subheader("AI Settings")
    provider_options = ["gemini"]
    configured_provider = (
        config.ai_provider if config.ai_provider in provider_options else "gemini"
    )
    ai_provider = st.selectbox(
        "Summary provider",
        provider_options,
        index=provider_options.index(configured_provider),
    )
    if ai_provider == "openai" and not config.openai_api_key:
        st.info("OPENAI_API_KEY is missing from .env.")
    elif ai_provider == "gemini" and not config.gemini_api_key:
        st.info("GEMINI_API_KEY is missing from .env.")

    if ai_provider == "gemini":
        gemini_models = enabled_gemini_models()
        recommended_model = recommended_gemini_model()
        configured_model = get_gemini_model_config(config.default_model)
        if not configured_model.enabled:
            configured_model = recommended_model
        model_labels = [model.ui_label for model in gemini_models]
        default_model_index = gemini_models.index(configured_model)
        label_col, details_col = st.columns([0.62, 0.38], vertical_alignment="center")
        label_col.markdown("**AI Model**")
        details_slot = details_col.empty()
        selected_model_label = st.selectbox(
            "AI Model",
            model_labels,
            index=default_model_index,
            key="ai_model_select",
            label_visibility="collapsed",
        )
        selected_gemini_model = gemini_models[model_labels.index(selected_model_label)]
        ai_model = selected_gemini_model.api_model_id
        with details_slot:
            with st.popover("Details", use_container_width=True):
                st.caption(
                    f"Recommended for Research Compiler: {recommended_model.display_name}"
                )
                st.write(
                    "**Free-tier limits:**  \n"
                    f"{selected_gemini_model.rpm} requests/minute  \n"
                    f"{selected_gemini_model.tpm:,} tokens/minute  \n"
                    f"{selected_gemini_model.rpd} requests/day"
                )
                if selected_gemini_model.notes:
                    st.caption(selected_gemini_model.notes)
                if selected_gemini_model.rpd <= 20:
                    st.warning(
                        "This model has a low daily free quota; large digests may exhaust it."
                    )
                st.caption(
                    "Free-tier quota information last updated: "
                    f"{format_quota_updated_date()}."
                )
    else:
        openai_default_model = (
            config.default_model
            if not config.default_model.startswith("gemini-")
            else "gpt-4o-mini"
        )
        ai_model = st.text_input("Model", value=openai_default_model)

    st.divider()
    st.subheader("Journals")
    with st.form("journal_search_form"):
        journal_query = st.text_input("Add journal by name")
        search_submitted = st.form_submit_button("Search Journals")
    if search_submitted:
        with st.spinner("Searching journals..."):
            try:
                st.session_state.journal_search_results = search_journals(journal_query)
            except Exception as exc:
                st.session_state.journal_search_results = []
                st.warning(f"Journal search failed: {exc}")

    if st.session_state.journal_search_results:
        result_labels = [
            f"{item['display_name']} ({', '.join(item.get('issns') or ['no ISSN'])})"
            for item in st.session_state.journal_search_results
        ]
        selected_result_label = st.selectbox("Search results", result_labels)
        selected_result = st.session_state.journal_search_results[
            result_labels.index(selected_result_label)
        ]
        if st.button("Add Selected Journal"):
            db.add_custom_journal(selected_result)
            st.session_state.journal_search_results = []
            st.success(f"Added {selected_result['display_name']}.")
            st.rerun()

    if custom_journals:
        removable = st.selectbox("Saved custom journals", list(custom_journals.keys()))
        if st.button("Remove Custom Journal"):
            db.delete_custom_journal(removable)
            st.success(f"Removed {removable}.")
            st.rerun()

    st.divider()
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

journal = st.selectbox("Journal", list(available_journals.keys()), index=0)

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

find_col, digest_col = st.columns(2)
find_clicked = find_col.button("Find New Papers", use_container_width=True)
generate_clicked = digest_col.button("Generate Digest", use_container_width=True)

if find_clicked:
    if end_date < start_date:
        st.error("End date must be on or after start date.")
    else:
        with st.spinner("Fetching papers..."):
            try:
                papers, warnings = fetch_papers(
                    journal,
                    start_date,
                    end_date,
                    journals=available_journals,
                )
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
        st.session_state.digest_html = ""

if st.session_state.ranked_papers:
    st.write(
        f"Found **{len(st.session_state.ranked_papers)}** papers: "
        f"**{len(st.session_state.new_papers)}** new, "
        f"**{len(st.session_state.seen_papers)}** previously seen"
    )

selected_digest_papers = st.session_state.new_papers
if st.session_state.new_papers:
    st.subheader("Digest Selection")
    digest_mode = st.radio(
        "Choose papers for this digest",
        ["Top scored papers", "Manual selection"],
        horizontal=True,
    )
    if digest_mode == "Top scored papers":
        digest_count = st.number_input(
            "Number of top-scored new papers to digest",
            min_value=1,
            max_value=len(st.session_state.new_papers),
            value=min(5, len(st.session_state.new_papers)),
            step=1,
        )
        selected_digest_papers = st.session_state.new_papers[: int(digest_count)]
    else:
        choice_map = {
            _paper_choice_label(paper): paper for paper in st.session_state.new_papers
        }
        selected_labels = st.multiselect(
            "New papers to include",
            list(choice_map.keys()),
            default=list(choice_map.keys())[: min(5, len(choice_map))],
        )
        selected_digest_papers = [choice_map[label] for label in selected_labels]

    st.caption(
        f"{len(selected_digest_papers)} of {len(st.session_state.new_papers)} "
        "new papers selected for digest generation."
    )

for paper in st.session_state.ranked_papers:
    badge = "SEEN" if db.is_seen(paper) else "NEW"
    with st.expander(
        f"[{badge}] {paper.get('title')} (score: {paper.get('relevance_score', 0):.3f})"
    ):
        st.write(f"**Journal:** {paper.get('journal')}")
        st.write(f"**Published:** {paper.get('publication_date')}")
        st.write(f"**DOI:** {paper.get('doi') or 'N/A'}")
        st.write(f"**URL:** {paper.get('url') or 'N/A'}")
        st.write(f"**Authors:** {', '.join(paper.get('authors') or []) or 'N/A'}")
        st.write(f"**Abstract:** {paper.get('abstract') or 'N/A'}")

if generate_clicked:
    all_new_papers = st.session_state.new_papers
    new_papers = selected_digest_papers
    if not new_papers:
        st.info("No new papers selected for digest generation.")
    else:
        summarizer = PaperSummarizer(
            db=db,
            provider=ai_provider,
            model=ai_model,
            openai_key=config.openai_api_key,
            gemini_key=config.gemini_api_key,
        )

        summarized = []
        summarized_keys = set()
        with st.spinner("Generating paper summaries..."):
            total = len(new_papers)
            progress = st.progress(0)
            status = st.empty()
            for index, paper in enumerate(new_papers, start=1):
                paper_with_summary = dict(paper)
                try:
                    if ai_provider == "gemini" and summarizer.requires_api_summary(
                        paper,
                        interests,
                    ):
                        gemini_model_config = get_gemini_model_config(ai_model)
                        daily_requests, _ = db.get_daily_api_usage("gemini", ai_model)
                        if daily_requests >= gemini_model_config.rpd:
                            st.error(
                                "Daily Gemini free-tier quota reached for "
                                f"{gemini_model_config.display_name} "
                                f"({gemini_model_config.rpd} requests/day). "
                                "No more new summary requests will be sent today."
                            )
                            break
                        estimated_tokens = summarizer.estimate_request_tokens(paper, interests)
                        if estimated_tokens > gemini_model_config.tpm:
                            st.warning(
                                f"Skipping '{paper.get('title')}' because the estimated "
                                "prompt size exceeds the selected model's tokens-per-minute limit."
                            )
                            paper_with_summary["summary"] = INSUFFICIENT_TEXT_SUMMARY
                            summarized.append(paper_with_summary)
                            progress.progress(index / total)
                            continue
                        status.caption(
                            "Generating summary "
                            f"{index}/{total} with {gemini_model_config.display_name} "
                            f"({daily_requests + 1}/{gemini_model_config.rpd} daily requests)."
                        )
                        _wait_for_gemini_request_slot(
                            gemini_model_config,
                            estimated_tokens,
                        )
                        db.record_api_request("gemini", ai_model, estimated_tokens)
                        _track_gemini_tokens(ai_model, estimated_tokens)
                        st.session_state.last_ai_request_at = time.monotonic()
                    else:
                        status.caption(f"Using cached or local summary {index}/{total}.")
                    paper_with_summary["summary"] = summarizer.summarize_paper(paper, interests)
                except SummarizationError as exc:
                    st.warning(f"Summary failed for '{paper.get('title')}': {exc}")
                    if "quota" in str(exc).lower() or "rate limit" in str(exc).lower():
                        st.info("Stopping new Gemini requests to avoid repeated quota failures.")
                        break
                    paper_with_summary["summary"] = INSUFFICIENT_TEXT_SUMMARY
                summarized.append(paper_with_summary)
                summarized_keys.add(_paper_identity(paper))
                progress.progress(index / total)

        if summarized:
            md = build_digest_markdown(summarized, st.session_state.date_range[0], st.session_state.date_range[1], interests)
            html = markdown_to_html(md)
            db.mark_digest_papers(summarized)

            st.session_state.digest_markdown = md
            st.session_state.digest_html = html
            st.session_state.new_papers = [
                paper for paper in all_new_papers if _paper_identity(paper) not in summarized_keys
            ]
            st.session_state.seen_papers = [
                paper for paper in st.session_state.ranked_papers if db.is_seen(paper)
            ]
            st.success("Digest generated. Summarized papers were added to digest history.")
            st.download_button("Download Markdown", md, file_name="research_digest.md", mime="text/markdown")
            st.download_button("Download HTML", html, file_name="research_digest.html", mime="text/html")
        else:
            st.info("No papers were summarized, so no digest was generated.")

if st.session_state.digest_markdown:
    st.markdown("---")
    st.subheader("Digest Preview")
    with st.expander("Audio Reader", expanded=True):
        components.html(
            build_audio_reader_html(
                digest_to_speech_text(st.session_state.digest_markdown)
            ),
            height=118,
        )
    st.download_button(
        "Download Markdown",
        st.session_state.digest_markdown,
        file_name="research_digest.md",
        mime="text/markdown",
        key="download_markdown_preview",
    )
    st.download_button(
        "Download HTML",
        st.session_state.digest_html,
        file_name="research_digest.html",
        mime="text/html",
        key="download_html_preview",
    )
    st.markdown(st.session_state.digest_markdown)
