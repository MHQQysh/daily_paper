#!/usr/bin/env python3
"""Fetch and publish daily token-pruning paper metadata."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "papers.json"
DOCS_PATH = ROOT / "docs" / "papers.json"
ARXIV_API = "https://export.arxiv.org/api/query"
DEEPSEEK_API = "https://api.deepseek.com/chat/completions"

TOPICS = {
    "visual-token-pruning": {
        "name": "Visual Token Pruning",
        "description": "Pruning or selecting image/video tokens for vision and multimodal models.",
        "keywords": [
            "visual token pruning",
            "vision token pruning",
            "image token pruning",
            "video token pruning",
            "visual token reduction",
            "visual tokens",
            "image tokens",
            "vision tokens",
        ],
    },
    "vlm-acceleration": {
        "name": "VLM / MLLM Acceleration",
        "description": "Efficient inference for vision-language and multimodal large language models.",
        "keywords": [
            "vision language model",
            "vision-language model",
            "multimodal large language model",
            "mllm",
            "vlm",
            "llava",
            "qwen-vl",
            "internvl",
            "multimodal inference",
        ],
    },
    "llm-context-kv-pruning": {
        "name": "LLM Context / KV Pruning",
        "description": "Context compression, prompt pruning, attention pruning, and KV cache reduction.",
        "keywords": [
            "kv cache pruning",
            "kv cache compression",
            "context pruning",
            "prompt pruning",
            "attention pruning",
            "token eviction",
            "long context",
            "key value cache",
        ],
    },
    "token-merging-compression": {
        "name": "Token Merging / Compression",
        "description": "Token merging, token compression, token dropping, or redundancy reduction.",
        "keywords": [
            "token merging",
            "token compression",
            "token reduction",
            "token dropping",
            "token sparsification",
            "redundant tokens",
            "merge tokens",
        ],
    },
    "efficient-vit": {
        "name": "Efficient ViT",
        "description": "Efficient vision transformer methods related to token sparsity or adaptive tokens.",
        "keywords": [
            "efficient vision transformer",
            "efficient vit",
            "vision transformer pruning",
            "vit pruning",
            "dynamic vit",
            "token learner",
            "token pooling",
        ],
    },
    "dynamic-token-selection": {
        "name": "Dynamic Token Selection",
        "description": "Input-adaptive token routing, selection, or early-exit style token control.",
        "keywords": [
            "dynamic token",
            "adaptive token",
            "token selection",
            "token routing",
            "token saliency",
            "token importance",
            "early exit",
        ],
    },
    "survey-benchmark": {
        "name": "Survey / Benchmark",
        "description": "Survey, benchmark, evaluation, or analysis papers for efficient token methods.",
        "keywords": [
            "survey",
            "benchmark",
            "taxonomy",
            "token pruning benchmark",
            "token compression benchmark",
            "efficient inference benchmark",
        ],
    },
}

BASE_QUERY_TERMS = [
    '"token pruning"',
    '"visual token pruning"',
    '"vision token pruning"',
    '"token reduction"',
    '"token compression"',
    '"token merging"',
    '"dynamic token selection"',
    '"kv cache pruning"',
    '"context pruning"',
    '"efficient vision transformer"',
    '"multimodal large language model" "token"',
    '"vision language model" "token"',
]

SIGNAL_TERMS = [
    "token",
    "pruning",
    "compression",
    "reduction",
    "merging",
    "selection",
    "sparsity",
    "sparsification",
    "eviction",
    "kv cache",
    "vision-language",
    "multimodal",
    "vision transformer",
]


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:100] or "paper"


def arxiv_query() -> str:
    title_abs = [f"ti:{term} OR abs:{term}" for term in BASE_QUERY_TERMS]
    return " OR ".join(f"({part})" for part in title_abs)


def fetch_url(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "daily-paper-token-pruning/1.0 (metadata only)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()


def fetch_arxiv(days: int, max_results: int) -> list[dict[str, Any]]:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    params = {
        "search_query": arxiv_query(),
        "start": "0",
        "max_results": str(max_results),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
    raw = fetch_url(url)
    root = ET.fromstring(raw)
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    papers: list[dict[str, Any]] = []
    for entry in root.findall("atom:entry", ns):
        source_id = normalize_text(entry.findtext("atom:id", default="", namespaces=ns))
        title = normalize_text(entry.findtext("atom:title", default="", namespaces=ns))
        abstract = normalize_text(entry.findtext("atom:summary", default="", namespaces=ns))
        published_raw = normalize_text(entry.findtext("atom:published", default="", namespaces=ns))
        updated_raw = normalize_text(entry.findtext("atom:updated", default="", namespaces=ns))
        try:
            published_dt = dt.datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
        except ValueError:
            published_dt = dt.datetime.now(dt.timezone.utc)
        if published_dt < cutoff:
            continue
        authors = [
            normalize_text(author.findtext("atom:name", default="", namespaces=ns))
            for author in entry.findall("atom:author", ns)
        ]
        links = {"abstract": source_id, "pdf": "", "code": ""}
        for link in entry.findall("atom:link", ns):
            title_attr = link.attrib.get("title")
            href = link.attrib.get("href", "")
            if title_attr == "pdf":
                links["pdf"] = href
        categories = [cat.attrib.get("term", "") for cat in entry.findall("atom:category", ns)]
        arxiv_id = source_id.rstrip("/").split("/")[-1]
        papers.append(
            {
                "id": f"arxiv-{arxiv_id}",
                "source": "arXiv",
                "source_id": arxiv_id,
                "title": title,
                "authors": [a for a in authors if a],
                "published": published_dt.date().isoformat(),
                "updated": updated_raw[:10] if updated_raw else published_dt.date().isoformat(),
                "abstract": abstract,
                "categories": categories,
                "links": links,
            }
        )
    return papers


def score_and_topics(paper: dict[str, Any]) -> tuple[list[str], int]:
    text = f"{paper.get('title', '')} {paper.get('abstract', '')}".lower()
    topic_scores: dict[str, int] = {}
    for topic_id, topic in TOPICS.items():
        score = 0
        for keyword in topic["keywords"]:
            if keyword.lower() in text:
                score += 3 if " " in keyword else 1
        if score:
            topic_scores[topic_id] = score
    broad_score = sum(1 for term in SIGNAL_TERMS if term in text)
    if "token" in text and any(term in text for term in ["pruning", "compression", "reduction", "merging", "selection"]):
        broad_score += 6
    if any(term in text for term in ["vision-language", "multimodal", "vision transformer", "kv cache"]):
        broad_score += 2
    topics = [k for k, _ in sorted(topic_scores.items(), key=lambda item: item[1], reverse=True)]
    if not topics and broad_score >= 3:
        topics = ["dynamic-token-selection"]
    relevance = min(100, max(0, broad_score * 8 + sum(topic_scores.values()) * 4))
    return topics[:4], relevance


def fallback_enrichment(paper: dict[str, Any]) -> dict[str, Any]:
    topics, relevance = score_and_topics(paper)
    abstract = paper.get("abstract", "")
    first_sentence = re.split(r"(?<=[.!?])\s+", abstract)[0] if abstract else ""
    if not first_sentence:
        first_sentence = "No abstract is available."
    if topics:
        topic_names = ", ".join(TOPICS[t]["name"] for t in topics)
    else:
        topic_names = "Unclassified"
    return {
        **paper,
        "topics": topics,
        "relevance_score": relevance,
        "summary_zh": f"候选论文：{first_sentence[:220]}",
        "why_relevant_zh": f"关键词匹配到 {topic_names}；DeepSeek API 未配置时使用本地规则打分。",
        "deepseek_used": False,
    }


def deepseek_prompt(papers: list[dict[str, Any]]) -> list[dict[str, str]]:
    topic_catalog = [
        {"id": topic_id, "name": topic["name"], "description": topic["description"]}
        for topic_id, topic in TOPICS.items()
    ]
    compact = [
        {
            "id": p["id"],
            "title": p["title"],
            "abstract": p["abstract"][:1800],
            "local_topics": p.get("topics", []),
            "local_score": p.get("relevance_score", 0),
        }
        for p in papers
    ]
    system = (
        "You are a research assistant tracking token pruning and efficient token methods. "
        "Return strict JSON only. Do not include markdown."
    )
    user = {
        "task": "Classify papers for a daily token-pruning website.",
        "topic_catalog": topic_catalog,
        "rules": [
            "Keep only topic ids from topic_catalog.",
            "relevance_score is an integer from 0 to 100.",
            "summary_zh is one concise Chinese sentence.",
            "why_relevant_zh is one concise Chinese sentence explaining the token-pruning relevance.",
            "If a paper is weakly related, give a low score and explain why.",
        ],
        "papers": compact,
        "output_schema": {
            "papers": [
                {
                    "id": "paper id",
                    "topics": ["topic-id"],
                    "relevance_score": 0,
                    "summary_zh": "中文一句话总结",
                    "why_relevant_zh": "中文相关性说明",
                }
            ]
        },
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def call_deepseek(papers: list[dict[str, Any]], model: str) -> dict[str, dict[str, Any]]:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key or not papers:
        return {}
    payload = {
        "model": model,
        "messages": deepseek_prompt(papers),
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        DEEPSEEK_API,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=90) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    return {item["id"]: item for item in parsed.get("papers", []) if "id" in item}


def enrich_papers(papers: list[dict[str, Any]], model: str, batch_size: int = 8) -> list[dict[str, Any]]:
    enriched = [fallback_enrichment(p) for p in papers]
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return enriched
    by_id = {p["id"]: p for p in enriched}
    for start in range(0, len(enriched), batch_size):
        batch = enriched[start : start + batch_size]
        try:
            result = call_deepseek(batch, model=model)
        except Exception as exc:  # Keep daily automation robust.
            print(f"DeepSeek batch failed: {exc}", file=sys.stderr)
            continue
        for paper_id, item in result.items():
            if paper_id not in by_id:
                continue
            topics = [t for t in item.get("topics", []) if t in TOPICS]
            by_id[paper_id].update(
                {
                    "topics": topics or by_id[paper_id].get("topics", []),
                    "relevance_score": int(item.get("relevance_score", by_id[paper_id].get("relevance_score", 0))),
                    "summary_zh": normalize_text(item.get("summary_zh", by_id[paper_id].get("summary_zh", ""))),
                    "why_relevant_zh": normalize_text(
                        item.get("why_relevant_zh", by_id[paper_id].get("why_relevant_zh", ""))
                    ),
                    "deepseek_used": True,
                }
            )
        time.sleep(1)
    return list(by_id.values())


def read_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"last_updated": None, "papers": []}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def paper_key(paper: dict[str, Any]) -> str:
    if paper.get("source") and paper.get("source_id"):
        return f"{paper['source']}:{paper['source_id']}".lower()
    return re.sub(r"\W+", "", paper.get("title", "").lower())


def merge_papers(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {paper_key(p): p for p in existing}
    for paper in incoming:
        key = paper_key(paper)
        if key in merged:
            merged[key].update({k: v for k, v in paper.items() if v not in (None, "", [])})
        else:
            merged[key] = paper
    papers = list(merged.values())
    papers.sort(key=lambda p: (p.get("published", ""), p.get("relevance_score", 0), p.get("title", "")), reverse=True)
    return papers


def build_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    return {
        "last_updated": now,
        "topics": [
            {"id": topic_id, "name": topic["name"], "description": topic["description"]}
            for topic_id, topic in TOPICS.items()
        ],
        "papers": papers,
    }


def write_outputs(papers: list[dict[str, Any]]) -> None:
    payload = build_payload(papers)
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOCS_PATH.parent.mkdir(parents=True, exist_ok=True)
    for path in (DATA_PATH, DOCS_PATH):
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch daily token-pruning papers.")
    parser.add_argument("--days", type=int, default=int(os.environ.get("PAPER_LOOKBACK_DAYS", "3")))
    parser.add_argument("--max-results", type=int, default=int(os.environ.get("PAPER_MAX_RESULTS", "80")))
    parser.add_argument("--min-score", type=int, default=int(os.environ.get("PAPER_MIN_SCORE", "18")))
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))
    parser.add_argument("--fresh", action="store_true", help="Ignore the existing store and rebuild from this run.")
    args = parser.parse_args()

    existing_store = {"papers": []} if args.fresh else read_store(DATA_PATH)
    raw = fetch_arxiv(days=args.days, max_results=args.max_results)
    prelim = [fallback_enrichment(p) for p in raw]
    candidates = [p for p in prelim if p.get("relevance_score", 0) >= args.min_score or p.get("topics")]
    enriched = enrich_papers(candidates, model=args.model)
    kept = [p for p in enriched if p.get("relevance_score", 0) >= args.min_score or p.get("topics")]
    merged = merge_papers(existing_store.get("papers", []), kept)
    write_outputs(merged)
    print(f"Fetched {len(raw)} arXiv papers, kept {len(kept)}, total stored {len(merged)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
