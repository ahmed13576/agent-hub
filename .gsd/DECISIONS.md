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
