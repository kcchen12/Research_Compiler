import unittest

from relevance import rank_papers


class TestRelevance(unittest.TestCase):
    def test_rank_orders_by_keyword_matches(self):
        papers = [
            {"title": "Wake flow around cylinder", "abstract": "vortex shedding affects drag"},
            {"title": "Unrelated topic", "abstract": "misc"},
        ]

        ranked = rank_papers(papers, "vortex shedding, drag, wake flow")
        self.assertGreaterEqual(ranked[0]["relevance_score"], ranked[1]["relevance_score"])


if __name__ == "__main__":
    unittest.main()
