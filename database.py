from __future__ import annotations

from datetime import date, datetime, timezone
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

    @staticmethod
    def _close_connection(conn: sqlite3.Connection) -> None:
        conn.close()

    def _init_db(self) -> None:
        conn = self._connect()
        try:
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_usage (
                    usage_date TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    token_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (usage_date, provider, model)
                )
                """
            )
            conn.commit()
        finally:
            self._close_connection(conn)

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
        conn = self._connect()
        try:
            if doi:
                row = conn.execute("SELECT 1 FROM seen_papers WHERE doi = ?", (doi,)).fetchone()
                return row is not None
            key = self._paper_key(paper)
            row = conn.execute(
                "SELECT 1 FROM seen_papers_no_doi WHERE paper_key = ?", (key,)
            ).fetchone()
            return row is not None
        finally:
            self._close_connection(conn)

    def split_new_and_seen(self, papers: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        new_papers: list[dict[str, Any]] = []
        seen_papers: list[dict[str, Any]] = []
        for paper in papers:
            (seen_papers if self.is_seen(paper) else new_papers).append(paper)
        return new_papers, seen_papers

    def mark_digest_papers(self, papers: list[dict[str, Any]]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
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
            conn.commit()
        finally:
            self._close_connection(conn)

    def get_history(self, limit: int = 200) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
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
        finally:
            self._close_connection(conn)

        rows = [dict(row) for row in rows_with_doi + rows_no_doi]
        rows.sort(key=lambda item: item.get("first_seen_at", ""), reverse=True)
        return rows[:limit]

    def count_seen(self) -> int:
        conn = self._connect()
        try:
            with_doi = conn.execute("SELECT COUNT(*) FROM seen_papers").fetchone()[0]
            without_doi = conn.execute("SELECT COUNT(*) FROM seen_papers_no_doi").fetchone()[0]
            return with_doi + without_doi
        finally:
            self._close_connection(conn)

    def reset_history(self) -> None:
        conn = self._connect()
        try:
            conn.execute("DELETE FROM seen_papers")
            conn.execute("DELETE FROM seen_papers_no_doi")
            conn.execute("DELETE FROM summary_cache")
            conn.commit()
        finally:
            self._close_connection(conn)

    def get_daily_api_usage(
        self,
        provider: str,
        model: str,
        usage_date: date | None = None,
    ) -> tuple[int, int]:
        usage_date = usage_date or date.today()
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT request_count, token_count
                FROM api_usage
                WHERE usage_date = ? AND provider = ? AND model = ?
                """,
                (usage_date.isoformat(), provider, model),
            ).fetchone()
            if not row:
                return 0, 0
            return int(row["request_count"]), int(row["token_count"])
        finally:
            self._close_connection(conn)

    def record_api_request(
        self,
        provider: str,
        model: str,
        token_count: int,
        usage_date: date | None = None,
    ) -> None:
        usage_date = usage_date or date.today()
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO api_usage
                (usage_date, provider, model, request_count, token_count)
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(usage_date, provider, model) DO UPDATE SET
                    request_count = request_count + 1,
                    token_count = token_count + excluded.token_count
                """,
                (usage_date.isoformat(), provider, model, token_count),
            )
            conn.commit()
        finally:
            self._close_connection(conn)

    def get_cached_summary(self, cache_key: str, provider: str) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT summary_json FROM summary_cache WHERE cache_key = ? AND provider = ?",
                (cache_key, provider),
            ).fetchone()
            return row[0] if row else None
        finally:
            self._close_connection(conn)

    def cache_summary(self, cache_key: str, provider: str, summary_json: str) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO summary_cache (cache_key, provider, summary_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (cache_key, provider, summary_json, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        finally:
            self._close_connection(conn)
