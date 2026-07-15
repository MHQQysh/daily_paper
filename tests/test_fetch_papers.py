import io
import datetime as dt
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
    def test_daily_category_retrieval_uses_broad_arxiv_categories(self):
        expected = [{"id": "paper-1"}]
        with mock.patch.object(fetch_papers, "fetch_arxiv", return_value=expected) as fetch:
            result = fetch_papers.fetch_daily_category_papers("2026-07-10")

        self.assertEqual(result, expected)
        fetch.assert_called_once()
        call = fetch.call_args.kwargs
        self.assertEqual(call["target_date"], "2026-07-10")
        self.assertEqual(call["max_results"], 1000)
        self.assertIn("(cat:cs.AI OR cat:cs.CV OR cat:cs.LG OR cat:cs.CL)", call["search_expression"])
        self.assertIn("submittedDate:[202607100000 TO 202607102359]", call["search_expression"])

    def test_date_range_defaults_to_previous_utc_day(self):
        today = dt.date(2026, 7, 15)
        self.assertEqual(fetch_papers.resolve_date_range("", "", today=today), ("2026-07-14", "2026-07-14"))
        self.assertEqual(
            fetch_papers.resolve_date_range("2026-07-10", "2026-07-12", today=today),
            ("2026-07-10", "2026-07-12"),
        )

    def test_date_range_is_inclusive_and_rejects_invalid_bounds(self):
        self.assertEqual(
            fetch_papers.iter_date_range("2026-07-10", "2026-07-12"),
            ["2026-07-10", "2026-07-11", "2026-07-12"],
        )
        with self.assertRaisesRegex(ValueError, "start date"):
            fetch_papers.resolve_date_range("2026-07-12", "2026-07-10")
        with self.assertRaisesRegex(ValueError, "31 days"):
            fetch_papers.resolve_date_range("2026-06-01", "2026-07-02")

    def test_category_range_fetches_each_day_and_deduplicates(self):
        daily = {
            "2026-07-10": [{"id": "a", "title": "Shared Paper", "published": "2026-07-10"}],
            "2026-07-11": [
                {"id": "a-v2", "title": "Shared Paper", "published": "2026-07-11"},
                {"id": "b", "title": "Unique Paper", "published": "2026-07-11"},
            ],
        }
        with mock.patch.object(
            fetch_papers, "fetch_daily_category_papers", side_effect=lambda day, max_scan=1000: daily[day]
        ) as fetch:
            papers, stats = fetch_papers.fetch_category_range("2026-07-10", "2026-07-11")

        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(stats, {"daily_retrievals": 2, "raw_found": 3})
        self.assertEqual({paper["title"] for paper in papers}, {"Shared Paper", "Unique Paper"})

    def test_shortlist_balances_dates_and_deduplicates_topics(self):
        topics = {
            "vision": {"name": "Vision", "description": "visual tokens", "keywords": ["visual token"]},
            "grpo": {"name": "GRPO", "description": "policy optimization", "keywords": ["grpo"]},
        }
        papers = [
            {
                "id": f"paper-{day}",
                "title": f"Visual token GRPO {day}",
                "abstract": "visual token grpo",
                "published": f"2026-07-{day}",
            }
            for day in ("10", "11", "12")
        ]
        with mock.patch.object(fetch_papers, "TOPICS", topics):
            shortlisted, counts = fetch_papers.shortlist_candidates(
                papers, papers_per_topic=1, per_topic_limit=3
            )

        self.assertEqual({paper["published"] for paper in shortlisted}, {"2026-07-10", "2026-07-11", "2026-07-12"})
        self.assertEqual(counts, {"vision": 3, "grpo": 3})

    def test_deepseek_ranking_normalizes_topic_scores(self):
        topics = {
            "vision": {"name": "Vision", "description": "Vision pruning", "keywords": ["visual token"]},
            "grpo": {"name": "GRPO", "description": "Policy optimization", "keywords": ["grpo"]},
        }
        papers = [
            {"id": "paper-1", "title": "Visual tokens", "abstract": "Compress visual tokens."},
            {"id": "paper-2", "title": "Policy", "abstract": "Group policy optimization."},
        ]
        response = {
            "papers": [
                {"id": "paper-1", "scores": {"vision": 93, "grpo": -4, "unknown": 100}},
                {"id": "paper-2", "scores": {"vision": "8", "grpo": 120}},
            ]
        }
        with mock.patch.object(fetch_papers, "TOPICS", topics), mock.patch.dict(
            fetch_papers.os.environ, {"DEEPSEEK_API_KEY": "sk-test"}
        ), mock.patch.object(fetch_papers, "call_deepseek_json", return_value=response):
            scores = fetch_papers.rank_papers_by_topic(papers, model="deepseek-chat", batch_size=20)

        self.assertEqual(scores["paper-1"], {"vision": 93, "grpo": 0})
        self.assertEqual(scores["paper-2"], {"vision": 8, "grpo": 100})

    def test_per_topic_selection_keeps_overlap_once_with_both_topics(self):
        topics = {
            "vision": {"name": "Vision", "description": "", "keywords": ["vision"]},
            "interpretability": {"name": "Interpretability", "description": "", "keywords": ["explain"]},
        }
        papers = [
            {"id": "shared", "title": "Shared", "published": "2026-07-10"},
            {"id": "vision-only", "title": "Vision", "published": "2026-07-10"},
            {"id": "interpret-only", "title": "Interpret", "published": "2026-07-10"},
        ]
        scores = {
            "shared": {"vision": 95, "interpretability": 91},
            "vision-only": {"vision": 80, "interpretability": 0},
            "interpret-only": {"vision": 0, "interpretability": 85},
        }
        with mock.patch.object(fetch_papers, "TOPICS", topics):
            selected, counts = fetch_papers.select_per_topic(papers, scores, papers_per_topic=2)

        self.assertEqual(counts, {"vision": 2, "interpretability": 2})
        self.assertEqual(len(selected), 3)
        shared = next(paper for paper in selected if paper["id"] == "shared")
        self.assertEqual(shared["topics"], ["vision", "interpretability"])
        self.assertEqual(shared["relevance_score"], 95)

    def test_fallback_enrichment_preserves_selected_topics_and_rank_score(self):
        topics = {
            "manifold": {"name": "Manifold", "description": "", "keywords": ["manifold"]},
        }
        paper = {
            "id": "paper-1",
            "title": "A geometric paper",
            "abstract": "A geometric representation method.",
            "topics": ["manifold"],
            "relevance_score": 82,
        }
        with mock.patch.object(fetch_papers, "TOPICS", topics):
            enriched = fetch_papers.fallback_enrichment(paper)
        self.assertEqual(enriched["topics"], ["manifold"])
        self.assertEqual(enriched["relevance_score"], 82)

    def test_deepseek_enrichment_cannot_add_unselected_topic(self):
        topics = {
            "vision": {"name": "Vision", "description": "Vision pruning", "keywords": ["visual token"]},
            "grpo": {"name": "GRPO", "description": "Policy optimization", "keywords": ["grpo"]},
        }
        paper = {
            "id": "paper-1",
            "title": "Visual token pruning",
            "abstract": "A visual token method.",
            "topics": ["vision"],
            "relevance_score": 91,
        }
        response = {
            "paper-1": {
                "id": "paper-1",
                "topics": ["vision", "grpo"],
                "relevance_score": 80,
                "summary_zh": "summary",
                "abstract_zh": "abstract",
                "why_relevant_zh": "relevant",
            }
        }
        with mock.patch.object(fetch_papers, "TOPICS", topics), mock.patch.dict(
            "os.environ", {"DEEPSEEK_API_KEY": "sk-test"}
        ), mock.patch.object(fetch_papers, "call_deepseek", return_value=response):
            enriched = fetch_papers.enrich_papers([paper], model="deepseek-chat")

        self.assertEqual(enriched[0]["topics"], ["vision"])
        self.assertEqual(enriched[0]["relevance_score"], 91)

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
