from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
