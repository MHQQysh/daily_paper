# Direct Shortlist Selection Design

## Goal

Simplify date-range searches so the local direction filter directly chooses the final N papers per direction. DeepSeek no longer performs a second relevance-scoring stage.

## Pipeline

1. Retrieve every arXiv paper for each day in the inclusive date range from `cs.AI`, `cs.CV`, `cs.LG`, and `cs.CL`.
2. Deduplicate the combined records.
3. Score titles and abstracts locally using each direction's name, description, and editable keywords.
4. Select the final N papers independently for each direction, preferring newer papers when local scores tie.
5. Deduplicate overlapping selections while retaining all selected directions.
6. Send only that selected union to DeepSeek for a Chinese TLDR and Chinese abstract translation.
7. Append the enriched records to the existing library.

## Removed Behavior

- No 50-to-200-paper shortlist per direction.
- No DeepSeek relevance score request for shortlisted papers.
- No second Top-N pass after DeepSeek ranking.

## Reporting

The run report shows the range, raw and deduplicated counts, selected counts per direction, unique selected count, merge counts, and DeepSeek availability. It no longer reports a shortlist or ranking phase.

## Compatibility

Date-range controls, direction editing, article details, manual PDF/arXiv addition, deletion, Chinese output, append-only storage, and multi-direction deduplication remain unchanged.
