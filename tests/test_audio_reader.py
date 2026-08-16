import unittest

from audio_reader import build_audio_reader_html, digest_to_speech_text


class TestAudioReader(unittest.TestCase):
    def test_digest_to_speech_text_removes_common_markdown(self):
        text = digest_to_speech_text(
            """# Weekly Digest

- **Paper:** [Wake flow](https://example.com)
1. Uses `delta` scaling.

```json
{"skip": true}
```
"""
        )

        self.assertIn("Weekly Digest", text)
        self.assertIn("Paper: Wake flow", text)
        self.assertIn("Uses delta scaling.", text)
        self.assertNotIn("https://example.com", text)
        self.assertNotIn("skip", text)

    def test_build_audio_reader_html_embeds_text_as_json(self):
        html = build_audio_reader_html('Read "quoted" text.')

        self.assertIn("SpeechSynthesisUtterance", html)
        self.assertIn('Read \\"quoted\\" text.', html)


if __name__ == "__main__":
    unittest.main()
