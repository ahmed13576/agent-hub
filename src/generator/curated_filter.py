"""
Agent Hub - Curated Strategies Filter

Filters enriched items by relevance threshold to produce a curated subset
of high-signal strategies. Items below the threshold remain in database.json
but are excluded from the markdown catalog and curated_strategies.json.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from src.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

# Items must score at or above this relevance to be curated
CURATED_RELEVANCE_THRESHOLD = 0.5

DEFAULT_CURATED_PATH = PROJECT_ROOT / "data" / "curated_strategies.json"


def filter_curated(items: list[dict]) -> list[dict]:
    """
    Filter items to only those meeting curation criteria.

    Criteria:
    - Must have been enriched (enriched_at field present)
    - Must have relevance_score >= CURATED_RELEVANCE_THRESHOLD

    Args:
        items: List of item dicts (may be enriched or raw).

    Returns:
        New list of items meeting curation criteria. Does NOT mutate input.
    """
    curated = [
        item for item in items
        if item.get("enriched_at") is not None
        and isinstance(item.get("relevance_score"), (int, float))
        and item["relevance_score"] >= CURATED_RELEVANCE_THRESHOLD
    ]
    logger.info(
        f"Curated filter: {len(curated)}/{len(items)} items "
        f"meet relevance >= {CURATED_RELEVANCE_THRESHOLD}"
    )
    return curated


def save_curated_strategies(
    items: list[dict],
    path: Optional[Path] = None,
) -> Path:
    """
    Filter items and save curated subset to JSON.

    Args:
        items: Full database items list.
        path: Output path. Defaults to data/curated_strategies.json.

    Returns:
        Path the curated file was written to.
    """
    output_path = path or DEFAULT_CURATED_PATH
    curated = filter_curated(items)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(curated, f, indent=2, ensure_ascii=False)

    logger.info(f"Saved {len(curated)} curated strategies to {output_path}")
    return output_path


def load_curated_strategies(path: Optional[Path] = None) -> list[dict]:
    """
    Load curated strategies from JSON file.

    Args:
        path: Input path. Defaults to data/curated_strategies.json.

    Returns:
        List of curated item dicts. Empty list if file doesn't exist.
    """
    input_path = path or DEFAULT_CURATED_PATH
    if not input_path.exists():
        return []
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load curated strategies: {e}")
        return []
