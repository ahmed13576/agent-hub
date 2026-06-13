"""
Tests for src.scrapers.reddit_scraper

Tests cover:
- RSS feed parsing with mocked feedparser output
- Keyword filtering (match and non-match scenarios)
- HTML tag stripping from summaries
- Schema compliance
- Graceful error handling for bad feeds
"""

import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scrapers.reddit_scraper import RedditScraper


def _make_feed_entry(title, summary, link, author="/u/testuser", published="2026-06-12T00:00:00Z"):
    """Create a mock feedparser entry."""
    entry = MagicMock()
    entry.title = title
    entry.summary = summary
    entry.link = link
    entry.author = author
    entry.published = published
    return entry


def _make_feed(entries):
    """Create a mock feedparser FeedParserDict."""
    feed = MagicMock()
    feed.entries = entries
    feed.bozo = False
    return feed


class TestRedditScraperFiltering(unittest.TestCase):
    """Test keyword filtering logic."""

    @patch("src.scrapers.reddit_scraper.config")
    def test_matching_posts_are_included(self, mock_config):
        mock_config.sources = {
            "reddit": {
                "subreddits": ["ClaudeDev"],
                "filter_keywords": ["claude code", "agent"],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()
        feed = _make_feed([
            _make_feed_entry(
                "How I use Claude Code for coding",
                "<p>Amazing agent workflow</p>",
                "https://reddit.com/r/ClaudeDev/1",
            ),
        ])
        mock_client.fetch_rss.return_value = feed

        scraper = RedditScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["source"], "reddit")
        self.assertIn("Claude Code", items[0]["title"])

    @patch("src.scrapers.reddit_scraper.config")
    def test_non_matching_posts_are_excluded(self, mock_config):
        mock_config.sources = {
            "reddit": {
                "subreddits": ["ClaudeDev"],
                "filter_keywords": ["claude code"],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()
        feed = _make_feed([
            _make_feed_entry(
                "Best pizza recipe ever",
                "<p>Nothing about AI here</p>",
                "https://reddit.com/r/ClaudeDev/2",
            ),
        ])
        mock_client.fetch_rss.return_value = feed

        scraper = RedditScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 0, "Non-matching posts should be filtered out")


class TestRedditScraperSchema(unittest.TestCase):
    """Test item schema compliance."""

    @patch("src.scrapers.reddit_scraper.config")
    def test_item_has_required_fields(self, mock_config):
        mock_config.sources = {
            "reddit": {
                "subreddits": ["ClaudeDev"],
                "filter_keywords": ["agent"],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()
        feed = _make_feed([
            _make_feed_entry(
                "Agent workflow tips",
                "<p>Great agent tips</p>",
                "https://reddit.com/r/ClaudeDev/3",
            ),
        ])
        mock_client.fetch_rss.return_value = feed

        scraper = RedditScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 1)
        item = items[0]
        required = ["id", "source", "title", "url", "description",
                     "author", "metadata", "tags", "scraped_at", "raw_content"]
        for field in required:
            self.assertIn(field, item, f"Missing field: {field}")


class TestRedditScraperHtmlStripping(unittest.TestCase):
    """Test HTML stripping from summaries."""

    @patch("src.scrapers.reddit_scraper.config")
    def test_html_is_stripped_from_description(self, mock_config):
        mock_config.sources = {
            "reddit": {
                "subreddits": ["ClaudeDev"],
                "filter_keywords": ["agent"],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()
        feed = _make_feed([
            _make_feed_entry(
                "Agent tips",
                "<p>This is <b>bold</b> and <a href='#'>linked</a> agent content</p>",
                "https://reddit.com/r/ClaudeDev/4",
            ),
        ])
        mock_client.fetch_rss.return_value = feed

        scraper = RedditScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 1)
        description = items[0]["description"]
        self.assertNotIn("<p>", description)
        self.assertNotIn("<b>", description)
        self.assertIn("bold", description)


class TestRedditScraperErrorHandling(unittest.TestCase):
    """Test graceful error handling."""

    @patch("src.scrapers.reddit_scraper.config")
    def test_continues_on_feed_error(self, mock_config):
        mock_config.sources = {
            "reddit": {
                "subreddits": ["BadSub", "ClaudeDev"],
                "filter_keywords": ["agent"],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()

        good_feed = _make_feed([
            _make_feed_entry("Agent post", "Agent content", "https://reddit.com/r/ClaudeDev/5"),
        ])

        # First sub fails, second succeeds
        mock_client.fetch_rss.side_effect = [
            Exception("Feed error"),
            good_feed,
        ]

        scraper = RedditScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 1, "Should continue scraping after one sub fails")


if __name__ == "__main__":
    unittest.main()
