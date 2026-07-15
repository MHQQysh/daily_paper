import io
import socket
import unittest
from unittest import mock
import urllib.error
import urllib.request

from scripts import pdf_import


def resolver_for(address):
    return lambda host, port, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]


class FakeHeaders(dict):
    def get_content_type(self):
        return self.get("Content-Type", "application/octet-stream").split(";", 1)[0]


class FakeResponse(io.BytesIO):
    def __init__(self, data, url="https://example.org/paper.pdf", headers=None):
        super().__init__(data)
        self._url = url
        self.headers = FakeHeaders(headers or {})

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


class FakeOpener:
    def __init__(self, response):
        self.response = response

    def open(self, request, timeout):
        return self.response


class RaisingOpener:
    def open(self, request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)


class PdfImportTests(unittest.TestCase):
    def test_public_https_url_is_accepted(self):
        result = pdf_import.validate_public_pdf_url(
            "https://example.org/paper.pdf",
            resolver=resolver_for("93.184.216.34"),
        )
        self.assertEqual(result, "https://example.org/paper.pdf")

    def test_private_and_credentialed_urls_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "public"):
            pdf_import.validate_public_pdf_url(
                "http://internal.example/paper.pdf",
                resolver=resolver_for("127.0.0.1"),
            )
        with self.assertRaisesRegex(ValueError, "public"):
            pdf_import.validate_public_pdf_url(
                "https://user:password@example.org/paper.pdf",
                resolver=resolver_for("93.184.216.34"),
            )

    def test_proxy_synthetic_dns_is_verified_through_public_dns(self):
        result = pdf_import.validate_public_pdf_url(
            "https://openreview.net/pdf?id=test",
            resolver=resolver_for("198.18.1.127"),
            public_dns_resolver=lambda host: ["34.120.73.14"],
        )
        self.assertEqual(result, "https://openreview.net/pdf?id=test")

    def test_redirect_to_private_network_is_rejected(self):
        handler = pdf_import.SafeRedirectHandler()
        request = urllib.request.Request("https://example.org/paper.pdf")
        with self.assertRaisesRegex(ValueError, "public"):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "http://127.0.0.1/private.pdf",
            )

    def test_download_rejects_invalid_pdf_signature(self):
        response = FakeResponse(b"<html>not a pdf</html>", headers={"Content-Type": "text/html"})
        with mock.patch.object(pdf_import, "validate_public_pdf_url", side_effect=lambda value: value):
            with self.assertRaisesRegex(ValueError, "valid PDF"):
                pdf_import.download_pdf("https://example.org/paper.pdf", opener=FakeOpener(response))

    def test_download_rejects_oversized_content_length(self):
        response = FakeResponse(
            b"%PDF-1.7",
            headers={"Content-Type": "application/pdf", "Content-Length": str(pdf_import.MAX_PDF_BYTES + 1)},
        )
        with mock.patch.object(pdf_import, "validate_public_pdf_url", side_effect=lambda value: value):
            with self.assertRaisesRegex(ValueError, "30 MB"):
                pdf_import.download_pdf("https://example.org/paper.pdf", opener=FakeOpener(response))

    def test_download_falls_back_to_curl_for_site_that_rejects_urllib(self):
        expected = ("https://openreview.net/pdf?id=test", b"%PDF-1.7 fallback")
        with mock.patch.object(pdf_import, "validate_public_pdf_url", side_effect=lambda value: value), mock.patch.object(
            pdf_import, "_download_pdf_with_curl", return_value=expected
        ) as curl_download:
            result = pdf_import.download_pdf("https://openreview.net/pdf?id=test", opener=RaisingOpener())
        self.assertEqual(result, expected)
        curl_download.assert_called_once_with("https://openreview.net/pdf?id=test")

    def test_extract_rejects_pdf_without_readable_text(self):
        page = mock.Mock()
        page.extract_text.return_value = ""
        reader = mock.Mock(pages=[page], metadata={})
        with self.assertRaisesRegex(ValueError, "readable text"):
            pdf_import.extract_pdf_text(b"%PDF-1.7", reader_factory=lambda handle: reader)

    def test_resolve_returns_compact_candidate_and_cache_token(self):
        with mock.patch.object(
            pdf_import,
            "download_pdf",
            return_value=("https://openreview.net/pdf?id=test123", b"%PDF-1.7"),
        ), mock.patch.object(
            pdf_import,
            "extract_pdf_text",
            return_value=("Readable paper text " * 100, {"title": "Cached Paper", "author": "A. Author"}),
        ):
            candidate = pdf_import.resolve_pdf_url("https://openreview.net/pdf?id=test123")

        self.assertEqual(candidate["source"], "OpenReview")
        self.assertEqual(candidate["links"]["pdf"], "https://openreview.net/pdf?id=test123")
        self.assertEqual(candidate["links"]["abstract"], "https://openreview.net/forum?id=test123")
        self.assertNotIn("document_text", candidate)
        cached = pdf_import.PDF_IMPORT_CACHE.get(candidate["import_token"])
        self.assertIn("Readable paper text", cached["text"])
        pdf_import.PDF_IMPORT_CACHE.discard(candidate["import_token"])

    def test_cache_entry_expires(self):
        now = [100.0]
        cache = pdf_import.PdfImportCache(ttl_seconds=10, clock=lambda: now[0])
        token = cache.put({"text": "paper"})
        now[0] = 111.0
        with self.assertRaisesRegex(LookupError, "expired"):
            cache.get(token)


if __name__ == "__main__":
    unittest.main()
