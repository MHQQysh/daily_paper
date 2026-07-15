# Three Paper Directions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the seven default paper directions with Vision Token Pruning, GRPO, and 可解释性 without losing existing papers.

**Architecture:** Keep `config/topics.json` as the topic source, reindex stored papers with the existing scorer, and use a frontend schema version to discard only the obsolete browser override once.

**Tech Stack:** JSON, Python 3, vanilla JavaScript.

## Global Constraints

- Preserve all existing paper records.
- Keep website topic editing available after migration.
- Send only the three active directions in future local and GitHub searches.

---

### Task 1: Replace Default Topics

**Files:**
- Modify: `config/topics.json`

- [ ] Define the three directions and focused keyword lists.
- [ ] Validate the JSON with `python -m json.tool config/topics.json`.

### Task 2: Migrate Browser Topic State

**Files:**
- Modify: `docs/app.js`

- [ ] Add a topic schema storage key and version.
- [ ] Clear the obsolete custom-topic payload only when the stored version differs.
- [ ] Run `node --check docs/app.js`.

### Task 3: Reindex Existing Papers

**Files:**
- Modify mechanically: `data/papers.json`
- Modify mechanically: `docs/papers.json`

- [ ] Load the new topic configuration through `fetch_papers.py`.
- [ ] Recompute each paper's topic IDs without changing the paper count.
- [ ] Write both stores through the existing structured JSON output function.
- [ ] Verify both files contain exactly three topic definitions and matching paper counts.

### Task 4: Browser Verification

- [ ] Load the local site with an old topic cache and verify migration.
- [ ] Confirm three direction groups render.
- [ ] Intercept a local run click and verify exactly three topics are posted.
