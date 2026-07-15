# Broad arXiv Retrieval and Per-Direction Top-N Design

## Goal

Replace narrow generated-query retrieval with the broad daily retrieval pattern
used by `zotero-arxiv-daily`. A user chooses one date and one paper count; the
system returns up to that count for every configured research direction.

## Retrieval

For the selected UTC date, retrieve all arXiv submissions in `cs.AI`, `cs.CV`,
`cs.LG`, and `cs.CL`, including cross-listed records returned by the category
query. Scan at most 1,000 records in descending submission order and stop after
the requested date has been passed. Generated topic queries no longer limit
which papers are fetched.

When a scheduled run has no explicit date, use the previous UTC date, matching
the reference project's daily behavior.

## Ranking

Ranking has two DeepSeek stages:

1. Send title and abstract batches for all retrieved papers. DeepSeek returns a
   relevance score from 0 to 100 for every configured direction. This stage
   does not translate abstracts.
2. Independently sort papers for every direction and select up to N papers with
   a positive score. Union the selected lists by paper identity. A paper chosen
   by multiple directions keeps every matching direction but is stored once.
3. Run the existing Chinese summary and abstract translation only for the
   selected union, limiting cost and latency.

If a DeepSeek ranking batch fails, deterministic keyword scores provide a
fallback for that batch. DeepSeek remains required for the intended local user
flow, but partial API failures do not corrupt the paper library.

## Interface

The run panel keeps:

- one required date field;
- one `Papers per direction` numeric input;
- the DeepSeek/GitHub token field and run button.

Remove Range, Max results, and Min score from the page, local API, workflow
inputs, and run report. Article title, authors, direction tags, relevance,
Chinese content, English abstract, links, manual add, and delete remain intact.

## Status

The completed report shows the date, requested count per direction, number of
arXiv papers retrieved, selected counts for each direction, union size, and
append/update/duplicate totals. It no longer displays generated search queries.

## Verification

Unit tests cover the broad category query, previous-day default, ranking batch
normalization, independent per-direction Top-N, overlap deduplication, local
request validation, and command construction. Browser QA verifies that only
date and quantity remain in the search controls while article details are
unchanged.
