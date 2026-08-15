from pathlib import Path
from datetime import date
import tempfile
import unittest

from database import PaperDatabase


class TestPaperDatabase(unittest.TestCase):
    def test_tracks_new_and_seen_for_doi_and_missing_doi(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = PaperDatabase(Path(tmp) / "papers.db")
            papers = [
                {
                    "title": "DOI paper",
                    "journal": "Journal of Fluid Mechanics",
                    "publication_date": "2026-08-01",
                    "doi": "10.1017/jfm.2026.1",
                    "url": "https://doi.org/10.1017/jfm.2026.1",
                },
                {
                    "title": "No DOI paper",
                    "journal": "Journal of Fluid Mechanics",
                    "publication_date": "2026-08-02",
                    "doi": None,
                    "url": "https://example.com/no-doi",
                },
            ]

            new_papers, seen_papers = db.split_new_and_seen(papers)
            self.assertEqual(len(new_papers), 2)
            self.assertEqual(len(seen_papers), 0)

            db.mark_digest_papers(new_papers)

            new_papers, seen_papers = db.split_new_and_seen(papers)
            self.assertEqual(len(new_papers), 0)
            self.assertEqual(len(seen_papers), 2)

    def test_records_daily_api_usage_by_provider_and_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = PaperDatabase(Path(tmp) / "papers.db")
            usage_date = date(2026, 8, 15)

            self.assertEqual(
                db.get_daily_api_usage("gemini", "gemini-3.5-flash-lite", usage_date),
                (0, 0),
            )

            db.record_api_request("gemini", "gemini-3.5-flash-lite", 123, usage_date)
            db.record_api_request("gemini", "gemini-3.5-flash-lite", 77, usage_date)

            self.assertEqual(
                db.get_daily_api_usage("gemini", "gemini-3.5-flash-lite", usage_date),
                (2, 200),
            )


if __name__ == "__main__":
    unittest.main()
