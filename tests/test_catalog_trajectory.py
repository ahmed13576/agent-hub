"""
Trajectory tests for the catalog generation pipeline.

Tests verify the PROCESS is correct: generator receives enriched data,
curated file is written, diff-guarded commit logic is present in the workflow.

Trajectory tests depending on pipeline integration are skipped until Plan 4.2.
"""

import pytest


class TestTrajectoryGeneratorReceivesEnrichedData:
    """Verify the catalog generator receives enriched items, not raw."""

    @pytest.mark.skip(reason="Awaiting Plan 4.2 pipeline integration")
    def test_generator_called_with_enriched_data(self):
        """Pipeline with generate=True should pass enriched items to the catalog."""
        pass  # Implementation in Plan 4.2


class TestTrajectoryCuratedFileWritten:
    """Verify curated_strategies.json is written during pipeline run."""

    @pytest.mark.skip(reason="Awaiting Plan 4.2 pipeline integration")
    def test_curated_file_exists_after_pipeline(self):
        """Pipeline with generate=True should create curated_strategies.json."""
        pass  # Implementation in Plan 4.2


class TestTrajectoryDiffGuardedCommit:
    """Verify the workflow YAML has diff-guarded commit logic."""

    @pytest.mark.skip(reason="Awaiting Plan 4.2 workflow integration")
    def test_workflow_has_diff_guard(self):
        """The GitHub Actions workflow should check git diff before committing."""
        pass  # Implementation in Plan 4.2
