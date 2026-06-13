# JOURNAL.md

# Project Journal

## 2026-06-13: Project Initialized
- Set up SPEC.md, REQUIREMENTS.md, ROADMAP.md, and initial project structure.
- Defined target of Option C (GitHub-centric automated database and markdown curation).

## Session: 2026-06-13 14:30–15:17 IST

### Objective
Execute Phase 2 (Scraping Engine & Dynamic Sources) and verify.

### Accomplished
- Created scraper package with `BaseScraper` abstract class (unified 10-field schema)
- Implemented `GitHubScraper` (Search API + tracked repos, cross-query dedup)
- Implemented `RedditScraper` (RSS feeds + keyword filtering + HTML stripping)
- Implemented `BlogScraper` (RSS feeds + keyword filtering + tag extraction)
- Implemented `TwitterScraper` stub (disabled by default, Nitter RSS ready)
- Built `Pipeline` orchestrator (run all scrapers → dedup → discover sources → save to DB)
- Created `src/main.py` entry point
- Wrote 30 new tests across 4 test files
- Debugged and fixed Reddit 403/429:
  - Root cause: browser-mimicking UAs blocked by Reddit
  - Fix: domain-aware bot UA + per-domain rate limiter + x-ratelimit-reset backoff
- Verified Phase 2: 18/18 checks, 52/52 tests passing
- Live pipeline confirmed working: 376 GitHub repos, Reddit RSS 25 entries/subreddit

### Verification
- [x] All scraper files exist (5 files)
- [x] Unified schema with 10 required fields
- [x] GitHub cross-query deduplication
- [x] Reddit keyword filtering
- [x] Pipeline dedup (DB + within-batch)
- [x] Dynamic source discovery + blacklist
- [x] Pipeline + main importable
- [x] Twitter stub returns [] when disabled
- [x] 52/52 tests passed
- [x] Live Reddit RSS: 25 entries with bot UA

### Paused Because
Session complete — Phase 2 fully implemented and verified.

### Handoff Notes
Phase 3 (AI Processing & Categorization with Groq) is the next milestone. Run `/plan 3` to start.
