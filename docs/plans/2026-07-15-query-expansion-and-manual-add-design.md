# Query Expansion And Manual Add Design

## Goal

Upgrade Daily Paper from fixed-keyword matching to DeepSeek-assisted query expansion and multi-query retrieval, while making every search append-only and allowing a user to add a paper from a title or arXiv reference.

## Discovery Pipeline

One DeepSeek planning call receives all enabled directions. For each direction it returns focused academic search terms, two or three retrieval queries, and ideal-paper intent descriptions. The generated plan is visible in the run report.

Each retrieval query runs independently against arXiv. Results are deduplicated by arXiv base ID and normalized title, then fused with reciprocal rank fusion. The best candidates are sent to the existing DeepSeek enrichment stage for relevance scoring, direction assignment, Chinese summary, Chinese abstract, and relevance explanation.

The planner has a deterministic fallback built from configured keywords. A planner failure therefore reduces retrieval quality but does not prevent a run.

## Append-Only Storage

Browser-triggered searches never pass `--fresh`. The local API does not accept a rebuild flag, and the run panel no longer presents one. Existing records are merged by arXiv ID, DOI when available, and normalized title. Newly discovered metadata may update an existing record, but records absent from a run are never removed.

Manually selected topic assignments are stored separately and unioned into automatic assignments. Later automatic runs cannot remove them.

## Manual Add Flow

The search field keeps its filtering behavior and gains an adjacent add button.

1. The user enters an arXiv URL, arXiv ID, or paper title.
2. The local API resolves an exact arXiv reference or returns up to five title candidates.
3. The user selects a candidate.
4. DeepSeek translates the paper and recommends one or more enabled directions.
5. A confirmation dialog shows editable direction checkboxes.
6. Confirmation merges the paper into the store and refreshes the page.

If DeepSeek analysis fails, the dialog still permits adding the English metadata. If the paper already exists, confirmation updates its metadata and unions the selected manual directions instead of creating a duplicate.

## Local API

- `POST /api/run`: starts append-only expanded discovery.
- `GET /api/status`: reports planner queries, retrieval progress, and merge statistics.
- `POST /api/papers/resolve`: resolves an arXiv reference or title to candidates.
- `POST /api/papers/analyze`: enriches one selected candidate and recommends directions.
- `POST /api/papers/add`: validates and merges a confirmed paper.

All endpoints remain loopback-only. The DeepSeek key is accepted per request, passed only in memory, and never written to status or data files.

## Verification

- Mock DeepSeek planning and validate fallback behavior.
- Mock multiple arXiv query result lists and validate deduplication plus RRF ordering.
- Verify web runs cannot construct a fresh/rebuild command.
- Verify manual paper resolution, analysis fallback, title deduplication, and manual-topic preservation.
- Exercise both browser flows with network interception and verify the final controls and payloads.
