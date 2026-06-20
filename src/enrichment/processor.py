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
- Batch mode sends multiple items per API call to minimize rate-limit pressure
- Fully testable with mocked GroqClient
"""

import json
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
    build_batch_prompt,
    get_prompt_version,
)

logger = logging.getLogger(__name__)

# Number of items to send per LLM call in batch mode.
# Kept at 5 to stay under Groq's 15K TPM limit for llama-3.3-70b.
BATCH_CHUNK_SIZE = 5

# Save a checkpoint to the database every N chunks
CHECKPOINT_INTERVAL = 5  # every 5 chunks = ~25 items


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

    def _enrich_chunk(self, chunk: list[dict]) -> list[dict]:
        """
        Enrich a chunk of items via a single batch LLM call.

        Sends multiple items in one prompt and expects a JSON array back.
        Falls back to single-item enrichment if the batch response can't be parsed.

        Args:
            chunk: List of up to BATCH_CHUNK_SIZE unenriched items.

        Returns:
            List of enriched items (or originals with error on failure).
        """
        try:
            # Build batch prompt
            user_message = build_batch_prompt(chunk)

            # Call LLM — expecting a JSON array
            raw_response = self._groq.chat(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.2,
                max_tokens=4096,
            )

            # Parse the JSON array response
            results = self._extract_json_array(raw_response)

            if not isinstance(results, list):
                raise ValueError(f"Expected JSON array, got {type(results).__name__}")

            # Build a lookup by ID for matching results back to items
            results_by_id = {}
            for r in results:
                if isinstance(r, dict) and "id" in r:
                    results_by_id[r["id"]] = r

            # Match results to items and merge
            enriched_items = []
            model_used = getattr(self._groq, "model", "unknown")
            version = get_prompt_version()

            for item in chunk:
                item_id = item.get("id", "")
                result = results_by_id.get(item_id)

                if result is None:
                    # Result not found for this item — fall back to single enrichment
                    logger.warning(
                        f"Batch response missing result for '{item.get('title', '?')}' "
                        f"(id={item_id}). Falling back to single enrichment."
                    )
                    enriched_items.append(self.enrich_item(item))
                    continue

                # Repair and validate
                result = self._repair_result(result)
                is_valid, errors = validate_enrichment(result)

                if not is_valid:
                    result = self._deep_repair(result)
                    is_valid, errors = validate_enrichment(result)

                if not is_valid:
                    logger.warning(
                        f"Batch enrichment validation failed for '{item.get('title', '?')}': {errors}"
                    )
                    self.failed_count += 1
                    failed_item = dict(item)
                    failed_item["enrichment_error"] = "; ".join(errors)
                    enriched_items.append(failed_item)
                    continue

                merged = merge_enrichment(item, result, model_used=model_used, enrichment_version=version)
                self.enriched_count += 1
                enriched_items.append(merged)

            return enriched_items

        except Exception as e:
            logger.warning(
                f"Batch enrichment failed ({e}). Falling back to single-item mode for {len(chunk)} items."
            )
            # Fall back to single-item enrichment for each item in the chunk
            return [self.enrich_item(item) for item in chunk]

    def enrich_batch(
        self,
        items: list[dict],
        progress_callback: Optional[Callable[[int, int], None]] = None,
        checkpoint_callback: Optional[Callable[[list[dict]], None]] = None,
    ) -> list[dict]:
        """
        Enrich a batch of scraped items using chunked batch LLM calls.

        Sends items in chunks of BATCH_CHUNK_SIZE per API call to minimize
        rate-limit pressure. Never crashes on individual item failure.
        Saves checkpoints periodically via checkpoint_callback.

        Args:
            items: List of scraped item dicts.
            progress_callback: Optional callback(current_index, total) for progress.
            checkpoint_callback: Optional callback(enriched_so_far) to save progress.

        Returns:
            List of all items (enriched or original with error).
        """
        results = []
        total = len(items)

        # Separate already-enriched items from unenriched
        to_enrich = []
        for item in items:
            if "enriched_at" in item:
                self.skipped_count += 1
                results.append(item)
            else:
                to_enrich.append(item)

        total_chunks = (len(to_enrich) + BATCH_CHUNK_SIZE - 1) // BATCH_CHUNK_SIZE if to_enrich else 0

        logger.info(
            f"Starting batch enrichment: {len(to_enrich)} items to enrich "
            f"({self.skipped_count} already enriched, skipping). "
            f"Chunk size: {BATCH_CHUNK_SIZE} → ~{total_chunks} API calls."
        )

        # Process in chunks
        processed = 0
        enriched_new_items = []  # Track enriched items for checkpoint saves

        for i in range(0, len(to_enrich), BATCH_CHUNK_SIZE):
            chunk = to_enrich[i : i + BATCH_CHUNK_SIZE]
            chunk_num = (i // BATCH_CHUNK_SIZE) + 1

            logger.info(f"Processing chunk {chunk_num}/{total_chunks} ({len(chunk)} items)...")

            enriched_chunk = self._enrich_chunk(chunk)
            results.extend(enriched_chunk)
            enriched_new_items.extend(enriched_chunk)

            processed += len(chunk)
            if progress_callback:
                progress_callback(processed, len(to_enrich))

            # Checkpoint save every CHECKPOINT_INTERVAL chunks
            if checkpoint_callback and chunk_num % CHECKPOINT_INTERVAL == 0:
                checkpoint_callback(enriched_new_items)

            # Inter-chunk cooldown to let Groq rate limits recover
            if i + BATCH_CHUNK_SIZE < len(to_enrich):
                import time
                logger.debug("Inter-chunk cooldown: 3s...")
                time.sleep(3)

        # Final checkpoint save (catch anything after last interval)
        if checkpoint_callback and enriched_new_items:
            checkpoint_callback(enriched_new_items)

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
    def _extract_json_array(text: str) -> list:
        """
        Extract a JSON array from a response that may contain markdown code fences.

        Handles responses like:
            ```json
            [{"id": "...", ...}, ...]
            ```
        """
        cleaned = text.strip()

        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [line for line in lines if not line.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        result = json.loads(cleaned)
        if not isinstance(result, list):
            raise ValueError(f"Expected JSON array, got {type(result).__name__}")
        return result

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
