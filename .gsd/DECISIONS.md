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

