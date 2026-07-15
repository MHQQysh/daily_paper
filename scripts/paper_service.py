from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import re
import shutil
from typing import Any
import urllib.parse
import xml.etree.ElementTree as ET

try:
    from scripts import fetch_papers as fp
except ImportError:
    import fetch_papers as fp


ROOT = Path(__file__).resolve().parents[1]
ARXIV_ID_PATTERN = re.compile(
    r"(?i)(?:arxiv\s*:\s*)?((?:\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z-]+)?/\d{7})(?:v\d+)?)"
)
PAPER_FIELDS = {
    "id",
    "source",
    "source_id",
    "title",
    "authors",
    "published",
    "updated",
    "abstract",
    "categories",
    "links",
    "doi",
    "topics",
    "relevance_score",
    "summary_zh",
    "abstract_zh",
    "why_relevant_zh",
    "deepseek_used",
}


def extract_arxiv_id(value: str) -> str:
    match = ARXIV_ID_PATTERN.search(value or "")
    return match.group(1) if match else ""


def _parse_feed(raw: bytes) -> list[dict[str, Any]]:
    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
    root = ET.fromstring(raw)
    papers = []
    cutoff = dt.datetime(1900, 1, 1, tzinfo=dt.timezone.utc)
    for entry in root.findall("atom:entry", ns):
        paper = fp.parse_arxiv_entry(entry, ns, cutoff, None)
        if paper is None:
            continue
        doi = fp.normalize_text(entry.findtext("arxiv:doi", default="", namespaces=ns))
        if doi:
            paper["doi"] = doi
            paper.setdefault("links", {})["doi"] = f"https://doi.org/{doi}"
        papers.append(paper)
    return papers


def _fetch_arxiv(params: dict[str, str]) -> list[dict[str, Any]]:
    url = f"{fp.ARXIV_API}?{urllib.parse.urlencode(params)}"
    return _parse_feed(fp.fetch_url(url, timeout=20, max_attempts=2))


def resolve_paper_input(value: str, max_candidates: int = 5) -> list[dict[str, Any]]:
    text = fp.normalize_text(value)
    if len(text) < 3:
        raise ValueError("Enter an arXiv link, arXiv ID, or a longer paper title.")
    arxiv_id = extract_arxiv_id(text)
    if arxiv_id:
        base_id = fp.arxiv_base_id(arxiv_id).lower()
        local = fp.read_store(fp.DATA_PATH).get("papers", [])
        local_match = next(
            (
                paper
                for paper in local
                if fp.arxiv_base_id(fp.normalize_text(paper.get("source_id", ""))).lower() == base_id
            ),
            None,
        )
        if local_match:
            return [local_match]
        return _fetch_arxiv({"id_list": arxiv_id, "max_results": "1"})

    phrase = text.replace('"', "")[:300]
    phrase_key = fp.normalize_title(phrase)
    local_matches = [
        paper
        for paper in fp.read_store(fp.DATA_PATH).get("papers", [])
        if phrase_key and phrase_key in fp.normalize_title(paper.get("title", ""))
    ]
    if local_matches:
        local_matches.sort(key=lambda paper: paper.get("published", ""), reverse=True)
        return local_matches[:max_candidates]
    return _fetch_arxiv(
        {
            "search_query": f'ti:"{phrase}"',
            "start": "0",
            "max_results": str(max(1, min(max_candidates, 5))),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )


def analyze_paper(
    paper: dict[str, Any], topics_payload: list[dict[str, Any]], api_key: str, model: str = "deepseek-chat"
) -> dict[str, Any]:
    topics = fp.normalize_topics_payload({"topics": topics_payload})
    fp.TOPICS = topics
    fallback = fp.fallback_enrichment(_sanitize_paper(paper))
    if not api_key:
        fallback["analysis_warning"] = "DeepSeek API key is not configured; using English metadata."
        return fallback
    try:
        parsed = fp.call_deepseek_json(fp.deepseek_prompt([fallback]), model=model, api_key=api_key)
        item = next(
            (candidate for candidate in parsed.get("papers", []) if candidate.get("id") == fallback.get("id")),
            {},
        )
        if not item:
            raise ValueError("DeepSeek returned no analysis for this paper")
        recommended = [topic_id for topic_id in item.get("topics", []) if topic_id in topics]
        fallback.update(
            {
                "topics": recommended,
                "relevance_score": int(item.get("relevance_score", fallback.get("relevance_score", 0))),
                "summary_zh": fp.normalize_text(item.get("summary_zh", fallback.get("summary_zh", ""))),
                "abstract_zh": fp.normalize_text(item.get("abstract_zh", fallback.get("abstract_zh", ""))),
                "why_relevant_zh": fp.normalize_text(
                    item.get("why_relevant_zh", fallback.get("why_relevant_zh", ""))
                ),
                "deepseek_used": True,
            }
        )
    except Exception as exc:
        fallback["analysis_warning"] = f"DeepSeek analysis failed: {exc}"
    return fallback


def _sanitize_paper(paper: Any) -> dict[str, Any]:
    if not isinstance(paper, dict):
        raise ValueError("paper must be an object")
    sanitized = {key: value for key, value in paper.items() if key in PAPER_FIELDS}
    sanitized["title"] = fp.normalize_text(sanitized.get("title", ""))
    if not sanitized["title"]:
        raise ValueError("paper title is required")
    sanitized["source"] = fp.normalize_text(sanitized.get("source", "arXiv")) or "arXiv"
    sanitized["source_id"] = fp.normalize_text(sanitized.get("source_id", ""))
    sanitized["id"] = fp.normalize_text(sanitized.get("id", "")) or f"manual-{fp.slugify(sanitized['title'])}"
    return sanitized


def _backup_before_add() -> Path | None:
    sources = {
        "data-papers.json": fp.DATA_PATH,
        "docs-papers.json": fp.DOCS_PATH,
        "run-status.json": fp.STATUS_PATH,
    }
    existing = {name: path for name, path in sources.items() if path.exists()}
    if not existing:
        return None
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_dir = ROOT / ".local_backups" / f"before-manual-add-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    for name, source in existing.items():
        shutil.copy2(source, backup_dir / name)
    return backup_dir


def add_paper(paper: dict[str, Any], selected_topics: list[str]) -> dict[str, Any]:
    fp.TOPICS = fp.load_topics()
    valid_topics = [topic_id for topic_id in selected_topics if topic_id in fp.TOPICS]
    if not valid_topics:
        raise ValueError("Select at least one direction")
    incoming = _sanitize_paper(paper)
    incoming["manual_topics"] = list(dict.fromkeys(incoming.get("manual_topics", []) + valid_topics))
    incoming["topics"] = list(dict.fromkeys(incoming.get("topics", []) + valid_topics))
    _backup_before_add()
    existing = fp.read_store(fp.DATA_PATH).get("papers", [])
    merged, stats = fp.merge_papers(existing, [incoming])
    fp.write_outputs(merged)
    keys = set(fp.paper_identity_keys(incoming))
    stored = next((item for item in merged if keys.intersection(fp.paper_identity_keys(item))), incoming)
    return {"paper": stored, **stats}
