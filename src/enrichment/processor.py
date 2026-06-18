"""
Agent Hub - Enrichment Processor

Core enrichment engine that sends scraped items through Groq LLM for AI analysis.
Validates all LLM output before merging, handles errors gracefully, and never
crashes the batch on individual item failures.

Design constraints:
- Single item failure never crashes the batch
- All LLM output is validated before merge
- Already-enriched items are skipped (no duplicate API calls)
- Scores are clamped, categories normalized, invalid tags filtered (repair mode)
- Fully testable with mocked GroqClient
"""

import logging
from typing import Optional, Callable

from src.clients.groq_client import GroqClient
from src.enrichment.schema import (
    VALID_CATEGORIES,
    VALID_TAGS,
    LLM_REQUIRED_FIELDS,
    validate_enrichment,
    merge_enrichment,
)
from src.enrichment.prompts import (
    SYSTEM_PROMPT,
    build_prompt,
    get_prompt_version,
)

logger = logging.getLogger(__name__)


class EnrichmentProcessor:
    """
    LLM-powered enrichment processor for scraped items.

    Usage:
        processor = EnrichmentProcessor()
        enriched_items = processor.enrich_batch(items)
        print(processor.get_stats())
    """

    def __init__(self, groq_client: Optional[GroqClient] = None):
        """
        Args:
            groq_client: Optional injected GroqClient for testability.
                         If None, creates one from config (default behavior).
        """
        if groq_client is not None:
            self._groq = groq_client
        else:
            self._groq = GroqClient()

        self.enriched_count: int = 0
        self.skipped_count: int = 0
        self.failed_count: int = 0

        logger.info("EnrichmentProcessor initialized")

    def enrich_item(self, item: dict) -> dict:
        """
        Enrich a single scraped item via LLM analysis.

        - Skips items that already have an 'enriched_at' field.
        - Builds a prompt, calls Groq, validates output, merges.
        - On validation failure, attempts repair (clamp scores, normalize category, filter tags).
        - On unrecoverable failure, returns original item with 'enrichment_error' field.

        Args:
            item: Scraped item dict (10-field unified schema).

        Returns:
            Enriched item dict (18 fields) or original item with error.
        """
        # Skip already-enriched items
        if "enriched_at" in item:
            logger.debug(f"Skipping already-enriched item: {item.get('title', 'unknown')}")
            self.skipped_count += 1
            return item

        try:
            # Build prompt
            user_message = build_prompt(item)

            # Call LLM
            result = self._groq.analyze_json(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.2,
            )

            # Repair common LLM output issues
            result = self._repair_result(result)

            # Validate
            is_valid, errors = validate_enrichment(result)
            if not is_valid:
                logger.warning(
                    f"Enrichment validation failed for '{item.get('title', '?')}': {errors}. "
                    f"Attempting deeper repair..."
                )
                result = self._deep_repair(result)
                is_valid, errors = validate_enrichment(result)

                if not is_valid:
                    logger.error(
                        f"Enrichment validation failed after repair for "
                        f"'{item.get('title', '?')}': {errors}"
                    )
                    self.failed_count += 1
                    failed_item = dict(item)
                    failed_item["enrichment_error"] = "; ".join(errors)
                    return failed_item

            # Merge validated enrichment into item
            model_used = getattr(self._groq, "model", "unknown")
            version = get_prompt_version()
            merged = merge_enrichment(item, result, model_used=model_used, enrichment_version=version)

            self.enriched_count += 1
            logger.debug(
                f"Enriched: '{item.get('title', '?')}' → "
                f"category={result.get('category')}, "
                f"relevance={result.get('relevance_score')}"
            )
            return merged

        except Exception as e:
            logger.error(f"Enrichment failed for '{item.get('title', '?')}': {e}")
            self.failed_count += 1
            failed_item = dict(item)
            failed_item["enrichment_error"] = str(e)
            return failed_item

    def enrich_batch(
        self,
        items: list[dict],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[dict]:
        """
        Enrich a batch of scraped items.

        Never crashes on individual item failure — always processes the full batch.

        Args:
            items: List of scraped item dicts.
            progress_callback: Optional callback(current_index, total) for progress.

        Returns:
            List of all items (enriched or original with error).
        """
        results = []
        total = len(items)

        logger.info(f"Starting batch enrichment: {total} items")

        for i, item in enumerate(items):
            try:
                enriched = self.enrich_item(item)
                results.append(enriched)
            except Exception as e:
                # This should never happen (enrich_item catches all), but just in case
                logger.error(f"Unexpected batch error on item {i}: {e}")
                self.failed_count += 1
                failed_item = dict(item)
                failed_item["enrichment_error"] = f"Batch error: {e}"
                results.append(failed_item)

            if progress_callback:
                progress_callback(i + 1, total)

        logger.info(
            f"Batch enrichment complete: "
            f"{self.enriched_count} enriched, "
            f"{self.skipped_count} skipped, "
            f"{self.failed_count} failed"
        )
        return results

    def get_stats(self) -> dict:
        """Return enrichment statistics."""
        return {
            "enriched": self.enriched_count,
            "skipped": self.skipped_count,
            "failed": self.failed_count,
        }

    @staticmethod
    def _repair_result(result: dict) -> dict:
        """
        Light repair of common LLM output issues.

        - Normalize category to lowercase
        - Clamp scores to 0-1 range
        - Filter tags to only valid values
        - Handle 'tags' vs 'enriched_tags' naming
        """
        repaired = dict(result)

        # Handle LLM returning 'tags' instead of 'enriched_tags'
        if "tags" in repaired and "enriched_tags" not in repaired:
            repaired["enriched_tags"] = repaired.pop("tags")

        # Normalize category
        if "category" in repaired and isinstance(repaired["category"], str):
            normalized = repaired["category"].lower().strip()
            # Map common variations
            if normalized in VALID_CATEGORIES:
                repaired["category"] = normalized

        # Clamp scores
        for score_field in ("effectiveness_score", "relevance_score"):
            if score_field in repaired and isinstance(repaired[score_field], (int, float)):
                repaired[score_field] = max(0.0, min(1.0, float(repaired[score_field])))

        # Filter tags to valid values only
        if "enriched_tags" in repaired and isinstance(repaired["enriched_tags"], list):
            original_tags = repaired["enriched_tags"]
            repaired["enriched_tags"] = [t for t in original_tags if t in VALID_TAGS]
            removed = set(original_tags) - set(repaired["enriched_tags"])
            if removed:
                logger.warning(f"Filtered invalid tags: {removed}")

        return repaired

    @staticmethod
    def _deep_repair(result: dict) -> dict:
        """
        Aggressive repair when light repair wasn't enough.

        - Add missing fields with defaults
        - Truncate/pad summary if needed
        """
        repaired = dict(result)

        # Ensure all required fields exist with defaults
        if "summary" not in repaired:
            repaired["summary"] = "No summary available. " * 4
        if "category" not in repaired:
            repaired["category"] = "experimental"
        if "effectiveness_score" not in repaired:
            repaired["effectiveness_score"] = 0.5
        if "relevance_score" not in repaired:
            repaired["relevance_score"] = 0.5
        if "enriched_tags" not in repaired:
            repaired["enriched_tags"] = []

        # Fix summary length
        summary = repaired["summary"]
        if isinstance(summary, str):
            if len(summary) < 50:
                repaired["summary"] = summary + " " + "Additional context needed. " * 3
            elif len(summary) > 500:
                repaired["summary"] = summary[:497] + "..."

        return repaired
