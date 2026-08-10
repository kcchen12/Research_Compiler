import unittest

from summarizer import _parse_summary_json


class TestSummarizer(unittest.TestCase):
    def test_parse_summary_json_accepts_fenced_json(self):
        parsed = _parse_summary_json(
            """```json
{"tldr": "Two sentences.", "key_findings": []}
```"""
        )

        self.assertEqual(parsed["tldr"], "Two sentences.")


if __name__ == "__main__":
    unittest.main()
