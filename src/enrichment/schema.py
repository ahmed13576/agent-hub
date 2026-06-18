"""
Agent Hub - Enrichment Schema & Validators

Defines the enrichment output schema, validation functions, and merge logic.
The enrichment schema extends the base scraper's 10-field unified item schema
with 8 additional fields produced by LLM analysis.

Validation is strict: all LLM output is validated before merge to prevent
hallucinated or malformed data from entering the database.
"""

from datetime import datetime, timezone
from typing import Any

# ── Valid Enums ──────────────────────────────────────────────────────────────

VALID_CATEGORIES = {"battle-tested", "new-upcoming", "experimental"}

VALID_TAGS = {
    "token-saving",
    "multi-agent",
    "prompting",
    "frameworks",
    "budget-control",
    "workflow",
    "configuration",
    "debugging",
    "cost-optimization",
    "context-management",
}

# ── Enrichment Field Definitions ─────────────────────────────────────────────

ENRICHMENT_FIELDS = {
    # LLM-generated fields
    "summary": {"type": str, "min_length": 50, "max_length": 500},
    "category": {"type": str, "enum": VALID_CATEGORIES},
    "effectiveness_score": {"type": (int, float), "min": 0.0, "max": 1.0},
    "relevance_score": {"type": (int, float), "min": 0.0, "max": 1.0},
    "enriched_tags": {"type": list, "valid_values": VALID_TAGS},
    # System-generated fields (not validated from LLM output)
    "enriched_at": {"type": str, "system": True},
    "model_used": {"type": str, "system": True},
    "enrichment_version": {"type": str, "system": True},
}

# Fields the LLM must return (subset of ENRICHMENT_FIELDS)
LLM_REQUIRED_FIELDS = {"summary", "category", "effectiveness_score", "relevance_score", "enriched_tags"}


def validate_enrichment(enrichment: dict) -> tuple[bool, list[str]]:
    """
    Validate an enrichment dict against the schema.

    Only validates the LLM-generated fields (summary, category, scores, tags).
    System fields (enriched_at, model_used, enrichment_version) are added by
    merge_enrichment() and are not expected from the LLM.

    Args:
        enrichment: Dict of enrichment fields to validate.

    Returns:
        Tuple of (is_valid, list_of_error_messages).
    """
    errors: list[str] = []

    # Check all required LLM fields are present
    for field in LLM_REQUIRED_FIELDS:
        if field not in enrichment:
            errors.append(f"Missing required field: {field}")

    # If fields are missing, further checks will fail — return early
    if errors:
        return False, errors

    # Validate summary
    summary = enrichment["summary"]
    if not isinstance(summary, str):
        errors.append(f"summary must be str, got {type(summary).__name__}")
    else:
        if len(summary) < ENRICHMENT_FIELDS["summary"]["min_length"]:
            errors.append(
                f"summary too short: {len(summary)} chars "
                f"(min {ENRICHMENT_FIELDS['summary']['min_length']})"
            )
        if len(summary) > ENRICHMENT_FIELDS["summary"]["max_length"]:
            errors.append(
                f"summary too long: {len(summary)} chars "
                f"(max {ENRICHMENT_FIELDS['summary']['max_length']})"
            )

    # Validate category
    category = enrichment["category"]
    if not isinstance(category, str):
        errors.append(f"category must be str, got {type(category).__name__}")
    elif category.lower().strip() not in VALID_CATEGORIES:
        errors.append(
            f"Invalid category: {category!r}. "
            f"Must be one of: {sorted(VALID_CATEGORIES)}"
        )

    # Validate scores
    for score_field in ("effectiveness_score", "relevance_score"):
        score = enrichment[score_field]
        if not isinstance(score, (int, float)):
            errors.append(f"{score_field} must be numeric, got {type(score).__name__}")
        else:
            if score < 0.0 or score > 1.0:
                errors.append(f"{score_field} out of range: {score} (must be 0.0-1.0)")

    # Validate enriched_tags
    tags = enrichment["enriched_tags"]
    if not isinstance(tags, list):
        errors.append(f"enriched_tags must be list, got {type(tags).__name__}")
    else:
        invalid_tags = [t for t in tags if t not in VALID_TAGS]
        if invalid_tags:
            errors.append(
                f"Invalid tags: {invalid_tags}. "
                f"Allowed: {sorted(VALID_TAGS)}"
            )

    return (len(errors) == 0, errors)


def merge_enrichment(
    item: dict,
    enrichment: dict,
    model_used: str = "unknown",
    enrichment_version: str = "unknown",
) -> dict:
    """
    Merge a validated enrichment result into a scraped item.

    Creates a NEW dict — does NOT mutate the input item.
    Adds system-generated fields: enriched_at, model_used, enrichment_version.

    Args:
        item: Original scraped item dict (10-field schema).
        enrichment: Validated enrichment dict (LLM output fields).
        model_used: Name of the model that produced the enrichment.
        enrichment_version: Hash of the prompt template used.

    Returns:
        New dict with all original fields + enrichment fields (18 total).
    """
    merged = dict(item)  # Shallow copy — does not mutate original

    # Add LLM-generated fields
    for field in LLM_REQUIRED_FIELDS:
        merged[field] = enrichment[field]

    # Add system-generated fields
    merged["enriched_at"] = datetime.now(timezone.utc).isoformat()
    merged["model_used"] = model_used
    merged["enrichment_version"] = enrichment_version

    return merged
