# Date Range Search Design

## Goal

Replace the single-date search with an inclusive start/end date range while keeping the result limit as a single Top-N value per research direction across the whole range.

## User Experience

The run panel contains only:

- Start date
- End date
- Papers per direction
- API key and run action

Both dates are required for interactive runs. The start date must not be later than the end date, and the inclusive range is limited to 31 days. Scheduled runs default both dates to the previous UTC day.

## Retrieval And Ranking

1. Retrieve every day in the inclusive range separately from `cs.AI`, `cs.CV`, `cs.LG`, and `cs.CL`.
2. Deduplicate the combined results by paper identity.
3. Score titles and abstracts locally using each direction's name, description, and editable keywords.
4. Directly select at most N positive-score papers per direction across the whole date range.
5. Deduplicate overlapping selections while retaining every selected direction.
6. Ask DeepSeek only for Chinese TLDRs and abstract translations for the selected union.
7. Append the selected papers to the existing library without deleting older records.

There is no intermediate shortlist and no DeepSeek relevance-ranking pass. DeepSeek receives only the final locally selected union.

## Status Reporting

The completed report includes:

- Start and end dates
- Requested papers per direction
- Number of daily retrievals
- Raw and deduplicated paper counts
- Selected count per direction
- Unique selected count
- Added, updated, duplicate, and total stored counts
- Whether DeepSeek was enabled

## Compatibility

Paper details, Chinese and English abstracts, source/PDF links, manual addition, deletion, category editing, append-only merge behavior, and multi-direction deduplication remain unchanged.

The command line and workflow move from `--date` / `target_date` to `--start-date` and `--end-date`. Empty scheduled values resolve to the previous UTC day for both bounds.

## Validation

Tests cover inclusive date generation, default dates, reversed or overlong ranges, daily retrieval calls, direct local per-direction Top-N selection, overlapping papers, local API payloads, and command construction. Browser checks cover desktop and mobile layouts, old-control removal, date-range validation, and horizontal overflow.
