from __future__ import annotations

import datetime as dt
import hashlib
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable
import urllib.parse
import urllib.error
import urllib.request

from pypdf import PdfReader


MAX_PDF_BYTES = 30 * 1024 * 1024
MAX_TEXT_CHARS = 120_000
MAX_REDIRECTS = 4
CACHE_TTL_SECONDS = 15 * 60
USER_AGENT = "DailyPaper/1.0 (+local PDF importer)"
PROXY_SYNTHETIC_NETWORK = ipaddress.ip_network("198.18.0.0/15")


def _resolve_public_dns(hostname: str) -> list[str]:
    query = urllib.parse.urlencode({"name": hostname, "type": "A"})
    request = urllib.request.Request(
        f"https://cloudflare-dns.com/dns-query?{query}",
        headers={"Accept": "application/dns-json", "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("Status") != 0:
        return []
    return [answer["data"] for answer in payload.get("Answer", []) if answer.get("type") in {1, 28}]


def validate_public_pdf_url(
    value: str,
    resolver: Callable[..., list[Any]] = socket.getaddrinfo,
    public_dns_resolver: Callable[[str], list[str]] = _resolve_public_dns,
) -> str:
    text = (value or "").strip()
    try:
        parsed = urllib.parse.urlsplit(text)
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise ValueError("Enter a valid public HTTP(S) PDF URL") from exc
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not hostname
        or hostname == "localhost"
        or hostname.endswith(".localhost")
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise ValueError("Enter a public HTTP(S) PDF URL without credentials")

    try:
        addresses = resolver(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ValueError("PDF URL host could not be resolved") from exc
    if not addresses:
        raise ValueError("PDF URL host could not be resolved")
    resolved_addresses = []
    for result in addresses:
        raw_address = str(result[4][0]).split("%", 1)[0]
        try:
            resolved_addresses.append(ipaddress.ip_address(raw_address))
        except ValueError as exc:
            raise ValueError("PDF URL resolved to an invalid network address") from exc
    if resolved_addresses and all(address in PROXY_SYNTHETIC_NETWORK for address in resolved_addresses):
        try:
            resolved_addresses = [ipaddress.ip_address(value) for value in public_dns_resolver(hostname)]
        except Exception as exc:
            raise ValueError("PDF URL public address could not be verified") from exc
        if not resolved_addresses:
            raise ValueError("PDF URL public address could not be verified")
    for address in resolved_addresses:
        if not address.is_global:
            raise ValueError("PDF URL must resolve to a public network address")

    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc, parsed.path or "/", parsed.query, "")
    )


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS
    max_repeats = 2

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        validated = validate_public_pdf_url(new_url)
        return super().redirect_request(request, file_pointer, code, message, headers, validated)


def build_safe_opener():
    return urllib.request.build_opener(SafeRedirectHandler())


def read_bounded(response, maximum: int = MAX_PDF_BYTES) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > maximum:
                raise ValueError("PDF is larger than the 30 MB limit")
        except ValueError as exc:
            if "30 MB" in str(exc):
                raise
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(1024 * 1024, maximum - total + 1))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > maximum:
            raise ValueError("PDF is larger than the 30 MB limit")
    return b"".join(chunks)


def _last_redirect_location(header_path: Path) -> str:
    lines = header_path.read_text(encoding="iso-8859-1", errors="replace").splitlines()
    for line in reversed(lines):
        if line.lower().startswith("location:"):
            return line.split(":", 1)[1].strip()
    return ""


def _download_pdf_with_curl(url: str) -> tuple[str, bytes]:
    curl = shutil.which("curl")
    if not curl:
        raise ValueError("PDF download failed and curl is unavailable")
    current_url = validate_public_pdf_url(url)
    with tempfile.TemporaryDirectory(prefix="daily-paper-pdf-") as directory:
        root = Path(directory)
        body_path = root / "paper.pdf"
        header_path = root / "headers.txt"
        for redirect_count in range(MAX_REDIRECTS + 1):
            command = [
                curl,
                "--silent",
                "--show-error",
                "--request",
                "GET",
                "--proto",
                "=http,https",
                "--max-time",
                "60",
                "--max-filesize",
                str(MAX_PDF_BYTES),
                "--header",
                "Accept: application/pdf,application/octet-stream;q=0.8,*/*;q=0.2",
                "--dump-header",
                str(header_path),
                "--output",
                str(body_path),
                "--write-out",
                "%{http_code}",
                current_url,
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=70, check=False)
            if result.returncode == 63:
                raise ValueError("PDF is larger than the 30 MB limit")
            if result.returncode != 0:
                detail = (result.stderr or "curl request failed").strip()[:300]
                raise ValueError(f"PDF download failed: {detail}")
            try:
                status = int(result.stdout.strip()[-3:])
            except ValueError as exc:
                raise ValueError("PDF download returned an unknown HTTP status") from exc
            if 300 <= status < 400:
                if redirect_count >= MAX_REDIRECTS:
                    raise ValueError("PDF URL redirected too many times")
                location = _last_redirect_location(header_path)
                if not location:
                    raise ValueError("PDF URL redirect did not include a destination")
                current_url = validate_public_pdf_url(urllib.parse.urljoin(current_url, location))
                continue
            if not 200 <= status < 300:
                hostname = (urllib.parse.urlsplit(current_url).hostname or "").lower()
                if status == 403 and hostname.endswith("openreview.net"):
                    raise ValueError(
                        "OpenReview denied this PDF (HTTP 403); it requires an OpenReview login or browser challenge"
                    )
                raise ValueError(f"PDF download returned HTTP {status}")
            if not body_path.exists():
                raise ValueError("PDF download returned no content")
            if body_path.stat().st_size > MAX_PDF_BYTES:
                raise ValueError("PDF is larger than the 30 MB limit")
            data = body_path.read_bytes()
            if not data.lstrip().startswith(b"%PDF"):
                raise ValueError("URL did not return a valid PDF")
            return current_url, data
    raise ValueError("PDF download did not complete")


def download_pdf(url: str, opener=None) -> tuple[str, bytes]:
    validated = validate_public_pdf_url(url)
    request = urllib.request.Request(
        validated,
        headers={
            "Accept": "application/pdf,application/octet-stream;q=0.8,*/*;q=0.2",
            "User-Agent": USER_AGENT,
        },
    )
    active_opener = opener or build_safe_opener()
    try:
        with active_opener.open(request, timeout=60) as response:
            final_url = validate_public_pdf_url(response.geturl())
            data = read_bounded(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return _download_pdf_with_curl(validated)
    if not data.lstrip().startswith(b"%PDF"):
        raise ValueError("URL did not return a valid PDF")
    return final_url, data


def _metadata_value(metadata: Any, name: str) -> str:
    if not metadata:
        return ""
    value = getattr(metadata, name.lower(), None)
    if not value and hasattr(metadata, "get"):
        value = metadata.get(f"/{name}") or metadata.get(name.lower()) or metadata.get(name)
    return re.sub(r"\s+", " ", str(value or "")).strip()


def extract_pdf_text(data: bytes, reader_factory=PdfReader) -> tuple[str, dict[str, str]]:
    try:
        with tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024, mode="w+b") as handle:
            handle.write(data)
            handle.seek(0)
            reader = reader_factory(handle)
            if getattr(reader, "is_encrypted", False):
                try:
                    reader.decrypt("")
                except Exception as exc:
                    raise ValueError("Password-protected PDFs are not supported") from exc
            parts: list[str] = []
            total = 0
            for page in reader.pages:
                page_text = re.sub(r"[ \t]+", " ", page.extract_text() or "")
                page_text = re.sub(r"\n{3,}", "\n\n", page_text).strip()
                if not page_text:
                    continue
                remaining = MAX_TEXT_CHARS - total
                if remaining <= 0:
                    break
                selected = page_text[:remaining]
                parts.append(selected)
                total += len(selected) + 2
            text = "\n\n".join(parts).strip()
            metadata = {
                "title": _metadata_value(getattr(reader, "metadata", None), "Title"),
                "author": _metadata_value(getattr(reader, "metadata", None), "Author"),
            }
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Could not read PDF: {exc}") from exc
    if len(text) < 200:
        raise ValueError("PDF contains no readable text; scanned PDFs are not supported yet")
    return text, metadata


class PdfImportCache:
    def __init__(self, ttl_seconds: int = CACHE_TTL_SECONDS, clock: Callable[[], float] = time.monotonic):
        self.ttl_seconds = ttl_seconds
        self.clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, dict[str, Any]]] = {}

    def _purge_expired(self, now: float) -> None:
        expired = [token for token, (deadline, _) in self._entries.items() if deadline <= now]
        for token in expired:
            self._entries.pop(token, None)

    def put(self, value: dict[str, Any]) -> str:
        token = secrets.token_urlsafe(24)
        now = self.clock()
        with self._lock:
            self._purge_expired(now)
            self._entries[token] = (now + self.ttl_seconds, value)
        return token

    def get(self, token: str) -> dict[str, Any]:
        now = self.clock()
        with self._lock:
            self._purge_expired(now)
            entry = self._entries.get(token)
            if entry is None:
                raise LookupError("PDF import expired; paste the URL again")
            return entry[1]

    def discard(self, token: str) -> None:
        with self._lock:
            self._entries.pop(token, None)


PDF_IMPORT_CACHE = PdfImportCache()


def _source_name(url: str) -> str:
    hostname = (urllib.parse.urlsplit(url).hostname or "").lower()
    if hostname == "openreview.net" or hostname.endswith(".openreview.net"):
        return "OpenReview"
    if hostname == "openaccess.thecvf.com" or hostname.endswith(".thecvf.com"):
        return "CVF Open Access"
    return "PDF"


def _abstract_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.hostname or "").lower().endswith("openreview.net"):
        review_id = urllib.parse.parse_qs(parsed.query).get("id", [""])[0]
        if review_id:
            return f"https://openreview.net/forum?id={urllib.parse.quote(review_id)}"
    return url


def _placeholder_title(url: str, metadata: dict[str, str]) -> str:
    if metadata.get("title"):
        return metadata["title"]
    parsed = urllib.parse.urlsplit(url)
    review_id = urllib.parse.parse_qs(parsed.query).get("id", [""])[0]
    if review_id and (parsed.hostname or "").lower().endswith("openreview.net"):
        return f"OpenReview paper {review_id}"
    stem = PurePosixPath(urllib.parse.unquote(parsed.path)).stem
    cleaned = re.sub(r"[_-]+", " ", stem).strip()
    return cleaned or "PDF paper"


def _metadata_authors(metadata: dict[str, str]) -> list[str]:
    author = metadata.get("author", "")
    if not author:
        return []
    return [item.strip() for item in re.split(r"\s*(?:;|\band\b)\s*", author) if item.strip()]


def resolve_pdf_url(url: str) -> dict[str, Any]:
    final_url, data = download_pdf(url)
    text, metadata = extract_pdf_text(data)
    digest = hashlib.sha256(final_url.encode("utf-8")).hexdigest()[:20]
    now = dt.datetime.now(dt.timezone.utc).date().isoformat()
    candidate: dict[str, Any] = {
        "id": f"pdf-{digest}",
        "source": _source_name(final_url),
        "source_id": f"pdf-{digest}",
        "title": _placeholder_title(final_url, metadata),
        "authors": _metadata_authors(metadata),
        "published": "",
        "updated": now,
        "abstract": "",
        "categories": [],
        "links": {"abstract": _abstract_url(final_url), "pdf": final_url, "code": ""},
        "topics": [],
        "relevance_score": 0,
        "summary_zh": "",
        "abstract_zh": "",
        "why_relevant_zh": "",
        "deepseek_used": False,
    }
    token = PDF_IMPORT_CACHE.put({"text": text, "candidate": candidate.copy(), "final_url": final_url})
    candidate["import_token"] = token
    return candidate
