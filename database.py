from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import sqlite3
from pathlib import Path
from typing import Any


class PaperDatabase:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_papers (
                    doi TEXT PRIMARY KEY,
                    title TEXT,
                    journal TEXT,
                    publication_date TEXT,
                    url TEXT,
                    first_seen_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_papers_no_doi (
                    paper_key TEXT PRIMARY KEY,
                    title TEXT,
                    journal TEXT,
                    publication_date TEXT,
                    url TEXT,
                    first_seen_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS summary_cache (
                    cache_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _normalize_doi(doi: str | None) -> str | None:
        if not doi:
            return None
        return doi.strip().lower() or None

    @staticmethod
    def _paper_key(paper: dict[str, Any]) -> str:
        payload = "|".join(
            [
                (paper.get("title") or "").strip().lower(),
                (paper.get("publication_date") or "").strip(),
                (paper.get("url") or "").strip().lower(),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def is_seen(self, paper: dict[str, Any]) -> bool:
        doi = self._normalize_doi(paper.get("doi"))
        with self._connect() as conn:
            if doi:
                row = conn.execute("SELECT 1 FROM seen_papers WHERE doi = ?", (doi,)).fetchone()
                return row is not None
            key = self._paper_key(paper)
            row = conn.execute(
                "SELECT 1 FROM seen_papers_no_doi WHERE paper_key = ?", (key,)
            ).fetchone()
            return row is not None

    def split_new_and_seen(self, papers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        new_papers: list[dict[str, Any]] = []
        seen_papers: list[dict[str, Any]] = []
        for paper in papers:
            (seen_papers if self.is_seen(paper) else new_papers).append(paper)
        return new_papers, seen_papers

    def mark_digest_papers(self, papers: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            for paper in papers:
                doi = self._normalize_doi(paper.get("doi"))
                if doi:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO seen_papers
                        (doi, title, journal, publication_date, url, first_seen_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            doi,
                            paper.get("title"),
                            paper.get("journal"),
                            paper.get("publication_date"),
                            paper.get("url"),
                            now,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO seen_papers_no_doi
                        (paper_key, title, journal, publication_date, url, first_seen_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            self._paper_key(paper),
                            paper.get("title"),
                            paper.get("journal"),
                            paper.get("publication_date"),
                            paper.get("url"),
                            now,
                        ),
                    )

    def get_history(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows_with_doi = conn.execute(
                """
                SELECT doi, title, journal, publication_date, url, first_seen_at
                FROM seen_papers
                """
            ).fetchall()
            rows_no_doi = conn.execute(
                """
                SELECT NULL AS doi, title, journal, publication_date, url, first_seen_at
                FROM seen_papers_no_doi
                """
            ).fetchall()

        rows = [dict(row) for row in rows_with_doi + rows_no_doi]
        rows.sort(key=lambda item: item.get("first_seen_at", ""), reverse=True)
        return rows[:limit]

    def count_seen(self) -> int:
        with self._connect() as conn:
            with_doi = conn.execute("SELECT COUNT(*) FROM seen_papers").fetchone()[0]
            without_doi = conn.execute("SELECT COUNT(*) FROM seen_papers_no_doi").fetchone()[0]
        return with_doi + without_doi

    def reset_history(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM seen_papers")
            conn.execute("DELETE FROM seen_papers_no_doi")
            conn.execute("DELETE FROM summary_cache")

    def get_cached_summary(self, cache_key: str, provider: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT summary_json FROM summary_cache WHERE cache_key = ? AND provider = ?",
                (cache_key, provider),
            ).fetchone()
        return row[0] if row else None

    def cache_summary(self, cache_key: str, provider: str, summary_json: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO summary_cache (cache_key, provider, summary_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (cache_key, provider, summary_json, datetime.now(timezone.utc).isoformat()),
            )
