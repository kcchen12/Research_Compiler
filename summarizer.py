from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

import google.generativeai as genai
from openai import OpenAI, OpenAIError

from database import PaperDatabase


INSUFFICIENT_TEXT_SUMMARY = {
    "tldr": "Insufficient information for reliable summary.",
    "key_findings": ["Insufficient information for reliable summary."],
    "methods": "Insufficient information for reliable summary.",
    "important_results": "Insufficient information for reliable summary.",
    "limitations": "Insufficient information for reliable summary.",
    "why_it_matters": "Insufficient information for reliable summary.",
    "interest_relevance": "Insufficient information for reliable summary.",
}


class SummarizationError(Exception):
    pass


def _is_gemini_quota_error(exc: Exception) -> bool:
    text = str(exc).lower()
    quota_markers = [
        "429",
        "resource_exhausted",
        "quota",
        "rate limit",
        "ratelimit",
        "generaterequestsperminuteperprojectpermodel-freetier",
    ]
    return any(marker in text for marker in quota_markers)


def _summarization_error_message(exc: Exception) -> str:
    text = str(exc)
    if _is_gemini_quota_error(exc):
        return (
            "Gemini quota or rate limit reached for the selected model. "
            "Wait for quota to reset, choose a higher-quota model, or generate "
            "a smaller digest."
        )
    if "exceeded your current quota" in text.lower():
        return "Provider quota exceeded. Check the provider billing/quota page or try again later."
    return text


def _retry_delay_seconds(exc: Exception) -> float | None:
    match = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)", str(exc))
    if match:
        return float(match.group(1)) + 1.0
    if "GenerateRequestsPerMinutePerProjectPerModel-FreeTier" in str(exc):
        return 65.0
    return None


def _parse_summary_json(output_text: str) -> dict[str, Any]:
    cleaned = output_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    json_text = _extract_json_object(cleaned)
    parsed = _loads_summary_json(json_text)

    if not isinstance(parsed, dict):
        raise SummarizationError("Model output JSON must be an object.")
    return parsed


def _extract_json_object(text: str) -> str:
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return text[start : end + 1]


def _loads_summary_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        if "Invalid \\escape" not in exc.msg:
            raise
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", text)
        return json.loads(repaired)


class PaperSummarizer:
    def __init__(
        self,
        db: PaperDatabase,
        provider: str,
        model: str,
        openai_key: str | None = None,
        gemini_key: str | None = None,
    ):
        self.db = db
        self.provider = provider.lower()
        self.model = model
        self.openai_key = openai_key
        self.gemini_key = gemini_key

    def _cache_key(self, paper: dict[str, Any], interests: str) -> str:
        payload = "|".join(
            [
                self.provider,
                self.model,
                (paper.get("doi") or "").lower(),
                paper.get("title") or "",
                paper.get("abstract") or "",
                interests,
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get_cached_summary(self, paper: dict[str, Any], interests: str) -> dict[str, Any] | None:
        cache_key = self._cache_key(paper, interests)
        cached = self.db.get_cached_summary(cache_key, self.provider)
        if cached:
            return json.loads(cached)
        return None

    def requires_api_summary(self, paper: dict[str, Any], interests: str) -> bool:
        abstract = (paper.get("abstract") or "").strip()
        if len(abstract) < 80:
            return False
        return self.get_cached_summary(paper, interests) is None

    @staticmethod
    def estimate_token_count(text: str) -> int:
        return max(1, len(text) // 4)

    def estimate_request_tokens(self, paper: dict[str, Any], interests: str) -> int:
        return self.estimate_token_count(self._build_prompt(paper, interests))

    def summarize_paper(self, paper: dict[str, Any], interests: str) -> dict[str, Any]:
        abstract = (paper.get("abstract") or "").strip()
        if len(abstract) < 80:
            return INSUFFICIENT_TEXT_SUMMARY

        cache_key = self._cache_key(paper, interests)
        cached_summary = self.get_cached_summary(paper, interests)
        if cached_summary:
            return cached_summary

        summary = self._generate_summary(paper, interests)
        self.db.cache_summary(cache_key, self.provider, json.dumps(summary))
        return summary

    def _build_prompt(self, paper: dict[str, Any], interests: str) -> str:
        return (
            "You are summarizing an academic paper for a research digest. "
            "Use the title and abstract only. Output strict JSON with keys: "
            "tldr (2 sentences), key_findings (3-5 bullets as array), methods, "
            "important_results, limitations, why_it_matters, interest_relevance."
            f"\n\nUser interests: {interests or 'Not provided'}"
            f"\nTitle: {paper.get('title')}"
            f"\nAbstract: {paper.get('abstract')}"
        )

    def _generate_summary(self, paper: dict[str, Any], interests: str) -> dict[str, Any]:
        prompt = self._build_prompt(paper, interests)

        if self.provider == "openai":
            if not self.openai_key:
                raise SummarizationError("OPENAI_API_KEY is missing.")
            client = OpenAI(api_key=self.openai_key)
            try:
                response = client.responses.create(
                    model=self.model,
                    input=prompt,
                    temperature=0.2,
                )
            except OpenAIError as exc:
                raise SummarizationError(str(exc)) from exc
            output_text = response.output_text
        elif self.provider == "gemini":
            if not self.gemini_key:
                raise SummarizationError("GEMINI_API_KEY is missing.")
            genai.configure(api_key=self.gemini_key)
            model = genai.GenerativeModel(self.model)
            try:
                response = self._generate_gemini_content(model, prompt)
            except Exception as exc:
                raise SummarizationError(_summarization_error_message(exc)) from exc
            output_text = response.text
        else:
            raise SummarizationError(f"Unsupported AI provider: {self.provider}")

        try:
            parsed = _parse_summary_json(output_text)
        except (json.JSONDecodeError, SummarizationError) as exc:
            raise SummarizationError(f"Failed to parse model output as JSON: {exc}") from exc

        required = {
            "tldr",
            "key_findings",
            "methods",
            "important_results",
            "limitations",
            "why_it_matters",
            "interest_relevance",
        }
        missing = required - parsed.keys()
        if missing:
            raise SummarizationError(f"Summary missing fields: {sorted(missing)}")

        return parsed

    def _generate_gemini_content(self, model: Any, prompt: str) -> Any:
        try:
            return model.generate_content(prompt)
        except Exception as exc:
            if _is_gemini_quota_error(exc):
                raise
            delay = _retry_delay_seconds(exc)
            if delay is None:
                raise
            time.sleep(delay)
            return model.generate_content(prompt)
