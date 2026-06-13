"""
Agent Hub - Main Entry Point

Runs the full scraping pipeline:
1. Configure logging
2. Validate configuration
3. Execute pipeline
4. Print summary
"""

import sys
import logging
from datetime import datetime, timezone

from src.config import config
from src.pipeline import Pipeline


def main():
    """Run the Agent Hub scraping pipeline."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger("agent-hub")

    logger.info("=" * 60)
    logger.info("Agent Hub — Agentic AI Strategy Scraper")
    logger.info(f"Run started at: {datetime.now(timezone.utc).isoformat()}")
    logger.info("=" * 60)

    # Validate configuration
    warnings = config.validate()
    for warning in warnings:
        logger.warning(f"Config: {warning}")

    # Run the pipeline
    try:
        pipeline = Pipeline()
        stats = pipeline.run()

        # Print summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("SUMMARY")
        logger.info("=" * 60)
        logger.info(f"  New items scraped:    {stats['new_items']}")
        logger.info(f"  Duplicates skipped:   {stats['duplicates_skipped']}")
        logger.info(f"  Domains discovered:   {stats['domains_discovered']}")
        logger.info(f"  Total items in DB:    {stats['total_in_db']}")

        if stats["errors"]:
            logger.warning(f"  Errors encountered:   {len(stats['errors'])}")
            for error in stats["errors"]:
                logger.warning(f"    - {error}")

        logger.info("=" * 60)
        return 0

    except Exception as e:
        logger.error(f"Pipeline failed with fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
