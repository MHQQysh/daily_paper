# Web Direction Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every research direction a stable unique ID and let users add, edit, delete, and persist directions from the web page.

**Architecture:** The browser normalizes legacy/custom direction IDs with a deterministic FNV-1a hash and renders a structured editor. Local saves call a new loopback API that validates and writes the topic catalog to `config/topics.json` plus the top-level catalogs in both paper stores; static hosting retains browser-only persistence.

**Tech Stack:** Vanilla JavaScript, HTML/CSS, Python 3.11 standard library, `unittest`.

## Global Constraints

- Do not delete or replace any paper records while saving directions.
- Keep API keys in browser storage and out of repository files and API responses.
- Preserve the existing append-only paper-search behavior.
- Keep the server bound to `127.0.0.1` by default.

---

### Task 1: Stable browser direction IDs

**Files:**
- Modify: `docs/app.js`
- Test: browser QA against `http://127.0.0.1:8766/`

**Interfaces:**
- Produces: `stableTopicId(name: string): string`
- Produces: `normalizeTopicIds(topics: Array<Topic>): Array<Topic>`
- Consumes: stored topics from `dailyPaper.customTopics.v1`

- [ ] **Step 1: Reproduce the collision**

Use the current editor data containing `可解释性 | ...` and `流形 | Manifold`. Verify both currently normalize to `direction` and therefore render the same paper set.

- [ ] **Step 2: Add deterministic ID helpers**

Add a 32-bit FNV-1a hash over the NFKC-normalized lowercase name:

```js
function stableTopicId(name) {
  let hash = 2166136261;
  for (const character of String(name || "").normalize("NFKC").toLowerCase()) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return `topic-${(hash >>> 0).toString(36)}`;
}
```

Normalize each catalog by retaining unique non-fallback IDs, replacing `direction` or duplicate IDs with `stableTopicId(name)`, and adding `-2`, `-3`, etc. only if a hash collision occurs.

- [ ] **Step 3: Migrate stored data on load and save**

Run `normalizeTopicIds` in `loadStoredTopics`, editor save, Reset, Copy JSON, workflow payload creation, and paper-analysis topic payload creation. Write the migrated catalog back to browser storage when it differs from the stored catalog.

- [ ] **Step 4: Verify the collision is gone**

In the browser, verify `可解释性` and `流形` have different `data-topic-id` values and different paper counts based on their own keyword sets.

---

### Task 2: Persistent local topic service

**Files:**
- Modify: `scripts/paper_service.py`
- Modify: `scripts/local_server.py`
- Modify: `tests/test_paper_service.py`
- Modify: `tests/test_local_server.py`

**Interfaces:**
- Produces: `paper_service.save_topics(topics_payload: list[dict]) -> dict`
- Produces: `POST /api/topics/save` with `{ "topics": [...] }`

- [ ] **Step 1: Write failing service tests**

Cover rejection of duplicate IDs and empty keywords, then verify a valid payload writes this shape:

```json
{
  "topics": [
    {
      "id": "topic-example",
      "name": "Example",
      "description": "example keyword",
      "keywords": ["example keyword"]
    }
  ]
}
```

Assert that `config/topics.json`, `data/papers.json`, and `docs/papers.json` receive the same top-level catalog while the `papers` arrays remain byte-for-byte equivalent after JSON parsing.

- [ ] **Step 2: Implement validation and persistence**

Use `fp.normalize_topics_payload` for the base shape, then enforce one to 100 topics, unique IDs, names no longer than 120 characters, one to 100 keywords per topic, and keywords no longer than 200 characters. Create a `before-topic-save-*` backup containing config and paper stores. Write UTF-8 JSON with `ensure_ascii=False`, two-space indentation, and a trailing newline.

- [ ] **Step 3: Add the loopback route**

Add `/api/topics/save` to the POST allowlist. Acquire `OPERATION_LOCK`, call `paper_service.save_topics`, release the lock in `finally`, and return HTTP 200. Existing exception mapping supplies 400 for validation and 409 for a busy service.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m unittest tests.test_paper_service tests.test_local_server -v
```

Expected: all focused tests pass and no fixture writes escape temporary directories.

---

### Task 3: Structured web editor and end-to-end verification

**Files:**
- Modify: `docs/index.html`
- Modify: `docs/styles.css`
- Modify: `docs/app.js`
- Modify: `README.md`

**Interfaces:**
- Consumes: `POST /api/topics/save`
- Produces: repeated `.topic-edit-row` elements containing name, keywords, and delete controls

- [ ] **Step 1: Replace the textarea editor**

Render a scrollable list of direction rows. Add an `Add direction` command above the list. Each row keeps its ID in `data-topic-id`, contains a labeled name input, a labeled comma-separated keyword input, and an icon-only delete button with an accessible label and tooltip.

- [ ] **Step 2: Implement editor state and validation**

Read rows into a normalized catalog. Keep IDs when editing existing rows and call `stableTopicId` for new rows. Display an inline status message and keep the dialog open when a name, keyword list, or duplicate name is invalid.

- [ ] **Step 3: Persist according to runtime mode**

In local mode, call:

```js
await postLocalApi("/api/topics/save", { topics });
```

After success, update `state.serverTopics`, browser storage, `state.topics`, and the paper topic model, then rerender. In static mode, save the same normalized catalog only in browser storage. Reset restores `state.serverTopics` and clears the custom catalog.

- [ ] **Step 4: Update documentation**

Explain that local direction edits persist to `config/topics.json`, while hosted-page edits remain browser-specific until used in a triggered workflow.

- [ ] **Step 5: Run complete verification**

Run:

```powershell
python -m unittest discover -s tests -v
python -m py_compile scripts/paper_service.py scripts/local_server.py
node --check docs/app.js
git diff --check
```

Expected: all tests and syntax checks pass.

- [ ] **Step 6: Browser QA**

Reload the local page, confirm separate counts for `可解释性` and `流形`, add a temporary direction, save it, reload and verify persistence, delete it, save again, and verify desktop plus mobile layouts have no horizontal overflow. Confirm no paper records were removed.

- [ ] **Step 7: Commit**

Stage only code, tests, and documentation. Do not stage runtime changes to `data/papers.json`, `docs/papers.json`, or `docs/run_status.json` unless the user explicitly asks to publish the current data snapshot.
