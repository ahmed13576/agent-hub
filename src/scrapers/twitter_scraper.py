"""
Agent Hub - Twitter/X Scraper (Stub)

Twitter/X scraping is disabled by default due to strict anti-scraping measures.
This module provides a stub that returns an empty list and can be activated
when a working Nitter instance or Bright Data proxy is configured.
"""

import logging
from typing import Optional

from src.config import config
from src.clients.http_client import HttpClient
from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class TwitterScraper(BaseScraper):
    """
    Stub scraper for Twitter/X.

    Returns empty results when twitter.enabled is false in sources.yaml.
    When enabled, attempts to fetch from Nitter RSS instances (experimental).
    """

    def __init__(self, http_client: Optional[HttpClient] = None):
        self._client = http_client or HttpClient(use_proxy=False)
        self._sources = config.sources.get("twitter", {})

    def scrape(self) -> list[dict]:
        """
        Scrape Twitter/X — currently returns empty list when disabled.

        Returns:
            Empty list (Twitter scraping disabled by default).
        """
        enabled = self._sources.get("enabled", False)

        if not enabled:
            logger.info(
                "Twitter/X scraping is disabled. "
                "Set 'twitter.enabled: true' in sources.yaml and configure "
                "Nitter instances or BRIGHTDATA_PROXY to enable."
            )
            return []

        # Experimental: attempt Nitter RSS if enabled
        logger.info("Twitter/X scraping enabled — attempting Nitter RSS feeds...")
        items = []
        nitter_instances = self._sources.get("nitter_instances", [])
        search_queries = self._sources.get("search_queries", [])

        for instance in nitter_instances:
            for query in search_queries:
                try:
                    feed_url = f"{instance}/search/rss?f=tweets&q={query}"
                    feed = self._client.fetch_rss(feed_url)
                    for entry in feed.entries:
                        title = getattr(entry, "title", "") or ""
                        link = getattr(entry, "link", "") or ""
                        description = self._strip_html(
                            getattr(entry, "summary", "") or ""
                        )

                        items.append(self._make_item(
                            source="twitter",
                            title=title[:200],
                            url=link,
                            description=description[:500],
                            author=getattr(entry, "author", "") or "",
                            metadata={
                                "nitter_instance": instance,
                                "query": query,
                                "published": getattr(entry, "published", ""),
                            },
                            tags=["twitter", query],
                            raw_content=f"{title}\n{description}",
                        ))
                except Exception as e:
                    logger.debug(
                        f"Nitter fetch failed ({instance}, query='{query}'): {e}"
                    )
                    continue

            if items:
                # If we found results from this instance, stop trying others
                break

        logger.info(f"Twitter/X scraper: {len(items)} tweets collected")
        return items
