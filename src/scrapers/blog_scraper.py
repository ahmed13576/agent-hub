"""
Agent Hub - Blog Scraper

Scrapes technical blogs via RSS feeds with keyword filtering.
Outputs items in the unified schema for downstream processing.
"""

import logging
from typing import Optional

from src.config import config
from src.clients.http_client import HttpClient
from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class BlogScraper(BaseScraper):
    """
    Scrapes technical blogs using their RSS/Atom feeds.

    - Fetches from configured blog RSS URLs
    - Filters entries by keyword matches in title/content
    - Supports Medium, WordPress, and generic RSS/Atom feeds
    """

    def __init__(self, http_client: Optional[HttpClient] = None):
        self._client = http_client or HttpClient(use_proxy=False)
        self._sources = config.sources.get("blogs", {})

    def scrape(self) -> list[dict]:
        """
        Scrape all configured blog RSS feeds and return filtered items.

        Returns:
            List of item dicts matching filter keywords.
        """
        items = []
        feeds = self._sources.get("rss_feeds", [])
        keywords = [kw.lower() for kw in self._sources.get("filter_keywords", [])]

        for feed_config in feeds:
            feed_url = feed_config.get("url", "")
            feed_name = feed_config.get("name", feed_url)

            if not feed_url:
                continue

            try:
                feed_items = self._scrape_feed(feed_url, feed_name, keywords)
                items.extend(feed_items)
            except Exception as e:
                logger.warning(f"Blog scraper failed for '{feed_name}': {e}")

        logger.info(f"Blog scraper: {len(items)} articles collected from {len(feeds)} feeds")
        return items

    def _scrape_feed(self, feed_url: str, feed_name: str, keywords: list[str]) -> list[dict]:
        """
        Fetch and filter a single blog RSS feed.

        Args:
            feed_url: RSS feed URL.
            feed_name: Human-readable feed name.
            keywords: Lowercase filter keywords.

        Returns:
            List of matching items.
        """
        try:
            feed = self._client.fetch_rss(feed_url)
        except Exception as e:
            logger.warning(f"Failed to fetch RSS for '{feed_name}' ({feed_url}): {e}")
            return []

        items = []
        for entry in feed.entries:
            title = getattr(entry, "title", "") or ""
            summary = getattr(entry, "summary", "") or ""
            link = getattr(entry, "link", "") or ""

            # Clean HTML from summary
            description = self._strip_html(summary)

            # Combine title + description for keyword matching
            search_text = f"{title} {description}".lower()

            # Check keyword match
            if not keywords or self._matches_keywords(search_text, keywords):
                author = getattr(entry, "author", "") or feed_name
                published = getattr(entry, "published", "") or ""

                # Extract tags from entry if available
                entry_tags = []
                if hasattr(entry, "tags"):
                    entry_tags = [
                        tag.get("term", "") for tag in entry.tags
                        if isinstance(tag, dict) and tag.get("term")
                    ]

                items.append(self._make_item(
                    source="blog",
                    title=title,
                    url=link,
                    description=description[:500],  # Cap description length
                    author=author,
                    metadata={
                        "feed_name": feed_name,
                        "feed_url": feed_url,
                        "published": published,
                    },
                    tags=entry_tags,
                    raw_content=f"{title}\n{description}",
                ))

        logger.debug(f"Blog '{feed_name}': {len(items)} matching articles from {len(feed.entries)} total entries")
        return items

    @staticmethod
    def _matches_keywords(text: str, keywords: list[str]) -> bool:
        """
        Check if text contains any of the filter keywords.

        Args:
            text: Lowercase text to search.
            keywords: List of lowercase keywords.

        Returns:
            True if any keyword is found in text.
        """
        return any(kw in text for kw in keywords)
