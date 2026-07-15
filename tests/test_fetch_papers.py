import io
import urllib.error
import urllib.parse
import unittest
from unittest import mock

from scripts import fetch_papers


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return self.body


class ArxivFetchTests(unittest.TestCase):
    def test_http_429_is_retried(self):
        error = urllib.error.HTTPError("https://example.test", 429, "limited", {"Retry-After": "0"}, io.BytesIO())
        with mock.patch.object(
            fetch_papers.urllib.request,
            "urlopen",
            side_effect=[error, FakeResponse(b"ok")],
        ) as urlopen, mock.patch.object(fetch_papers.time, "sleep") as sleep:
            body = fetch_papers.fetch_url("https://example.test", max_attempts=2)

        self.assertEqual(body, b"ok")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(3.0)

    def test_timeout_is_retried(self):
        with mock.patch.object(
            fetch_papers.urllib.request,
            "urlopen",
            side_effect=[TimeoutError("slow"), FakeResponse(b"ok")],
        ) as urlopen, mock.patch.object(fetch_papers.time, "sleep") as sleep:
            body = fetch_papers.fetch_url("https://example.test", max_attempts=2)
        self.assertEqual(body, b"ok")
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(3.0)

    def test_single_date_uses_large_pages_even_for_small_result_limit(self):
        feed = b"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry><id>https://arxiv.org/abs/2607.00001v1</id><title>Token pruning one</title><summary>Token pruning.</summary><published>2026-07-08T00:00:00Z</published></entry>
          <entry><id>https://arxiv.org/abs/2607.00002v1</id><title>Token pruning two</title><summary>Token pruning.</summary><published>2026-07-08T01:00:00Z</published></entry>
        </feed>"""
        urls = []

        def fake_fetch(url, timeout=30, max_attempts=5):
            urls.append(url)
            return feed

        with mock.patch.object(fetch_papers, "fetch_url", side_effect=fake_fetch):
            papers = fetch_papers.fetch_arxiv(days=30, max_results=2, target_date="2026-07-08")

        query = urllib.parse.parse_qs(urllib.parse.urlparse(urls[0]).query)
        self.assertEqual(query["max_results"], ["100"])
        self.assertEqual(len(papers), 2)

    def test_query_plan_uses_deepseek_and_fills_missing_topics(self):
        topics = {
            "vision": {"name": "Vision", "description": "Visual pruning", "keywords": ["visual token pruning"]},
            "grpo": {"name": "GRPO", "description": "Policy optimization", "keywords": ["grpo"]},
        }
        response = {
            "topics": [
                {
                    "topic_id": "vision",
                    "search_queries": ["adaptive visual token pruning", "adaptive visual token pruning"],
                    "intent_queries": ["Papers that prune image tokens dynamically."],
                },
                {"topic_id": "unknown", "search_queries": ["ignore me"], "intent_queries": ["ignore me"]},
            ]
        }
        with mock.patch.object(fetch_papers, "call_deepseek_json", return_value=response):
            plan = fetch_papers.build_query_plan(topics, model="deepseek-chat", api_key="sk-test")

        self.assertTrue(plan["deepseek_used"])
        self.assertEqual(plan["topics"][0]["search_queries"], ["adaptive visual token pruning"])
        self.assertEqual(plan["topics"][1]["search_queries"], ["grpo"])

    def test_query_plan_falls_back_without_key(self):
        topics = {"grpo": {"name": "GRPO", "description": "Policy optimization", "keywords": ["grpo", "rlvr"]}}
        plan = fetch_papers.build_query_plan(topics, model="deepseek-chat", api_key="")
        self.assertFalse(plan["deepseek_used"])
        self.assertEqual(plan["topics"][0]["search_queries"], ["grpo", "rlvr"])

    def test_rrf_fuses_arxiv_versions_and_tracks_queries(self):
        first = {
            "source": "arXiv",
            "source_id": "2607.00001v1",
            "title": "A Paper",
            "published": "2026-07-10",
        }
        revised = {**first, "source_id": "2607.00001v2"}
        other = {
            "source": "arXiv",
            "source_id": "2607.00002v1",
            "title": "Another Paper",
            "published": "2026-07-10",
        }
        fused = fetch_papers.fuse_query_results(
            [
                {"topic_id": "vision", "query": "visual pruning", "papers": [first, other]},
                {"topic_id": "vision", "query": "image token reduction", "papers": [revised]},
            ]
        )
        self.assertEqual(len(fused), 2)
        self.assertEqual(fused[0]["source_id"], "2607.00001v1")
        self.assertEqual(len(fused[0]["matched_queries"]), 2)

    def test_merge_is_append_only_and_preserves_manual_topics(self):
        existing = [
            {
                "source": "arXiv",
                "source_id": "2607.00001v1",
                "title": "A Paper",
                "topics": ["vision"],
                "manual_topics": ["interpretability"],
            },
            {"source": "arXiv", "source_id": "2607.00002v1", "title": "Historical Paper", "topics": ["grpo"]},
        ]
        incoming = [
            {
                "source": "arXiv",
                "source_id": "2607.00001v2",
                "title": "A Paper",
                "topics": ["grpo"],
                "summary_zh": "updated",
            }
        ]
        merged, stats = fetch_papers.merge_papers(existing, incoming)
        updated = next(paper for paper in merged if paper["title"] == "A Paper")

        self.assertEqual(len(merged), 2)
        self.assertIn("interpretability", updated["topics"])
        self.assertEqual(stats["added"], 0)
        self.assertEqual(stats["duplicates"], 1)


if __name__ == "__main__":
    unittest.main()
