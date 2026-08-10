from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "papers.db"

JOURNALS = {
    "Journal of Fluid Mechanics": {
        "openalex_name": "Journal of Fluid Mechanics",
        "crossref_container": "Journal of Fluid Mechanics",
    }
}


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class AppConfig:
    openai_api_key: str | None
    gemini_api_key: str | None
    ai_provider: str
    default_model: str



def load_config() -> AppConfig:
    load_dotenv()
    return AppConfig(
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        ai_provider=os.getenv("AI_PROVIDER", "openai").lower(),
        default_model=os.getenv("AI_MODEL", "gpt-4o-mini"),
    )
