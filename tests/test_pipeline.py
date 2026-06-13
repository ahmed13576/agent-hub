"""
Tests for src.pipeline

Tests cover:
- De-duplication against existing database and within batch
- Dynamic source discovery (URL extraction, blacklist filtering)
- Database save/load cycle
- Full pipeline run with mocked scrapers
"""

import unittest
import json
import tempfile
import os
from unittest.mock import patch, MagicMock
from pathlib import Path

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.pipeline import Pipeline, URL_PATTERN, BLACKLISTED_DOMAINS


def _make_item(title, url, source="github", description="", raw_content=""):
    """Create a minimal test item dict."""
    import hashlib
    from datetime import datetime, timezone
    return {
        "id": hashlib.sha256(url.encode()).hexdigest(),
        "source": source,
        "title": title,
        "url": url,
        "description": description or title,
        "author": "test",
        "metadata": {},
        "tags": [],
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "raw_content": raw_content or title,
    }


class TestDeduplication(unittest.TestCase):
    """Test the _deduplicate method."""

    @patch("src.pipeline.config")
    def setUp(self, mock_config):
        mock_config.database_path = Path(tempfile.mktemp(suffix=".json"))
        mock_config.discovered_sources_path = Path(tempfile.mktemp(suffix=".json"))
        mock_config.sources = {"github": {}, "reddit": {}, "blogs": {}, "twitter": {}}
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""
        mock_config.github_token = ""
        mock_config.groq_api_key = ""

        # Write empty database
        with open(mock_config.database_path, "w") as f:
            json.dump([], f)
        with open(mock_config.discovered_sources_path, "w") as f:
            json.dump({}, f)

        self.pipeline = Pipeline.__new__(Pipeline)
        self.pipeline._scrapers = []
        self.pipeline._db_path = mock_config.database_path
        self.pipeline._discovered_path = mock_config.discovered_sources_path

    def test_removes_duplicates_within_batch(self):
        """Items with the same URL in the same batch should be deduplicated."""
        items = [
            _make_item("Repo A", "https://github.com/test/repo-a"),
            _make_item("Repo A (duplicate)", "https://github.com/test/repo-a"),
            _make_item("Repo B", "https://github.com/test/repo-b"),
        ]

        result = self.pipeline._deduplicate(items)
        self.assertEqual(len(result), 2)

    def test_removes_duplicates_against_database(self):
        """Items already in the database should be skipped."""
        existing_item = _make_item("Existing", "https://github.com/test/existing")

        # Write existing item to database
        with open(self.pipeline._db_path, "w") as f:
            json.dump([existing_item], f)

        items = [
            existing_item,
            _make_item("New Repo", "https://github.com/test/new"),
        ]

        result = self.pipeline._deduplicate(items)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "New Repo")

    def test_empty_batch_returns_empty(self):
        result = self.pipeline._deduplicate([])
        self.assertEqual(len(result), 0)


class TestSourceDiscovery(unittest.TestCase):
    """Test the _discover_sources method."""

    @patch("src.pipeline.config")
    def setUp(self, mock_config):
        mock_config.database_path = Path(tempfile.mktemp(suffix=".json"))
        mock_config.discovered_sources_path = Path(tempfile.mktemp(suffix=".json"))
        mock_config.sources = {"github": {}, "reddit": {}, "blogs": {}, "twitter": {}}
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""
        mock_config.github_token = ""
        mock_config.groq_api_key = ""

        with open(mock_config.database_path, "w") as f:
            json.dump([], f)
        with open(mock_config.discovered_sources_path, "w") as f:
            json.dump({}, f)

        self.pipeline = Pipeline.__new__(Pipeline)
        self.pipeline._scrapers = []
        self.pipeline._db_path = mock_config.database_path
        self.pipeline._discovered_path = mock_config.discovered_sources_path

    def test_extracts_new_domains(self):
        """URLs in raw_content should be extracted and tracked."""
        items = [
            _make_item(
                "Post about tools",
                "https://reddit.com/r/test/1",
                raw_content="Check out https://awesome-ai-tools.dev/blog/tips for great agent advice",
            ),
        ]

        count = self.pipeline._discover_sources(items)
        self.assertGreater(count, 0)

        # Verify the discovered domain was saved
        with open(self.pipeline._discovered_path) as f:
            discovered = json.load(f)
        self.assertIn("awesome-ai-tools.dev", discovered)

    def test_blacklisted_domains_are_excluded(self):
        """URLs from blacklisted domains should not be tracked."""
        items = [
            _make_item(
                "Post with common links",
                "https://reddit.com/r/test/2",
                raw_content="See https://github.com/user/repo and https://youtube.com/watch?v=123",
            ),
        ]

        count = self.pipeline._discover_sources(items)
        self.assertEqual(count, 0, "Blacklisted domains should not be discovered")

    def test_increments_mention_count(self):
        """Repeated mentions of same domain should increment count."""
        items = [
            _make_item(
                "Post 1",
                "https://reddit.com/r/test/3",
                raw_content="Visit https://newblog.io/post1",
            ),
            _make_item(
                "Post 2",
                "https://reddit.com/r/test/4",
                raw_content="Also see https://newblog.io/post2",
            ),
        ]

        self.pipeline._discover_sources(items)

        with open(self.pipeline._discovered_path) as f:
            discovered = json.load(f)

        self.assertEqual(discovered["newblog.io"]["mention_count"], 2)


class TestDatabaseSave(unittest.TestCase):
    """Test database save/load operations."""

    @patch("src.pipeline.config")
    def setUp(self, mock_config):
        mock_config.database_path = Path(tempfile.mktemp(suffix=".json"))
        mock_config.discovered_sources_path = Path(tempfile.mktemp(suffix=".json"))
        mock_config.sources = {"github": {}, "reddit": {}, "blogs": {}, "twitter": {}}
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""
        mock_config.github_token = ""
        mock_config.groq_api_key = ""

        with open(mock_config.database_path, "w") as f:
            json.dump([], f)
        with open(mock_config.discovered_sources_path, "w") as f:
            json.dump({}, f)

        self.pipeline = Pipeline.__new__(Pipeline)
        self.pipeline._scrapers = []
        self.pipeline._db_path = mock_config.database_path
        self.pipeline._discovered_path = mock_config.discovered_sources_path

    def test_save_appends_to_existing(self):
        """New items should be appended to the database, not overwrite."""
        existing = _make_item("Existing", "https://example.com/1")
        with open(self.pipeline._db_path, "w") as f:
            json.dump([existing], f)

        new_item = _make_item("New", "https://example.com/2")
        self.pipeline._save_to_database([new_item])

        with open(self.pipeline._db_path) as f:
            db = json.load(f)

        self.assertEqual(len(db), 2)

    def test_load_empty_database(self):
        """Loading an empty [] database should return empty list."""
        result = self.pipeline._load_database()
        self.assertEqual(result, [])


class TestFullPipeline(unittest.TestCase):
    """Test the full pipeline orchestration with mocked scrapers."""

    @patch("src.pipeline.config")
    @patch("src.pipeline.GitHubScraper")
    @patch("src.pipeline.RedditScraper")
    @patch("src.pipeline.BlogScraper")
    @patch("src.pipeline.TwitterScraper")
    def test_full_run_with_mocked_scrapers(
        self, MockTwitter, MockBlog, MockReddit, MockGitHub, mock_config
    ):
        mock_config.database_path = Path(tempfile.mktemp(suffix=".json"))
        mock_config.discovered_sources_path = Path(tempfile.mktemp(suffix=".json"))
        mock_config.sources = {"github": {}, "reddit": {}, "blogs": {}, "twitter": {}}
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""
        mock_config.github_token = ""
        mock_config.groq_api_key = ""

        with open(mock_config.database_path, "w") as f:
            json.dump([], f)
        with open(mock_config.discovered_sources_path, "w") as f:
            json.dump({}, f)

        # Mock scraper outputs
        MockGitHub.return_value.scrape.return_value = [
            _make_item("GH Repo", "https://github.com/test/repo"),
        ]
        MockReddit.return_value.scrape.return_value = [
            _make_item("Reddit Post", "https://reddit.com/r/test/1", source="reddit"),
        ]
        MockBlog.return_value.scrape.return_value = [
            _make_item("Blog Article", "https://blog.example.com/article", source="blog"),
        ]
        MockTwitter.return_value.scrape.return_value = []

        pipeline = Pipeline()
        stats = pipeline.run()

        self.assertEqual(stats["new_items"], 3)
        self.assertEqual(stats["duplicates_skipped"], 0)
        self.assertEqual(len(stats["errors"]), 0)
        self.assertEqual(stats["total_in_db"], 3)

    @patch("src.pipeline.config")
    @patch("src.pipeline.GitHubScraper")
    @patch("src.pipeline.RedditScraper")
    @patch("src.pipeline.BlogScraper")
    @patch("src.pipeline.TwitterScraper")
    def test_scraper_error_does_not_crash_pipeline(
        self, MockTwitter, MockBlog, MockReddit, MockGitHub, mock_config
    ):
        mock_config.database_path = Path(tempfile.mktemp(suffix=".json"))
        mock_config.discovered_sources_path = Path(tempfile.mktemp(suffix=".json"))
        mock_config.sources = {"github": {}, "reddit": {}, "blogs": {}, "twitter": {}}
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""
        mock_config.github_token = ""
        mock_config.groq_api_key = ""

        with open(mock_config.database_path, "w") as f:
            json.dump([], f)
        with open(mock_config.discovered_sources_path, "w") as f:
            json.dump({}, f)

        # GitHub scraper crashes
        MockGitHub.return_value.scrape.side_effect = Exception("API down")
        # Others work fine
        MockReddit.return_value.scrape.return_value = [
            _make_item("Reddit Post", "https://reddit.com/r/test/2", source="reddit"),
        ]
        MockBlog.return_value.scrape.return_value = []
        MockTwitter.return_value.scrape.return_value = []

        pipeline = Pipeline()
        stats = pipeline.run()

        self.assertEqual(stats["new_items"], 1)
        self.assertEqual(len(stats["errors"]), 1)
        self.assertIn("API down", stats["errors"][0])


class TestUrlPattern(unittest.TestCase):
    """Test the URL extraction regex."""

    def test_extracts_https_urls(self):
        text = "Check out https://awesome-tool.dev/docs for info"
        urls = URL_PATTERN.findall(text)
        self.assertEqual(len(urls), 1)
        self.assertIn("https://awesome-tool.dev/docs", urls[0])

    def test_extracts_http_urls(self):
        text = "Visit http://example.com/page"
        urls = URL_PATTERN.findall(text)
        self.assertEqual(len(urls), 1)

    def test_handles_multiple_urls(self):
        text = "See https://a.com and https://b.com for details"
        urls = URL_PATTERN.findall(text)
        self.assertEqual(len(urls), 2)


if __name__ == "__main__":
    unittest.main()
