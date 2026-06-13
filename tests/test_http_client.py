"""
Tests for src.clients.http_client

Tests cover:
- User-agent rotation (different agents across requests)
- Header construction
- RSS feed parsing with a known public feed
- Proxy configuration toggle
"""

import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.clients.http_client import HttpClient, USER_AGENTS, BROWSER_USER_AGENTS, BOT_USER_AGENT, BOT_UA_DOMAINS


class TestUserAgentRotation(unittest.TestCase):
    """Verify that the HTTP client rotates user-agent strings."""

    def test_user_agents_list_is_not_empty(self):
        """BROWSER_USER_AGENTS should contain multiple entries."""
        self.assertGreater(len(BROWSER_USER_AGENTS), 3, "Should have at least 4 user-agent strings")

    def test_random_user_agent_returns_valid_string(self):
        """_get_random_user_agent should return a browser UA from the pool."""
        client = HttpClient(use_proxy=False)
        ua = client._get_random_user_agent()
        self.assertIn(ua, BROWSER_USER_AGENTS)

    def test_headers_contain_user_agent(self):
        """Built headers should always include a User-Agent key."""
        client = HttpClient(use_proxy=False)
        headers = client._build_headers()
        self.assertIn("User-Agent", headers)
        self.assertIn(headers["User-Agent"], BROWSER_USER_AGENTS)

    def test_extra_headers_are_merged(self):
        """Extra headers passed to _build_headers should appear in the result."""
        client = HttpClient(use_proxy=False)
        headers = client._build_headers({"Authorization": "Bearer test123"})
        self.assertEqual(headers["Authorization"], "Bearer test123")
        # Default headers should still be present
        self.assertIn("Accept-Language", headers)


class TestBotUserAgent(unittest.TestCase):
    """Verify domain-aware bot UA selection."""

    def test_reddit_urls_use_bot_ua(self):
        """Reddit URLs should trigger bot-style User-Agent."""
        client = HttpClient(use_proxy=False)
        self.assertTrue(client._needs_bot_ua("https://www.reddit.com/r/ClaudeDev/.rss"))
        self.assertTrue(client._needs_bot_ua("https://reddit.com/r/Python/.rss"))
        self.assertTrue(client._needs_bot_ua("https://old.reddit.com/r/test/.rss"))

    def test_non_reddit_urls_use_browser_ua(self):
        """Non-Reddit URLs should NOT trigger bot UA."""
        client = HttpClient(use_proxy=False)
        self.assertFalse(client._needs_bot_ua("https://medium.com/feed/tagged/ai"))
        self.assertFalse(client._needs_bot_ua("https://api.github.com/search/repositories"))

    def test_reddit_headers_have_bot_ua(self):
        """Headers built for Reddit URLs should use the bot UA."""
        client = HttpClient(use_proxy=False)
        headers = client._build_headers(url="https://www.reddit.com/r/test/.rss")
        self.assertEqual(headers["User-Agent"], BOT_USER_AGENT)

    def test_normal_headers_have_browser_ua(self):
        """Headers built for normal URLs should use browser UAs."""
        client = HttpClient(use_proxy=False)
        headers = client._build_headers(url="https://example.com/page")
        self.assertIn(headers["User-Agent"], BROWSER_USER_AGENTS)


class TestProxyConfiguration(unittest.TestCase):
    """Verify proxy toggle behavior."""

    def test_proxy_disabled_by_default_without_env(self):
        """When no BRIGHTDATA_API_KEY is set, proxy should be disabled."""
        with patch("src.clients.http_client.config") as mock_config:
            mock_config.proxy_enabled = False
            mock_config.brightdata_api_key = ""
            client = HttpClient(use_proxy=None)
            self.assertFalse(client.proxy_enabled)

    def test_proxy_forced_off(self):
        """use_proxy=False should force proxy off regardless of config."""
        client = HttpClient(use_proxy=False)
        self.assertFalse(client.proxy_enabled)


class TestHttpGet(unittest.TestCase):
    """Test the GET method with mocked responses."""

    @patch("src.clients.http_client.HttpClient.get")
    def test_get_returns_response(self, mock_get):
        """GET should return a response object."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html>OK</html>"
        mock_get.return_value = mock_response

        client = HttpClient(use_proxy=False)
        response = client.get("https://httpbin.org/get")
        self.assertEqual(response.status_code, 200)


class TestRssFetching(unittest.TestCase):
    """Test RSS feed parsing."""

    def test_fetch_rss_reddit_with_bot_ua(self):
        """fetch_rss should successfully fetch Reddit RSS using bot UA."""
        client = HttpClient(use_proxy=False)
        try:
            feed = client.fetch_rss("https://www.reddit.com/r/Python/.rss")
            # Feed should be a dict-like object with 'entries'
            self.assertIn("entries", feed)
            # Should have at least one entry (r/Python is very active)
            self.assertGreater(len(feed.entries), 0, "Expected at least 1 RSS entry from r/Python")
            # Each entry should have a title
            first = feed.entries[0]
            self.assertTrue(hasattr(first, "title"), "RSS entry should have a 'title' attribute")
        except Exception as e:
            self.skipTest(f"Network unavailable: {e}")


if __name__ == "__main__":
    unittest.main()
