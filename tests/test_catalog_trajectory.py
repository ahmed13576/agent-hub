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

from src.pipeline import Pipeline
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

class TestPipelineTrajectory:
    """Verify trajectory of catalog generation via pipeline integration."""

    @patch("src.pipeline.Pipeline._run_scrapers")
    @patch("src.enrichment.processor.EnrichmentProcessor.enrich_batch")
    @patch("src.pipeline.Pipeline._load_database")
    @patch("src.pipeline.Pipeline._save_to_database")
    def test_pipeline_generates_catalog_with_enriched_items(
        self, mock_save, mock_load, mock_enrich, mock_scrape, enriched_items, tmp_path
    ):
        """Pipeline with generate=True passes enriched items to generator and writes curated_strategies.json."""
        # Scraper returns the raw version of the items (strip enrichment fields)
        raw_items = []
        for item in enriched_items:
            raw = item.copy()
            raw.pop("enriched_at", None)
            raw.pop("relevance_score", None)
            raw.pop("category", None)
            raw.pop("summary", None)
            raw.pop("enriched_tags", None)
            raw.pop("effectiveness_score", None)
            raw_items.append(raw)
            
        mock_scrape.return_value = raw_items
        mock_enrich.return_value = enriched_items
        mock_load.return_value = enriched_items
        
        # Patch paths to use tmp_path
        curated_path = tmp_path / "curated.json"
        with patch("src.generator.curated_filter.DEFAULT_CURATED_PATH", curated_path), \
             patch("src.generator.catalog.PROJECT_ROOT", tmp_path):
             
            pipeline = Pipeline()
            pipeline._db_path = tmp_path / "database.json"
            pipeline._discovered_path = tmp_path / "discovered.json"
            
            stats = pipeline.run(enrich=True, generate=True)
            
            assert "catalog_stats" in stats
            
            # 1. Verify Curated File Written
            assert curated_path.exists(), "curated_strategies.json was not created"
            with open(curated_path, "r", encoding="utf-8") as f:
                curated_saved = json.load(f)
                
            curated_ids = {item["id"] for item in curated_saved}
            # 2. Verify includes high relevance (e.g. bt-001) and excludes low relevance (e.g. noise-001)
            assert "bt-001" in curated_ids, "High relevance item missing from curated file"
            assert "noise-001" not in curated_ids, "Low relevance item should be filtered out"
            
            # 3. Verify Generator receives enriched data
            for item in curated_saved:
                assert "enriched_at" in item, f"Item {item['title']} missing enriched_at"
                assert item["relevance_score"] >= 0.5
                
            # Verify Markdown files generated
            assert (tmp_path / "README.md").exists()
            assert (tmp_path / "docs" / "battle-tested.md").exists()


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
