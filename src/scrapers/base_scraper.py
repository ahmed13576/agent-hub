"""
Agent Hub - Base Scraper

Abstract base class that defines the interface and shared utilities
for all platform-specific scrapers.
"""

import hashlib
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """
    Abstract base for all scrapers.

    Subclasses must implement `scrape()` which returns a list of item dicts
    conforming to the unified schema.
    """

    @abstractmethod
    def scrape(self) -> list[dict]:
        """
        Execute the scraping logic and return a list of items.

        Returns:
            List of item dicts following the unified schema.
        """
        ...

    @staticmethod
    def _make_id(url: str) -> str:
        """Generate a deterministic ID from a URL using SHA256."""
        return hashlib.sha256(url.encode("utf-8")).hexdigest()

    @staticmethod
    def _make_item(
        source: str,
        title: str,
        url: str,
        description: str,
        author: str,
        metadata: dict,
        tags: list[str],
        raw_content: str,
    ) -> dict:
        """
        Build a unified schema item dict.

        Args:
            source: Platform identifier ("github", "reddit", "blog", "twitter").
            title: Item title.
            url: Canonical URL.
            description: Summary or body snippet.
            author: Author name or handle.
            metadata: Source-specific metadata (stars, forks, subreddit, etc.).
            tags: Raw tags from the source (topics, flair, etc.).
            raw_content: Full text for downstream LLM processing.

        Returns:
            Dict conforming to the unified item schema.
        """
        return {
            "id": BaseScraper._make_id(url),
            "source": source,
            "title": title,
            "url": url,
            "description": description,
            "author": author,
            "metadata": metadata,
            "tags": tags,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "raw_content": raw_content,
        }

    @staticmethod
    def _strip_html(text: str) -> str:
        """
        Remove HTML tags from a string.

        A lightweight approach using string replacement — avoids importing
        heavy HTML parsing libraries for simple tag stripping.
        """
        import re
        clean = re.sub(r"<[^>]+>", " ", text)
        # Collapse multiple whitespace
        clean = re.sub(r"\s+", " ", clean).strip()
        return clean
