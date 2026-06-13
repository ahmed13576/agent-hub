"""
Tests for src.scrapers.blog_scraper

Tests cover:
- RSS feed parsing with mocked feedparser output
- Keyword filtering (match and non-match scenarios)
- Tag extraction from feed entries
- Schema compliance
- Graceful error handling for bad feeds
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scrapers.blog_scraper import BlogScraper


def _make_feed_entry(title, summary, link, author="Author", published="2026-06-11T00:00:00Z", tags=None):
    """Create a mock feedparser entry."""
    entry = MagicMock()
    entry.title = title
    entry.summary = summary
    entry.link = link
    entry.author = author
    entry.published = published
    if tags:
        entry.tags = [{"term": t} for t in tags]
    else:
        # Remove the tags attribute entirely
        del entry.tags
    return entry


def _make_feed(entries):
    """Create a mock feedparser FeedParserDict."""
    feed = MagicMock()
    feed.entries = entries
    feed.bozo = False
    return feed


class TestBlogScraperFiltering(unittest.TestCase):
    """Test keyword filtering logic."""

    @patch("src.scrapers.blog_scraper.config")
    def test_matching_articles_are_included(self, mock_config):
        mock_config.sources = {
            "blogs": {
                "rss_feeds": [{"url": "https://example.com/feed", "name": "Test Blog"}],
                "filter_keywords": ["agent", "claude"],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()
        feed = _make_feed([
            _make_feed_entry(
                "Building AI Agents with Claude",
                "<p>A tutorial on agent workflows</p>",
                "https://example.com/post-1",
            ),
        ])
        mock_client.fetch_rss.return_value = feed

        scraper = BlogScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "blog")
        self.assertIn("Claude", items[0]["title"])

    @patch("src.scrapers.blog_scraper.config")
    def test_non_matching_articles_are_excluded(self, mock_config):
        mock_config.sources = {
            "blogs": {
                "rss_feeds": [{"url": "https://example.com/feed", "name": "Test Blog"}],
                "filter_keywords": ["agent"],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()
        feed = _make_feed([
            _make_feed_entry(
                "Best Python Libraries for Data Science",
                "<p>Pandas, NumPy, and matplotlib</p>",
                "https://example.com/post-2",
            ),
        ])
        mock_client.fetch_rss.return_value = feed

        scraper = BlogScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 0, "Non-matching articles should be filtered out")


class TestBlogScraperSchema(unittest.TestCase):
    """Test item schema compliance."""

    @patch("src.scrapers.blog_scraper.config")
    def test_item_has_required_fields(self, mock_config):
        mock_config.sources = {
            "blogs": {
                "rss_feeds": [{"url": "https://example.com/feed", "name": "Test Blog"}],
                "filter_keywords": ["agent"],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()
        feed = _make_feed([
            _make_feed_entry(
                "Agent framework comparison",
                "<p>Comparing agent tools</p>",
                "https://example.com/post-3",
            ),
        ])
        mock_client.fetch_rss.return_value = feed

        scraper = BlogScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 1)
        item = items[0]
        required = ["id", "source", "title", "url", "description",
                     "author", "metadata", "tags", "scraped_at", "raw_content"]
        for field in required:
            self.assertIn(field, item, f"Missing field: {field}")

    @patch("src.scrapers.blog_scraper.config")
    def test_metadata_contains_feed_info(self, mock_config):
        mock_config.sources = {
            "blogs": {
                "rss_feeds": [{"url": "https://example.com/feed", "name": "My Blog"}],
                "filter_keywords": ["agent"],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()
        feed = _make_feed([
            _make_feed_entry(
                "Agent tips",
                "Agent content",
                "https://example.com/post-4",
            ),
        ])
        mock_client.fetch_rss.return_value = feed

        scraper = BlogScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(items[0]["metadata"]["feed_name"], "My Blog")
        self.assertEqual(items[0]["metadata"]["feed_url"], "https://example.com/feed")


class TestBlogScraperTags(unittest.TestCase):
    """Test tag extraction from feed entries."""

    @patch("src.scrapers.blog_scraper.config")
    def test_tags_extracted_from_entry(self, mock_config):
        mock_config.sources = {
            "blogs": {
                "rss_feeds": [{"url": "https://example.com/feed", "name": "Test Blog"}],
                "filter_keywords": ["agent"],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()
        feed = _make_feed([
            _make_feed_entry(
                "Agent frameworks",
                "Agent frameworks review",
                "https://example.com/post-5",
                tags=["AI", "Agents", "LLM"],
            ),
        ])
        mock_client.fetch_rss.return_value = feed

        scraper = BlogScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 1)
        self.assertIn("AI", items[0]["tags"])
        self.assertIn("Agents", items[0]["tags"])


class TestBlogScraperErrorHandling(unittest.TestCase):
    """Test graceful error handling."""

    @patch("src.scrapers.blog_scraper.config")
    def test_continues_on_feed_error(self, mock_config):
        mock_config.sources = {
            "blogs": {
                "rss_feeds": [
                    {"url": "https://bad.com/feed", "name": "Bad Feed"},
                    {"url": "https://good.com/feed", "name": "Good Feed"},
                ],
                "filter_keywords": ["agent"],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()

        good_feed = _make_feed([
            _make_feed_entry("Agent post", "Agent content", "https://good.com/post-1"),
        ])

        mock_client.fetch_rss.side_effect = [
            Exception("Bad feed error"),
            good_feed,
        ]

        scraper = BlogScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 1, "Should continue scraping after one feed fails")


if __name__ == "__main__":
    unittest.main()
