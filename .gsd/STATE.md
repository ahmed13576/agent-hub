# STATE.md

## Current Position
- **Phase**: 3 (planned)
- **Task**: Planning complete — ready for execution
- **Status**: Active (resumed 2026-06-18T21:41 IST)

## Completed
- Phase 1: Research & Foundation ✅ (verified)
  - Project skeleton with data/, src/, tests/ directories
  - sources.yaml with comprehensive seed targets
  - config.py loading env vars and YAML config
  - HTTP client with user-agent rotation + Bright Data proxy support
  - Groq client with rate-limiting and exponential backoff

- Phase 2: Scraping Engine & Dynamic Sources ✅ (verified)
  - GitHub scraper (Search API + tracked repos, de-duplication)
  - Reddit scraper (RSS feeds + keyword filtering)
  - Blog scraper (RSS feeds + keyword filtering + tag extraction)
  - Twitter stub (disabled by default, Nitter hooks ready)
  - Pipeline orchestrator (run all scrapers, deduplicate, discover sources, save to DB)
  - Main entry point (src/main.py)
  - Debug fix: domain-aware bot UA for Reddit + per-domain rate limiter + x-ratelimit-reset support
  - 52/52 tests passing, 18/18 verification checks passing

## Last Session Summary
- Executed Phase 2 in 2 waves (Plan 2.1: scrapers, Plan 2.2: pipeline/entry point)
- Debugged and fixed Reddit 403/429 issue (browser UA → bot UA, added rate limiting)
- Verified Phase 2 with full empirical evidence
- Live pipeline test confirmed: 376 GitHub repos, 25 Reddit entries per subreddit

## In-Progress Work
None — all work committed and verified.
- Tests status: 52/52 passing
- Git: clean working tree

## Blockers
None.

## Context Dump

### Decisions Made
- **Bot UA for Reddit**: Reddit blocks browser-mimicking UAs with 403. Switched to descriptive bot-style UA (`AgentHub/1.0`). Other sites keep browser UA rotation.
- **Per-domain rate limiting**: 2s minimum between Reddit requests (within 100 req/10min limit).
- **x-ratelimit-reset aware backoff**: Reads Reddit's response headers for optimal retry timing.
- **Twitter disabled by default**: Stub scraper returns [] — Nitter RSS hooks ready for when enabled.

### Key Architecture
- `BaseScraper` enforces unified 10-field schema (id, source, title, url, description, author, metadata, tags, scraped_at, raw_content)
- `Pipeline` orchestrates all scrapers → dedup → discover sources → save to DB
- `HttpClient._build_headers(url=...)` does domain-aware UA selection automatically
- `HttpClient._domain_throttle(url)` enforces per-domain rate limits

### Files of Interest
- `src/clients/http_client.py`: Domain-aware UA, rate limiting, x-ratelimit support
- `src/pipeline.py`: Full orchestrator with dedup + dynamic source discovery
- `src/scrapers/`: All 4 scrapers (github, reddit, blog, twitter)
- `src/main.py`: Entry point
- `sources.yaml`: Configured search queries, subreddits, blog feeds, tracked repos
- `.gsd/DEBUG.md`: Reddit 403/429 debug session documentation

## Next Steps
1. `/execute 3` — Execute Phase 3 plans (Wave 1: EDD foundation, Wave 2: processor + integration)
2. `/verify 3` — Verify Phase 3 after execution
3. `/plan 4` — Plan Phase 4: Git-Backed Automation & Markdown Generation
