from __future__ import annotations

from datetime import date
from html import unescape
import re
from typing import Any

import requests

OPENALEX_URL = "https://api.openalex.org/works"
CROSSREF_URL = "https://api.crossref.org/works"


class PaperFetcherError(Exception):
    pass


def _iso(d: date) -> str:
    return d.isoformat()


def _parse_openalex_abstract(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    pos_word = [(pos, word) for word, positions in index.items() for pos in positions]
    if not pos_word:
        return None
    return " ".join(word for _, word in sorted(pos_word, key=lambda item: item[0]))


def _clean_html(text: str | None) -> str | None:
    if not text:
        return None
    no_tags = re.sub(r"<[^>]+>", " ", text)
    compact = re.sub(r"\s+", " ", unescape(no_tags)).strip()
    return compact or None


def _normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi.strip().lower() or None


def _extract_openalex_paper(item: dict[str, Any]) -> dict[str, Any]:
    authors = [
        author.get("author", {}).get("display_name", "")
        for author in item.get("authorships", [])
        if author.get("author", {}).get("display_name")
    ]
    source = item.get("primary_location", {}).get("source", {})
    return {
        "title": item.get("title") or "Untitled",
        "authors": authors,
        "journal": source.get("display_name") or "Unknown Journal",
        "publication_date": item.get("publication_date"),
        "doi": _normalize_doi(item.get("doi", "").replace("https://doi.org/", "")),
        "abstract": _parse_openalex_abstract(item.get("abstract_inverted_index")),
        "url": item.get("primary_location", {}).get("landing_page_url")
        or item.get("ids", {}).get("doi")
        or item.get("id"),
        "source": "openalex",
    }


def _extract_crossref_paper(item: dict[str, Any]) -> dict[str, Any]:
    authors = []
    for author in item.get("author", []):
        given = author.get("given", "")
        family = author.get("family", "")
        full = f"{given} {family}".strip()
        if full:
            authors.append(full)

    date_parts = (
        item.get("published-print", {}).get("date-parts")
        or item.get("published-online", {}).get("date-parts")
        or item.get("created", {}).get("date-parts")
    )
    publication_date = None
    if date_parts and date_parts[0]:
        ymd = date_parts[0]
        while len(ymd) < 3:
            ymd.append(1)
        publication_date = f"{ymd[0]:04d}-{ymd[1]:02d}-{ymd[2]:02d}"

    doi = _normalize_doi(item.get("DOI"))
    return {
        "title": (item.get("title") or ["Untitled"])[0],
        "authors": authors,
        "journal": (item.get("container-title") or ["Unknown Journal"])[0],
        "publication_date": publication_date,
        "doi": doi,
        "abstract": _clean_html(item.get("abstract")),
        "url": f"https://doi.org/{doi}" if doi else item.get("URL"),
        "source": "crossref",
    }


def _dedupe_papers(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for paper in papers:
        key = (
            paper.get("doi")
            or f"{paper.get('title', '').strip().lower()}|{paper.get('publication_date')}"
        )
        if key in deduped:
            if not deduped[key].get("abstract") and paper.get("abstract"):
                deduped[key]["abstract"] = paper["abstract"]
            continue
        deduped[key] = paper
    return sorted(
        deduped.values(),
        key=lambda p: p.get("publication_date") or "",
        reverse=True,
    )


def fetch_openalex_papers(journal_name: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    params = {
        "filter": f"primary_location.source.display_name.search:{journal_name},from_publication_date:{_iso(start_date)},to_publication_date:{_iso(end_date)}",
        "per-page": 200,
        "sort": "publication_date:desc",
    }
    response = requests.get(OPENALEX_URL, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    return [_extract_openalex_paper(item) for item in payload.get("results", [])]


def fetch_crossref_papers(journal_name: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    params = {
        "filter": f"from-pub-date:{_iso(start_date)},until-pub-date:{_iso(end_date)},type:journal-article",
        "query.container-title": journal_name,
        "rows": 200,
        "sort": "published",
        "order": "desc",
    }
    response = requests.get(CROSSREF_URL, params=params, timeout=30)
    response.raise_for_status()
    items = response.json().get("message", {}).get("items", [])
    papers = [_extract_crossref_paper(item) for item in items]
    journal_lower = journal_name.lower()
    return [paper for paper in papers if journal_lower in paper.get("journal", "").lower()]


def fetch_papers(journal_name: str, start_date: date, end_date: date) -> tuple[list[dict[str, Any]], list[str]]:
    papers: list[dict[str, Any]] = []
    errors: list[str] = []
    for fetcher in (fetch_openalex_papers, fetch_crossref_papers):
        try:
            papers.extend(fetcher(journal_name, start_date, end_date))
        except requests.RequestException as exc:
            errors.append(f"{fetcher.__name__} failed: {exc}")

    if not papers and errors:
        raise PaperFetcherError("; ".join(errors))

    return _dedupe_papers(papers), errors
