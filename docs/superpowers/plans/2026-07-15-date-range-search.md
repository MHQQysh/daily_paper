# Date Range Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users search an inclusive date range up to 31 days and select one Top-N set per direction across the entire range.

**Architecture:** Retrieve each UTC day independently from the four broad arXiv categories, deduplicate the union, and create a date-balanced local shortlist per direction. DeepSeek scores only the shortlist, after which the existing per-direction selection, Chinese enrichment, and append-only merge run unchanged.

**Tech Stack:** Python 3.11 standard library, DeepSeek chat completions API, arXiv Atom API, static HTML/CSS/JavaScript, GitHub Actions, Python `unittest`.

## Global Constraints

- Interactive ranges are inclusive and must contain between 1 and 31 calendar days.
- Scheduled runs default both dates to the previous UTC day.
- `papers_per_topic` remains bounded from 1 through 50 and applies to the whole range.
- Retrieval stays broad across `cs.AI`, `cs.CV`, `cs.LG`, and `cs.CL`.
- Existing paper details, manual add/delete, category editing, PDF import, and append-only storage remain unchanged.
- Runtime data files `data/papers.json`, `docs/papers.json`, and `docs/run_status.json` must not be staged.

---

### Task 1: Range Validation And Retrieval

**Files:**
- Modify: `scripts/fetch_papers.py`
- Test: `tests/test_fetch_papers.py`

**Interfaces:**
- Produces: `resolve_date_range(start_value: str, end_value: str, today: date | None = None) -> tuple[str, str]`
- Produces: `iter_date_range(start_date: str, end_date: str) -> list[str]`
- Produces: `fetch_category_range(start_date: str, end_date: str, max_per_day: int = 1000) -> tuple[list[dict], dict[str, int]]`

- [ ] **Step 1: Write failing tests for defaults, inclusive ranges, reversed dates, and 31-day bounds**

```python
def test_date_range_defaults_to_previous_utc_day(self):
    start, end = fetch_papers.resolve_date_range("", "", today=dt.date(2026, 7, 15))
    self.assertEqual((start, end), ("2026-07-14", "2026-07-14"))

def test_date_range_is_inclusive_and_rejects_invalid_bounds(self):
    self.assertEqual(
        fetch_papers.iter_date_range("2026-07-10", "2026-07-12"),
        ["2026-07-10", "2026-07-11", "2026-07-12"],
    )
    with self.assertRaisesRegex(ValueError, "start date"):
        fetch_papers.resolve_date_range("2026-07-12", "2026-07-10")
    with self.assertRaisesRegex(ValueError, "31 days"):
        fetch_papers.resolve_date_range("2026-06-01", "2026-07-02")
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run: `python -m unittest tests.test_fetch_papers.ArxivFetchTests.test_date_range_defaults_to_previous_utc_day tests.test_fetch_papers.ArxivFetchTests.test_date_range_is_inclusive_and_rejects_invalid_bounds -v`

Expected: `AttributeError` for the new range helpers.

- [ ] **Step 3: Implement range helpers and daily retrieval union**

```python
def resolve_date_range(start_value, end_value, today=None):
    previous = (today or dt.datetime.now(dt.timezone.utc).date()) - dt.timedelta(days=1)
    start = dt.date.fromisoformat(start_value) if start_value else previous
    end = dt.date.fromisoformat(end_value) if end_value else previous
    if start > end:
        raise ValueError("start date must not be later than end date")
    if (end - start).days + 1 > 31:
        raise ValueError("date range cannot exceed 31 days")
    return start.isoformat(), end.isoformat()
```

`fetch_category_range` calls `fetch_daily_category_papers` once per value returned by `iter_date_range`, merges duplicate identities with `paper_identity_keys`, and returns the deduplicated papers plus the number of daily retrievals.

- [ ] **Step 4: Run `tests.test_fetch_papers`**

Run: `python -m unittest tests.test_fetch_papers -v`

Expected: all fetcher tests pass.

### Task 2: Balanced Local Shortlist And Range Main Pipeline

**Files:**
- Modify: `scripts/fetch_papers.py`
- Test: `tests/test_fetch_papers.py`

**Interfaces:**
- Consumes: `fallback_topic_scores`, `paper_identity_keys`, `fetch_category_range`
- Produces: `shortlist_candidates(papers: list[dict], papers_per_topic: int) -> tuple[list[dict], dict[str, int]]`

- [ ] **Step 1: Add a failing test proving every date contributes before global fill**

```python
def test_shortlist_balances_dates_and_deduplicates_topics(self):
    topics = {
        "vision": {"name": "Vision", "description": "visual tokens", "keywords": ["visual token"]},
        "grpo": {"name": "GRPO", "description": "policy optimization", "keywords": ["grpo"]},
    }
    papers = [
        {"id": f"paper-{day}", "title": "Visual token GRPO", "abstract": "visual token grpo", "published": f"2026-07-{day}"}
        for day in ("10", "11", "12")
    ]
    with mock.patch.object(fetch_papers, "TOPICS", topics):
        shortlisted, counts = fetch_papers.shortlist_candidates(papers, papers_per_topic=1, per_topic_limit=3)
    self.assertEqual({paper["published"] for paper in shortlisted}, {"2026-07-10", "2026-07-11", "2026-07-12"})
    self.assertEqual(counts, {"vision": 3, "grpo": 3})
```

- [ ] **Step 2: Implement the shortlist**

For each direction, rank by local score, date, and title. Reserve `max(1, limit // date_count)` candidates per date, then fill remaining slots from the global ranking. Use `limit = min(200, max(50, papers_per_topic * 8))` in production and deduplicate the union by paper identity.

- [ ] **Step 3: Replace single-date CLI execution**

Use `--start-date` and `--end-date`; resolve the range, call `fetch_category_range`, shortlist, DeepSeek ranking, per-topic selection, enrichment, and append-only merge. Write status keys `start_date`, `end_date`, `daily_retrievals`, `raw_found`, `deduplicated_found`, `shortlisted`, `shortlisted_per_topic`, `selected_per_topic`, and `selected_union`.

- [ ] **Step 4: Run fetcher tests and syntax checks**

Run: `python -m unittest tests.test_fetch_papers -v && python -m compileall -q scripts`

Expected: all tests pass and compilation exits 0.

### Task 3: Local API And GitHub Workflow

**Files:**
- Modify: `scripts/local_server.py`
- Modify: `scripts/run_local_day.ps1`
- Modify: `.github/workflows/daily.yml`
- Test: `tests/test_local_server.py`

**Interfaces:**
- Consumes JSON keys: `start_date`, `end_date`, `papers_per_topic`, `topics`, `deepseek_api_key`
- Produces CLI arguments: `--start-date`, `--end-date`, `--papers-per-topic`

- [ ] **Step 1: Rewrite local payload tests**

Assert both dates default to yesterday, reversed and 32-day ranges fail, and the generated command contains both new date arguments without the API key.

- [ ] **Step 2: Implement local validation and command construction**

Parse both ISO dates, enforce the inclusive 31-day limit, and pass them to the fetcher. Keep the DeepSeek key only in the child-process environment.

- [ ] **Step 3: Update PowerShell and Actions inputs**

Rename workflow inputs and environment variables to `start_date`, `end_date`, `PAPER_START_DATE`, and `PAPER_END_DATE`. Scheduled empty values continue to resolve in Python. Update `run_local_day.ps1` to accept `$StartDate`, `$EndDate`, and `$PapersPerTopic`.

- [ ] **Step 4: Run local server tests**

Run: `python -m unittest tests.test_local_server -v`

Expected: all tests pass.

### Task 4: Web Range Controls And Reporting

**Files:**
- Modify: `docs/index.html`
- Modify: `docs/app.js`
- Modify: `docs/styles.css`
- Modify: `README.md`

**Interfaces:**
- Sends: `{start_date, end_date, papers_per_topic, topics, deepseek_api_key}` locally
- Sends workflow inputs: `{start_date, end_date, papers_per_topic, topics_json}`

- [ ] **Step 1: Replace the date control**

Add required inputs `startDate` and `endDate`, retain `papersPerTopic`, and keep the existing responsive two-column grid.

- [ ] **Step 2: Validate and serialize the range**

`selectedRunOptions()` parses both values, rejects missing, reversed, or over-31-day ranges, and returns `{startDate, endDate, papersPerTopic}`. Both local and GitHub request builders use those values.

- [ ] **Step 3: Render range status**

Show `start_date to end_date`, retrieved/deduplicated/shortlisted/selected counts, per-direction selected counts, and merge totals. Continue tolerating older status files.

- [ ] **Step 4: Update README usage**

Document the inclusive 31-day range, range-wide N semantics, daily broad retrieval, local shortlist, DeepSeek final ranking, and new command-line arguments.

- [ ] **Step 5: Run JavaScript syntax and diff checks**

Run: `node --check docs/app.js && git diff --check`

Expected: both commands exit 0.

### Task 5: End-To-End Verification And Commit

**Files:**
- Verify all modified files

- [ ] **Step 1: Run the full test suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 2: Restart the loopback server**

Safely stop only the process whose command line contains `daily_paper` and `local_server.py`, restart it hidden on `127.0.0.1:8766`, and confirm `/api/status` returns HTTP 200.

- [ ] **Step 3: Browser QA**

At desktop and 390x844 mobile sizes, assert both date inputs and the per-direction count exist, the old `targetDate` control does not exist, there is no horizontal overflow, paper details still render, and browser logs are empty.

- [ ] **Step 4: Secret and staging checks**

Run a tracked-file scan for `sk-[0-9a-f]{24,}` excluding runtime JSON. Stage only source, tests, workflow, and documentation; leave all three runtime data files unstaged.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: search papers across date ranges"
```
