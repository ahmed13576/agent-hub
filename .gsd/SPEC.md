# SPEC.md — Project Specification

> **Status**: `FINALIZED`

## Vision
A self-updating GitHub repository and database that automatically scrapes, categorizes, and curates techniques, tools, and strategies for utilizing AI coding agents (like Claude Code, Cursor, Gemini Code CLI, etc.) effectively, optimizing token use, preventing resource/budget wastage, and orchestrating multi-agent setups.

## Goals
1. **Automated Scraping Pipeline**: Create a robust scraping system that runs every other day to extract posts, discussions, repositories, and blogs about agentic AI practices.
2. **Multi-Source Scraping**: Scrape GitHub (repos, discussions), Reddit (r/ClaudeDev, r/LocalLLaMA), tech blogs (Towards Data Science, Analytics India Mag), and investigate Twitter/X and Bright Data tools.
3. **AI Enrichment with Groq**: Analyze and enrich scraped data using Groq's LLM APIs (automatically summarising, tagging, classifying, and rating).
4. **Dynamic Source Discovery**: Implement mechanism to scan and capture new sources dynamically during runs to prevent missing new platforms.
5. **Curation System**: Categorize findings into "battle-tested" vs "new/upcoming" strategies, with tags for "token-saving", "budget-control", "multi-agent", "prompting", and "frameworks".
6. **Git-backed Storage**: Run as a serverless GitHub Actions cron workflow that commits the structured database (`data.json`) and generated Markdown documentation back to the repository.

## Non-Goals (Out of Scope for v1)
- Building a custom web dashboard/app frontend (will start purely with GitHub Markdown and JSON files; web dashboard is for a later milestone).
- User authentication, bookmarks, or user-submitted strategies (everything is curated automatically).
- Paid/expensive proxy networks unless explicitly required and configured.

## Users
Developers, AI engineers, and prompt engineers who want a central, searchable, and auto-updating hub of best practices and toolkits to optimize their use of agentic coding systems.

## Constraints
- **Groq API Limits**: Must operate within Groq's free-tier rate limits (tokens per minute, requests per minute).
- **Anti-Scraping Defenses**: Reddit and Twitter/X have strict scraping blocks. We must handle these elegantly (e.g., using official APIs, custom headers, or Bright Data tools).
- **GitHub Actions Environment**: Execution must be fast and headless, running on Ubuntu runners without state persistence across runs (must commit state back to the repo).

## Success Criteria
- [ ] Scheduled GitHub Actions workflow runs every 48 hours without failing.
- [ ] Scraper extracts relevant data from at least 3 distinct platforms.
- [ ] Groq API successfully processes, rates, and categorizes scraped strategies.
- [ ] The pipeline commits an updated `data/raw_scrapes.json`, `data/curated_strategies.json`, and a beautifully formatted `README.md` directory catalog back to the repository.
