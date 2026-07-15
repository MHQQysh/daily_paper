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
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "papers.json"
DOCS_PATH = ROOT / "docs" / "papers.json"
CONFIG_PATH = ROOT / "config" / "topics.json"
STATUS_PATH = ROOT / "docs" / "run_status.json"
ARXIV_API = "https://export.arxiv.org/api/query"
DEEPSEEK_API = "https://api.deepseek.com/chat/completions"

TOPICS = {
    "vision-token-pruning": {
        "name": "Visual Token Pruning",
        "description": "Pruning, selecting, merging, or compressing visual tokens in vision and multimodal models.",
        "keywords": [
            "visual token pruning",
            "vision token pruning",
            "image token pruning",
            "video token pruning",
            "visual token compression",
            "vision token compression",
            "visual token reduction",
            "visual token selection",
            "visual token merging",
            "multimodal token pruning",
            "visual tokens",
            "image tokens",
            "vision tokens",
        ],
    },
    "grpo": {
        "name": "GRPO",
        "description": "Group Relative Policy Optimization and closely related reinforcement-learning methods.",
        "keywords": [
            "grpo",
            "group relative policy optimization",
            "group relative policy optimisation",
            "group relative policy",
            "reinforcement learning with verifiable rewards",
            "rlvr",
            "reasoning policy optimization",
            "reasoning policy optimisation",
        ],
    },
    "interpretability": {
        "name": "可解释性",
        "description": "Interpretability, explainability, attribution, and mechanistic analysis of machine-learning models.",
        "keywords": [
            "interpretability",
            "explainability",
            "mechanistic interpretability",
            "model interpretation",
            "feature attribution",
            "concept attribution",
            "activation attribution",
            "saliency map",
            "explainable ai",
            "xai",
            "circuit analysis",
            "representation analysis",
            "multimodal interpretability",
            "vision-language interpretability",
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


def arxiv_base_id(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id)


def normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", normalize_text(title).lower())


def paper_identity_keys(paper: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    source_id = normalize_text(paper.get("source_id", ""))
    if source_id and str(paper.get("source", "")).lower() == "arxiv":
        keys.append(f"arxiv:{arxiv_base_id(source_id).lower()}")
    doi = normalize_text(paper.get("doi", ""))
    if doi:
        normalized_doi = doi.lower().removeprefix("https://doi.org/").removeprefix("doi:")
        keys.append(f"doi:{normalized_doi}")
    title_key = normalize_title(paper.get("title", ""))
    if title_key:
        keys.append(f"title:{title_key}")
    return list(dict.fromkeys(keys))


def load_topics(override_json: str = "") -> dict[str, dict[str, Any]]:
    if override_json:
        try:
            data = json.loads(override_json)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"Invalid topics JSON: {exc}") from exc
        return normalize_topics_payload(data)
    if not CONFIG_PATH.exists():
        return TOPICS
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return normalize_topics_payload(data)


def normalize_topics_payload(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for item in data.get("topics", []):
        name = normalize_text(item.get("name", ""))
        if not name:
            continue
        topic_id = normalize_text(item.get("id", "")) or slugify(name)
        keywords = [normalize_text(k) for k in item.get("keywords", []) if normalize_text(k)]
        loaded[topic_id] = {
            "name": name,
            "description": normalize_text(item.get("description", "")),
            "keywords": keywords,
        }
    return loaded or TOPICS


def arxiv_query() -> str:
    dynamic_terms = list(BASE_QUERY_TERMS)
    for topic in TOPICS.values():
        for keyword in topic.get("keywords", []):
            keyword = normalize_text(keyword)
            if keyword:
                dynamic_terms.append(f'"{keyword}"' if " " in keyword else keyword)
    seen: set[str] = set()
    unique_terms: list[str] = []
    for term in dynamic_terms:
        key = term.lower()
        if key not in seen:
            seen.add(key)
            unique_terms.append(term)
    title_abs = [f"ti:{term} OR abs:{term}" for term in unique_terms[:60]]
    return " OR ".join(f"({part})" for part in title_abs)


def _unique_texts(values: Any, limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values if isinstance(values, list) else []:
        text = normalize_text(value)
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text[:180])
        if len(result) >= limit:
            break
    return result


def fallback_query_plan(topics: dict[str, dict[str, Any]]) -> dict[str, Any]:
    plan = []
    for topic_id, topic in topics.items():
        keywords = _unique_texts(topic.get("keywords", []), 6)
        description = normalize_text(topic.get("description", ""))
        plan.append(
            {
                "topic_id": topic_id,
                "search_queries": keywords[:3] or [topic.get("name", topic_id)],
                "intent_queries": [description] if description else [f"Recent research about {topic.get('name', topic_id)}"],
            }
        )
    return {"topics": plan, "deepseek_used": False}


def query_plan_prompt(topics: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    catalog = [
        {
            "id": topic_id,
            "name": topic.get("name", topic_id),
            "description": topic.get("description", ""),
            "seed_keywords": topic.get("keywords", []),
        }
        for topic_id, topic in topics.items()
    ]
    request = {
        "task": "Expand each research direction into precise academic discovery queries for recent papers.",
        "directions": catalog,
        "rules": [
            "Return every direction exactly once using its existing id.",
            "search_queries must contain 2 or 3 concise English concept phrases suitable for title/abstract search.",
            "Do not use boolean syntax in search_queries.",
            "Vary method, task, and application angles instead of returning simple synonyms.",
            "intent_queries must contain 2 or 3 English sentences describing ideal relevant papers for reranking.",
        ],
        "output_schema": {
            "topics": [
                {
                    "topic_id": "existing topic id",
                    "search_queries": ["academic phrase"],
                    "intent_queries": ["ideal paper description"],
                }
            ]
        },
    }
    return [
        {
            "role": "system",
            "content": "You are an academic query expansion assistant. Return strict JSON only, without markdown.",
        },
        {"role": "user", "content": json.dumps(request, ensure_ascii=False)},
    ]


def build_query_plan(
    topics: dict[str, dict[str, Any]], model: str, api_key: str | None = None
) -> dict[str, Any]:
    fallback = fallback_query_plan(topics)
    key = api_key if api_key is not None else os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        print("DeepSeek query planner is unavailable; using configured keyword queries.", flush=True)
        return fallback
    try:
        parsed = call_deepseek_json(query_plan_prompt(topics), model=model, api_key=key)
    except Exception as exc:
        print(f"DeepSeek query planner failed; using fallback queries: {exc}", flush=True)
        return fallback

    supplied = {
        normalize_text(item.get("topic_id", "")): item
        for item in parsed.get("topics", [])
        if isinstance(item, dict)
    }
    fallback_by_id = {item["topic_id"]: item for item in fallback["topics"]}
    planned = []
    for topic_id in topics:
        item = supplied.get(topic_id, {})
        base = fallback_by_id[topic_id]
        planned.append(
            {
                "topic_id": topic_id,
                "search_queries": _unique_texts(item.get("search_queries", []), 3) or base["search_queries"],
                "intent_queries": _unique_texts(item.get("intent_queries", []), 3) or base["intent_queries"],
            }
        )
    return {"topics": planned, "deepseek_used": True}


def fetch_url(url: str, timeout: int = 30, max_attempts: int = 5) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "daily-paper-token-pruning/1.0 (metadata only)",
        },
    )
    last_error: Exception | None = None
    for attempt in range(max_attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code != 429 and not 500 <= exc.code < 600:
                raise
            retry_after = exc.headers.get("Retry-After", "") if exc.headers else ""
            try:
                server_delay = float(retry_after)
            except ValueError:
                server_delay = 0.0
            delay = max(server_delay, min(30.0, 3.0 * (2**attempt)))
            print(
                f"arXiv API returned HTTP {exc.code}; retrying in {delay:g} seconds "
                f"({attempt + 1}/{max_attempts}).",
                flush=True,
            )
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            delay = min(30.0, 3.0 * (2**attempt))
            print(
                f"arXiv connection failed; retrying in {delay:g} seconds "
                f"({attempt + 1}/{max_attempts}).",
                flush=True,
            )
        if attempt + 1 < max_attempts:
            time.sleep(delay)
    assert last_error is not None
    raise last_error


def fetch_arxiv(
    days: int,
    max_results: int,
    target_date: str = "",
    search_expression: str = "",
    query_label: str = "",
) -> list[dict[str, Any]]:
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    date_filter = None
    if target_date:
        try:
            date_filter = dt.date.fromisoformat(target_date)
        except ValueError as exc:
            raise SystemExit(f"Invalid --date value {target_date!r}; expected YYYY-MM-DD.") from exc
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    papers: list[dict[str, Any]] = []
    seen: set[str] = set()
    start = 0
    page_size = 100 if date_filter else max_results
    scan_limit = max(max_results, 1000) if date_filter else max_results

    while start < scan_limit and len(papers) < max_results:
        page_number = start // page_size + 1
        label = f" [{query_label}]" if query_label else ""
        print(
            f"Scanning arXiv{label} page {page_number}: offset={start}, page_size={page_size}, matched={len(papers)}.",
            flush=True,
        )
        params = {
            "search_query": search_expression or arxiv_query(),
            "start": str(start),
            "max_results": str(page_size if date_filter else max_results),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        url = f"{ARXIV_API}?{urllib.parse.urlencode(params)}"
        raw = fetch_url(url)
        root = ET.fromstring(raw)
        entries = root.findall("atom:entry", ns)
        if not entries:
            print(f"arXiv page {page_number} returned no entries.", flush=True)
            break
        oldest_seen = None
        for entry in entries:
            parsed = parse_arxiv_entry(entry, ns, cutoff, date_filter)
            if parsed is None:
                published_raw = normalize_text(entry.findtext("atom:published", default="", namespaces=ns))
                try:
                    published_dt = dt.datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
                    oldest_seen = published_dt.date() if oldest_seen is None else min(oldest_seen, published_dt.date())
                except ValueError:
                    pass
                continue
            oldest_seen = (
                dt.date.fromisoformat(parsed["published"])
                if oldest_seen is None
                else min(oldest_seen, dt.date.fromisoformat(parsed["published"]))
            )
            if parsed["id"] in seen:
                continue
            seen.add(parsed["id"])
            papers.append(parsed)
            if len(papers) >= max_results:
                break
        print(
            f"arXiv page {page_number} returned {len(entries)} entries; "
            f"oldest={oldest_seen or 'unknown'}, matched={len(papers)}.",
            flush=True,
        )
        if not date_filter:
            break
        if len(papers) >= max_results:
            break
        if oldest_seen and oldest_seen < date_filter:
            break
        start += page_size
        time.sleep(3.0)
    return papers


def arxiv_expression_for_phrase(value: str) -> str:
    phrase = normalize_text(value).replace('"', "")[:180]
    if not phrase:
        return arxiv_query()
    return f'(ti:"{phrase}" OR abs:"{phrase}")'


def fuse_query_results(query_results: list[dict[str, Any]], rrf_k: int = 60) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    identity_index: dict[str, int] = {}
    scores: list[float] = []
    for result in query_results:
        topic_id = normalize_text(result.get("topic_id", ""))
        query = normalize_text(result.get("query", ""))
        for rank, paper in enumerate(result.get("papers", []), start=1):
            keys = paper_identity_keys(paper)
            record_index = next((identity_index[key] for key in keys if key in identity_index), None)
            if record_index is None:
                record_index = len(records)
                records.append(dict(paper))
                scores.append(0.0)
            record = records[record_index]
            for key in keys:
                identity_index[key] = record_index
            scores[record_index] += 1.0 / (rrf_k + rank)
            record["discovery_topics"] = list(
                dict.fromkeys(record.get("discovery_topics", []) + ([topic_id] if topic_id else []))
            )
            record["matched_queries"] = list(
                dict.fromkeys(record.get("matched_queries", []) + ([query] if query else []))
            )

    for index, paper in enumerate(records):
        paper["rrf_score"] = round(scores[index], 8)
    records.sort(key=lambda paper: (paper.get("rrf_score", 0), paper.get("published", "")), reverse=True)
    return records


def fetch_from_query_plan(
    plan: dict[str, Any], days: int, max_results: int, target_date: str = ""
) -> tuple[list[dict[str, Any]], int]:
    tasks = [
        (item.get("topic_id", ""), query)
        for item in plan.get("topics", [])
        for query in item.get("search_queries", [])[:3]
        if normalize_text(query)
    ]
    per_query_limit = max(10, min(50, max_results))
    query_results: list[dict[str, Any]] = []
    occurrences = 0
    for index, (topic_id, query) in enumerate(tasks, start=1):
        print(f"Retrieval query {index}/{len(tasks)}: {topic_id} | {query}", flush=True)
        papers = fetch_arxiv(
            days=days,
            max_results=per_query_limit,
            target_date=target_date,
            search_expression=arxiv_expression_for_phrase(query),
            query_label=f"{topic_id}:{index}",
        )
        occurrences += len(papers)
        query_results.append({"topic_id": topic_id, "query": query, "papers": papers})
        if index < len(tasks):
            time.sleep(3.0)
    fused = fuse_query_results(query_results)
    print(f"RRF fused {occurrences} query hits into {len(fused)} unique papers.", flush=True)
    return fused[:max_results], occurrences


def parse_arxiv_entry(
    entry: ET.Element,
    ns: dict[str, str],
    cutoff: dt.datetime,
    date_filter: dt.date | None,
) -> dict[str, Any] | None:
        source_id = normalize_text(entry.findtext("atom:id", default="", namespaces=ns))
        title = normalize_text(entry.findtext("atom:title", default="", namespaces=ns))
        abstract = normalize_text(entry.findtext("atom:summary", default="", namespaces=ns))
        published_raw = normalize_text(entry.findtext("atom:published", default="", namespaces=ns))
        updated_raw = normalize_text(entry.findtext("atom:updated", default="", namespaces=ns))
        try:
            published_dt = dt.datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
        except ValueError:
            published_dt = dt.datetime.now(dt.timezone.utc)
        if date_filter and published_dt.date() != date_filter:
            return None
        if published_dt < cutoff:
            return None
        authors = [
            normalize_text(author.findtext("atom:name", default="", namespaces=ns))
            for author in entry.findall("atom:author", ns)
        ]
        categories = [cat.attrib.get("term", "") for cat in entry.findall("atom:category", ns)]
        arxiv_id = source_id.rstrip("/").split("/")[-1]
        base_id = arxiv_base_id(arxiv_id)
        links = {
            "abstract": f"https://arxiv.org/abs/{arxiv_id}",
            "pdf": f"https://arxiv.org/pdf/{base_id}.pdf",
            "code": "",
        }
        return {
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
    vision_terms = ["vision", "visual", "image", "video", "multimodal"]
    if not topics and broad_score >= 3 and any(term in text for term in vision_terms):
        if "vision-token-pruning" in TOPICS:
            topics = ["vision-token-pruning"]
    relevance = min(100, max(0, broad_score * 8 + sum(topic_scores.values()) * 4))
    return topics[:4], relevance


def fallback_enrichment(paper: dict[str, Any]) -> dict[str, Any]:
    topics, relevance = score_and_topics(paper)
    discovery_topics = [topic_id for topic_id in paper.get("discovery_topics", []) if topic_id in TOPICS]
    topics = list(dict.fromkeys(topics + discovery_topics))
    if discovery_topics:
        relevance = max(relevance, 20)
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
        "abstract_zh": paper.get("abstract", ""),
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
            "discovery_topics": p.get("discovery_topics", []),
            "matched_queries": p.get("matched_queries", []),
        }
        for p in papers
    ]
    system = (
        "You are a research assistant maintaining a personalized academic paper tracker. "
        "Return strict JSON only. Do not include markdown."
    )
    user = {
        "task": "Classify and summarize papers for the configured research directions.",
        "topic_catalog": topic_catalog,
        "rules": [
            "Keep only topic ids from topic_catalog.",
            "relevance_score is an integer from 0 to 100.",
            "summary_zh is one concise Chinese sentence.",
            "abstract_zh is a faithful Chinese translation of the abstract, 1 to 3 concise paragraphs.",
            "why_relevant_zh is one concise Chinese sentence explaining relevance to the selected direction.",
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
                    "abstract_zh": "中文摘要翻译",
                    "why_relevant_zh": "中文相关性说明",
                }
            ]
        },
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def call_deepseek_json(
    messages: list[dict[str, str]], model: str, api_key: str | None = None, timeout: int = 90
) -> dict[str, Any]:
    key = api_key if api_key is not None else os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        raise ValueError("DeepSeek API key is not configured")
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        DEEPSEEK_API,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = json.loads(response.read().decode("utf-8"))
    content = body["choices"][0]["message"]["content"]
    return json.loads(content)


def call_deepseek(papers: list[dict[str, Any]], model: str) -> dict[str, dict[str, Any]]:
    if not papers:
        return {}
    parsed = call_deepseek_json(deepseek_prompt(papers), model=model)
    return {item["id"]: item for item in parsed.get("papers", []) if "id" in item}


def enrich_papers(papers: list[dict[str, Any]], model: str, batch_size: int = 8) -> list[dict[str, Any]]:
    enriched = [fallback_enrichment(p) for p in papers]
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("DeepSeek API key is not configured; using local fallback text.", flush=True)
        return enriched
    total_batches = (len(enriched) + batch_size - 1) // batch_size
    print(f"DeepSeek enabled. Enriching {len(enriched)} papers in {total_batches} batches.", flush=True)
    by_id = {p["id"]: p for p in enriched}
    for start in range(0, len(enriched), batch_size):
        batch = enriched[start : start + batch_size]
        batch_no = start // batch_size + 1
        print(f"DeepSeek batch {batch_no}/{total_batches}: {len(batch)} papers...", flush=True)
        try:
            result = call_deepseek(batch, model=model)
        except Exception as exc:  # Keep daily automation robust.
            print(f"DeepSeek batch failed: {exc}", file=sys.stderr)
            continue
        for paper_id, item in result.items():
            if paper_id not in by_id:
                continue
            topics = [t for t in item.get("topics", []) if t in TOPICS]
            resolved_topics = topics if "topics" in item else by_id[paper_id].get("topics", [])
            by_id[paper_id].update(
                {
                    "topics": resolved_topics,
                    "relevance_score": int(item.get("relevance_score", by_id[paper_id].get("relevance_score", 0))),
                    "summary_zh": normalize_text(item.get("summary_zh", by_id[paper_id].get("summary_zh", ""))),
                    "abstract_zh": normalize_text(item.get("abstract_zh", by_id[paper_id].get("abstract_zh", ""))),
                    "why_relevant_zh": normalize_text(
                        item.get("why_relevant_zh", by_id[paper_id].get("why_relevant_zh", ""))
                    ),
                    "deepseek_used": True,
                }
            )
        print(f"DeepSeek batch {batch_no}/{total_batches}: done.", flush=True)
        time.sleep(1)
    return list(by_id.values())


def read_store(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"last_updated": None, "papers": []}
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def paper_key(paper: dict[str, Any]) -> str:
    keys = paper_identity_keys(paper)
    return keys[0] if keys else f"unknown:{id(paper)}"


def merge_papers(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    merged = [dict(paper) for paper in existing]
    identity_index: dict[str, int] = {}
    for index, paper in enumerate(merged):
        for key in paper_identity_keys(paper):
            identity_index[key] = index
    added = 0
    updated = 0
    for paper in incoming:
        keys = paper_identity_keys(paper)
        existing_index = next((identity_index[key] for key in keys if key in identity_index), None)
        if existing_index is not None:
            current = merged[existing_index]
            manual_topics = list(dict.fromkeys(current.get("manual_topics", []) + paper.get("manual_topics", [])))
            current.update({k: v for k, v in paper.items() if v not in (None, "", [])})
            current["manual_topics"] = manual_topics
            current["topics"] = list(dict.fromkeys(current.get("topics", []) + manual_topics))
            for key in paper_identity_keys(current):
                identity_index[key] = existing_index
            updated += 1
        else:
            next_paper = dict(paper)
            next_paper["topics"] = list(
                dict.fromkeys(next_paper.get("topics", []) + next_paper.get("manual_topics", []))
            )
            merged.append(next_paper)
            next_index = len(merged) - 1
            for key in keys:
                identity_index[key] = next_index
            added += 1
    papers = merged
    papers.sort(key=lambda p: (p.get("published", ""), p.get("relevance_score", 0), p.get("title", "")), reverse=True)
    return papers, {"added": added, "updated": updated, "duplicates": updated, "total": len(papers)}


def build_payload(papers: list[dict[str, Any]]) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
    return {
        "last_updated": now,
        "topics": [
            {
                "id": topic_id,
                "name": topic["name"],
                "description": topic["description"],
                "keywords": topic.get("keywords", []),
            }
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


def write_status(status: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with STATUS_PATH.open("w", encoding="utf-8") as handle:
        json.dump(status, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def main() -> int:
    global TOPICS
    parser = argparse.ArgumentParser(description="Fetch daily token-pruning papers.")
    parser.add_argument("--days", type=int, default=int(os.environ.get("PAPER_LOOKBACK_DAYS", "3")))
    parser.add_argument("--max-results", type=int, default=int(os.environ.get("PAPER_MAX_RESULTS", "80")))
    parser.add_argument("--min-score", type=int, default=int(os.environ.get("PAPER_MIN_SCORE", "18")))
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"))
    parser.add_argument("--fresh", action="store_true", help="Ignore the existing store and rebuild from this run.")
    parser.add_argument("--topics-json", default=os.environ.get("PAPER_TOPICS_JSON", ""))
    parser.add_argument("--date", default=os.environ.get("PAPER_TARGET_DATE", ""), help="Only process one date, YYYY-MM-DD.")
    args = parser.parse_args()
    TOPICS = load_topics(args.topics_json)

    existing_store = {"papers": []} if args.fresh else read_store(DATA_PATH)
    effective_days = args.days
    if args.date:
        target = dt.date.fromisoformat(args.date)
        today = dt.datetime.now(dt.timezone.utc).date()
        effective_days = max(args.days, (today - target).days + 2)
    print(
        f"Starting fetch: days={effective_days}, target_date={args.date or 'latest window'}, "
        f"max_results={args.max_results}, min_score={args.min_score}, fresh={args.fresh}, topics={len(TOPICS)}.",
        flush=True,
    )
    query_plan = build_query_plan(TOPICS, model=args.model)
    for item in query_plan["topics"]:
        print(
            f"Generated queries [{item['topic_id']}]: " + " | ".join(item["search_queries"]),
            flush=True,
        )
    raw, retrieved_occurrences = fetch_from_query_plan(
        query_plan,
        days=effective_days,
        max_results=args.max_results,
        target_date=args.date,
    )
    print(f"Fetched unique arXiv candidates: {len(raw)}.", flush=True)
    prelim = [fallback_enrichment(p) for p in raw]
    candidates = [p for p in prelim if p.get("relevance_score", 0) >= args.min_score or p.get("topics")]
    print(f"Local filter candidates: {len(candidates)}.", flush=True)
    enriched = enrich_papers(candidates, model=args.model)
    if os.environ.get("DEEPSEEK_API_KEY"):
        kept = [p for p in enriched if p.get("relevance_score", 0) >= args.min_score and p.get("topics")]
    else:
        kept = [p for p in enriched if p.get("relevance_score", 0) >= args.min_score or p.get("topics")]
    print(f"Kept after enrichment: {len(kept)}.", flush=True)
    merged, merge_stats = merge_papers(existing_store.get("papers", []), kept)
    write_outputs(merged)
    status = {
        "last_run_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "lookback_days": args.days,
        "target_date": args.date,
        "max_results": args.max_results,
        "min_score": args.min_score,
        "raw_found": len(raw),
        "retrieved_occurrences": retrieved_occurrences,
        "candidates": len(candidates),
        "kept": len(kept),
        "added": merge_stats["added"],
        "updated": merge_stats["updated"],
        "duplicates": merge_stats["duplicates"],
        "total": merge_stats["total"],
        "query_plan": query_plan,
        "deepseek_enabled": bool(os.environ.get("DEEPSEEK_API_KEY")),
        "topics": [{"id": topic_id, **topic} for topic_id, topic in TOPICS.items()],
        "github_run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "github_server_url": os.environ.get("GITHUB_SERVER_URL", ""),
        "github_repository": os.environ.get("GITHUB_REPOSITORY", ""),
    }
    if status["github_run_id"] and status["github_server_url"] and status["github_repository"]:
        status["workflow_url"] = (
            f"{status['github_server_url']}/{status['github_repository']}/actions/runs/{status['github_run_id']}"
        )
    write_status(status)
    print(
        "Fetched {raw} arXiv papers, kept {kept}, added {added}, updated {updated}, total stored {total}.".format(
            raw=len(raw),
            kept=len(kept),
            added=merge_stats["added"],
            updated=merge_stats["updated"],
            total=merge_stats["total"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
