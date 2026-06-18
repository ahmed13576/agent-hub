"""
Agent Hub - Golden Dataset Evaluation Runner

Runs enrichment against the golden eval dataset and scores results
against the human-labeled expected enrichments. Results are stored
in data/evals/ with timestamps for regression tracking.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default paths
DEFAULT_GOLDEN_PATH = "data/evals/golden_dataset.json"
DEFAULT_RESULTS_DIR = "data/evals"

# Passing thresholds (from ADR-003)
THRESHOLDS = {
    "category_accuracy": 0.80,
    "relevance_accuracy": 0.85,
    "effectiveness_accuracy": 0.85,
    "avg_tag_recall": 0.75,
    "noise_filtering": 1.0,  # 100% — all noise items must have relevance < 0.3
}


def load_golden_dataset(path: str = DEFAULT_GOLDEN_PATH) -> list[dict]:
    """Load the golden eval dataset from JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    logger.info(f"Loaded golden dataset: {len(data)} items from {path}")
    return data


def score_enrichment(enriched_item: dict, expected: dict) -> dict:
    """
    Score an enriched item against expected enrichment values.

    Args:
        enriched_item: The item after LLM enrichment (18-field schema).
        expected: The expected_enrichment dict from the golden dataset.

    Returns:
        Score dict with per-metric results.
    """
    scores = {}

    # Category correctness
    scores["category_correct"] = (
        enriched_item.get("category") == expected.get("expected_category")
    )

    # Relevance score in expected range
    rel = enriched_item.get("relevance_score", -1)
    rel_range = expected.get("expected_relevance_range", [0, 1])
    scores["relevance_in_range"] = rel_range[0] <= rel <= rel_range[1]

    # Effectiveness score in expected range
    eff = enriched_item.get("effectiveness_score", -1)
    eff_range = expected.get("expected_effectiveness_range", [0, 1])
    scores["effectiveness_in_range"] = eff_range[0] <= eff <= eff_range[1]

    # Tag precision & recall
    actual_tags = set(enriched_item.get("enriched_tags", []))
    must_include = set(expected.get("expected_tags_must_include", []))
    must_not_include = set(expected.get("expected_tags_must_not_include", []))

    if must_include:
        scores["tags_recall"] = len(actual_tags & must_include) / len(must_include)
    else:
        scores["tags_recall"] = 1.0  # No required tags = automatic pass

    if actual_tags:
        # Precision relative to expected tags that should appear
        scores["tags_precision"] = len(actual_tags & must_include) / len(actual_tags) if must_include else 1.0
    else:
        scores["tags_precision"] = 1.0 if not must_include else 0.0

    scores["tags_no_forbidden"] = len(actual_tags & must_not_include) == 0

    # Summary keyword coverage
    summary = enriched_item.get("summary", "").lower()
    must_mention = expected.get("summary_must_mention", [])
    if must_mention:
        found = sum(1 for kw in must_mention if kw.lower() in summary)
        scores["summary_keywords_found"] = found / len(must_mention)
    else:
        scores["summary_keywords_found"] = 1.0

    return scores


def run_eval(
    processor,
    dataset_path: str = DEFAULT_GOLDEN_PATH,
    results_dir: str = DEFAULT_RESULTS_DIR,
) -> dict:
    """
    Run golden dataset evaluation.

    Enriches each item in the golden dataset via the processor (LIVE LLM calls),
    scores against expected enrichments, and saves detailed results.

    Args:
        processor: An EnrichmentProcessor instance.
        dataset_path: Path to the golden dataset JSON.
        results_dir: Directory to save eval results.

    Returns:
        Aggregate metrics dict.
    """
    dataset = load_golden_dataset(dataset_path)

    # Enrich all items
    items_only = [{k: v for k, v in item.items() if k != "expected_enrichment"} for item in dataset]
    enriched_items = processor.enrich_batch(items_only)

    # Score each item
    item_scores = []
    for enriched, golden in zip(enriched_items, dataset):
        expected = golden["expected_enrichment"]
        score = score_enrichment(enriched, expected)
        item_scores.append({
            "title": golden.get("title", "unknown"),
            "expected_category": expected.get("expected_category"),
            "actual_category": enriched.get("category"),
            "scores": score,
            "has_error": "enrichment_error" in enriched,
        })

    # Compute aggregate metrics
    n = len(item_scores)
    successful = [s for s in item_scores if not s["has_error"]]
    n_successful = len(successful)

    if n_successful == 0:
        logger.error("All items failed enrichment — cannot compute metrics")
        return {"error": "All items failed", "item_scores": item_scores}

    metrics = {
        "category_accuracy": sum(1 for s in successful if s["scores"]["category_correct"]) / n_successful,
        "relevance_accuracy": sum(1 for s in successful if s["scores"]["relevance_in_range"]) / n_successful,
        "effectiveness_accuracy": sum(1 for s in successful if s["scores"]["effectiveness_in_range"]) / n_successful,
        "avg_tag_recall": sum(s["scores"]["tags_recall"] for s in successful) / n_successful,
        "avg_tag_precision": sum(s["scores"]["tags_precision"] for s in successful) / n_successful,
        "avg_summary_coverage": sum(s["scores"]["summary_keywords_found"] for s in successful) / n_successful,
        "total_items": n,
        "successful_items": n_successful,
        "failed_items": n - n_successful,
    }

    # Noise filtering: check that all noise items (relevance range max <= 0.35) have relevance < 0.3
    noise_items = [
        (s, golden) for s, golden in zip(item_scores, dataset)
        if golden["expected_enrichment"].get("expected_relevance_range", [0, 1])[1] <= 0.35
        and not s["has_error"]
    ]
    if noise_items:
        noise_pass = sum(
            1 for s, golden in noise_items
            if s["scores"]["relevance_in_range"]
        )
        metrics["noise_filtering"] = noise_pass / len(noise_items)
    else:
        metrics["noise_filtering"] = 1.0

    # Save detailed results
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    results_path = Path(results_dir) / f"eval_results_{timestamp}.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_data = {
        "timestamp": timestamp,
        "metrics": metrics,
        "thresholds": THRESHOLDS,
        "item_scores": item_scores,
        "processor_stats": processor.get_stats(),
    }
    results_path.write_text(json.dumps(results_data, indent=2), encoding="utf-8")
    logger.info(f"Eval results saved to {results_path}")

    return metrics


def check_thresholds(metrics: dict) -> tuple[bool, list[str]]:
    """
    Check aggregate metrics against passing thresholds.

    Args:
        metrics: Aggregate metrics dict from run_eval().

    Returns:
        Tuple of (all_pass, list_of_failure_messages).
    """
    failures = []

    for metric_name, threshold in THRESHOLDS.items():
        actual = metrics.get(metric_name)
        if actual is None:
            failures.append(f"{metric_name}: not available")
        elif actual < threshold:
            failures.append(
                f"{metric_name}: {actual:.2%} < {threshold:.2%} threshold"
            )

    return (len(failures) == 0, failures)
