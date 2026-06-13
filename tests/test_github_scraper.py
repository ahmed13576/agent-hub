"""
Tests for src.scrapers.github_scraper

Tests cover:
- Repo-to-item schema conversion
- Search query formatting and result parsing
- Tracked repo fetching
- De-duplication across multiple queries
- Error handling for API failures
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.scrapers.github_scraper import GitHubScraper


# Sample GitHub API repo response
SAMPLE_REPO = {
    "full_name": "anthropics/claude-code",
    "html_url": "https://github.com/anthropics/claude-code",
    "description": "Claude Code is an agentic coding tool by Anthropic",
    "topics": ["claude", "agent", "coding"],
    "stargazers_count": 5000,
    "forks_count": 300,
    "language": "Python",
    "updated_at": "2026-06-10T12:00:00Z",
    "created_at": "2025-01-01T00:00:00Z",
    "open_issues_count": 42,
    "watchers_count": 5000,
    "license": {"spdx_id": "MIT"},
    "owner": {"login": "anthropics"},
}

SAMPLE_REPO_2 = {
    "full_name": "openai/codex",
    "html_url": "https://github.com/openai/codex",
    "description": "Codex CLI by OpenAI",
    "topics": ["codex", "openai", "cli"],
    "stargazers_count": 2000,
    "forks_count": 100,
    "language": "TypeScript",
    "updated_at": "2026-06-09T12:00:00Z",
    "created_at": "2025-03-01T00:00:00Z",
    "open_issues_count": 15,
    "watchers_count": 2000,
    "license": {"spdx_id": "Apache-2.0"},
    "owner": {"login": "openai"},
}

SEARCH_RESPONSE = {
    "total_count": 2,
    "items": [SAMPLE_REPO, SAMPLE_REPO_2],
}


class TestGitHubScraperSchema(unittest.TestCase):
    """Test repo-to-item conversion and schema compliance."""

    @patch("src.scrapers.github_scraper.config")
    def test_repo_to_item_has_required_fields(self, mock_config):
        mock_config.github_token = ""
        mock_config.sources = {"github": {"search_queries": [], "tracked_repos": []}}
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        scraper = GitHubScraper(http_client=MagicMock())
        item = scraper._repo_to_item(SAMPLE_REPO)

        required_fields = ["id", "source", "title", "url", "description",
                           "author", "metadata", "tags", "scraped_at", "raw_content"]
        for field in required_fields:
            self.assertIn(field, item, f"Missing required field: {field}")

    @patch("src.scrapers.github_scraper.config")
    def test_repo_to_item_values(self, mock_config):
        mock_config.github_token = ""
        mock_config.sources = {"github": {"search_queries": [], "tracked_repos": []}}
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        scraper = GitHubScraper(http_client=MagicMock())
        item = scraper._repo_to_item(SAMPLE_REPO)

        self.assertEqual(item["source"], "github")
        self.assertEqual(item["title"], "anthropics/claude-code")
        self.assertEqual(item["url"], "https://github.com/anthropics/claude-code")
        self.assertEqual(item["author"], "anthropics")
        self.assertEqual(item["metadata"]["stars"], 5000)
        self.assertEqual(item["metadata"]["language"], "Python")
        self.assertIn("claude", item["tags"])


class TestGitHubScraperSearch(unittest.TestCase):
    """Test search query execution."""

    @patch("src.scrapers.github_scraper.config")
    def test_search_returns_parsed_items(self, mock_config):
        mock_config.github_token = "fake-token"
        mock_config.sources = {
            "github": {
                "search_queries": ["claude code agent"],
                "tracked_repos": [],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = SEARCH_RESPONSE
        mock_client.get.return_value = mock_response

        scraper = GitHubScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 2)
        titles = [i["title"] for i in items]
        self.assertIn("anthropics/claude-code", titles)
        self.assertIn("openai/codex", titles)

    @patch("src.scrapers.github_scraper.config")
    def test_deduplication_across_queries(self, mock_config):
        """Same repo appearing in multiple queries should only appear once."""
        mock_config.github_token = "fake-token"
        mock_config.sources = {
            "github": {
                "search_queries": ["query1", "query2"],
                "tracked_repos": [],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()
        mock_response = MagicMock()
        # Both queries return the same repo
        mock_response.json.return_value = {"total_count": 1, "items": [SAMPLE_REPO]}
        mock_client.get.return_value = mock_response

        scraper = GitHubScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 1, "Duplicate repos should be deduplicated")

    @patch("src.scrapers.github_scraper.config")
    def test_tracked_repos_are_fetched(self, mock_config):
        mock_config.github_token = "fake-token"
        mock_config.sources = {
            "github": {
                "search_queries": [],
                "tracked_repos": ["anthropics/claude-code"],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = SAMPLE_REPO
        mock_client.get.return_value = mock_response

        scraper = GitHubScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "anthropics/claude-code")

    @patch("src.scrapers.github_scraper.config")
    def test_handles_api_error_gracefully(self, mock_config):
        """Scraper should not crash on API errors."""
        mock_config.github_token = ""
        mock_config.sources = {
            "github": {
                "search_queries": ["test"],
                "tracked_repos": [],
            }
        }
        mock_config.proxy_enabled = False
        mock_config.brightdata_api_key = ""

        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("403 Forbidden")

        scraper = GitHubScraper(http_client=mock_client)
        items = scraper.scrape()

        self.assertEqual(len(items), 0, "Should return empty list on API error")


if __name__ == "__main__":
    unittest.main()
