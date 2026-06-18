"""
Agent Hub - Pipeline Orchestrator

Runs all scrapers, de-duplicates results, discovers new sources from
scraped content, and saves everything to the database.
"""

import json
import hashlib
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from src.config import config
from src.scrapers.github_scraper import GitHubScraper
from src.scrapers.reddit_scraper import RedditScraper
from src.scrapers.blog_scraper import BlogScraper
from src.scrapers.twitter_scraper import TwitterScraper

logger = logging.getLogger(__name__)

# Domains to exclude from dynamic source discovery
BLACKLISTED_DOMAINS = {
    "github.com",
    "reddit.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "youtu.be",
    "wikipedia.org",
    "medium.com",
    "google.com",
    "googleapis.com",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "t.co",
    "bit.ly",
    "imgur.com",
    "gist.github.com",
    "raw.githubusercontent.com",
    "docs.google.com",
    "drive.google.com",
    "amazon.com",
    "amzn.to",
    "apple.com",
    "microsoft.com",
    "w3.org",
    "schema.org",
}

# Regex to extract URLs from text
URL_PATTERN = re.compile(
    r'https?://[^\s<>"\')\]},;]+',
    re.IGNORECASE,
)


class Pipeline:
    """
    Orchestrates the full scraping pipeline:
    1. Run all scrapers
    2. De-duplicate against existing database
    3. Discover new sources from scraped content
    4. Save new items to database
    """

    def __init__(self):
        self._scrapers = [
            GitHubScraper(),
            RedditScraper(),
            BlogScraper(),
            TwitterScraper(),
        ]
        self._db_path = config.database_path
        self._discovered_path = config.discovered_sources_path

    def run(self, enrich: bool = False, generate: bool = False) -> dict:
        """
        Execute the full pipeline.

        Returns:
            Stats dict with keys: new_items, duplicates_skipped,
            domains_discovered, total_in_db, errors, and
            enrichment_stats (if enrich=True),
            catalog_stats (if generate=True).
        """
        stats = {
            "new_items": 0,
            "duplicates_skipped": 0,
            "domains_discovered": 0,
            "total_in_db": 0,
            "errors": [],
        }

        # Step 1: Run all scrapers
        logger.info("=" * 60)
        logger.info("PIPELINE: Starting scraping run")
        logger.info("=" * 60)

        all_items = self._run_scrapers(stats)
        logger.info(f"PIPELINE: {len(all_items)} total items scraped")

        # Step 2: De-duplicate
        new_items = self._deduplicate(all_items)
        stats["duplicates_skipped"] = len(all_items) - len(new_items)
        stats["new_items"] = len(new_items)
        logger.info(
            f"PIPELINE: {len(new_items)} new items "
            f"({stats['duplicates_skipped']} duplicates skipped)"
        )

        # Step 3: Enrich (optional)
        if enrich and new_items:
            from src.enrichment.processor import EnrichmentProcessor
            processor = EnrichmentProcessor()
            new_items = processor.enrich_batch(
                new_items,
                progress_callback=lambda i, t: logger.info(f"Enriching: {i}/{t}"),
            )
            stats["enrichment_stats"] = processor.get_stats()
            logger.info(f"PIPELINE: Enrichment complete — {processor.get_stats()}")

        # Step 4: Discover new sources
        if new_items:
            discovered_count = self._discover_sources(new_items)
            stats["domains_discovered"] = discovered_count
            logger.info(f"PIPELINE: {discovered_count} new domains discovered")

        # Step 5: Save to database
        if new_items:
            self._save_to_database(new_items)

        # Step 6: Final count
        db = self._load_database()
        stats["total_in_db"] = len(db)

        # Step 7: Generate catalog (optional)
        if generate:
            from src.generator.curated_filter import save_curated_strategies
            from src.generator.catalog import write_catalog
            from src.generator.curated_filter import load_curated_strategies

            curated_path = save_curated_strategies(db)
            logger.info(f"PIPELINE: Curated strategies saved to {curated_path}")

            curated = load_curated_strategies()
            catalog_stats = write_catalog(curated)
            stats["catalog_stats"] = catalog_stats
            logger.info(f"PIPELINE: Catalog generated — {catalog_stats}")

        logger.info("=" * 60)
        logger.info(f"PIPELINE: Run complete — {stats['new_items']} new, "
                     f"{stats['total_in_db']} total in DB")
        logger.info("=" * 60)

        return stats

    def _run_scrapers(self, stats: dict) -> list[dict]:
        """
        Run each scraper, catching per-scraper errors.

        Returns:
            Aggregated list of all scraped items.
        """
        all_items = []

        for scraper in self._scrapers:
            scraper_name = type(scraper).__name__
            try:
                logger.info(f"Running {scraper_name}...")
                items = scraper.scrape()
                all_items.extend(items)
                logger.info(f"{scraper_name}: {len(items)} items")
            except Exception as e:
                error_msg = f"{scraper_name} failed: {e}"
                logger.error(error_msg)
                stats["errors"].append(error_msg)

        return all_items

    def _deduplicate(self, items: list[dict]) -> list[dict]:
        """
        Remove items that already exist in the database or are duplicates
        within the current batch.

        Args:
            items: List of scraped item dicts.

        Returns:
            List of new, unique items.
        """
        # Load existing IDs from database
        db = self._load_database()
        existing_ids = {item["id"] for item in db}

        # Track seen IDs in current batch
        seen_ids = set()
        new_items = []

        for item in items:
            item_id = item["id"]
            if item_id not in existing_ids and item_id not in seen_ids:
                seen_ids.add(item_id)
                new_items.append(item)

        return new_items

    def _discover_sources(self, items: list[dict]) -> int:
        """
        Extract URLs from scraped content and track new domains.

        Args:
            items: List of newly scraped items.

        Returns:
            Number of newly discovered domains.
        """
        discovered = self._load_discovered_sources()
        new_count = 0

        for item in items:
            # Scan both description and raw_content for URLs
            text = f"{item.get('description', '')} {item.get('raw_content', '')}"
            urls = URL_PATTERN.findall(text)

            for url in urls:
                # Clean trailing punctuation
                url = url.rstrip(".,;:!?)>]}'\"")

                try:
                    parsed = urlparse(url)
                    domain = parsed.netloc.lower()

                    # Remove www. prefix for consistency
                    if domain.startswith("www."):
                        domain = domain[4:]

                    # Skip blacklisted and empty domains
                    if not domain or domain in BLACKLISTED_DOMAINS:
                        continue

                    # Skip if any parent domain is blacklisted
                    parts = domain.split(".")
                    parent_blacklisted = False
                    for i in range(len(parts) - 1):
                        parent = ".".join(parts[i:])
                        if parent in BLACKLISTED_DOMAINS:
                            parent_blacklisted = True
                            break
                    if parent_blacklisted:
                        continue

                    # Track the domain
                    if domain not in discovered:
                        discovered[domain] = {
                            "first_seen": datetime.now(timezone.utc).isoformat(),
                            "mention_count": 0,
                            "sample_urls": [],
                        }
                        new_count += 1

                    discovered[domain]["mention_count"] += 1

                    # Keep up to 5 sample URLs per domain
                    samples = discovered[domain]["sample_urls"]
                    if url not in samples and len(samples) < 5:
                        samples.append(url)

                except Exception as e:
                    logger.debug(f"Failed to parse URL '{url}': {e}")

        # Save updated discovered sources
        self._save_discovered_sources(discovered)
        return new_count

    def _save_to_database(self, new_items: list[dict]):
        """
        Append new items to the database JSON file.

        Args:
            new_items: List of new item dicts to save.
        """
        db = self._load_database()
        db.extend(new_items)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._db_path, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
        logger.info(f"Database updated: {len(db)} total items")

    def _load_database(self) -> list[dict]:
        """Load the database JSON file."""
        if not self._db_path.exists():
            return []
        try:
            with open(self._db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load database: {e}")
            return []

    def _load_discovered_sources(self) -> dict:
        """Load the discovered sources JSON file."""
        if not self._discovered_path.exists():
            return {}
        try:
            with open(self._discovered_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load discovered sources: {e}")
            return {}

    def _save_discovered_sources(self, discovered: dict):
        """Save the discovered sources JSON file."""
        self._discovered_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._discovered_path, "w", encoding="utf-8") as f:
            json.dump(discovered, f, indent=2, ensure_ascii=False)
