import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import fetch_papers
from scripts import pdf_import
from scripts import paper_service


TOPICS = {
    "vision": {"name": "Vision", "description": "Visual pruning", "keywords": ["visual token pruning"]},
    "interpretability": {"name": "Interpretability", "description": "Explainability", "keywords": ["interpretability"]},
}


class PaperServiceTests(unittest.TestCase):
    def test_extract_arxiv_id_from_url(self):
        self.assertEqual(
            paper_service.extract_arxiv_id("https://arxiv.org/pdf/2607.12345v2.pdf"),
            "2607.12345v2",
        )

    def test_title_search_returns_candidates(self):
        expected = [{"title": "Matched paper"}]
        with mock.patch.object(paper_service, "_fetch_arxiv", return_value=expected) as fetch:
            result = paper_service.resolve_paper_input("A descriptive paper title")
        self.assertEqual(result, expected)
        self.assertIn('ti:"A descriptive paper title"', fetch.call_args.args[0]["search_query"])

    def test_pdf_url_uses_generic_pdf_importer(self):
        expected = {"title": "PDF candidate", "import_token": "token"}
        with mock.patch.object(pdf_import, "resolve_pdf_url", return_value=expected) as resolve:
            result = paper_service.resolve_paper_input("https://openreview.net/pdf?id=test123")
        self.assertEqual(result, [expected])
        resolve.assert_called_once_with("https://openreview.net/pdf?id=test123")

    def test_analysis_filters_recommended_topics(self):
        paper = {
            "id": "arxiv-2607.12345v1",
            "source": "arXiv",
            "source_id": "2607.12345v1",
            "title": "Visual pruning",
            "abstract": "We prune visual tokens.",
        }
        topics_payload = [{"id": key, **value} for key, value in TOPICS.items()]
        response = {
            "papers": [
                {
                    "id": paper["id"],
                    "topics": ["vision", "unknown"],
                    "relevance_score": 88,
                    "summary_zh": "中文总结",
                    "abstract_zh": "中文摘要",
                    "why_relevant_zh": "相关原因",
                }
            ]
        }
        with mock.patch.object(fetch_papers, "call_deepseek_json", return_value=response):
            analyzed = paper_service.analyze_paper(paper, topics_payload, "sk-test")
        self.assertEqual(analyzed["topics"], ["vision"])
        self.assertTrue(analyzed["deepseek_used"])

    def test_pdf_analysis_extracts_metadata_and_preserves_validated_links(self):
        candidate = {
            "id": "pdf-stable",
            "source": "OpenReview",
            "source_id": "pdf-stable",
            "title": "OpenReview paper test123",
            "authors": [],
            "published": "",
            "abstract": "",
            "links": {
                "abstract": "https://openreview.net/forum?id=test123",
                "pdf": "https://openreview.net/pdf?id=test123",
                "code": "",
            },
            "import_token": "import-token",
        }
        topics_payload = [{"id": key, **value} for key, value in TOPICS.items()]
        response = {
            "paper": {
                "title": "Extracted Paper Title",
                "authors": ["Alice Example", "Bob Example"],
                "published": "2026-07-01",
                "abstract": "A faithful English abstract.",
                "topics": ["vision", "unknown"],
                "relevance_score": 91,
                "summary_zh": "中文总结",
                "abstract_zh": "中文摘要",
                "why_relevant_zh": "相关原因",
            }
        }
        cache_entry = {"text": "Full extracted PDF text " * 100, "candidate": candidate.copy()}
        with mock.patch.object(pdf_import.PDF_IMPORT_CACHE, "get", return_value=cache_entry), mock.patch.object(
            pdf_import.PDF_IMPORT_CACHE, "discard"
        ) as discard, mock.patch.object(fetch_papers, "call_deepseek_json", return_value=response) as deepseek:
            analyzed = paper_service.analyze_paper(candidate, topics_payload, "sk-test")

        self.assertEqual(analyzed["title"], "Extracted Paper Title")
        self.assertEqual(analyzed["authors"], ["Alice Example", "Bob Example"])
        self.assertEqual(analyzed["topics"], ["vision"])
        self.assertEqual(analyzed["links"], candidate["links"])
        self.assertNotIn("import_token", analyzed)
        self.assertTrue(analyzed["deepseek_used"])
        self.assertIn("Full extracted PDF text", deepseek.call_args.args[0][1]["content"])
        discard.assert_called_once_with("import-token")

    def test_pdf_analysis_requires_deepseek_key(self):
        candidate = {
            "id": "pdf-stable",
            "source": "PDF",
            "source_id": "pdf-stable",
            "title": "PDF paper",
            "links": {"pdf": "https://example.org/paper.pdf"},
            "import_token": "import-token",
        }
        with self.assertRaisesRegex(ValueError, "DeepSeek API key"):
            paper_service.analyze_paper(candidate, [], "")

    def test_add_duplicate_unions_manual_topics(self):
        existing = {
            "papers": [
                {
                    "id": "arxiv-2607.12345v1",
                    "source": "arXiv",
                    "source_id": "2607.12345v1",
                    "title": "Same Paper",
                    "topics": ["vision"],
                    "manual_topics": ["vision"],
                }
            ]
        }
        incoming = {
            "id": "arxiv-2607.12345v2",
            "source": "arXiv",
            "source_id": "2607.12345v2",
            "title": "Same Paper",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_path = root / "data.json"
            docs_path = root / "docs.json"
            status_path = root / "status.json"
            data_path.write_text(json.dumps(existing), encoding="utf-8")
            with mock.patch.object(fetch_papers, "DATA_PATH", data_path), mock.patch.object(
                fetch_papers, "DOCS_PATH", docs_path
            ), mock.patch.object(fetch_papers, "STATUS_PATH", status_path), mock.patch.object(
                fetch_papers, "load_topics", return_value=TOPICS
            ), mock.patch.object(paper_service, "_backup_before_mutation", return_value=None):
                result = paper_service.add_paper(incoming, ["interpretability"])

            stored = json.loads(data_path.read_text(encoding="utf-8"))["papers"]
        self.assertEqual(len(stored), 1)
        self.assertEqual(set(stored[0]["manual_topics"]), {"vision", "interpretability"})
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["updated"], 1)

    def test_delete_removes_current_record_without_blocking_future_merge(self):
        removed_paper = {
            "id": "arxiv-2607.12345v1",
            "source": "arXiv",
            "source_id": "2607.12345v1",
            "title": "Paper to remove",
            "topics": ["vision"],
        }
        retained_paper = {
            "id": "arxiv-2607.99999v1",
            "source": "arXiv",
            "source_id": "2607.99999v1",
            "title": "Paper to retain",
            "topics": ["interpretability"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_path = root / "data.json"
            docs_path = root / "docs.json"
            status_path = root / "status.json"
            data_path.write_text(json.dumps({"papers": [removed_paper, retained_paper]}), encoding="utf-8")
            with mock.patch.object(fetch_papers, "DATA_PATH", data_path), mock.patch.object(
                fetch_papers, "DOCS_PATH", docs_path
            ), mock.patch.object(fetch_papers, "STATUS_PATH", status_path), mock.patch.object(
                fetch_papers, "TOPICS", TOPICS
            ), mock.patch.object(paper_service, "_backup_before_mutation", return_value=None):
                result = paper_service.delete_paper(removed_paper)
                stored = json.loads(data_path.read_text(encoding="utf-8"))["papers"]
                published = json.loads(docs_path.read_text(encoding="utf-8"))["papers"]
                restored, stats = fetch_papers.merge_papers(stored, [removed_paper])

        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["total"], 1)
        self.assertEqual([paper["source_id"] for paper in stored], ["2607.99999v1"])
        self.assertEqual([paper["source_id"] for paper in published], ["2607.99999v1"])
        self.assertEqual(len(restored), 2)
        self.assertEqual(stats["added"], 1)

    def test_delete_missing_paper_raises_lookup_error(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data_path = root / "data.json"
            data_path.write_text(json.dumps({"papers": []}), encoding="utf-8")
            with mock.patch.object(fetch_papers, "DATA_PATH", data_path):
                with self.assertRaisesRegex(LookupError, "not found"):
                    paper_service.delete_paper(
                        {
                            "id": "arxiv-2607.12345v1",
                            "source": "arXiv",
                            "source_id": "2607.12345v1",
                            "title": "Missing paper",
                        }
                    )


if __name__ == "__main__":
    unittest.main()
