# ROADMAP.md

> **Current Phase**: Not started
> **Milestone**: v1.0

## Must-Haves (from SPEC)
- [ ] GitHub Actions cron workflow executing the scrapes.
- [ ] Multi-source scraper for GitHub, Reddit, and technical blogs.
- [ ] Groq LLM integration to analyze and categorize strategies.
- [ ] Automatic git commit back to repository for `data.json` and Markdown catalogs.

## Phases

### Phase 1: Research & Foundation
**Status**: ✅ Complete
**Objective**: Set up the project skeleton, investigate Bright Data options, evaluate Groq API limits/free models, and implement the storage/config system.
**Requirements**: REQ-06, REQ-09

### Phase 2: Scraping Engine & Dynamic Sources
**Status**: ✅ Complete
**Objective**: Build the core scrapers (GitHub, Reddit, and Blogs) and implement dynamic source discovery/tracking.
**Requirements**: REQ-02, REQ-03, REQ-04, REQ-05

### Phase 3: AI Processing & Categorization
**Status**: ⬜ Not Started
**Objective**: Connect the scraper output to Groq APIs for summarization, tagging, and grading ("battle-tested" vs "new/upcoming").
**Requirements**: REQ-06, REQ-07

### Phase 4: Git-Backed Automation & Markdown Generation
**Status**: ⬜ Not Started
**Objective**: Write the Markdown page generator to build a beautiful `README.md` and detailed strategy sheets, and configure the GitHub Actions workflow to run cron jobs and commit changes back.
**Requirements**: REQ-01, REQ-08
