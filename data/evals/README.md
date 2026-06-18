# Golden Eval Dataset

## Purpose
This dataset defines "correct" enrichment output for the AI enrichment pipeline.
It contains 18 human-labeled reference items used for Evaluation-Driven Development (EDD).

## Dataset Composition

| Category | Count | Description |
|----------|-------|-------------|
| Battle-tested | 5 | Well-known tools/techniques with significant adoption |
| New/upcoming | 5 | Recently published, gaining traction |
| Experimental | 3 | Prototype stage, research-oriented |
| Noise (low relevance) | 5 | Unrelated items that should score low relevance |

## Expected Enrichment Fields

Each item includes an `expected_enrichment` dict:
- `expected_category`: The correct category classification
- `expected_relevance_range`: `[min, max]` acceptable relevance score
- `expected_effectiveness_range`: `[min, max]` acceptable effectiveness score
- `expected_tags_must_include`: Tags that MUST appear in output
- `expected_tags_must_not_include`: Tags that must NOT appear
- `summary_must_mention`: Keywords the summary should reference

## Scoring Rubric

| Metric | Passing Threshold | Measurement |
|--------|-------------------|-------------|
| Category accuracy | ≥80% | Matches expected_category |
| Relevance accuracy | ≥85% | Score within expected range |
| Effectiveness accuracy | ≥85% | Score within expected range |
| Tag recall | ≥75% | expected_tags_must_include found |
| Summary coverage | ≥70% | summary_must_mention keywords found |
| Noise filtering | 100% | All noise items relevance < 0.3 |

## How to Run Evals

```bash
# Run golden dataset evaluation (requires GROQ_API_KEY)
python src/main.py --eval

# Run without enriching new data (eval only)
python -c "from src.enrichment.eval_runner import run_eval; from src.enrichment.processor import EnrichmentProcessor; print(run_eval(EnrichmentProcessor()))"
```

## How to Update

1. Add new items to `golden_dataset.json` following the same schema
2. Ensure each item has all 10 scraper fields + `expected_enrichment`
3. Run evals to verify the new items don't break existing thresholds
4. Commit with message: `docs(evals): update golden dataset — N items`
