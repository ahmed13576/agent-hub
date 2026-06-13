# RESEARCH.md — Phase 1: Scraping and LLM Integration Research

## 1. Groq API Limits & Model Evaluation
Groq provides high-speed, free-tier LLM inference. For our categorization and enrichment engine, we need a model with strong reasoning capabilities, reliable JSON schema compliance, and reasonable rate limits.

### Available Groq Models (Free Tier)
1. **Llama 3.3 70B Versatile (`llama-3.3-70b-versatile`)**:
   - **Specs**: 70B parameters, 128k context window.
   - **Performance**: High reasoning capability, ideal for classifying complex technical strategies.
   - **Rate Limits**: ~30 RPM (Requests Per Minute), ~1,000 RPD (Requests Per Day).
   - **Verdict**: **Primary choice** for processing scraped items. Since we run every other day and process ~50–100 items per run, 1,000 RPD is more than sufficient.

2. **Llama 3.1 8B Instant (`llama-3.1-8b-instant`)**:
   - **Specs**: 8B parameters, 128k context window.
   - **Performance**: Extremely fast, but lower reasoning depth for fine-grained categorization.
   - **Rate Limits**: ~30 RPM, ~14,400 RPD.
   - **Verdict**: Use as a **backup/fallback** or for quick pre-filtering (e.g., checking if a scraped post is actually about LLM agents before sending it to the 70B model).

---

## 2. Scraping Feasibility & Free-Tier Bypasses
To minimize running costs, we will use lightweight, unauthenticated APIs and RSS feeds by default.

### Source Breakdown & Scraping Methods

| Source | Scraping Method | Authentication / Access | Difficulty |
| :--- | :--- | :--- | :--- |
| **GitHub Repos / Discussions** | GitHub Search API (`/search/repositories`, `/search/code`) | Auth using repository's standard `${{ secrets.GITHUB_TOKEN }}` in GitHub Actions. | Easy |
| **Reddit (r/ClaudeDev, etc.)** | Subreddit RSS feeds (e.g. `https://www.reddit.com/r/ClaudeDev/.rss`) | No authentication required. Returns XML containing latest posts. | Easy (no auth blocks) |
| **Tech Blogs (Medium/TDS)** | Medium Tag RSS Feed (e.g. `https://medium.com/feed/towards-data-science/tagged/ai-agents`) | No authentication required. | Easy |
| **Tech Blogs (AIM)** | WordPress RSS Feed (e.g. `https://analyticsindiamag.com/feed/`) | No authentication required. | Easy |
| **Twitter / X** | Scraper API or Bright Data | Requires login session or paid proxy/API (SocialData / Bright Data). | Hard (strictly blocked) |

### Free-Tier Scraping Architecture
1. **Default Request Client**: Python `urllib` or `requests` with a randomized User-Agent header.
2. **Reddit RSS**: Fetching `https://www.reddit.com/r/Subreddit/new/.rss` yields XML with title, link, and author. We parse this with Python's built-in `xml.etree.ElementTree` or `feedparser` without hitting Reddit API blocks.
3. **GitHub API**: Using `PyGithub` or standard requests to GitHub API with the Actions token.

---

## 3. Bright Data Viability & Cost Analysis
Bright Data is the industry leader for bypassing strict anti-scraping walls (like Cloudflare, Twitter login walls, and Reddit scrapers blocks).

### Viable Bright Data Tools
1. **Web Unlocker**:
   - **What it is**: An API that manages proxy rotation, browser fingerprinting, and CAPTCHA solving. You make a request to Web Unlocker, and it returns the raw HTML of the target site.
   - **Cost**: Starts at ~$3.00/GB or Pay-Per-Request (approx. $1.00 per 1,000 successful requests).
   - **Verdict**: Excellent backup option. We can configure our scraping pipeline to use a standard HTTP proxy string (e.g., `http://username:password@zproxy.lum-superproxy.io:22225`).
2. **Bright Data Python SDK / Scraping Browser**:
   - **What it is**: Playwright/Puppeteer script runner connected to Bright Data's cloud browser.
   - **Cost**: ~$0.04/hour + residential proxy bandwidth costs.
   - **Verdict**: Overkill for RSS feeds and GitHub APIs, but highly relevant if we eventually need to scrape dynamic SPA (Single Page Application) forums or Twitter/X.

### Recommended Integration Path
Implement a **hybrid client proxy**:
- If the environment variable `BRIGHTDATA_PROXY` is defined, the Python scraper will route blocked requests (e.g., to X or Medium) through Bright Data's Web Unlocker proxy.
- If it is not defined, the scraper runs purely via free public HTTP/RSS clients.

---

## 4. Dynamic Source Discovery
To prevent being left out of new platforms and blogs, we will implement **Dynamic Source Tracking**:
- **Source Config (`data/sources.yaml`)**: Stores seed URLs, subreddits, and search queries.
- **Reference Extraction**: During LLM enrichment, we will ask Groq to extract any referenced URLs, external tools, or blogs mentioned in the scraped posts.
- **Auto-Discovery Log (`data/discovered_sources.json`)**: Newly discovered links will be written to this file. On subsequent runs, the pipeline will inspect these links, classify them, and automatically append them to `sources.yaml` if they meet safety/relevance thresholds.
