# Internal improvement cycle 001 — readiness evaluator

Input is entirely invented: `improvement-cycle-synthetic-report.json` contains 100 search calls, 40 stale. `improvement-cycle-001.json` is the validated read-only analyzer output. No client data was used.

Observation: stale calls merit investigation. Competing explanations include expected source edits, missed refreshes and broken recovery. The aggregate alone cannot distinguish them. Hypothesis: explicit refresh may fail to restore fresh results. Acceptance: on synthetic saved-file drift, stale must become ready with the expected item after refresh, repeated three times. Retrieval and privacy suites must continue to pass. Do not add automatic refresh without evidence.

The reproduction passed: existing refresh restores evidence. The proposed product behavior change was unnecessary. While preparing that check, the initial benchmark artifact (`client-readiness-baseline-2026-09-10.json`, suite 1) exposed a separate evaluator defect: `kotlin_parser_ready` was false while overall `passed` was true. The one-line Kotlin fixture was also unsuitable for this parser.

Bounded correction: use a multiline Kotlin fixture, require Kotlin items for the overall readiness pass, and add the stale/reindex case. A regression test forces Kotlin lookup to return no items and requires overall failure while the other cases pass. The candidate artifact (`client-readiness-benchmark-2026-09-10.json`, suite 2) passes the four cases, each repeated three times, with Kotlin ready.

Decision: retain explicit recovery, accept the evaluator correction for review, and establish suite 2 as the new baseline. Because the evaluator/fixture changed, suite 1 versus suite 2 is not a valid speed or quality improvement comparison. No token/cost savings or causal client benefit is claimed. The regression and the rejected hypothesis both improve the next cycle.

Rollback: revert the evaluator correction only for investigation; do not release the known false-positive readiness gate. All changes remain local for Laura's review. Real feedback intake, independent acceptance fixtures and any release decision remain deliberate manual steps.
