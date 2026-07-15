# Read-Only Public Site Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the current paper library as a public read-only GitHub Pages site without changing localhost operations.

**Architecture:** Keep one frontend and use the existing hostname check to select capabilities. Localhost retains every control and API path; non-local hosts hide all mutation controls and load only the committed `docs/papers.json` snapshot.

**Tech Stack:** Static HTML/CSS/JavaScript, Python `unittest`, GitHub Pages, GitHub Actions

## Global Constraints

- Do not change the Python local API or local search behavior.
- Public mode must expose no GitHub or DeepSeek token input.
- Publish the current committed JSON snapshot only after verification.

---

### Task 1: Public Capability Gate

**Files:**
- Modify: `docs/index.html`
- Modify: `docs/app.js`
- Modify: `docs/styles.css`
- Test: `tests/test_public_site.py`

**Interfaces:**
- Consumes: `IS_LOCAL_MODE: boolean`
- Produces: `configureRunMode()` that keeps local controls visible and hides public mutation controls

- [ ] **Step 1: Write the failing static contract test**

Create a unittest that verifies the run panel and search label have stable IDs, public mode hides the run panel and direction editor, and local mode keeps the existing run button behavior.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `python -m unittest tests.test_public_site -v`

Expected: FAIL because the stable public-mode selectors and visibility assignments do not exist.

- [ ] **Step 3: Implement the capability gate**

Add `id="searchModeLabel"` and `id="runPanel"` in `docs/index.html`. In `configureRunMode()`, set `runPanel.hidden`, `editTopicsButton.hidden`, and `addPaperButton.hidden` from `IS_LOCAL_MODE`; set the public label to `Search papers`; return before configuring token controls in public mode. Add a generic `[hidden] { display: none !important; }` rule.

- [ ] **Step 4: Run the focused and full tests**

Run:

```powershell
python -m unittest tests.test_public_site -v
python -m unittest discover -s tests -v
node --check docs/app.js
```

Expected: all tests pass and JavaScript syntax is valid.

### Task 2: Browser Verification

**Files:**
- Verify: `docs/index.html`
- Verify: `docs/app.js`
- Verify: `docs/styles.css`

**Interfaces:**
- Consumes: localhost at `http://127.0.0.1:8766/` and a non-local hostname simulation
- Produces: evidence that local controls remain available and public controls are absent

- [ ] **Step 1: Verify localhost**

Confirm the run panel, direction editor, and add button are visible; paper data renders; no horizontal overflow or console errors occur.

- [ ] **Step 2: Verify public mode**

Serve the same static files through a non-local hostname or override the hostname detection in a browser test. Confirm the run panel, direction editor, add button, and delete button are absent while paper navigation and details remain visible.

- [ ] **Step 3: Verify mobile layout**

Check a 390 by 844 viewport and confirm there is no horizontal overflow.

### Task 3: Publish Snapshot

**Files:**
- Commit: `data/papers.json`
- Commit: `docs/papers.json`
- Commit: `docs/run_status.json`
- Commit: `docs/index.html`
- Commit: `docs/app.js`
- Commit: `docs/styles.css`
- Commit: `tests/test_public_site.py`

**Interfaces:**
- Consumes: verified local working tree and authenticated `origin`
- Produces: updated `main` and deployed GitHub Pages site

- [ ] **Step 1: Validate data and secrets**

Run JSON parsing, `git diff --check`, and a filename-only secret scan. Verify `docs/papers.json` contains the expected current paper count.

- [ ] **Step 2: Commit the implementation and snapshot**

Stage only the listed files and commit with `feat: publish read-only paper showcase`.

- [ ] **Step 3: Push main**

Run `git push origin main` and verify the GitHub Pages workflow completes.

- [ ] **Step 4: Verify production**

Open the public URL, confirm the expected paper count and read-only controls, check desktop/mobile overflow and console errors, and retain the production tab for handoff.
