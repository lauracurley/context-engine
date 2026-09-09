# Frozen retrieval comparison — 2026-09-09

`questions.json` contains 16 newly authored questions, frozen before their first run, with file-level relevance judgments. They include natural-language behavior questions, identifiers, cross-source evidence, paraphrases, cross-environment negatives, and absent behavior. They were not used to tune retrieval. The author had already seen these four fixture files, so this is a prospective regression set, not an independent blinded holdout. Once used to guide changes, treat it as a development set and obtain a fresh evaluation set.

Run from the repository root:

```sh
python3 evaluate_retrieval.py --output /tmp/context-engine-retrieval-results.json
```

The original `python3 evaluate.py` remains the five-case smoke gate. The new comparison exits successfully when measurement completes; imperfect retrieval is reported, not hidden by an execution failure.

Both methods search the same eligible files from the same manifest, use a 10-item cap and an 8000 serialized-evidence-byte budget by default, and use temporary index stores. Context Engine uses its normal BM25 excerpts. The plain-file baseline uses case-insensitive literal OR matches over query words in paths/content, returning full files in source/path order with no index, camel-case expansion, or relevance ranking. It is a deterministic plain-file comparator, not a simulated developer using iterative ripgrep searches. Both responses use provenance-bearing evidence records; different metadata and excerpt sizes incur different costs. Absolute path lengths can affect costs across machines.

Metrics deduplicate returned files. Positive-case macro precision penalizes extra files, recall measures expected-file coverage, and reciprocal rank measures the first expected file's rank. Negative accuracy is the fraction of empty-expectation cases that return no files. Exact file sets require all and only the labeled files, including negative cases. This evaluates retrieval, not answer correctness or task completion.

## Initial results

See `results-2026-09-09.json` for every question, prediction, and metric. The first run used the staged implementation and unchanged demo contents; the final repository rerun reproduced all summary metrics. This artifact records the final repository run. No ranking changes were made after seeing results.

| Metric | Context Engine | Literal file search |
| --- | --- | --- |
| Exact file sets | 10/16 | 9/16 |
| Mean precision, 11 positive cases | 0.773 | 0.727 |
| Mean recall, 11 positive cases | 1.000 | 1.000 |
| Mean reciprocal rank, positive cases | 1.000 | 0.864 |
| Negative accuracy, 5 cases | 4/5 | 4/5 |

The tiny corpus and common-word OR matches inflate recall. Successful paraphrase retrieval is not evidence of semantic understanding: common words can retrieve the labeled file. Both methods falsely return evidence for the absent credit-card-payment question. Context Engine also over-expands `dispatchParcel` to handbook evidence, and a natural-language question containing `UNKNOWN_EVENT` returns API evidence as well as the expected worker. The baseline wins those two exact-file cases. No latency or statistically significant quality advantage is claimed.

Next, collect a larger independent corpus with near-match distractors and independently labeled questions. Compare exact-identifier preservation and common-word filtering using a development set, then evaluate on a fresh holdout. Do not tune repeatedly against these 16 questions and continue calling them held out. Budget-omission reporting is tested separately; this comparison does not measure confidence or whether a retrieved function actually implements the queried behavior.
