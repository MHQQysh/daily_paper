# Generic PDF URL Import Design

## Goal

Allow the local Daily Paper interface to import a research paper from any public direct PDF URL, including OpenReview and CVF links, without requiring an arXiv record or a user-managed download.

## User Experience

- The existing search-and-add field accepts a public `http` or `https` PDF URL.
- The local server downloads and reads the PDF temporarily while the dialog reports progress.
- DeepSeek extracts the title, authors, publication date, English abstract, Chinese abstract, concise Chinese summary, relevance explanation, and recommended directions.
- The user can edit the recommended direction checkboxes before adding the paper.
- The saved paper keeps the original URL as its PDF link.
- Temporary PDF bytes and extracted full text are not written to the paper library.

## Processing Flow

1. `POST /api/papers/resolve` recognizes a non-arXiv URL.
2. The server validates that the URL uses HTTP(S) and resolves only to public network addresses.
3. It follows a small number of redirects, revalidating every destination.
4. It downloads at most 30 MB with a 60-second timeout and verifies the PDF content type or `%PDF` signature.
5. `pypdf` extracts readable text, capped at approximately 120,000 characters.
6. The extracted text is stored in a short-lived in-memory cache and represented in the browser by an opaque import token.
7. `POST /api/papers/analyze` consumes that token and asks DeepSeek to extract structured metadata, translate the abstract, classify the paper, and produce the existing Chinese summary fields.
8. The cache entry is consumed and removed after analysis. The temporary file is deleted immediately after extraction.
9. The existing add endpoint persists only the structured paper record and original URL.

## Security And Resource Limits

- Reject non-HTTP(S) schemes, embedded credentials, localhost names, and private, loopback, link-local, multicast, reserved, or unspecified IP addresses.
- Revalidate redirect destinations to prevent private-network redirect attacks.
- Limit redirects, response size, extraction size, request body size, and cache lifetime.
- Never include the DeepSeek API key in logs, cache entries, or stored paper data.
- Return clear errors for oversized files, invalid PDFs, empty/scanned PDFs, expired import tokens, download failures, and DeepSeek failures.

## Data Model

PDF imports use a deterministic URL-based source id and record:

- `source`: host-derived name such as `OpenReview`, `CVF Open Access`, or `PDF`.
- `source_id`: a SHA-256-derived stable URL identifier.
- `links.pdf`: the final validated PDF URL.
- `links.abstract`: an OpenReview forum link when it can be derived; otherwise the PDF URL.

The full extracted document text and import token are transient and must never appear in `data/papers.json` or `docs/papers.json`.

## Dependency

Add a bounded `pypdf` requirement. PDF importing remains a localhost feature; scheduled arXiv automation does not download arbitrary PDFs.

## Testing

- Unit-test URL validation, redirect validation, size limits, PDF signature checks, extraction, cache expiry, and prompt/result normalization.
- Use mocked downloads and generated in-memory PDFs for deterministic tests.
- Verify both supplied OpenReview and CVF URLs through the real local flow without adding test records to the live library.
- Browser-test progress text, editable direction recommendations, preserved PDF links, and unchanged arXiv/title flows.
