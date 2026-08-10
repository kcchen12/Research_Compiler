from __future__ import annotations

import hashlib
import json
import re
from typing import Any

import google.generativeai as genai
from openai import OpenAI

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


def _parse_summary_json(output_text: str) -> dict[str, Any]:
    cleaned = output_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        parsed = json.loads(cleaned[start : end + 1])

    if not isinstance(parsed, dict):
        raise SummarizationError("Model output JSON must be an object.")
    return parsed


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

    def summarize_paper(self, paper: dict[str, Any], interests: str) -> dict[str, Any]:
        abstract = (paper.get("abstract") or "").strip()
        if len(abstract) < 80:
            return INSUFFICIENT_TEXT_SUMMARY

        cache_key = self._cache_key(paper, interests)
        cached = self.db.get_cached_summary(cache_key, self.provider)
        if cached:
            return json.loads(cached)

        summary = self._generate_summary(paper, interests)
        self.db.cache_summary(cache_key, self.provider, json.dumps(summary))
        return summary

    def _generate_summary(self, paper: dict[str, Any], interests: str) -> dict[str, Any]:
        prompt = (
            "You are summarizing an academic paper for a research digest. "
            "Use the title and abstract only. Output strict JSON with keys: "
            "tldr (2 sentences), key_findings (3-5 bullets as array), methods, "
            "important_results, limitations, why_it_matters, interest_relevance."
            f"\n\nUser interests: {interests or 'Not provided'}"
            f"\nTitle: {paper.get('title')}"
            f"\nAbstract: {paper.get('abstract')}"
        )

        if self.provider == "openai":
            if not self.openai_key:
                raise SummarizationError("OPENAI_API_KEY is missing.")
            client = OpenAI(api_key=self.openai_key)
            response = client.responses.create(
                model=self.model,
                input=prompt,
                temperature=0.2,
            )
            output_text = response.output_text
        elif self.provider == "gemini":
            if not self.gemini_key:
                raise SummarizationError("GEMINI_API_KEY is missing.")
            genai.configure(api_key=self.gemini_key)
            model = genai.GenerativeModel(self.model)
            response = model.generate_content(prompt)
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
