import unittest

from summarizer import (
    _parse_summary_json,
    _retry_delay_seconds,
    _summarization_error_message,
)


class TestSummarizer(unittest.TestCase):
    def test_parse_summary_json_accepts_fenced_json(self):
        parsed = _parse_summary_json(
            """```json
{"tldr": "Two sentences.", "key_findings": []}
```"""
        )

        self.assertEqual(parsed["tldr"], "Two sentences.")

    def test_summarization_error_message_compacts_gemini_rate_limit(self):
        message = _summarization_error_message(
            Exception("GenerateRequestsPerMinutePerProjectPerModel-FreeTier")
        )

        self.assertIn("5 requests per minute", message)

    def test_retry_delay_seconds_reads_gemini_retry_delay(self):
        delay = _retry_delay_seconds(Exception("retry_delay { seconds: 5 }"))

        self.assertEqual(delay, 6.0)


if __name__ == "__main__":
    unittest.main()
