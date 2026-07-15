# Query Expansion And Manual Add Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add DeepSeek-planned multi-query discovery, append-only storage, and browser-based manual paper addition.

**Architecture:** Extend the existing standard-library Python fetcher with a planner and RRF fusion layer. Extend the loopback server with focused manual-paper APIs, and add a browser dialog that resolves, analyzes, confirms, and merges a paper.

**Tech Stack:** Python 3 standard library, DeepSeek chat completions, arXiv Atom API, vanilla JavaScript, HTML/CSS.

## Global Constraints

- Browser-triggered searches must never remove stored papers.
- Deduplicate by arXiv base ID, DOI, and normalized title.
- Preserve manually selected topics across later automatic updates.
- Never write the DeepSeek key to disk, logs, or API responses.
- Keep local API access bound to `127.0.0.1`.

---

### Task 1: Query Planner

**Files:**
- Modify: `scripts/fetch_papers.py`
- Test: `tests/test_fetch_papers.py`

**Interfaces:**
- `build_query_plan(topics, model) -> dict`
- Plan item: `{topic_id, search_queries, intent_queries}`.

- [ ] Add tests for valid DeepSeek JSON, unknown topic removal, query deduplication, and deterministic keyword fallback.
- [ ] Implement one combined DeepSeek planner call for all topics.
- [ ] Print the generated plan without printing credentials.
- [ ] Run `python -m unittest tests.test_fetch_papers -v`.

### Task 2: Multi-Query Retrieval And RRF

**Files:**
- Modify: `scripts/fetch_papers.py`
- Test: `tests/test_fetch_papers.py`

**Interfaces:**
- `fetch_arxiv_query(query, days, max_results, target_date) -> list[dict]`
- `fuse_query_results(results_by_query, rrf_k=60) -> list[dict]`

- [ ] Add mocked Atom-feed tests for independent queries, base-ID deduplication, normalized-title deduplication, and RRF ordering.
- [ ] Execute planner queries with arXiv rate-limit spacing and existing retry behavior.
- [ ] Attach matched query and discovery topic metadata to fused candidates.
- [ ] Send only top fused candidates to DeepSeek enrichment.

### Task 3: Append-Only Merge

**Files:**
- Modify: `scripts/fetch_papers.py`
- Modify: `scripts/local_server.py`
- Modify: `docs/index.html`
- Modify: `docs/app.js`
- Test: `tests/test_fetch_papers.py`
- Test: `tests/test_local_server.py`

**Interfaces:**
- `paper_identity_keys(paper) -> list[str]`
- `merge_papers(existing, incoming) -> (papers, stats)` where stats includes `added`, `updated`, `duplicates`, `total`.

- [ ] Add tests proving absent historical papers remain and manual topics survive automatic updates.
- [ ] Remove `fresh` from local request validation and command construction.
- [ ] Remove the replace-library control and all frontend fresh-run payload fields.
- [ ] Keep the CLI-only `--fresh` switch for explicit maintenance outside the browser.

### Task 4: Manual Paper APIs

**Files:**
- Create: `scripts/paper_service.py`
- Modify: `scripts/local_server.py`
- Test: `tests/test_paper_service.py`

**Interfaces:**
- `resolve_paper_input(value) -> list[dict]`
- `analyze_paper(paper, topics, api_key, model) -> dict`
- `add_paper(paper, selected_topics) -> dict`
- HTTP endpoints: `/api/papers/resolve`, `/api/papers/analyze`, `/api/papers/add`.

- [ ] Test arXiv URL/ID parsing and title candidate resolution with mocked network responses.
- [ ] Test DeepSeek recommendation filtering and English fallback.
- [ ] Test duplicate manual add and manual-topic union.
- [ ] Serialize write access so manual add cannot race with an automatic job.

### Task 5: Manual Add Browser Flow

**Files:**
- Modify: `docs/index.html`
- Modify: `docs/app.js`
- Modify: `docs/styles.css`

- [ ] Add a plus icon button beside the existing search field.
- [ ] Build a dialog with candidate selection, analysis progress, translated preview, and three direction checkboxes.
- [ ] Confirm through `/api/papers/add`, close the dialog, reload data, and select the added paper.
- [ ] Show actionable errors without clearing the user's input.

### Task 6: Run Report And Verification

**Files:**
- Modify: `scripts/fetch_papers.py`
- Modify: `docs/app.js`
- Modify: `README.md`

- [ ] Store the generated query plan and duplicate count in `docs/run_status.json`.
- [ ] Render an expandable “Generated queries” section in the run panel.
- [ ] Run Python compile, all unit tests, JavaScript syntax validation, and JSON validation.
- [ ] Use browser interception to verify append-only run payload, title-candidate selection, recommended-topic editing, and final add payload.
