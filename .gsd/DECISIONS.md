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
