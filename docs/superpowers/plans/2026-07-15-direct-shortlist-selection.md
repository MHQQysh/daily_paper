# Direct Shortlist Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local direction filter choose the final N papers and use DeepSeek only for Chinese output.

**Architecture:** Reuse broad range retrieval and local topic scoring, but replace the bounded intermediate shortlist plus DeepSeek ranking with a single date-aware local Top-N selector. Feed the deduplicated selected union directly into the existing enrichment and append-only merge stages.

**Tech Stack:** Python 3.11 standard library, DeepSeek chat completions API, static JavaScript, Python `unittest`.

## Global Constraints

- N applies independently to each direction across the complete date range.
- DeepSeek must not be called for relevance scoring.
- DeepSeek receives only the final selected union for Chinese TLDR and abstract translation.
- Runtime JSON files remain unstaged.

---

### Task 1: Direct Local Top-N

**Files:**
- Modify: `scripts/fetch_papers.py`
- Test: `tests/test_fetch_papers.py`

**Interfaces:**
- Produces: `select_local_per_topic(papers: list[dict], papers_per_topic: int) -> tuple[list[dict], dict[str, int]]`

- [ ] Add a failing test with overlapping directions and verify the returned union stores one record with both topic IDs.

```python
with mock.patch.object(fetch_papers, "TOPICS", topics):
    selected, counts = fetch_papers.select_local_per_topic(papers, papers_per_topic=1)
self.assertEqual(counts, {"vision": 1, "interpretability": 1})
self.assertEqual(len(selected), 1)
self.assertEqual(selected[0]["topics"], ["vision", "interpretability"])
```

- [ ] Implement local ranking from `fallback_topic_scores`, sort by score/date/title, keep positive-score Top-N per direction, and deduplicate with `paper_identity_keys`.

```python
scores = {paper["id"]: fallback_topic_scores(paper) for paper in papers}
chosen = [
    paper for paper in ranked
    if scores.get(paper.get("id", ""), {}).get(topic_id, 0) > 0
][:papers_per_topic]
```
- [ ] Remove the `rank_papers_by_topic` call from `main` and send the selected union directly to `enrich_papers`.
- [ ] Run `python -m unittest tests.test_fetch_papers -v` and expect all tests to pass.

### Task 2: Status And Documentation Cleanup

**Files:**
- Modify: `docs/app.js`
- Modify: `README.md`
- Modify: `docs/plans/2026-07-15-date-range-search-design.md`

- [ ] Remove shortlist counts from the run status renderer and describe direct local selection.
- [ ] Remove claims that DeepSeek ranks candidates; retain DeepSeek TLDR and translation behavior.
- [ ] Run `node --check docs/app.js` and `git diff --check`; both must exit 0.

### Task 3: Verification And Commit

**Files:**
- Verify all modified source, tests, and documentation.

- [ ] Run `python -m unittest discover -s tests -v` and expect all tests to pass.
- [ ] Restart only the verified Daily Paper loopback server and confirm `/api/status` returns HTTP 200.
- [ ] Verify the page still shows both dates, N, paper details, and no horizontal overflow.
- [ ] Scan tracked source for long `sk-` secrets, excluding runtime JSON.
- [ ] Stage source/tests/docs only and commit with `git commit -m "feat: select papers directly after local filtering"`.
