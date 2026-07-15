# Daily Paper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a pure-online daily token-pruning paper tracker named `daily_paper` with GitHub Actions updates and GitHub Pages hosting.

**Architecture:** A Python fetcher queries arXiv, filters token-pruning-related papers, calls DeepSeek to classify and summarize them, stores paper metadata in JSON, then writes static assets under `docs/`. The frontend is a single static page with a left expandable topic tree and a right detail pane.

**Tech Stack:** Python 3.11 standard library, DeepSeek OpenAI-compatible chat completions, GitHub Actions cron, GitHub Pages static hosting, vanilla HTML/CSS/JavaScript.

## Global Constraints

- Pure online: do not download PDFs; save only metadata and links.
- Repository name: `daily_paper`.
- DeepSeek API key is read from `DEEPSEEK_API_KEY` in GitHub Secrets or local environment.
- Left navigation must support expandable directions and per-paper selection.
- Keep implementation lightweight and maintainable; no heavy frontend build step.

---

### Task 1: Project Scaffolding

**Files:**
- Create: `README.md`
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `data/papers.json`
- Create: `docs/papers.json`

**Interfaces:**
- Produces: a repository layout that scripts and GitHub Pages can use.

- [x] **Step 1: Create project metadata files**

Create a README explaining local use, GitHub Secrets, and Pages deployment.

- [x] **Step 2: Create empty JSON stores**

Initialize `data/papers.json` and `docs/papers.json` with `{"papers": [], "last_updated": null}`.

### Task 2: Paper Fetcher

**Files:**
- Create: `scripts/fetch_papers.py`

**Interfaces:**
- Produces: `fetch_arxiv(days: int, max_results: int) -> list[dict]`
- Produces: `classify_with_deepseek(papers: list[dict]) -> list[dict]`
- Produces: `write_outputs(papers: list[dict]) -> None`

- [x] **Step 1: Implement arXiv search**

Query arXiv Atom API with topic-specific keywords and parse IDs, dates, titles, authors, abstracts, and links.

- [x] **Step 2: Implement keyword filter and topic assignment**

Assign papers to directions such as `visual-token-pruning`, `vlm-acceleration`, `llm-context-kv-pruning`, `token-merging-compression`, `efficient-vit`, `dynamic-token-selection`, and `survey-benchmark`.

- [x] **Step 3: Implement DeepSeek enrichment**

If `DEEPSEEK_API_KEY` is available, call `https://api.deepseek.com/chat/completions` with JSON output instructions and merge score, Chinese summary, and relevance reason into each paper. If unavailable, use deterministic fallback summaries.

- [x] **Step 4: Implement dedupe and output writing**

Merge with existing `data/papers.json`, dedupe by source ID or normalized title, sort newest first, and write both `data/papers.json` and `docs/papers.json`.

### Task 3: Static Website

**Files:**
- Create: `docs/index.html`
- Create: `docs/styles.css`
- Create: `docs/app.js`

**Interfaces:**
- Consumes: `docs/papers.json`
- Produces: a GitHub Pages-compatible static app.

- [x] **Step 1: Build shell layout**

Create a two-pane layout with a fixed left topic tree, mobile top bar, search box, and detail pane.

- [x] **Step 2: Build topic tree behavior**

Render expandable topic groups with counts and nested paper rows. Selecting a paper updates the detail pane without navigating away.

- [x] **Step 3: Build detail cards**

Show title, authors, published date, score, topics, Chinese summary, relevance reason, abstract, and links.

### Task 4: Automation

**Files:**
- Create: `.github/workflows/daily.yml`

**Interfaces:**
- Consumes: `DEEPSEEK_API_KEY` secret.
- Produces: daily commits to `data/papers.json` and `docs/papers.json`.

- [x] **Step 1: Add scheduled workflow**

Run daily at Beijing morning time, support manual dispatch, install requirements, run fetcher, and commit changed JSON/static files.

### Task 5: Verification and Publish

**Files:**
- Modify: repository git state.

**Interfaces:**
- Produces: GitHub repository `daily_paper`.

- [ ] **Step 1: Run the fetcher locally**

Run `python scripts/fetch_papers.py --days 14 --max-results 60` and verify JSON output.

- [ ] **Step 2: Serve the site locally**

Run `python -m http.server 8000 --directory docs` and inspect the page.

- [ ] **Step 3: Create GitHub repository and push**

Initialize git, commit, create `daily_paper` on GitHub, and push `main`.

- [ ] **Step 4: Configure Pages**

Enable GitHub Pages from the `main` branch `/docs` folder or report the exact manual setting if API permissions do not allow enabling it automatically.
