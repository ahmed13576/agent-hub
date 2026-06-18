"""
Trajectory tests for the enrichment pipeline.

These tests verify the PROCESS is correct (right prompt sent, rate limiting,
fallback, version tracking) — not just the output. They use mocked LLM calls
to verify the system follows the expected trajectory.
"""

from unittest.mock import MagicMock

import pytest

from src.enrichment.processor import EnrichmentProcessor
from src.enrichment.prompts import SYSTEM_PROMPT, get_prompt_version


# ── Helper: valid LLM response ──────────────────────────────────────────────

def _mock_llm_response() -> dict:
    """Return a valid enrichment JSON that the mocked LLM would return."""
    return {
        "summary": "A " * 30 + "comprehensive tool for agentic AI coding workflows.",
        "category": "battle-tested",
        "effectiveness_score": 0.85,
        "relevance_score": 0.9,
        "enriched_tags": ["multi-agent", "frameworks"],
    }


def _sample_item() -> dict:
    """Return a minimal valid scraped item dict."""
    return {
        "id": "abc123",
        "source": "github",
        "title": "Test Repo",
        "url": "https://github.com/test/repo",
        "description": "A test repository for AI coding agents.",
        "author": "testuser",
        "metadata": {"stars": 100},
        "tags": ["test", "ai"],
        "scraped_at": "2026-06-13T10:00:00Z",
        "raw_content": "Full content of the test repo with details about AI coding agents.",
    }


# ── Trajectory Tests ─────────────────────────────────────────────────────────

class TestTrajectoryCorrectPromptSent:
    """Verify the processor sends the correct prompt to the LLM."""

    def test_system_prompt_matches_template(self):
        """The system prompt sent to Groq must match SYSTEM_PROMPT."""
        mock_groq = MagicMock()
        mock_groq.analyze_json.return_value = _mock_llm_response()
        mock_groq.model = "test-model"

        processor = EnrichmentProcessor(groq_client=mock_groq)
        item = _sample_item()
        processor.enrich_item(item)

        call_args = mock_groq.analyze_json.call_args
        assert call_args is not None, "analyze_json was never called"
        # Check system_prompt kwarg
        system_prompt_sent = call_args.kwargs.get("system_prompt")
        assert system_prompt_sent == SYSTEM_PROMPT, \
            "System prompt does not match SYSTEM_PROMPT template"

    def test_user_message_contains_item_details(self):
        """The user message must contain the item's title and source."""
        mock_groq = MagicMock()
        mock_groq.analyze_json.return_value = _mock_llm_response()
        mock_groq.model = "test-model"

        processor = EnrichmentProcessor(groq_client=mock_groq)
        item = _sample_item()
        processor.enrich_item(item)

        call_args = mock_groq.analyze_json.call_args
        user_message = call_args.kwargs.get("user_message") or call_args.args[0]
        assert item["title"] in user_message, "User message missing item title"
        assert item["source"] in user_message, "User message missing item source"


class TestTrajectorySkipAlreadyEnriched:
    """Verify items with existing enrichment are skipped."""

    def test_already_enriched_item_not_sent_to_llm(self):
        """An item with enriched_at should not trigger an LLM call."""
        mock_groq = MagicMock()
        mock_groq.model = "test-model"

        processor = EnrichmentProcessor(groq_client=mock_groq)
        item = _sample_item()
        item["enriched_at"] = "2026-06-13T10:00:00Z"  # Already enriched

        result = processor.enrich_item(item)

        mock_groq.analyze_json.assert_not_called()
        assert result == item, "Already-enriched item should be returned unchanged"


class TestTrajectoryEnrichmentVersionTracked:
    """Verify enrichment version is tracked in output."""

    def test_output_contains_correct_version(self):
        """Output must contain enrichment_version matching get_prompt_version()."""
        mock_groq = MagicMock()
        mock_groq.analyze_json.return_value = _mock_llm_response()
        mock_groq.model = "test-model"

        processor = EnrichmentProcessor(groq_client=mock_groq)
        item = _sample_item()
        result = processor.enrich_item(item)

        expected_version = get_prompt_version()
        assert result.get("enrichment_version") == expected_version, \
            f"Expected version {expected_version}, got {result.get('enrichment_version')}"


class TestTrajectoryFallbackOnFailure:
    """Verify error handling on LLM failure."""

    def test_error_recorded_on_llm_failure(self):
        """When the LLM call fails entirely, enrichment_error should be set."""
        mock_groq = MagicMock()
        mock_groq.model = "primary-model"
        mock_groq.analyze_json.side_effect = RuntimeError("Groq API failed after 5 retries")

        processor = EnrichmentProcessor(groq_client=mock_groq)
        item = _sample_item()
        result = processor.enrich_item(item)

        assert "enrichment_error" in result, "Failed item should have enrichment_error"
        assert "Groq API failed" in result["enrichment_error"]
        assert processor.failed_count == 1
