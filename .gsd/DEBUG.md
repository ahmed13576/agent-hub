# Debug Session: Groq 429 Rate Limits + No Intermediate Saves

## Symptom
Pipeline crashes or gets stuck on Groq 429 rate limit errors during enrichment, and all scraped/enriched data is lost because saves only happen at the very end.

**When:** Running `python -m src.main --enrich --generate` with ~589 items.
**Expected:** Pipeline should enrich all items and save progress regularly.
**Actual:** 
- Run 1 (single-item): Managed 89/586 items before exhausting rate limits entirely (22 min, constant 429s).
- Run 2 (batch): Failed on very first chunk — 5 retries all 429, then fallback also 429'd.
- Database was empty after both runs (0 items saved).

## Evidence

1. `MIN_REQUEST_INTERVAL = 60/25 = 2.4s` — too aggressive for Groq free tier.
2. Groq free tier: 30 RPM, 15,000 TPM for llama-3.3-70b. Batch prompts with 10 items easily exceed TPM.
3. `INITIAL_BACKOFF = 2s` — too short. Groq retries need 30-60s+ cooldowns.
4. Pipeline saves ONLY in Step 5 (`_save_to_database`), which happens AFTER all enrichment completes.
5. If enrichment crashes at item 400/589, ALL 589 scraped items + 400 enrichments are lost.
6. Scraping takes ~6 minutes (Reddit rate limits) — also wasted on crash.

## Hypotheses

| # | Hypothesis | Likelihood | Status |
|---|------------|------------|--------|
| 1 | MIN_REQUEST_INTERVAL too short (2.4s), INITIAL_BACKOFF too short (2s) for Groq TPM limits | 90% | CONFIRMED |
| 2 | Pipeline has no checkpoint saves — crash = total data loss | 100% | CONFIRMED |
| 3 | Batch chunk size of 10 with 1500 chars per item may exceed Groq's 15K TPM | 70% | CONFIRMED |

## Resolution Plan

### Fix 1: Groq throttling
- Increase `MIN_REQUEST_INTERVAL` to 6s (10 RPM effective rate — safe margin)
- Increase `INITIAL_BACKOFF` to 10s with smarter 429 handling
- Reduce batch chunk size from 10 to 5 to stay under TPM limits

### Fix 2: Checkpoint saves
- Save scraped items to database IMMEDIATELY after scraping (before enrichment)
- Save enrichment progress every 5 chunks (~25 items)
- Pipeline becomes resumable — already-enriched items are skipped on re-run

### Fix 3: Pipeline architecture
- Split pipeline into: scrape → save → enrich-with-checkpoints → generate
- Each phase saves its output, so partial progress is never lost
