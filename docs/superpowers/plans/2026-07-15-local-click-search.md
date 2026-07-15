# Local Click-to-Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the local Daily Paper page run arXiv search and DeepSeek translation from one browser click without a GitHub token or terminal command.

**Architecture:** A loopback-only Python server serves `docs/` and exposes asynchronous run/status endpoints. The frontend selects local or GitHub mode from its origin, stores the matching API token in browser localStorage, and polls until updated data is available.

**Tech Stack:** Python 3 standard library, existing `fetch_papers.py`, vanilla JavaScript, HTML/CSS, PowerShell launcher.

## Global Constraints

- Bind the local API server only to `127.0.0.1`.
- Never write the DeepSeek key to disk or include it in logs/status responses.
- Allow only one local fetch process at a time.
- Keep GitHub Pages workflow dispatch working outside localhost.
- Preserve existing paper data unless the user selects Rebuild.

---

### Task 1: Local API Server

**Files:**
- Create: `scripts/local_server.py`
- Test: `tests/test_local_server.py`

**Interfaces:**
- Consumes: JSON fields `lookback_days`, `target_date`, `max_results`, `min_score`, `fresh`, `topics`, and `deepseek_api_key`.
- Produces: `POST /api/run` with HTTP 202 and `GET /api/status` with `{state, message, output, started_at, finished_at, return_code}`.

- [ ] **Step 1: Write failing validation and command-construction tests**

Test valid requests, invalid dates/ranges, API-key redaction, and inclusion of `--fresh`/`--topics-json`.

- [ ] **Step 2: Run the focused tests**

Run: `python -m unittest tests.test_local_server -v`
Expected: FAIL because `scripts.local_server` does not exist.

- [ ] **Step 3: Implement the server**

Use `ThreadingHTTPServer`, a locked in-memory `JobState`, and a background thread that runs `fetch_papers.py` with the key only in the child environment. Serve files from `docs/` for all non-API paths.

- [ ] **Step 4: Run focused tests again**

Run: `python -m unittest tests.test_local_server -v`
Expected: all tests PASS.

### Task 2: Local And Remote Browser Modes

**Files:**
- Modify: `docs/index.html`
- Modify: `docs/app.js`
- Modify: `docs/styles.css`

**Interfaces:**
- Consumes local API responses from Task 1.
- Produces mode-aware token labels, local key persistence, local run dispatch, progress polling, and automatic paper reload.

- [ ] **Step 1: Replace fixed GitHub token identifiers with mode-neutral controls**

Add stable IDs for token label/help text while keeping the existing run form layout.

- [ ] **Step 2: Add local-mode detection and token persistence**

Treat `localhost` and `127.0.0.1` as local. Store the local key under `dailyPaper.deepseekApiKey.v1`; retain `dailyPaper.githubToken.v1` for deployed mode.

- [ ] **Step 3: Add local run and status polling**

Send the form to `/api/run`, poll `/api/status` every two seconds, render progress output, re-read `run_status.json`, and reload papers after success.

- [ ] **Step 4: Validate JavaScript syntax**

Run: `node --check docs/app.js`
Expected: no output and exit code 0.

### Task 3: One-Click Launcher And Documentation

**Files:**
- Create: `start_daily_paper.ps1`
- Create: `start_daily_paper.cmd`
- Modify: `README.md`

**Interfaces:**
- Consumes: `scripts/local_server.py` from Task 1.
- Produces: a double-click launcher that reuses an existing server or starts one hidden, then opens `http://127.0.0.1:8766/`.

- [ ] **Step 1: Implement the launcher**

Check port 8766, stop only the obsolete repository-owned `python -m http.server` process when detected, start `pythonw scripts/local_server.py`, wait for `/api/status`, and open the browser.

- [ ] **Step 2: Update local usage documentation**

Document double-click startup, browser-stored DeepSeek key, local run behavior, and the distinction from GitHub Pages mode.

- [ ] **Step 3: Run end-to-end smoke verification**

Run the launcher, request `/api/status`, post an invalid request to verify HTTP 400, then trigger a tiny local run without exposing a real key and confirm the job reaches a terminal state.

- [ ] **Step 4: Validate all artifacts**

Run: `python -m py_compile scripts/fetch_papers.py scripts/local_server.py`
Run: `python -m unittest tests.test_local_server -v`
Run: `node --check docs/app.js`
Expected: all commands exit 0.
