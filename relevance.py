from __future__ import annotations

import re
from typing import Any

SEMANTIC_ALIASES = {
    "vortex shedding": [
        "karman vortex street",
        "periodic vortex formation",
        "vortex street",
        "wake oscillation",
        "wake oscillations",
    ],
    "oscillating cylinder": [
        "cylinder oscillation",
        "cylinder vibration",
        "forced oscillation",
        "vibrating cylinder",
    ],
    "wake flow": [
        "bluff-body wake",
        "near wake",
        "wake dynamics",
        "wake structure",
    ],
    "drag": [
        "aerodynamic resistance",
        "drag coefficient",
        "drag force",
        "hydrodynamic resistance",
    ],
    "lift": [
        "lift coefficient",
        "lift force",
        "transverse force",
    ],
    "cfd": [
        "computational fluid dynamics",
        "flow simulation",
        "numerical simulation",
        "numerical simulations",
    ],
    "fluid-structure interaction": [
        "coupled flow structure",
        "flow-induced vibration",
        "fsi",
    ],
}


def parse_keywords(interests: str) -> list[str]:
    return [kw.strip().lower() for kw in interests.split(",") if kw.strip()]


def _count_occurrences(text: str, term: str) -> int:
    return len(re.findall(re.escape(term), text))


def _semantic_aliases(keyword: str) -> list[str]:
    return SEMANTIC_ALIASES.get(keyword, [])


def _exact_relevance_score(paper: dict[str, Any], keywords: list[str]) -> float:
    title = (paper.get("title") or "").lower()
    abstract = (paper.get("abstract") or "").lower()

    score = 0.0
    for keyword in keywords:
        score += _count_occurrences(title, keyword) * 2.0
        score += _count_occurrences(abstract, keyword) * 1.0

    norm = max(len(keywords), 1)
    return round(score / norm, 3)


def _semantic_relevance_score(paper: dict[str, Any], keywords: list[str]) -> float:
    title = (paper.get("title") or "").lower()
    abstract = (paper.get("abstract") or "").lower()

    score = 0.0
    for keyword in keywords:
        title_matched = False
        abstract_matched = False
        for alias in _semantic_aliases(keyword):
            title_matched = title_matched or _count_occurrences(title, alias) > 0
            abstract_matched = abstract_matched or _count_occurrences(abstract, alias) > 0
        score += 1.0 if title_matched else 0.0
        score += 0.5 if abstract_matched else 0.0

    norm = max(len(keywords), 1)
    return round(score / norm, 3)


def relevance_breakdown(paper: dict[str, Any], keywords: list[str]) -> dict[str, float]:
    if not keywords:
        return {
            "exact_relevance_score": 0.0,
            "semantic_relevance_score": 0.0,
            "relevance_score": 0.0,
        }

    exact_score = _exact_relevance_score(paper, keywords)
    semantic_score = _semantic_relevance_score(paper, keywords)
    return {
        "exact_relevance_score": exact_score,
        "semantic_relevance_score": semantic_score,
        "relevance_score": round(exact_score + semantic_score, 3),
    }


def relevance_score(paper: dict[str, Any], keywords: list[str]) -> float:
    return relevance_breakdown(paper, keywords)["relevance_score"]


def rank_papers(papers: list[dict[str, Any]], interests: str) -> list[dict[str, Any]]:
    keywords = parse_keywords(interests)
    ranked: list[dict[str, Any]] = []
    for paper in papers:
        updated = dict(paper)
        updated.update(relevance_breakdown(updated, keywords))
        ranked.append(updated)
    return sorted(ranked, key=lambda p: p.get("relevance_score", 0.0), reverse=True)
