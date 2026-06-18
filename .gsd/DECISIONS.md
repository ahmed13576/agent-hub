# DECISIONS.md

# Architecture Decision Records (ADR)

This file tracks all key architectural and design decisions made throughout the lifecycle of the project.

---

## ADR-001: Initial Project Target (Option C)

**Date:** 2026-06-13
**Status:** Accepted

### Context
We want to provide developers with a curated list of agentic AI strategies, tools, and token saving hacks. We decided to start with a GitHub Repository containing Markdown docs and a structured database (`data.json`) updated via GitHub Actions.

### Decision
We will build a serverless Python scraping and LLM-enrichment pipeline run via GitHub Actions cron. The workflow will pull from GitHub, Reddit, and Blogs, process the results using Groq API, and automatically commit the data and Markdown catalogs back to the repository.

### Consequences
- No hosting cost or server maintenance.
- Front-end developers can easily consume the output JSON to build web dashboards later.
- Limits dynamic user interactivity (e.g. user search queries must be done client-side or in the repository files).

---

## ADR-002: Hybrid Client Scraping Strategy

**Date:** 2026-06-13
**Status:** Accepted

### Context
Reddit, Medium/TDS, and Twitter/X implement different tiers of anti-scraping walls. Bright Data provides reliable bypassing tools but charges usage fees. We need a way to run the scraper completely free by default but retain the ability to route traffic through paid proxies if blocks occur.

### Decision
We will implement a hybrid HTTP client:
- **Free-by-default**: Fetch Reddit and Blog RSS feeds directly using standard HTTP requests with rotating User-Agent headers, and search GitHub using official APIs.
- **Modular proxy support**: If the `BRIGHTDATA_PROXY` environment variable is defined, the client will route blocked target URLs through Bright Data's Web Unlocker proxy. Otherwise, it defaults to direct unproxied requests.

### Consequences
- Scraping runs completely free on GitHub Actions using seed feeds.
- Zero maintenance cost for default operation.
- Easy upgrade path: setting a single secret (`BRIGHTDATA_PROXY`) in the GitHub repo activates paid bypasses for trickier sources (like Twitter) without modifying code.

---

## ADR-003: Phase 3 — AI Enrichment Architecture & Evaluation Strategy

**Date:** 2026-06-18
**Status:** Accepted

### Context
Phase 3 connects scraper output to Groq LLMs for summarization, tagging, and categorization. LLM outputs are inherently non-deterministic, so we need a robust evaluation strategy that separates testable (deterministic) parts from stochastic parts.

### Decision: Enrichment Schema
Each scraped item gets enriched with:
- `summary` (string): 2-3 sentence synopsis
- `category` (enum): `battle-tested` / `new-upcoming` / `experimental` (3-way)
- `effectiveness_score` (float 0-1): How impactful is this strategy
- `tags` (list[str]): Normalized tags (e.g., `token-saving`, `multi-agent`, `prompting`, `frameworks`, `budget-control`)
- `relevance_score` (float 0-1): How relevant to agentic AI coding
- `enriched_at` (ISO timestamp): When enrichment ran
- `model_used` (string): Which Groq model produced this
- `enrichment_version` (string): Hash of prompt template for regression tracking

### Decision: Prompt Architecture — Option C (Single Structured JSON)
One API call per item with a single prompt that asks for all fields as a JSON object. Each field is independently eval-able even though they come from one call.
- **Rationale:** Groq free-tier limits us to 25 RPM. Multi-step would require 3x calls and hit rate limits with ~450 items per run.

### Decision: Evaluation-Driven Development (EDD) — 5 Layers
1. **Unit Tests** (deterministic, no LLM): JSON schema compliance, prompt building, retry/throttle logic
2. **Contract Tests** (deterministic, mock LLM): Enrichment output matches expected schema, validators work
3. **Golden Dataset Evals** (stochastic, live LLM): ~15-20 human-labeled items scored against rubric
4. **Trajectory Evals** (deterministic, mock LLM): Correct prompt sent, rate limiting enforced, fallback triggered, enrichment version tracked
5. **Regression Evals** (stochastic, live LLM): Compare scores across prompt version changes

### Decision: CI/CD Split
- Unit + Contract + Trajectory tests → every push (free, fast, deterministic)
- Golden Dataset evals → separate weekly schedule or manual trigger only (saves Groq API credits)
- Eval results stored in `data/evals/` with timestamps

### Consequences
- Prompt changes are regression-tested against a golden dataset before deployment
- Deterministic pipeline logic has full test coverage
- LLM output quality is tracked over time via versioned eval results
- API costs for evals are controlled by running them on a separate schedule

---

## ADR-004: Phase 4 — Git-Backed Automation & Markdown Generation

**Date:** 2026-06-18
**Status:** Accepted

### Context
Phase 4 is the final phase: generate Markdown catalogs from enriched data and wire up a GitHub Actions
workflow that runs the full pipeline on a schedule and commits results back to the repo.

### Decision: Output Files
- `data/database.json` — raw scraper output (unchanged name, already exists)
- `data/curated_strategies.json` — enriched items with `relevance_score ≥ 0.5` only
- `README.md` — root catalog (auto-generated, human-readable)
- `docs/battle-tested.md`, `docs/new-upcoming.md`, `docs/experimental.md` — per-category files

### Decision: Markdown Format — Rich Table Style
Each category file uses a rich table layout:
- Columns: Title (linked), Source, Category, Relevance, Effectiveness, Tags, Summary
- Sorted by `relevance_score` descending within each file
- Root README.md contains top-10 items per category + links to full docs

### Decision: Curated Threshold
`relevance_score ≥ 0.5` → appears in `curated_strategies.json` and all markdown files.
Below 0.5 → stored in `database.json` only (available for future use, not surfaced).

### Decision: GitHub Actions Schedule
- **Cron:** Every 5 days (`0 2 */5 * *`) — saves GitHub Actions minutes vs. 48h
- **Manual trigger:** `workflow_dispatch` always enabled for ad-hoc runs
- **No push trigger** — pipeline is data-driven, not code-driven

### Decision: Git Commit Strategy — Diff-Guarded
- After generating all output files, check `git diff --quiet`
- Only commit + push if diff is non-empty
- Commit message format: `chore(data): auto-update catalog [YYYY-MM-DD] — N new items`
- Uses `GITHUB_TOKEN` with `contents: write` permission (no PAT needed)

### Decision: Groq API Key in Actions
- `GROQ_API_KEY` stored as a GitHub Actions secret
- Workflow fails gracefully (skips enrichment, still commits raw data) if key is absent
- Failure mode: log warning, set `ENRICH=false`, continue with scrape-only run

### Decision: Golden Evals — Manual-Only
- No second cron job for golden evals — keep fully manual via `workflow_dispatch` with `eval: true` input
- The workflow accepts an optional `run_eval` boolean input for one-click eval runs
- Easy to promote to a cron later by adding a second `on.schedule` block

### Decision: EDD for Phase 4
- Wave 1: Define "correct" — markdown snapshot fixtures, generator schema, trajectory stubs
- Wave 2: Build generator + CI workflow + unskip trajectory tests
- Deterministic tests: snapshot diffs, sort order, empty-category edge cases, diff-guard logic
- Trajectory tests: assert commit only runs on non-empty diff, assert correct CLI flags in workflow

### Risks & Mitigations
| Risk | Mitigation |
|------|------------|
| No GROQ_API_KEY in Actions | Graceful fallback: scrape-only run, warn in logs |
| git push requires write access | Use `GITHUB_TOKEN` with `contents: write` |
| Special chars in titles break markdown | Sanitize in generator (escape pipes, backticks) |
| Cron disabled on inactive repos | `workflow_dispatch` always available as fallback |
| First run commits very large diff | Expected — not a problem for GitHub |

