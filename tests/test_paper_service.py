import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts import fetch_papers
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
            ), mock.patch.object(paper_service, "_backup_before_add", return_value=None):
                result = paper_service.add_paper(incoming, ["interpretability"])

            stored = json.loads(data_path.read_text(encoding="utf-8"))["papers"]
        self.assertEqual(len(stored), 1)
        self.assertEqual(set(stored[0]["manual_topics"]), {"vision", "interpretability"})
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["updated"], 1)


if __name__ == "__main__":
    unittest.main()
