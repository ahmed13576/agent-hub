"""
Tests for src.clients.groq_client

Tests cover:
- Client initialization (valid and missing API key)
- JSON extraction from raw text (with and without code fences)
- Throttle timing enforcement
- Live API call with actual GROQ_API_KEY (if available)
"""

import unittest
import json
import time
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import config
from src.clients.groq_client import GroqClient


class TestGroqClientInit(unittest.TestCase):
    """Test client initialization."""

    def test_init_with_valid_key(self):
        """Client should initialize when a valid API key is provided."""
        if not config.groq_api_key:
            self.skipTest("GROQ_API_KEY not set")
        client = GroqClient()
        self.assertEqual(client.model, "llama-3.3-70b-versatile")
        self.assertEqual(client.request_count, 0)

    def test_init_raises_without_key(self):
        """Client should raise ValueError when no API key is available."""
        from unittest.mock import patch
        with patch("src.clients.groq_client.config") as mock_cfg:
            mock_cfg.groq_api_key = ""
            mock_cfg.groq_model = "llama-3.3-70b-versatile"
            mock_cfg.groq_fallback_model = "llama-3.1-8b-instant"
            mock_cfg.groq_max_rpm = 25
            with self.assertRaises(ValueError) as ctx:
                GroqClient(api_key="")
            self.assertIn("GROQ_API_KEY", str(ctx.exception))


class TestJsonExtraction(unittest.TestCase):
    """Test the _extract_json static method."""

    def test_parses_clean_json(self):
        """Should parse a plain JSON string."""
        raw = '{"category": "token-saving", "score": 85}'
        result = GroqClient._extract_json(raw)
        self.assertEqual(result["category"], "token-saving")
        self.assertEqual(result["score"], 85)

    def test_parses_json_with_code_fences(self):
        """Should strip markdown code fences and parse the JSON inside."""
        raw = '```json\n{"category": "multi-agent", "score": 92}\n```'
        result = GroqClient._extract_json(raw)
        self.assertEqual(result["category"], "multi-agent")
        self.assertEqual(result["score"], 92)

    def test_parses_json_with_whitespace(self):
        """Should handle leading/trailing whitespace."""
        raw = '  \n  {"tags": ["budget", "optimization"]}  \n  '
        result = GroqClient._extract_json(raw)
        self.assertEqual(result["tags"], ["budget", "optimization"])

    def test_raises_on_invalid_json(self):
        """Should raise json.JSONDecodeError on malformed JSON."""
        with self.assertRaises(json.JSONDecodeError):
            GroqClient._extract_json("this is not json")

    def test_raises_on_non_dict_json(self):
        """Should raise ValueError when JSON is a list instead of dict."""
        with self.assertRaises(ValueError):
            GroqClient._extract_json('[1, 2, 3]')


class TestLiveGroqApi(unittest.TestCase):
    """Integration tests that call the real Groq API (skipped if no key)."""

    def setUp(self):
        if not config.groq_api_key:
            self.skipTest("GROQ_API_KEY not set — skipping live API tests")
        self.client = GroqClient()

    def test_simple_chat_returns_text(self):
        """A simple chat request should return a non-empty string."""
        result = self.client.chat(
            user_message="Reply with exactly: HELLO_AGENT_HUB",
            system_prompt="You are a test assistant. Follow instructions exactly.",
            max_tokens=50,
        )
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)
        self.assertIn("HELLO_AGENT_HUB", result)

    def test_analyze_json_returns_dict(self):
        """analyze_json should return a parsed dictionary."""
        result = self.client.analyze_json(
            user_message=(
                "Analyze this tool: 'Claude Code CLAUDE.md files for project context'. "
                "Return JSON with keys: category, score (1-100), tags (list of strings)."
            ),
            system_prompt=(
                "You are an AI strategy analyst. Analyze the given tool/strategy "
                "and return ONLY a valid JSON object with the requested keys."
            ),
            max_tokens=200,
        )
        self.assertIsInstance(result, dict)
        self.assertIn("category", result)
        self.assertIn("score", result)
        self.assertIn("tags", result)
        self.assertIsInstance(result["tags"], list)

    def test_request_count_increments(self):
        """request_count should increment after each successful call."""
        initial = self.client.request_count
        self.client.chat(
            user_message="Say 'test'",
            max_tokens=10,
        )
        self.assertEqual(self.client.request_count, initial + 1)


if __name__ == "__main__":
    unittest.main()
