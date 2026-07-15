# Local Paper Deletion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a localhost-only, confirmed paper deletion action that removes the current record without blocking future rediscovery.

**Architecture:** `paper_service.py` owns identity-based deletion, backup, and output writes. `local_server.py` exposes the operation behind the existing mutation lock. The static frontend conditionally renders a trash icon, confirms the action, calls the local endpoint, and reloads the library.

**Tech Stack:** Python 3 standard library, `unittest`, vanilla JavaScript, HTML, and CSS.

## Global Constraints

- Deletion removes only the current record; no tombstone or ignore list is created.
- Future automatic search or manual addition may restore the same paper.
- The delete control is visible only on `127.0.0.1` and `localhost`.
- Back up current paper outputs before deletion.
- Use the existing operation lock to prevent deletion during another mutation.
- Do not overwrite or revert unrelated changes already present in the paper data files.

---

### Task 1: Identity-Based Paper Deletion

**Files:**
- Modify: `scripts/paper_service.py`
- Modify: `tests/test_paper_service.py`

**Interfaces:**
- Consumes: `fp.paper_identity_keys(paper)` and `fp.write_outputs(papers)`.
- Produces: `delete_paper(paper: dict[str, Any]) -> dict[str, Any]` returning `deleted`, `total`, and the removed paper.

- [ ] **Step 1: Write failing deletion tests**

Add tests that create temporary `data/papers.json` and `docs/papers.json`, delete a paper by its arXiv identity, assert both outputs no longer contain it, and assert that a second deletion raises `LookupError`.

```python
result = paper_service.delete_paper({"source_id": "2607.12356v1", "title": "VistaVLA"})
self.assertEqual(result["deleted"], 1)
self.assertEqual(result["total"], 1)
with self.assertRaises(LookupError):
    paper_service.delete_paper({"source_id": "2607.12356v1", "title": "VistaVLA"})
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `python -m unittest tests.test_paper_service -v`

Expected: failure because `delete_paper` does not exist.

- [ ] **Step 3: Implement deletion with backup and identity matching**

Implement deletion without an ignore list:

```python
def delete_paper(paper: dict[str, Any]) -> dict[str, Any]:
    target = _sanitize_paper(paper)
    target_keys = set(fp.paper_identity_keys(target))
    existing = fp.read_store(fp.DATA_PATH).get("papers", [])
    removed = [item for item in existing if target_keys.intersection(fp.paper_identity_keys(item))]
    if not removed:
        raise LookupError("Paper was not found in the current library")
    kept = [item for item in existing if not target_keys.intersection(fp.paper_identity_keys(item))]
    _backup_before_mutation("before-manual-delete")
    fp.write_outputs(kept)
    return {"paper": removed[0], "deleted": len(removed), "total": len(kept)}
```

Rename the existing add-specific backup helper to `_backup_before_mutation(prefix: str)` and use it from both add and delete.

- [ ] **Step 4: Run the focused tests**

Run: `python -m unittest tests.test_paper_service -v`

Expected: all paper service tests pass.

---

### Task 2: Local Delete API

**Files:**
- Modify: `scripts/local_server.py`
- Modify: `tests/test_local_server.py`

**Interfaces:**
- Consumes: JSON `{ "paper": { ... } }` at `POST /api/papers/delete`.
- Produces: HTTP 200 with deletion statistics, HTTP 404 for a missing paper, or HTTP 409 while another operation holds the lock.

- [ ] **Step 1: Add a failing route test**

Assert that `/api/papers/delete` is an accepted POST path and that a `LookupError` maps to HTTP 404 rather than HTTP 502.

- [ ] **Step 2: Run the server tests and verify failure**

Run: `python -m unittest tests.test_local_server -v`

Expected: failure because the route is not registered.

- [ ] **Step 3: Add the locked delete route and not-found handling**

Register `/api/papers/delete`, acquire `OPERATION_LOCK` without blocking, call `paper_service.delete_paper(payload.get("paper", {}))`, and release the lock in `finally`. Add a `LookupError` handler returning:

```python
self._send_json({"error": str(exc)}, HTTPStatus.NOT_FOUND)
```

- [ ] **Step 4: Run server and full Python tests**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass.

---

### Task 3: Confirmed Localhost-Only Delete Control

**Files:**
- Modify: `docs/app.js`
- Modify: `docs/styles.css`
- Modify: `README.md`

**Interfaces:**
- Consumes: selected paper in `state.papers` and `POST /api/papers/delete`.
- Produces: a trash icon in the detail action row on localhost, confirmation through the browser dialog, and a refreshed library after success.

- [ ] **Step 1: Render the icon only in local mode**

Add an icon button with `data-delete-paper`, `aria-label="Delete paper"`, and `title="Delete paper"` beside the paper links only when `IS_LOCAL_MODE` is true. Use a familiar trash-can symbol rather than a rounded text button.

- [ ] **Step 2: Implement confirmation and deletion**

Attach the detail button after each render. Confirm with the paper title, call:

```javascript
await postLocalApi("/api/papers/delete", { paper });
state.selectedPaperId = null;
await loadData();
runStatus.textContent = `Deleted: ${paper.title}`;
```

Keep the current paper unchanged when the user cancels or the request fails.

- [ ] **Step 3: Style a stable destructive icon button**

Add a fixed-size square action with visible focus, restrained red hover state, and no layout shift. Ensure the link row wraps cleanly on mobile.

- [ ] **Step 4: Document deletion semantics**

State that local deletion removes the current record only, creates a local backup, and does not prevent future rediscovery.

- [ ] **Step 5: Run syntax and browser verification**

Run:

```powershell
python -m py_compile scripts\paper_service.py scripts\local_server.py
python -m unittest discover -s tests -v
node --check docs\app.js
git diff --check
```

Browser verification at desktop and mobile widths must confirm: delete is visible locally, cancel preserves the paper, confirmation sends one request, successful deletion refreshes counts, public/static mode omits the icon, and no horizontal overflow appears.

- [ ] **Step 6: Commit the implementation**

```powershell
git add scripts/paper_service.py scripts/local_server.py tests docs/app.js docs/styles.css README.md
git commit -m "feat: add local paper deletion"
```
