"""
Unit tests for the EnrichmentProcessor.

All tests use mocked GroqClient — no actual Groq API calls.
Tests validate: enrichment output, skip logic, score clamping,
tag filtering, error handling, batch resilience, and stats tracking.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.enrichment.processor import EnrichmentProcessor
from src.enrichment.schema import VALID_TAGS


# ── Helpers ──────────────────────────────────────────────────────────────────

def _mock_llm_response() -> dict:
    """Return a valid enrichment JSON that the mocked LLM would return."""
    return {
        "summary": "A " * 30 + "comprehensive tool for agentic AI coding workflows.",
        "category": "battle-tested",
        "effectiveness_score": 0.85,
        "relevance_score": 0.9,
        "enriched_tags": ["multi-agent", "frameworks"],
    }


def _sample_item(title="Test Repo", url="https://github.com/test/repo") -> dict:
    """Return a minimal valid scraped item dict."""
    return {
        "id": "abc123",
        "source": "github",
        "title": title,
        "url": url,
        "description": "A test repository for AI coding agents.",
        "author": "testuser",
        "metadata": {"stars": 100},
        "tags": ["test", "ai"],
        "scraped_at": "2026-06-13T10:00:00Z",
        "raw_content": "Full content of the test repo with details about AI coding agents.",
    }


def _make_processor(llm_response=None, side_effect=None) -> tuple[EnrichmentProcessor, MagicMock]:
    """Create a processor with a mocked Groq client."""
    mock_groq = MagicMock()
    mock_groq.model = "test-model"
    mock_groq.fallback_model = "fallback-model"

    if side_effect:
        mock_groq.analyze_json.side_effect = side_effect
    else:
        mock_groq.analyze_json.return_value = llm_response or _mock_llm_response()

    processor = EnrichmentProcessor(groq_client=mock_groq)
    return processor, mock_groq


# ── TestEnrichItem ───────────────────────────────────────────────────────────

class TestEnrichItem:
    """Unit tests for enrich_item()."""

    def test_enrich_item_returns_all_fields(self):
        processor, _ = _make_processor()
        item = _sample_item()
        result = processor.enrich_item(item)

        # 10 original + 5 LLM + 3 system = 18
        assert len(result) == 18, f"Expected 18 fields, got {len(result)}: {list(result.keys())}"
        assert "summary" in result
        assert "category" in result
        assert "effectiveness_score" in result
        assert "relevance_score" in result
        assert "enriched_tags" in result
        assert "enriched_at" in result
        assert "model_used" in result
        assert "enrichment_version" in result

    def test_enrich_item_skips_already_enriched(self):
        processor, mock_groq = _make_processor()
        item = _sample_item()
        item["enriched_at"] = "2026-06-13T10:00:00Z"

        result = processor.enrich_item(item)

        mock_groq.analyze_json.assert_not_called()
        assert result == item
        assert processor.skipped_count == 1

    def test_enrich_item_clamps_out_of_range_scores(self):
        response = _mock_llm_response()
        response["effectiveness_score"] = 1.5  # Out of range
        response["relevance_score"] = -0.3     # Out of range

        processor, _ = _make_processor(llm_response=response)
        result = processor.enrich_item(_sample_item())

        assert result["effectiveness_score"] == 1.0, "Score should be clamped to 1.0"
        assert result["relevance_score"] == 0.0, "Score should be clamped to 0.0"

    def test_enrich_item_filters_invalid_tags(self):
        response = _mock_llm_response()
        response["enriched_tags"] = ["multi-agent", "invalid-tag-xyz", "frameworks"]

        processor, _ = _make_processor(llm_response=response)
        result = processor.enrich_item(_sample_item())

        assert "invalid-tag-xyz" not in result["enriched_tags"]
        assert "multi-agent" in result["enriched_tags"]
        assert "frameworks" in result["enriched_tags"]

    def test_enrich_item_handles_llm_error(self):
        processor, _ = _make_processor(side_effect=Exception("API unavailable"))
        item = _sample_item()
        result = processor.enrich_item(item)

        assert "enrichment_error" in result
        assert "API unavailable" in result["enrichment_error"]
        assert processor.failed_count == 1

    def test_enrich_item_normalizes_category(self):
        response = _mock_llm_response()
        response["category"] = "Battle-Tested"  # Wrong case

        processor, _ = _make_processor(llm_response=response)
        result = processor.enrich_item(_sample_item())

        assert result["category"] == "battle-tested"

    def test_enrich_item_handles_tags_key_from_llm(self):
        """LLM might return 'tags' instead of 'enriched_tags' — processor should handle it."""
        response = _mock_llm_response()
        # Simulate LLM returning 'tags' instead of 'enriched_tags'
        response["tags"] = response.pop("enriched_tags")

        processor, _ = _make_processor(llm_response=response)
        result = processor.enrich_item(_sample_item())

        assert "enriched_tags" in result
        assert result["enriched_tags"] == ["multi-agent", "frameworks"]


# ── TestEnrichBatch ──────────────────────────────────────────────────────────

class TestEnrichBatch:
    """Unit tests for enrich_batch()."""

    def test_batch_processes_all_items(self):
        processor, _ = _make_processor()
        items = [_sample_item(f"Repo {i}", f"https://example.com/{i}") for i in range(3)]

        results = processor.enrich_batch(items)

        assert len(results) == 3

    def test_batch_continues_on_failure(self):
        """If item 2 of 3 fails, all 3 should still be returned."""
        responses = [
            _mock_llm_response(),
            Exception("Item 2 failed"),
            _mock_llm_response(),
        ]

        processor, mock_groq = _make_processor()
        mock_groq.analyze_json.side_effect = responses

        items = [_sample_item(f"Repo {i}", f"https://example.com/{i}") for i in range(3)]
        results = processor.enrich_batch(items)

        assert len(results) == 3, "All 3 items should be returned even if 1 fails"
        assert "enrichment_error" in results[1], "Failed item should have error field"
        assert "enrichment_error" not in results[0], "Successful item should not have error"
        assert "enrichment_error" not in results[2], "Successful item should not have error"

    def test_batch_stats_are_correct(self):
        responses = [
            _mock_llm_response(),  # Success
            Exception("fail"),     # Failure
            _mock_llm_response(),  # Success
        ]

        processor, mock_groq = _make_processor()
        mock_groq.analyze_json.side_effect = responses

        items = [_sample_item(f"Repo {i}", f"https://example.com/{i}") for i in range(3)]
        processor.enrich_batch(items)

        stats = processor.get_stats()
        assert stats["enriched"] == 2
        assert stats["failed"] == 1
        assert stats["skipped"] == 0

    def test_batch_calls_progress_callback(self):
        processor, _ = _make_processor()
        items = [_sample_item(f"Repo {i}", f"https://example.com/{i}") for i in range(3)]

        callback_calls = []
        def callback(current, total):
            callback_calls.append((current, total))

        processor.enrich_batch(items, progress_callback=callback)

        assert len(callback_calls) == 3
        assert callback_calls[0] == (1, 3)
        assert callback_calls[1] == (2, 3)
        assert callback_calls[2] == (3, 3)


# ── TestEnrichItemEdgeCases ──────────────────────────────────────────────────

class TestEnrichItemEdgeCases:
    """Edge case tests for enrich_item()."""

    def test_empty_raw_content(self):
        processor, _ = _make_processor()
        item = _sample_item()
        item["raw_content"] = ""

        result = processor.enrich_item(item)
        assert "enrichment_error" not in result  # Should still process

    def test_very_long_content_truncated(self):
        """Very long content should be truncated in the prompt, not cause errors."""
        processor, mock_groq = _make_processor()
        item = _sample_item()
        item["raw_content"] = "x" * 100000

        processor.enrich_item(item)

        # Verify the prompt sent to LLM was truncated
        call_args = mock_groq.analyze_json.call_args
        user_message = call_args.kwargs.get("user_message") or call_args.args[0]
        assert len(user_message) < 100000, "Prompt should be truncated"
        assert "... [truncated]" in user_message
