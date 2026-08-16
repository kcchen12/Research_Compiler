from __future__ import annotations

from datetime import date
from html import unescape
import re
import time
from typing import Any

import requests

from config import JOURNALS

OPENALEX_URL = "https://api.openalex.org/works"
OPENALEX_SOURCES_URL = "https://api.openalex.org/sources"
CROSSREF_URL = "https://api.crossref.org/works"


class PaperFetcherError(Exception):
    pass


def _retry_delay(response: requests.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            pass
    return float(attempt)


def _get_json(
    url: str,
    params: dict[str, Any],
    service_name: str,
    max_attempts: int = 3,
) -> dict[str, Any]:
    for attempt in range(1, max_attempts + 1):
        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 429:
            response.raise_for_status()
            return response.json()

        if attempt < max_attempts:
            time.sleep(_retry_delay(response, attempt))
            continue

        raise requests.HTTPError(
            f"{service_name} rate limit reached after {max_attempts} attempts. "
            "Please wait a minute and try again.",
            response=response,
        )

    raise PaperFetcherError(f"{service_name} returned no response.")


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
    normalized = doi.strip().lower()
    normalized = re.sub(r"^https?://(dx\.)?doi\.org/", "", normalized)
    return normalized or None


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _within_date_range(paper: dict[str, Any], start_date: date, end_date: date) -> bool:
    published = _parse_date(paper.get("publication_date"))
    if published is None:
        return False
    return start_date <= published <= end_date


def _journal_config(journal_name: str, journals: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    return (journals or JOURNALS).get(journal_name, {})


def _openalex_source_id(source_id: str | None) -> str | None:
    if not source_id:
        return None
    return source_id.rstrip("/").split("/")[-1]


def search_journals(query: str, limit: int = 10) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        return []

    payload = _get_json(
        OPENALEX_SOURCES_URL,
        params={"search": query, "filter": "type:journal", "per-page": limit},
        service_name="OpenAlex",
    )
    results = payload.get("results", [])
    matches: list[dict[str, Any]] = []
    for item in results:
        display_name = item.get("display_name")
        source_id = _openalex_source_id(item.get("id"))
        if not display_name or not source_id:
            continue
        issns = item.get("issn") or []
        issn_l = item.get("issn_l")
        if issn_l and issn_l not in issns:
            issns.insert(0, issn_l)
        matches.append(
            {
                "display_name": display_name,
                "openalex_name": display_name,
                "openalex_source_id": source_id,
                "crossref_container": display_name,
                "issns": issns,
            }
        )
    return matches


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
        "doi": _normalize_doi(item.get("doi")),
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
            if deduped[key].get("source") != "openalex" and paper.get("source") == "openalex":
                deduped[key]["source"] = "openalex"
            continue
        deduped[key] = paper
    return sorted(
        deduped.values(),
        key=lambda p: p.get("publication_date") or "",
        reverse=True,
    )


def fetch_openalex_papers(
    journal_name: str,
    start_date: date,
    end_date: date,
    journals: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    journal_config = _journal_config(journal_name, journals)
    source_id = journal_config.get("openalex_source_id")
    if not source_id:
        return []

    filters = [
        f"journal:{source_id}",
        f"from_publication_date:{_iso(start_date)}",
        f"to_publication_date:{_iso(end_date)}",
    ]
    papers: list[dict[str, Any]] = []
    cursor: str | None = "*"
    seen_cursors: set[str] = set()

    while cursor:
        if cursor in seen_cursors:
            break
        seen_cursors.add(cursor)

        params = {
            "filter": ",".join(filters),
            "per-page": 100,
            "sort": "publication_date:desc",
            "cursor": cursor,
        }
        payload = _get_json(OPENALEX_URL, params=params, service_name="OpenAlex")
        results = payload.get("results", [])
        papers.extend(_extract_openalex_paper(item) for item in results)

        next_cursor = payload.get("meta", {}).get("next_cursor")
        cursor = next_cursor if results and next_cursor else None

    return papers


def fetch_crossref_papers(
    journal_name: str,
    start_date: date,
    end_date: date,
    journals: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    journal_config = _journal_config(journal_name, journals)
    container_title = journal_config.get("crossref_container") or journal_name
    params = {
        "filter": f"from-pub-date:{_iso(start_date)},until-pub-date:{_iso(end_date)},type:journal-article",
        "query.container-title": container_title,
        "rows": 200,
        "sort": "published",
        "order": "desc",
    }
    items = _get_json(CROSSREF_URL, params=params, service_name="Crossref").get(
        "message",
        {},
    ).get("items", [])
    papers = [_extract_crossref_paper(item) for item in items]
    journal_lower = container_title.lower()
    return [paper for paper in papers if journal_lower in paper.get("journal", "").lower()]


def fetch_papers(
    journal_name: str,
    start_date: date,
    end_date: date,
    journals: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if end_date < start_date:
        raise PaperFetcherError("End date must be on or after start date.")

    papers: list[dict[str, Any]] = []
    errors: list[str] = []
    for fetcher in (fetch_openalex_papers, fetch_crossref_papers):
        try:
            papers.extend(fetcher(journal_name, start_date, end_date, journals))
        except requests.RequestException as exc:
            errors.append(f"{fetcher.__name__} failed: {exc}")

    if not papers and errors:
        raise PaperFetcherError("; ".join(errors))

    filtered = [paper for paper in papers if _within_date_range(paper, start_date, end_date)]
    return _dedupe_papers(filtered), errors
