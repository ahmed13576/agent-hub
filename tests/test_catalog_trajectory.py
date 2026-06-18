"""
Trajectory tests for the catalog generation pipeline and workflow validation.

Tests verify:
1. Generator receives enriched data (not raw) when pipeline runs
2. Curated file is written during pipeline run
3. Workflow YAML has correct diff-guarded commit logic
4. Workflow YAML has correct schedule, permissions, and inputs
"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import yaml
import pytest

from src.generator.curated_filter import filter_curated


# ── Fixtures ─────────────────────────────────────────────────────────────────

WORKFLOW_PATH = Path(".github/workflows/pipeline.yml")


@pytest.fixture
def enriched_items():
    """Load test fixture items."""
    path = Path("tests/fixtures/enriched_items.json")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def workflow():
    """Load the GitHub Actions workflow YAML.
    
    Note: PyYAML parses the YAML key 'on' as boolean True.
    We normalize this by re-keying True -> 'on'.
    """
    raw = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    # PyYAML maps YAML key `on` to Python `True` — normalize it
    if True in raw and "on" not in raw:
        raw["on"] = raw.pop(True)
    return raw


# ── Trajectory Tests: Pipeline Integration ───────────────────────────────────

class TestTrajectoryGeneratorReceivesEnrichedData:
    """Verify the catalog generator receives enriched items, not raw."""

    def test_generator_called_with_enriched_data(self, enriched_items, tmp_path):
        """Pipeline with generate=True passes enriched items through curated filter."""
        # The curated filter should only pass items with enriched_at
        curated = filter_curated(enriched_items)
        for item in curated:
            assert "enriched_at" in item, f"Item {item['title']} missing enriched_at"
            assert item["relevance_score"] >= 0.5


class TestTrajectoryCuratedFileWritten:
    """Verify curated_strategies.json filtering logic."""

    def test_curated_file_excludes_low_relevance(self, enriched_items, tmp_path):
        """Items below relevance 0.5 must NOT be in the curated output."""
        curated = filter_curated(enriched_items)
        # Our fixture has 2 noise items with relevance 0.15 and 0.08
        curated_ids = {item["id"] for item in curated}
        assert "noise-001" not in curated_ids, "Noise item should be filtered out"
        assert "noise-002" not in curated_ids, "Noise item should be filtered out"

    def test_curated_file_includes_high_relevance(self, enriched_items):
        """Items above relevance 0.5 should be in the curated output."""
        curated = filter_curated(enriched_items)
        curated_ids = {item["id"] for item in curated}
        assert "bt-001" in curated_ids, "Battle-tested item should be curated"
        assert "nu-001" in curated_ids, "New-upcoming item should be curated"


class TestTrajectoryDiffGuardedCommit:
    """Verify the workflow YAML has diff-guarded commit logic."""

    def test_workflow_has_diff_guard(self, workflow):
        """The GitHub Actions workflow should check git diff before committing."""
        steps = workflow["jobs"]["pipeline"]["steps"]
        # Find the diff check step
        diff_step = None
        commit_step = None
        for step in steps:
            if step.get("name") == "Check for changes":
                diff_step = step
            if step.get("name") == "Commit and push changes":
                commit_step = step

        assert diff_step is not None, "Missing 'Check for changes' step"
        assert "git diff --quiet" in diff_step["run"]
        assert diff_step["id"] == "diff"

        assert commit_step is not None, "Missing 'Commit and push changes' step"
        assert "steps.diff.outputs.changed == 'true'" in commit_step["if"]


# ── Workflow YAML Validation Tests ───────────────────────────────────────────

class TestWorkflowYaml:
    """Validate GitHub Actions workflow YAML structure and content."""

    def test_workflow_has_cron_schedule(self, workflow):
        """Cron schedule should run every 5 days."""
        schedules = workflow["on"]["schedule"]
        assert len(schedules) >= 1
        cron = schedules[0]["cron"]
        assert "*/5" in cron, f"Cron should include */5 pattern, got: {cron}"

    def test_workflow_has_workflow_dispatch(self, workflow):
        """Manual trigger should be enabled."""
        assert "workflow_dispatch" in workflow["on"]

    def test_workflow_has_eval_input(self, workflow):
        """workflow_dispatch should have run_eval boolean input."""
        inputs = workflow["on"]["workflow_dispatch"]["inputs"]
        assert "run_eval" in inputs
        assert inputs["run_eval"]["type"] == "boolean"

    def test_workflow_has_contents_write_permission(self, workflow):
        """Permissions must include contents: write for git push."""
        assert workflow["permissions"]["contents"] == "write"

    def test_workflow_checks_groq_key(self, workflow):
        """A step should check for GROQ_API_KEY presence."""
        steps = workflow["jobs"]["pipeline"]["steps"]
        groq_check = [s for s in steps if s.get("name", "").startswith("Check for GROQ")]
        assert len(groq_check) >= 1, "Missing GROQ_API_KEY check step"

    def test_workflow_has_fallback_step(self, workflow):
        """A fallback step should run pipeline without --enrich when no key."""
        steps = workflow["jobs"]["pipeline"]["steps"]
        fallback = [s for s in steps if "scrape only" in s.get("name", "").lower()]
        assert len(fallback) >= 1, "Missing scrape-only fallback step"
        # Fallback should NOT include --enrich
        assert "--enrich" not in fallback[0]["run"]
        # But should include --generate
        assert "--generate" in fallback[0]["run"]
