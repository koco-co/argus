# ADR-012: Tiered evidence storage — summaries/patches in git, heavy evidence as artifacts

- Date: 2026-08-27
- Status: Accepted
- Related: ADR-010, ADR-014, DATA_MODEL §9/§10, PRD §4.7/§6/§7.2, ARCHITECTURE §2/§8, ENVIRONMENT_SETUP gitignore

## Background

ADR-010 placed every run's evidence under `iterations/<id>/runs/<run_id>/` but left its git strategy undecided, and both naive answers are wrong. Committing everything drags Playwright traces (DOM snapshots, network captures with tokens/cookies/response bodies) and multi-MB Allure results into permanent git history — the §10 redaction boundary does not cover trace internals, and sanitizing them means rewriting Playwright's format. Ignoring everything breaks the §7.2 claim that acceptance is reconstructable from `iterations/<id>/` alone once CI artifacts (90-day default retention) expire, and hides locally produced evidence from PR reviewers.

## Decision

Three tiers:

1. **In git (minimum acceptance-closure set)**: `run-summary.yaml`, `execution-manifest.json` (the 1.1 exact-nodeid/SHA/digest binding), and the patch texts behind `attempts[].diff_ref`. These are small, structured/text records and exactly what terminal diff review needs.
2. **Gitignored, reviewed in-session**: `allure-results/`, `logs/`, `traces/` under a run directory, for locally produced evidence. Mandatory review happens inside the session before acceptance; after that they are reproducible-by-rerun and disposable.
3. **CI artifacts only**: JUnit XML, Allure results, traces and logs produced by CI are uploaded as workflow artifacts (retention configured) and linked from the PR; their paths, digests and counts are recorded by the execution manifest, but the heavy files are never committed.

Traces are added to the DATA_MODEL §10 redaction-boundary list: trace material never leaves the session/machine unsanitized.

## Consequences

`.gitignore` carries explicit `iterations/*/runs/*/` rules (keep `run-summary.yaml`, `execution-manifest.json` and patches, ignore the heavy subdirectories); CI's upload path lists the report and run-evidence trees explicitly; acceptance reviewers rely on the summary + manifest + diffs in-repo plus the session transcript (local) or artifact link (CI).
