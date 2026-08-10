from __future__ import annotations

from datetime import date
from typing import Any

import markdown


def build_digest_markdown(
    papers: list[dict[str, Any]],
    start_date: date,
    end_date: date,
    interests: str,
) -> str:
    top_papers = papers[:5]

    lines = [
        "# Research Paper Digest",
        "",
        f"**Date Range:** {start_date.isoformat()} to {end_date.isoformat()}",
        f"**New Papers:** {len(papers)}",
        f"**Research Interests:** {interests or 'Not specified'}",
        "",
        "## Overall Themes / Trends",
    ]

    if papers:
        lines.append(
            "- Current set emphasizes fluid dynamics topics with highest-scoring papers listed below."
        )
    else:
        lines.append("- No new papers found in this period.")

    lines.extend(["", "## Most Relevant Papers"])
    if top_papers:
        for paper in top_papers:
            lines.append(
                f"- **{paper.get('title')}** (score: {paper.get('relevance_score', 0):.3f})"
            )
    else:
        lines.append("- No relevant papers to rank.")

    lines.extend(["", "## Individual Summaries"])
    if not papers:
        lines.append("No new papers to summarize.")

    for idx, paper in enumerate(papers, start=1):
        summary = paper.get("summary", {})
        doi = paper.get("doi") or "N/A"
        lines.extend(
            [
                "",
                f"### {idx}. {paper.get('title')}",
                f"- **Journal:** {paper.get('journal')}",
                f"- **Publication Date:** {paper.get('publication_date')}",
                f"- **DOI:** {doi}",
                f"- **Link:** {paper.get('url') or 'N/A'}",
                f"- **Relevance Score:** {paper.get('relevance_score', 0):.3f}",
                f"- **TL;DR:** {summary.get('tldr', 'N/A')}",
                "- **Key Findings:**",
            ]
        )

        key_findings = summary.get("key_findings") or ["N/A"]
        for finding in key_findings:
            lines.append(f"  - {finding}")

        lines.extend(
            [
                f"- **Methods:** {summary.get('methods', 'N/A')}",
                f"- **Important Results:** {summary.get('important_results', 'N/A')}",
                f"- **Limitations:** {summary.get('limitations', 'N/A')}",
                f"- **Why It Matters:** {summary.get('why_it_matters', 'N/A')}",
                f"- **Relevance to Interests:** {summary.get('interest_relevance', 'N/A')}",
            ]
        )

    return "\n".join(lines)


def markdown_to_html(md_text: str) -> str:
    return markdown.markdown(md_text, extensions=["extra"])
