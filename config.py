from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "papers.db"

GEMINI_QUOTAS_LAST_UPDATED = "2026-08-15"


@dataclass(frozen=True)
class GeminiModelConfig:
    display_name: str
    api_model_id: str
    rpm: int
    tpm: int
    rpd: int
    recommended: bool = False
    enabled: bool = True
    notes: str = ""

    @property
    def ui_label(self) -> str:
        if self.recommended:
            return f"{self.display_name} (Recommended)"
        return self.display_name


# Manually maintained Gemini free-tier quotas. These values were obtained from
# Google AI Studio's free-tier quota dashboard; Google may change model
# availability and quota limits, so update this configuration when that happens.
GEMINI_MODELS: dict[str, GeminiModelConfig] = {
    "gemini-3.5-flash-lite": GeminiModelConfig(
        display_name="Gemini 3.5 Flash Lite",
        api_model_id="gemini-3.5-flash-lite",
        rpm=15,
        tpm=250_000,
        rpd=500,
        recommended=True,
        notes="High free-tier quota; recommended for bulk paper summarization.",
    ),
    "gemini-3.1-flash-lite": GeminiModelConfig(
        display_name="Gemini 3.1 Flash Lite",
        api_model_id="gemini-3.1-flash-lite",
        rpm=15,
        tpm=250_000,
        rpd=500,
        notes="High free-tier quota; good fallback for bulk summarization.",
    ),
    "gemini-3.5-flash": GeminiModelConfig(
        display_name="Gemini 3.5 Flash",
        api_model_id="gemini-3.5-flash",
        rpm=5,
        tpm=250_000,
        rpd=20,
        notes="Lower daily free quota; best for smaller comparison runs.",
    ),
    "gemini-3.6-flash": GeminiModelConfig(
        display_name="Gemini 3.6 Flash",
        api_model_id="gemini-3.6-flash",
        rpm=5,
        tpm=250_000,
        rpd=20,
        notes="Lower daily free quota; large digests may exhaust the free tier.",
    ),
    "gemini-3.7-flash": GeminiModelConfig(
        display_name="Gemini 3.7 Flash",
        api_model_id="gemini-3.7-flash",
        rpm=5,
        tpm=250_000,
        rpd=20,
        notes="Lower daily free quota; large digests may exhaust the free tier.",
    ),
    "gemini-3-flash-preview": GeminiModelConfig(
        display_name="Gemini 3 Flash",
        api_model_id="gemini-3-flash-preview",
        rpm=5,
        tpm=250_000,
        rpd=20,
        notes="Preview model; large digests may exhaust the free tier.",
    ),
    "gemini-2.5-flash": GeminiModelConfig(
        display_name="Gemini 2.5 Flash",
        api_model_id="gemini-2.5-flash",
        rpm=5,
        tpm=250_000,
        rpd=20,
        notes="Older Flash model with a lower daily free quota.",
    ),
    "gemini-2.5-flash-lite": GeminiModelConfig(
        display_name="Gemini 2.5 Flash Lite",
        api_model_id="gemini-2.5-flash-lite",
        rpm=10,
        tpm=250_000,
        rpd=20,
        notes="Lite model, but with a lower daily free quota than the recommended 3.5 Flash Lite.",
    ),
}

JOURNALS = {
    "Journal of Fluid Mechanics": {
        "openalex_name": "Journal of Fluid Mechanics",
        "openalex_source_id": "S152000018",
        "crossref_container": "Journal of Fluid Mechanics",
        "issns": ["0022-1120", "1469-7645", "1750-6859"],
    }
}


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class AppConfig:
    openai_api_key: Optional[str]
    gemini_api_key: Optional[str]
    ai_provider: str
    default_model: str


def enabled_gemini_models() -> list[GeminiModelConfig]:
    return [model for model in GEMINI_MODELS.values() if model.enabled]


def recommended_gemini_model() -> GeminiModelConfig:
    for model in enabled_gemini_models():
        if model.recommended:
            return model
    return enabled_gemini_models()[0]


def get_gemini_model_config(model_id: str) -> GeminiModelConfig:
    return GEMINI_MODELS.get(model_id, recommended_gemini_model())


def gemini_request_spacing_seconds(model: GeminiModelConfig) -> float:
    return (60 / model.rpm) * 1.1


def format_quota_updated_date() -> str:
    year, month, day = GEMINI_QUOTAS_LAST_UPDATED.split("-")
    return f"{int(month)}/{int(day)}/{year}"


def _get_secret_value(name: str) -> Optional[str]:
    try:
        import streamlit as st

        value: Any = st.secrets.get(name)
    except Exception:
        value = None
    return str(value) if value else None


def load_config() -> AppConfig:
    load_dotenv()
    default_gemini_model = recommended_gemini_model().api_model_id
    return AppConfig(
        openai_api_key=os.getenv("OPENAI_API_KEY") or _get_secret_value("OPENAI_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY") or _get_secret_value("GEMINI_API_KEY"),
        ai_provider=os.getenv("AI_PROVIDER", "gemini").strip().lower(),
        default_model=os.getenv("AI_MODEL", default_gemini_model).strip(),
    )
