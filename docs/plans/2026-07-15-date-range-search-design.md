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
3. Apply a lightweight local relevance pass using each direction's name, description, and keywords against titles and abstracts. Keep a balanced shortlist per direction so every date can contribute candidates.
4. Union and deduplicate those shortlists.
5. Ask DeepSeek to score the shortlisted papers against every direction.
6. Select at most N positive-score papers per direction across the whole date range.
7. Deduplicate overlapping selections while retaining every selected direction.
8. Ask DeepSeek only for Chinese summaries and abstract translations for the selected union.
9. Append the selected papers to the existing library without deleting older records.

For small ranges the local shortlist can include every paper. For large ranges, each direction receives a bounded shortlist derived from all dates, preventing a long range from sending thousands of irrelevant abstracts to DeepSeek while avoiding a newest-date-only bias.

## Status Reporting

The completed report includes:

- Start and end dates
- Requested papers per direction
- Number of daily retrievals
- Raw and deduplicated paper counts
- Shortlist size
- Selected count per direction
- Unique selected count
- Added, updated, duplicate, and total stored counts
- Whether DeepSeek was enabled

## Compatibility

Paper details, Chinese and English abstracts, source/PDF links, manual addition, deletion, category editing, append-only merge behavior, and multi-direction deduplication remain unchanged.

The command line and workflow move from `--date` / `target_date` to `--start-date` and `--end-date`. Empty scheduled values resolve to the previous UTC day for both bounds.

## Validation

Tests cover inclusive date generation, default dates, reversed or overlong ranges, daily retrieval calls, balanced shortlist behavior, per-direction Top-N selection, overlapping papers, local API payloads, and command construction. Browser checks cover desktop and mobile layouts, old-control removal, date-range validation, and horizontal overflow.
