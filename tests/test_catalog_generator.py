"""
Tests for the markdown catalog generator and curated filter.

All tests are deterministic — no LLM or network calls.
Uses the fixture file tests/fixtures/enriched_items.json.
"""

import json
from pathlib import Path

import pytest

from src.generator.curated_filter import (
    CURATED_RELEVANCE_THRESHOLD,
    filter_curated,
    save_curated_strategies,
    load_curated_strategies,
)
from src.generator.catalog import (
    CATEGORY_FILES,
    sanitize_markdown,
    generate_category_table,
    generate_category_file,
    generate_readme,
    write_catalog,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def enriched_items():
    """Load the test fixture with 10 enriched items."""
    path = Path("tests/fixtures/enriched_items.json")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def curated_items(enriched_items):
    """Return only items that pass the curated filter (relevance >= 0.5)."""
    return filter_curated(enriched_items)


# ── TestCuratedFilter ────────────────────────────────────────────────────────

class TestCuratedFilter:
    """Tests for filter_curated()."""

    def test_filters_by_relevance_threshold(self, enriched_items):
        result = filter_curated(enriched_items)
        for item in result:
            assert item["relevance_score"] >= CURATED_RELEVANCE_THRESHOLD, \
                f"Item '{item['title']}' has relevance {item['relevance_score']} < threshold"

    def test_excludes_unenriched_items(self):
        items = [
            {"title": "Raw", "relevance_score": 0.9},  # No enriched_at
            {"title": "Enriched", "relevance_score": 0.9, "enriched_at": "2026-01-01T00:00:00Z"},
        ]
        result = filter_curated(items)
        assert len(result) == 1
        assert result[0]["title"] == "Enriched"

    def test_does_not_mutate_input(self, enriched_items):
        original = list(enriched_items)
        filter_curated(enriched_items)
        assert enriched_items == original

    def test_empty_input_returns_empty(self):
        assert filter_curated([]) == []

    def test_all_below_threshold_returns_empty(self):
        items = [
            {"title": "Low", "relevance_score": 0.1, "enriched_at": "2026-01-01T00:00:00Z"},
            {"title": "Lower", "relevance_score": 0.2, "enriched_at": "2026-01-01T00:00:00Z"},
        ]
        assert filter_curated(items) == []

    def test_save_and_load_curated(self, enriched_items, tmp_path):
        out_path = tmp_path / "curated.json"
        save_curated_strategies(enriched_items, path=out_path)
        loaded = load_curated_strategies(path=out_path)
        assert len(loaded) == len(filter_curated(enriched_items))

    def test_load_missing_file_returns_empty(self, tmp_path):
        result = load_curated_strategies(path=tmp_path / "nonexistent.json")
        assert result == []


# ── TestSanitizeMarkdown ─────────────────────────────────────────────────────

class TestSanitizeMarkdown:
    """Tests for sanitize_markdown()."""

    def test_escapes_pipe_characters(self):
        result = sanitize_markdown("Token | Best Practices")
        assert "|" not in result or "\\|" in result
        assert "\\|" in result

    def test_strips_newlines(self):
        result = sanitize_markdown("Line one\nLine two\nLine three")
        assert "\n" not in result
        assert "Line one" in result and "Line two" in result

    def test_truncates_long_summary(self):
        long_text = "x" * 200
        result = sanitize_markdown(long_text, max_length=150)
        assert len(result) <= 150
        assert result.endswith("...")

    def test_short_summary_unchanged(self):
        short = "This is fine."
        assert sanitize_markdown(short) == short


# ── TestCategoryTable ────────────────────────────────────────────────────────

class TestCategoryTable:
    """Tests for generate_category_table()."""

    def test_table_has_correct_columns(self, curated_items):
        table = generate_category_table(curated_items, "battle-tested")
        assert "| Title |" in table
        assert "| Source |" in table or "Source" in table
        assert "Relevance" in table
        assert "Effectiveness" in table
        assert "Tags" in table
        assert "Summary" in table

    def test_items_sorted_by_relevance_desc(self, curated_items):
        table = generate_category_table(curated_items, "battle-tested")
        lines = [l for l in table.strip().split("\n") if l.startswith("| [")]
        # Extract relevance scores from table rows
        scores = []
        for line in lines:
            cells = line.split("|")
            # Relevance is the 4th cell (index 3)
            if len(cells) >= 5:
                try:
                    scores.append(float(cells[3].strip()))
                except ValueError:
                    pass
        assert scores == sorted(scores, reverse=True), f"Scores not sorted desc: {scores}"

    def test_title_is_markdown_link(self, curated_items):
        table = generate_category_table(curated_items, "battle-tested")
        # Should contain [title](url) pattern
        assert "](https://" in table

    def test_empty_category_shows_message(self, curated_items):
        table = generate_category_table(curated_items, "nonexistent-category")
        assert "No items yet" in table

    def test_tags_are_comma_separated(self, curated_items):
        table = generate_category_table(curated_items, "battle-tested")
        # The first battle-tested item has tags ["configuration", "prompting"]
        assert "configuration, prompting" in table

    def test_special_chars_sanitized(self):
        items = [{
            "category": "test",
            "title": "Token | Pipes",
            "url": "https://example.com",
            "source": "github",
            "relevance_score": 0.9,
            "effectiveness_score": 0.8,
            "enriched_tags": ["token-saving"],
            "summary": "Test with | pipes in summary",
        }]
        table = generate_category_table(items, "test")
        # The raw pipe in the title should be escaped
        assert "Token \\| Pipes" in table


# ── TestCategoryFile ─────────────────────────────────────────────────────────

class TestCategoryFile:
    """Tests for generate_category_file()."""

    def test_file_has_header(self, curated_items):
        content = generate_category_file(curated_items, "battle-tested", generated_at="2026-06-18")
        assert "# Battle-Tested Strategies" in content

    def test_file_has_table(self, curated_items):
        content = generate_category_file(curated_items, "battle-tested", generated_at="2026-06-18")
        assert "| Title |" in content

    def test_file_has_footer(self, curated_items):
        content = generate_category_file(curated_items, "battle-tested", generated_at="2026-06-18")
        assert "Auto-generated by Agent Hub" in content
        assert "2026-06-18" in content


# ── TestReadmeGeneration ─────────────────────────────────────────────────────

class TestReadmeGeneration:
    """Tests for generate_readme()."""

    def test_readme_has_title(self, curated_items):
        readme = generate_readme(curated_items, generated_at="2026-06-18")
        assert "# 🤖 Agent Hub" in readme

    def test_readme_has_stats(self, curated_items):
        readme = generate_readme(curated_items, generated_at="2026-06-18")
        assert "Total curated items" in readme
        assert str(len(curated_items)) in readme

    def test_readme_has_category_sections(self, curated_items):
        readme = generate_readme(curated_items, generated_at="2026-06-18")
        assert "## Battle-Tested" in readme
        assert "## New & Upcoming" in readme
        assert "## Experimental" in readme

    def test_readme_links_to_category_files(self, curated_items):
        readme = generate_readme(curated_items, generated_at="2026-06-18")
        for filepath in CATEGORY_FILES.values():
            assert filepath in readme, f"Missing link to {filepath}"

    def test_readme_top_10_limit(self):
        # Create 15 items in one category
        items = []
        for i in range(15):
            items.append({
                "category": "battle-tested",
                "title": f"Item {i}",
                "url": f"https://example.com/{i}",
                "source": "github",
                "relevance_score": 0.9 - (i * 0.01),
                "effectiveness_score": 0.8,
                "enriched_tags": [],
                "summary": f"Summary for item {i} in the collection.",
            })
        readme = generate_readme(items, generated_at="2026-06-18")
        # Count data rows in the battle-tested section (between ## Battle-Tested and next ##)
        bt_section = readme.split("## Battle-Tested")[1].split("##")[0]
        data_rows = [l for l in bt_section.split("\n") if l.startswith("| [")]
        assert len(data_rows) <= 10, f"README should show at most 10 items, got {len(data_rows)}"


# ── TestWriteCatalog ─────────────────────────────────────────────────────────

class TestWriteCatalog:
    """Tests for write_catalog() — filesystem tests."""

    def test_creates_readme_file(self, curated_items, tmp_path):
        write_catalog(curated_items, output_dir=tmp_path, generated_at="2026-06-18")
        assert (tmp_path / "README.md").exists()

    def test_creates_category_files(self, curated_items, tmp_path):
        write_catalog(curated_items, output_dir=tmp_path, generated_at="2026-06-18")
        for filepath in CATEGORY_FILES.values():
            assert (tmp_path / filepath).exists(), f"Missing: {filepath}"

    def test_creates_docs_directory(self, curated_items, tmp_path):
        write_catalog(curated_items, output_dir=tmp_path, generated_at="2026-06-18")
        assert (tmp_path / "docs").is_dir()

    def test_returns_stats(self, curated_items, tmp_path):
        stats = write_catalog(curated_items, output_dir=tmp_path, generated_at="2026-06-18")
        assert stats["readme_written"] is True
        assert stats["category_files"] == 3
        assert stats["total_items"] == len(curated_items)
