# Debug Session: Trajectory Tests Missing Actual Trajectory

## Symptom
Plan 4.2 Task 3 specified trajectory tests that verify the full pipeline by mocking scrapers and the GroqClient, running `pipeline.run(enrich=True, generate=True)`, and asserting the `curated_strategies.json` was written with the expected items.
**When:** Running the pipeline trajectory tests.
**Expected:** The tests should simulate a real run by mocking out external calls and asserting pipeline behavior.
**Actual:** The implemented tests bypassed the pipeline entirely and just called `filter_curated(enriched_items)` on a fixture, totally bypassing the pipeline, mock scrapers, and mock Groq client. Thus, the trajectory tests were missing the actual trajectory simulation.

## Hypotheses

| # | Hypothesis | Likelihood | Status |
|---|------------|------------|--------|
| 1 | The tests were written as unit tests for the filter rather than trajectory tests for the pipeline. Rewriting them to patch pipeline dependencies and instantiate the `Pipeline` class will fulfill the spec. | 100% | CONFIRMED |

## Attempts

### Attempt 1
**Testing:** H1 — The tests were written as unit tests for the filter rather than trajectory tests for the pipeline.
**Action:** Wrote `scratch/debug_trajectory.py` using `patch("src.pipeline.Pipeline._run_scrapers")` and `Pipeline.run(enrich=True, generate=True)`.
**Result:** Passed.
**Conclusion:** CONFIRMED

## Resolution

**Root Cause:** The trajectory tests implemented during Plan 4.2 Wave 2 Task 3 skipped the actual pipeline implementation.
**Fix:** Rewrite `TestTrajectoryGeneratorReceivesEnrichedData` and `TestTrajectoryCuratedFileWritten` to use `pipeline.run()` directly with mocked dependencies.
**Verified:** Running `pytest scratch/debug_trajectory.py`. Will apply to `tests/test_catalog_trajectory.py` and commit.
**Regression Check:** Entire test suite.
