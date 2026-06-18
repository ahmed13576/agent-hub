"""
Tests for enrichment schema validation, merge logic, and prompt building.

All tests are deterministic — no LLM calls. This is the Unit + Contract
layer of the EDD evaluation harness.
"""

import json
from pathlib import Path

import pytest

from src.enrichment.schema import (
    VALID_CATEGORIES,
    VALID_TAGS,
    LLM_REQUIRED_FIELDS,
    validate_enrichment,
    merge_enrichment,
)
from src.enrichment.prompts import (
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
    build_prompt,
    get_prompt_version,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _valid_enrichment() -> dict:
    """Return a minimal valid enrichment dict."""
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


# ── TestSchemaValidation (Unit Tests) ────────────────────────────────────────

class TestSchemaValidation:
    """Unit tests for validate_enrichment()."""

    def test_valid_enrichment_passes(self):
        enrichment = _valid_enrichment()
        is_valid, errors = validate_enrichment(enrichment)
        assert is_valid is True, f"Expected valid, got errors: {errors}"
        assert errors == []

    def test_missing_field_fails(self):
        for field in LLM_REQUIRED_FIELDS:
            enrichment = _valid_enrichment()
            del enrichment[field]
            is_valid, errors = validate_enrichment(enrichment)
            assert is_valid is False, f"Missing '{field}' should fail validation"
            assert any(field in e for e in errors)

    def test_invalid_category_fails(self):
        enrichment = _valid_enrichment()
        enrichment["category"] = "invalid-category"
        is_valid, errors = validate_enrichment(enrichment)
        assert is_valid is False
        assert any("category" in e.lower() for e in errors)

    def test_score_out_of_range_high_fails(self):
        enrichment = _valid_enrichment()
        enrichment["effectiveness_score"] = 1.5
        is_valid, errors = validate_enrichment(enrichment)
        assert is_valid is False
        assert any("effectiveness_score" in e for e in errors)

    def test_score_out_of_range_low_fails(self):
        enrichment = _valid_enrichment()
        enrichment["relevance_score"] = -0.1
        is_valid, errors = validate_enrichment(enrichment)
        assert is_valid is False
        assert any("relevance_score" in e for e in errors)

    def test_invalid_tag_fails(self):
        enrichment = _valid_enrichment()
        enrichment["enriched_tags"] = ["multi-agent", "not-a-valid-tag"]
        is_valid, errors = validate_enrichment(enrichment)
        assert is_valid is False
        assert any("not-a-valid-tag" in e for e in errors)

    def test_summary_too_short_fails(self):
        enrichment = _valid_enrichment()
        enrichment["summary"] = "Too short."
        is_valid, errors = validate_enrichment(enrichment)
        assert is_valid is False
        assert any("too short" in e.lower() for e in errors)

    def test_summary_too_long_fails(self):
        enrichment = _valid_enrichment()
        enrichment["summary"] = "x" * 501
        is_valid, errors = validate_enrichment(enrichment)
        assert is_valid is False
        assert any("too long" in e.lower() for e in errors)


# ── TestMergeEnrichment (Contract Tests) ─────────────────────────────────────

class TestMergeEnrichment:
    """Contract tests for merge_enrichment()."""

    def test_merge_adds_all_enrichment_fields(self):
        item = _sample_item()
        enrichment = _valid_enrichment()
        merged = merge_enrichment(item, enrichment, model_used="llama-3.3-70b", enrichment_version="abc123def456")
        # 10 original + 5 LLM + 3 system = 18
        assert len(merged) == 18, f"Expected 18 fields, got {len(merged)}: {list(merged.keys())}"

    def test_merge_preserves_original_fields(self):
        item = _sample_item()
        enrichment = _valid_enrichment()
        merged = merge_enrichment(item, enrichment)
        for key in item:
            assert merged[key] == item[key], f"Original field '{key}' was modified"

    def test_merge_adds_system_fields(self):
        item = _sample_item()
        enrichment = _valid_enrichment()
        merged = merge_enrichment(item, enrichment, model_used="test-model", enrichment_version="v1hash")
        assert "enriched_at" in merged
        assert merged["model_used"] == "test-model"
        assert merged["enrichment_version"] == "v1hash"
        # enriched_at should be an ISO timestamp string
        assert "T" in merged["enriched_at"]

    def test_merge_does_not_mutate_input(self):
        item = _sample_item()
        item_copy = dict(item)
        enrichment = _valid_enrichment()
        merge_enrichment(item, enrichment)
        assert item == item_copy, "merge_enrichment mutated the input item"


# ── TestPromptBuilding (Unit Tests) ──────────────────────────────────────────

class TestPromptBuilding:
    """Unit tests for build_prompt() and get_prompt_version()."""

    def test_build_prompt_contains_title(self):
        item = _sample_item()
        prompt = build_prompt(item)
        assert item["title"] in prompt

    def test_build_prompt_truncates_content(self):
        item = _sample_item()
        item["raw_content"] = "x" * 10000
        prompt = build_prompt(item, max_content_chars=100)
        assert "... [truncated]" in prompt
        # The raw content in the prompt should be ~100 chars, not 10000
        assert "x" * 10000 not in prompt

    def test_build_prompt_includes_enum_values(self):
        item = _sample_item()
        prompt = build_prompt(item)
        for cat in VALID_CATEGORIES:
            assert cat in prompt, f"Category '{cat}' missing from prompt"

    def test_prompt_version_is_stable(self):
        v1 = get_prompt_version()
        v2 = get_prompt_version()
        assert v1 == v2, "Same prompt text should produce same version hash"
        assert len(v1) == 12, f"Version should be 12 hex chars, got {len(v1)}"

    def test_prompt_version_changes_on_edit(self):
        import src.enrichment.prompts as prompts_module
        original_system = prompts_module.SYSTEM_PROMPT
        v1 = get_prompt_version()
        try:
            prompts_module.SYSTEM_PROMPT = original_system + " MODIFIED"
            v2 = get_prompt_version()
            assert v1 != v2, "Modified prompt should produce different version hash"
        finally:
            prompts_module.SYSTEM_PROMPT = original_system


# ── TestGoldenDatasetIntegrity ───────────────────────────────────────────────

class TestGoldenDatasetIntegrity:
    """Verify the golden dataset file is well-formed."""

    def test_golden_dataset_loads(self):
        path = Path("data/evals/golden_dataset.json")
        assert path.exists(), "Golden dataset file missing"
        data = json.loads(path.read_text())
        assert isinstance(data, list)
        assert len(data) == 18, f"Expected 18 items, got {len(data)}"

    def test_all_items_have_expected_enrichment(self):
        data = json.loads(Path("data/evals/golden_dataset.json").read_text())
        for i, item in enumerate(data):
            assert "expected_enrichment" in item, f"Item {i} missing expected_enrichment"
            expected = item["expected_enrichment"]
            assert "expected_category" in expected, f"Item {i} missing expected_category"
            assert "expected_relevance_range" in expected, f"Item {i} missing expected_relevance_range"

    def test_all_items_have_scraper_fields(self):
        data = json.loads(Path("data/evals/golden_dataset.json").read_text())
        required = ["id", "source", "title", "url", "description", "author", "metadata", "tags", "scraped_at", "raw_content"]
        for i, item in enumerate(data):
            for field in required:
                assert field in item, f"Item {i} ('{item.get('title', '?')}') missing field: {field}"
