from datetime import date
import unittest
from unittest.mock import Mock, patch

from paper_fetcher import (
    PaperFetcherError,
    fetch_openalex_papers,
    fetch_papers,
)


class TestPaperFetcher(unittest.TestCase):
    def test_openalex_uses_configured_journal_id_and_paginates(self):
        first = Mock()
        first.raise_for_status.return_value = None
        first.json.return_value = {
            "meta": {"next_cursor": "next"},
            "results": [
                {
                    "title": "First paper",
                    "publication_date": "2026-08-10",
                    "doi": "https://doi.org/10.1017/jfm.2026.1",
                    "abstract_inverted_index": {"flow": [0], "wake": [1]},
                    "authorships": [],
                    "primary_location": {
                        "source": {"display_name": "Journal of Fluid Mechanics"},
                        "landing_page_url": "https://example.com/first",
                    },
                    "ids": {},
                }
            ],
        }
        second = Mock()
        second.raise_for_status.return_value = None
        second.json.return_value = {"meta": {"next_cursor": None}, "results": []}

        with patch("paper_fetcher.requests.get", side_effect=[first, second]) as get:
            papers = fetch_openalex_papers(
                "Journal of Fluid Mechanics",
                date(2026, 8, 1),
                date(2026, 8, 10),
            )

        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["doi"], "10.1017/jfm.2026.1")
        self.assertEqual(papers[0]["abstract"], "flow wake")
        first_params = get.call_args_list[0].kwargs["params"]
        self.assertIn("journal:S152000018", first_params["filter"])
        self.assertEqual(first_params["per-page"], 100)

    @patch("paper_fetcher.fetch_crossref_papers")
    @patch("paper_fetcher.fetch_openalex_papers")
    def test_fetch_papers_dedupes_and_filters_dates(self, openalex, crossref):
        openalex.return_value = [
            {
                "title": "Inside range",
                "publication_date": "2026-08-05",
                "doi": "10.1017/jfm.2026.2",
                "abstract": None,
                "url": "https://example.com/openalex",
                "source": "openalex",
            },
            {
                "title": "Outside range",
                "publication_date": "2026-07-01",
                "doi": "10.1017/jfm.2026.3",
                "abstract": "too old",
                "url": "https://example.com/old",
                "source": "openalex",
            },
        ]
        crossref.return_value = [
            {
                "title": "Inside range",
                "publication_date": "2026-08-05",
                "doi": "10.1017/jfm.2026.2",
                "abstract": "crossref abstract",
                "url": "https://example.com/crossref",
                "source": "crossref",
            }
        ]

        papers, warnings = fetch_papers(
            "Journal of Fluid Mechanics",
            date(2026, 8, 1),
            date(2026, 8, 10),
        )

        self.assertEqual(warnings, [])
        self.assertEqual(len(papers), 1)
        self.assertEqual(papers[0]["abstract"], "crossref abstract")

    def test_fetch_papers_rejects_invalid_date_range(self):
        with self.assertRaises(PaperFetcherError):
            fetch_papers(
                "Journal of Fluid Mechanics",
                date(2026, 8, 10),
                date(2026, 8, 1),
            )


if __name__ == "__main__":
    unittest.main()
