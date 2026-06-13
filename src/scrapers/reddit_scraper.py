"""
Agent Hub - Reddit Scraper

Scrapes Reddit subreddits via RSS feeds with keyword filtering.
Outputs items in the unified schema for downstream processing.
"""

import logging
from typing import Optional

from src.config import config
from src.clients.http_client import HttpClient
from src.scrapers.base_scraper import BaseScraper

logger = logging.getLogger(__name__)


class RedditScraper(BaseScraper):
    """
    Scrapes Reddit subreddits using public RSS feeds.

    - Fetches from /r/{subreddit}/.rss
    - Filters entries by keyword matches in title/content
    - No API keys or authentication required
    """

    def __init__(self, http_client: Optional[HttpClient] = None):
        self._client = http_client or HttpClient(use_proxy=False)
        self._sources = config.sources.get("reddit", {})

    def scrape(self) -> list[dict]:
        """
        Scrape all configured subreddits and return filtered items.

        Returns:
            List of item dicts matching filter keywords.
        """
        items = []
        subreddits = self._sources.get("subreddits", [])
        keywords = [kw.lower() for kw in self._sources.get("filter_keywords", [])]

        for subreddit in subreddits:
            try:
                sub_items = self._scrape_subreddit(subreddit, keywords)
                items.extend(sub_items)
            except Exception as e:
                logger.warning(f"Reddit scraper failed for r/{subreddit}: {e}")

        logger.info(f"Reddit scraper: {len(items)} posts collected from {len(subreddits)} subreddits")
        return items

    def _scrape_subreddit(self, subreddit: str, keywords: list[str]) -> list[dict]:
        """
        Fetch and filter a single subreddit's RSS feed.

        Args:
            subreddit: Subreddit name (e.g., "ClaudeDev").
            keywords: Lowercase filter keywords.

        Returns:
            List of matching items.
        """
        feed_url = f"https://www.reddit.com/r/{subreddit}/.rss"

        try:
            feed = self._client.fetch_rss(feed_url)
        except Exception as e:
            logger.warning(f"Failed to fetch RSS for r/{subreddit}: {e}")
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
                author = getattr(entry, "author", "") or ""
                # Remove Reddit's /u/ prefix if present
                if author.startswith("/u/"):
                    author = author[3:]

                published = getattr(entry, "published", "") or ""

                items.append(self._make_item(
                    source="reddit",
                    title=title,
                    url=link,
                    description=description[:500],  # Cap description length
                    author=author,
                    metadata={
                        "subreddit": subreddit,
                        "published": published,
                    },
                    tags=[f"r/{subreddit}"],
                    raw_content=f"{title}\n{description}",
                ))

        logger.debug(f"r/{subreddit}: {len(items)} matching posts from {len(feed.entries)} total entries")
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
