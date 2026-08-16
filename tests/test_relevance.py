import unittest

from relevance import rank_papers, relevance_breakdown


class TestRelevance(unittest.TestCase):
    def test_rank_orders_by_keyword_matches(self):
        papers = [
            {"title": "Wake flow around cylinder", "abstract": "vortex shedding affects drag"},
            {"title": "Unrelated topic", "abstract": "misc"},
        ]

        ranked = rank_papers(papers, "vortex shedding, drag, wake flow")
        self.assertGreaterEqual(ranked[0]["relevance_score"], ranked[1]["relevance_score"])

    def test_relevance_breakdown_combines_exact_and_semantic_scores(self):
        paper = {
            "title": "Karman vortex street behind a bluff body",
            "abstract": "The wake dynamics increase drag on the cylinder.",
        }

        breakdown = relevance_breakdown(paper, ["vortex shedding", "wake flow", "drag"])

        self.assertEqual(breakdown["exact_relevance_score"], 0.333)
        self.assertEqual(breakdown["semantic_relevance_score"], 0.5)
        self.assertEqual(breakdown["relevance_score"], 0.833)

    def test_rank_includes_score_breakdown_fields(self):
        ranked = rank_papers(
            [{"title": "Wake oscillations", "abstract": ""}],
            "vortex shedding",
        )

        self.assertIn("exact_relevance_score", ranked[0])
        self.assertIn("semantic_relevance_score", ranked[0])
        self.assertEqual(ranked[0]["semantic_relevance_score"], 1.0)


if __name__ == "__main__":
    unittest.main()
