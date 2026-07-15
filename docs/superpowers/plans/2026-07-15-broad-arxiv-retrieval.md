# Broad arXiv Retrieval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retrieve every relevant arXiv-category paper for one date, rank the full set with DeepSeek, and keep up to N papers independently for each configured direction.

**Architecture:** `fetch_papers.py` performs one broad category retrieval and a lightweight ranking pass before translating only the selected union. The local API, GitHub workflow, and web panel expose only `target_date` and `papers_per_topic` as search controls.

**Tech Stack:** Python 3.11 standard library, DeepSeek OpenAI-compatible chat API, vanilla JavaScript, GitHub Actions, `unittest`.

## Global Constraints

- Retrieve arXiv categories `cs.AI`, `cs.CV`, `cs.LG`, and `cs.CL`.
- Scan at most 1,000 arXiv records for one UTC date.
- Store an overlapping paper once while retaining every selected direction.
- Keep existing paper detail, manual add, delete, and append-only merge behavior.
- Do not stage runtime changes to `data/papers.json`, `docs/papers.json`, or `docs/run_status.json`.

---

### Task 1: Broad daily retrieval and ranking primitives

**Files:**
- Modify: `scripts/fetch_papers.py`
- Modify: `tests/test_fetch_papers.py`

**Interfaces:**
- Produces: `fetch_daily_category_papers(target_date: str, max_scan: int = 1000) -> list[dict]`
- Produces: `rank_papers_by_topic(papers, model, batch_size=20) -> dict[str, dict[str, int]]`
- Produces: `select_per_topic(papers, scores, papers_per_topic) -> tuple[list[dict], dict[str, int]]`

- [ ] **Step 1: Add failing tests**

Assert that broad retrieval calls `fetch_arxiv` with `(cat:cs.AI OR cat:cs.CV OR cat:cs.LG OR cat:cs.CL)`, the selected date, and a 1,000-paper scan limit. Assert that per-topic selection chooses N independently, retains multi-topic overlap, and returns a deduplicated union.

- [ ] **Step 2: Implement broad retrieval**

Add constants for the four categories and category expression. Validate the ISO date and call the existing paginated `fetch_arxiv` exactly once.

- [ ] **Step 3: Implement ranking prompts and fallback**

Send batches of at most 20 compact `{id,title,abstract}` records. Require JSON shaped as:

```json
{"papers":[{"id":"paper-id","scores":{"topic-id":85}}]}
```

Clamp scores to 0 through 100 and ignore unknown topic IDs. When a batch fails, derive topic-specific scores from configured keyword phrase matches.

- [ ] **Step 4: Implement independent Top-N selection**

Sort by topic score, publication date, and title. Select positive-score papers up to N for each topic. Merge by paper identity, attach all selected topic IDs, set `relevance_score` to the maximum selected score, and return per-topic counts.

---

### Task 2: Replace the command-line pipeline

**Files:**
- Modify: `scripts/fetch_papers.py`
- Modify: `tests/test_fetch_papers.py`

**Interfaces:**
- Consumes: Task 1 ranking primitives
- Produces: CLI option `--papers-per-topic`

- [ ] **Step 1: Add main-pipeline tests**

Mock retrieval, ranking, selection, enrichment, merge, and output writes. Assert that no query plan or minimum-score filter is invoked and that status contains `papers_per_topic`, `selected_per_topic`, `raw_found`, and `kept`.

- [ ] **Step 2: Replace legacy arguments**

Remove active use of `--days`, `--max-results`, and `--min-score`. Add `--papers-per-topic`, bounded to 1 through 50. Default an empty date to yesterday in UTC.

- [ ] **Step 3: Wire the new pipeline**

Execute broad fetch, rank, per-topic selection, selected-only enrichment, append-only merge, output write, and the new status report. Do not call `build_query_plan` or `fetch_from_query_plan` from `main`.

---

### Task 3: Simplify local API and GitHub workflow

**Files:**
- Modify: `scripts/local_server.py`
- Modify: `tests/test_local_server.py`
- Modify: `.github/workflows/daily.yml`

**Interfaces:**
- Produces: local request `{target_date, papers_per_topic, topics, deepseek_api_key}`
- Produces: workflow inputs `target_date`, `papers_per_topic`, and `topics_json`

- [ ] **Step 1: Rewrite local validation tests**

Assert ISO-date validation, `papers_per_topic` bounds of 1 through 50, API-key redaction, and a command containing only `--date`, `--papers-per-topic`, and optional `--topics-json` search options.

- [ ] **Step 2: Update local server validation and command construction**

Default a missing date to yesterday UTC. Remove lookback, maximum-result, and minimum-score fields from validated requests and subprocess commands.

- [ ] **Step 3: Update workflow inputs**

Scheduled runs pass an empty date, allowing the Python previous-day default. Manual dispatch accepts the date and papers per direction, with a default count of 5.

---

### Task 4: Simplify the web controls and verify

**Files:**
- Modify: `docs/index.html`
- Modify: `docs/app.js`
- Modify: `docs/styles.css`
- Modify: `README.md`

**Interfaces:**
- Consumes: new local and workflow request shapes
- Produces: date and `Papers per direction` controls

- [ ] **Step 1: Replace run controls**

Remove Range, Max results, and Min score. Keep a required date input and add a numeric `Papers per direction` input with minimum 1, maximum 50, and default 5.

- [ ] **Step 2: Update request and report rendering**

Send only the new search parameters. Replace generated-query output with selected counts for each direction and show date, retrieved count, union size, additions, updates, duplicates, and total.

- [ ] **Step 3: Update documentation**

Describe broad category retrieval, DeepSeek per-direction ranking, per-direction N semantics, overlap deduplication, and previous-day scheduled runs.

- [ ] **Step 4: Run verification**

```powershell
python -m unittest discover -s tests -v
python -m py_compile scripts/fetch_papers.py scripts/local_server.py
node --check docs/app.js
git diff --check
```

Expected: all tests and syntax checks pass.

- [ ] **Step 5: Browser QA**

Verify desktop and mobile controls contain only date, papers per direction, token, and run command. Confirm existing article details and links remain visible, no horizontal overflow occurs, and console errors are empty.
