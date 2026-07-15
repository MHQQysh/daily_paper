# Generic PDF URL Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import a paper from any public direct PDF URL, extract its text locally, analyze it with DeepSeek, and save only structured metadata plus the original link.

**Architecture:** A focused `pdf_import.py` module owns URL safety, bounded downloading, PDF text extraction, stable source metadata, and a short-lived in-memory text cache. `paper_service.py` routes URL inputs into that module and uses a PDF-specific DeepSeek prompt. The existing local API and add dialog continue to carry only a compact candidate plus an opaque import token.

**Tech Stack:** Python 3.11 standard library, `pypdf` 6.x, `unittest`, vanilla JavaScript, HTML, and CSS.

## Global Constraints

- Accept public direct `http` and `https` PDF URLs, including the supplied OpenReview and CVF examples.
- Reject local, private, link-local, multicast, reserved, and unspecified network destinations, including redirects.
- Limit PDF downloads to 30 MB, extraction to 120,000 characters, redirects to 4, and cache lifetime to 15 minutes.
- Do not persist PDF bytes, extracted full text, import tokens, or API keys in paper JSON files.
- Preserve the final validated PDF URL in `links.pdf`.
- Keep all existing arXiv ID and title-search behavior unchanged.
- Do not stage or overwrite unrelated live changes in `data/papers.json` or `docs/papers.json` during implementation or QA.

---

### Task 1: Safe PDF Download And Text Extraction

**Files:**
- Create: `scripts/pdf_import.py`
- Modify: `requirements.txt`
- Create: `tests/test_pdf_import.py`

**Interfaces:**
- Produces: `resolve_pdf_url(url: str) -> dict[str, Any]` with a compact candidate and `import_token`.
- Produces: `PDF_IMPORT_CACHE.get(token: str) -> dict[str, Any]` and `discard(token: str) -> None`.

- [ ] **Step 1: Add failing URL and cache tests**

Test accepted public HTTPS URLs, rejected localhost/private addresses, rejected redirect destinations, a 30 MB size overflow, invalid PDF signatures, empty extracted text, stable URL-derived identifiers, and expired tokens.

```python
with self.assertRaisesRegex(ValueError, "public"):
    pdf_import.validate_public_pdf_url("http://127.0.0.1/paper.pdf")

candidate = pdf_import.resolve_pdf_url("https://example.org/paper.pdf")
self.assertIn("import_token", candidate)
self.assertEqual(candidate["links"]["pdf"], "https://example.org/paper.pdf")
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `python -m unittest tests.test_pdf_import -v`

Expected: import failure because `scripts.pdf_import` does not exist.

- [ ] **Step 3: Implement bounded safe downloading**

Implement:

```python
MAX_PDF_BYTES = 30 * 1024 * 1024
MAX_TEXT_CHARS = 120_000
MAX_REDIRECTS = 4
CACHE_TTL_SECONDS = 15 * 60

def validate_public_pdf_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Enter a public HTTP(S) PDF URL")
    for result in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM):
        address = ipaddress.ip_address(result[4][0])
        if not address.is_global:
            raise ValueError("PDF URL must resolve to a public network address")
    return urllib.parse.urlunsplit(parsed)

def download_pdf(url: str) -> tuple[str, bytes]:
    request = urllib.request.Request(validate_public_pdf_url(url), headers={"User-Agent": USER_AGENT})
    with build_safe_opener().open(request, timeout=60) as response:
        final_url = validate_public_pdf_url(response.geturl())
        data = read_bounded(response, MAX_PDF_BYTES)
    if not data.lstrip().startswith(b"%PDF"):
        raise ValueError("URL did not return a valid PDF")
    return final_url, data
```

Use `urllib.request`, `socket.getaddrinfo`, and `ipaddress.ip_address`. Revalidate each redirect with a custom `HTTPRedirectHandler`. Read in chunks and stop once the byte limit is exceeded. Require the `%PDF` signature after leading whitespace.

- [ ] **Step 4: Implement pypdf extraction and transient cache**

Use `pypdf.PdfReader` over a `tempfile.SpooledTemporaryFile`, normalize page text, cap it at 120,000 characters, and reject documents with less than 200 readable characters. Store `{text, final_url, candidate}` behind a random `secrets.token_urlsafe(24)` token protected by a lock and expiry timestamp.

- [ ] **Step 5: Add dependency and pass focused tests**

Set `requirements.txt` to:

```text
pypdf>=6.0,<7
```

Run: `python -m unittest tests.test_pdf_import -v`

Expected: all PDF import tests pass.

---

### Task 2: DeepSeek Metadata Extraction For PDF Imports

**Files:**
- Modify: `scripts/paper_service.py`
- Modify: `tests/test_paper_service.py`

**Interfaces:**
- Consumes: `import_token` from the PDF candidate.
- Produces: the existing normalized paper schema with title, authors, dates, abstract, Chinese fields, topics, and original PDF links.

- [ ] **Step 1: Add failing PDF resolution and analysis tests**

Mock `pdf_import.resolve_pdf_url` and `PDF_IMPORT_CACHE.get`. Assert URL input bypasses arXiv and that DeepSeek metadata replaces the filename placeholder while preserving the validated links and stable id.

```python
result = paper_service.resolve_paper_input("https://example.org/paper.pdf")
pdf_import.resolve_pdf_url.assert_called_once()

analyzed = paper_service.analyze_paper(candidate, topics_payload, "sk-test")
self.assertEqual(analyzed["title"], "Extracted title")
self.assertEqual(analyzed["links"]["pdf"], candidate["links"]["pdf"])
```

- [ ] **Step 2: Run service tests and verify failure**

Run: `python -m unittest tests.test_paper_service -v`

Expected: failures because PDF URL routing and PDF-specific analysis do not exist.

- [ ] **Step 3: Route generic URLs before title search**

Recognize parsed HTTP(S) URLs after the arXiv branch and call `pdf_import.resolve_pdf_url`. Update the validation message to include PDF URLs.

- [ ] **Step 4: Add the PDF DeepSeek JSON prompt**

Require DeepSeek for PDF candidates. Ask for strict JSON fields:

```json
{
  "title": "paper title",
  "authors": ["author"],
  "published": "YYYY-MM-DD or empty",
  "abstract": "faithful English abstract",
  "topics": ["topic-id"],
  "relevance_score": 0,
  "summary_zh": "中文总结",
  "abstract_zh": "中文摘要",
  "why_relevant_zh": "相关性"
}
```

Normalize all fields, keep only configured topics, preserve source/id/links from the validated candidate, set `deepseek_used=true`, and discard the cache token only after successful parsing.

- [ ] **Step 5: Run service and full unit tests**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass and no extracted text appears in serialized candidate data.

---

### Task 3: Locking, Errors, And Browser Progress

**Files:**
- Modify: `scripts/local_server.py`
- Modify: `tests/test_local_server.py`
- Modify: `docs/app.js`
- Modify: `docs/index.html`
- Modify: `README.md`

**Interfaces:**
- Consumes: existing `/api/papers/resolve` and `/api/papers/analyze` requests.
- Produces: conflict-safe PDF imports and clear progress/error messages in the existing add dialog.

- [ ] **Step 1: Add API conflict tests**

Verify PDF resolution holds `OPERATION_LOCK`, returns HTTP 409 when another operation is active, and keeps title/arXiv response schemas unchanged.

- [ ] **Step 2: Lock PDF resolution without exposing secrets**

Detect a generic URL through a small `paper_service.is_pdf_url_input` helper. Acquire the operation lock around PDF resolution and release it in `finally`. Keep API keys out of the resolve request.

- [ ] **Step 3: Improve add-dialog progress text**

For HTTP(S) input, show `Downloading and reading PDF`; during analysis show `DeepSeek is reading the paper, translating it, and recommending directions`. Keep the existing title/arXiv wording for other inputs. Update the placeholder to mention `PDF URL`.

- [ ] **Step 4: Document setup and limits**

Document `python -m pip install -r requirements.txt`, supported PDF URLs, 30 MB limit, temporary extraction, DeepSeek requirement, and scanned-PDF behavior.

- [ ] **Step 5: Run static and unit verification**

Run:

```powershell
python -m py_compile scripts\pdf_import.py scripts\paper_service.py scripts\local_server.py
python -m unittest discover -s tests -v
node --check docs\app.js
git diff --check
```

Expected: all commands succeed.

---

### Task 4: Real-Link And Browser Verification

**Files:**
- No live library files should be modified.

**Interfaces:**
- Verifies the supplied OpenReview and CVF URLs end to end through download and extraction, with DeepSeek analysis performed through the browser's saved key only when available.

- [ ] **Step 1: Resolve both supplied links without adding them**

Call the local resolve API for both URLs. Assert each result has an import token, readable extracted text in server cache, a stable id, and the original/final PDF URL.

- [ ] **Step 2: Browser-test with intercepted DeepSeek analysis**

Verify a PDF URL triggers the PDF progress message, one candidate is analyzed, directions remain editable, confirmation payload excludes `import_token`, the saved PDF link is preserved, and desktop/mobile layouts do not overflow.

- [ ] **Step 3: Re-run regression tests and commit**

Run the full verification suite again, stage only implementation files, and commit:

```powershell
git commit -m "feat: import papers from PDF URLs"
```
