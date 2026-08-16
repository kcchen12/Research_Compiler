from __future__ import annotations

import re
from typing import Any


def parse_keywords(interests: str) -> list[str]:
    return [kw.strip().lower() for kw in interests.split(",") if kw.strip()]


def _count_occurrences(text: str, term: str) -> int:
    return len(re.findall(re.escape(term), text))


def relevance_score(paper: dict[str, Any], keywords: list[str]) -> float:
    if not keywords:
        return 0.0

    title = (paper.get("title") or "").lower()
    abstract = (paper.get("abstract") or "").lower()

    score = 0.0
    for keyword in keywords:
        score += _count_occurrences(title, keyword) * 2.0
        score += _count_occurrences(abstract, keyword) * 1.0

    norm = max(len(keywords), 1)
    return round(score / norm, 3)


def rank_papers(papers: list[dict[str, Any]], interests: str) -> list[dict[str, Any]]:
    keywords = parse_keywords(interests)
    ranked: list[dict[str, Any]] = []
    for paper in papers:
        updated = dict(paper)
        updated["relevance_score"] = relevance_score(updated, keywords)
        ranked.append(updated)
    return sorted(ranked, key=lambda p: p.get("relevance_score", 0.0), reverse=True)
