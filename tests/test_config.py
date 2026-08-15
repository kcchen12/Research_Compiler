import unittest

from config import (
    GEMINI_MODELS,
    enabled_gemini_models,
    gemini_request_spacing_seconds,
    recommended_gemini_model,
)


class TestGeminiConfig(unittest.TestCase):
    def test_recommended_gemini_model_is_flash_lite(self):
        model = recommended_gemini_model()

        self.assertEqual(model.api_model_id, "gemini-3.5-flash-lite")
        self.assertTrue(model.recommended)

    def test_enabled_models_are_returned_for_dropdown(self):
        enabled_ids = {model.api_model_id for model in enabled_gemini_models()}

        self.assertIn("gemini-3.7-flash", enabled_ids)
        self.assertTrue(GEMINI_MODELS["gemini-3.7-flash"].enabled)

    def test_request_spacing_uses_configured_rpm(self):
        model = GEMINI_MODELS["gemini-3.5-flash-lite"]

        self.assertAlmostEqual(gemini_request_spacing_seconds(model), 4.4)


if __name__ == "__main__":
    unittest.main()
