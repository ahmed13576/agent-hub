"""
Agent Hub - Configuration Module

Loads environment variables from .env and parses data/sources.yaml.
Provides a single Config object used across all modules.
"""

import os
import yaml
from pathlib import Path
from dotenv import load_dotenv


# Project root is two levels up from src/config.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Load .env from project root
load_dotenv(PROJECT_ROOT / ".env")


class Config:
    """Central configuration for the Agent Hub pipeline."""

    def __init__(self):
        # --- API Keys ---
        self.groq_api_key: str = os.getenv("GROQ_API_KEY", "")
        self.github_token: str = os.getenv("GITHUB_TOKEN", "")
        self.brightdata_api_key: str = os.getenv("BRIGHTDATA_API_KEY", "")
        self.brightdata_sbr_ws_endpoint: str = os.getenv("BRIGHTDATA_SBR_WS_ENDPOINT", "")

        # --- Proxy ---
        # If any Bright Data credential is present, we consider proxy available
        self.proxy_enabled: bool = bool(self.brightdata_api_key)

        # --- Groq Model ---
        self.groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        self.groq_fallback_model: str = os.getenv("GROQ_FALLBACK_MODEL", "llama-3.1-8b-instant")
        self.groq_max_rpm: int = int(os.getenv("GROQ_MAX_RPM", "25"))  # Stay under 30 RPM limit

        # --- Paths ---
        self.data_dir: Path = DATA_DIR
        self.sources_path: Path = DATA_DIR / "sources.yaml"
        self.database_path: Path = DATA_DIR / "database.json"
        self.discovered_sources_path: Path = DATA_DIR / "discovered_sources.json"

        # --- Sources ---
        self._sources: dict | None = None

    @property
    def sources(self) -> dict:
        """Lazy-load and cache the sources.yaml configuration."""
        if self._sources is None:
            self._sources = self._load_sources()
        return self._sources

    def _load_sources(self) -> dict:
        """Parse the sources.yaml file."""
        if not self.sources_path.exists():
            raise FileNotFoundError(
                f"Sources config not found at {self.sources_path}. "
                f"Expected file: data/sources.yaml"
            )
        with open(self.sources_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            raise ValueError("sources.yaml must be a YAML dictionary at the top level.")
        return data

    def validate(self) -> list[str]:
        """
        Validate the configuration and return a list of warnings.
        Returns an empty list if everything is OK.
        """
        warnings = []
        if not self.groq_api_key:
            warnings.append("GROQ_API_KEY is not set — AI enrichment will be disabled.")
        if not self.github_token:
            warnings.append("GITHUB_TOKEN is not set — GitHub API rate limits will be very low.")
        if not self.proxy_enabled:
            warnings.append(
                "BRIGHTDATA_API_KEY is not set — proxy routing is disabled. "
                "Scraping will use direct HTTP only."
            )
        return warnings

    def __repr__(self) -> str:
        return (
            f"Config("
            f"groq_model={self.groq_model!r}, "
            f"proxy_enabled={self.proxy_enabled}, "
            f"sources_loaded={self._sources is not None}"
            f")"
        )


# Singleton instance for easy importing
config = Config()
