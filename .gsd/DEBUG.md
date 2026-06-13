# Debug Session: Reddit RSS 403/429

## Symptom
HTTP client live RSS test skipped because Reddit returns 403 (Blocked) or 429 (Too Many Requests).

**When:** Every time `fetch_rss` is called for `reddit.com` URLs.
**Expected:** RSS feed should return 200 with XML entries.
**Actual:** 403 Blocked (when using browser-style User-Agents) or 429 Too Many Requests (when rate limit exhausted).

## Evidence Gathered
1. Reddit returns **403 Blocked** when receiving browser-mimicking User-Agent headers from a script context.
2. Reddit returns **200 OK** (73KB, 25 entries) when receiving a descriptive bot-style UA like `AgentHub/1.0 (research bot)`.
3. Reddit's rate limit: 100 requests per 10-minute sliding window for unauthenticated.
4. Reddit provides `x-ratelimit-remaining` and `x-ratelimit-reset` headers.
5. `old.reddit.com` returns 429, `www.reddit.com` with bot UA returns 200.
6. The JSON API (`/new.json`) returns 403 regardless of UA.

## Hypotheses

| # | Hypothesis | Likelihood | Status |
|---|------------|------------|--------|
| 1 | Browser-mimicking UAs get 403'd by Reddit | 90% | CONFIRMED |
| 2 | Retry backoff too short for Reddit 429s | 70% | CONFIRMED |
| 3 | No per-domain rate limiting causes rapid-fire requests | 60% | CONFIRMED |

## Resolution

**Root Cause:** Two issues:
1. Reddit blocks browser-mimicking User-Agent strings (Chrome/Firefox/Safari) with 403. Reddit's API guidelines require honest bot-style UAs.
2. HTTP client had no per-domain rate limiting and used too-short backoff (2-4-8s) for 429 errors.

**Fix (3 changes to `src/clients/http_client.py`):**
1. **Domain-aware UA selection**: Added `BOT_UA_DOMAINS` set and `_needs_bot_ua()` — Reddit URLs now automatically use `AgentHub/1.0 (automated research bot)` instead of browser UAs.
2. **Per-domain rate limiting**: Added `DOMAIN_RATE_LIMITS` dict and `_domain_throttle()` — enforces 2s minimum between Reddit requests to stay within 100 req/10min.
3. **Smart 429 backoff**: Added `_compute_429_wait()` — reads `Retry-After` header, then Reddit's `x-ratelimit-reset` header, falls back to 10-20-30s escalating backoff.

**Also updated `tests/test_http_client.py`:**
- 4 new tests for bot UA detection (reddit vs non-reddit URLs).
- Updated existing tests for `BROWSER_USER_AGENTS` naming.
- RSS test updated with clearer skip message.

**Regression Check:** 48/48 offline tests pass.
