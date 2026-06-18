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
    """Run the Agent Hub scraping pipeline.

    CLI flags:
        --enrich  Enable LLM enrichment via Groq API
        --eval    Run golden dataset evaluation (requires --enrich or standalone)
    """
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

    # Parse CLI flags
    enrich = "--enrich" in sys.argv
    run_eval = "--eval" in sys.argv

    if enrich:
        logger.info("Enrichment: ENABLED (--enrich flag)")
    if run_eval:
        logger.info("Evaluation: ENABLED (--eval flag)")

    # Run the pipeline
    try:
        pipeline = Pipeline()
        stats = pipeline.run(enrich=enrich)

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

        if "enrichment_stats" in stats:
            es = stats["enrichment_stats"]
            logger.info(f"  Enriched:             {es['enriched']}")
            logger.info(f"  Enrichment skipped:   {es['skipped']}")
            logger.info(f"  Enrichment failed:    {es['failed']}")

        # Run golden dataset evaluation if requested
        if run_eval:
            logger.info("")
            logger.info("=" * 60)
            logger.info("GOLDEN DATASET EVALUATION")
            logger.info("=" * 60)
            from src.enrichment.processor import EnrichmentProcessor
            from src.enrichment.eval_runner import run_eval as do_eval, check_thresholds
            processor = EnrichmentProcessor()
            metrics = do_eval(processor)
            passed, failures = check_thresholds(metrics)
            logger.info(f"  Category accuracy:    {metrics.get('category_accuracy', 0):.1%}")
            logger.info(f"  Relevance accuracy:   {metrics.get('relevance_accuracy', 0):.1%}")
            logger.info(f"  Effectiveness acc.:   {metrics.get('effectiveness_accuracy', 0):.1%}")
            logger.info(f"  Avg tag recall:       {metrics.get('avg_tag_recall', 0):.1%}")
            logger.info(f"  Noise filtering:      {metrics.get('noise_filtering', 0):.1%}")
            if passed:
                logger.info("  VERDICT: ✅ PASS — all thresholds met")
            else:
                logger.warning(f"  VERDICT: ❌ FAIL — {len(failures)} threshold(s) missed")
                for f in failures:
                    logger.warning(f"    - {f}")

        logger.info("=" * 60)
        return 0

    except Exception as e:
        logger.error(f"Pipeline failed with fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
