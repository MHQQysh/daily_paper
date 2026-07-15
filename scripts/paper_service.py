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
    from scripts import pdf_import
except ImportError:
    import fetch_papers as fp
    import pdf_import


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


def is_pdf_url_input(value: str) -> bool:
    text = (value or "").strip()
    parsed = urllib.parse.urlsplit(text)
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc) and not extract_arxiv_id(text)


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
        raise ValueError("Enter a PDF URL, arXiv link, arXiv ID, or a longer paper title.")
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
    if is_pdf_url_input(text):
        return [pdf_import.resolve_pdf_url(text)]

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


def _pdf_deepseek_prompt(document_text: str, topics: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    topic_catalog = [
        {
            "id": topic_id,
            "name": topic["name"],
            "description": topic.get("description", ""),
            "keywords": topic.get("keywords", []),
        }
        for topic_id, topic in topics.items()
    ]
    system = (
        "You extract structured academic-paper metadata from PDF text for a personalized paper tracker. "
        "Return strict JSON only. Do not include markdown. Do not invent unavailable metadata."
    )
    user = {
        "task": (
            "Read the extracted paper text. Recover the paper title, ordered authors, publication date when explicit, "
            "and the paper's own English abstract. Translate that abstract into Chinese, summarize the contribution, "
            "and classify it against the configured directions."
        ),
        "topic_catalog": topic_catalog,
        "rules": [
            "Keep only topic ids from topic_catalog.",
            "Use an empty published string when an exact date is unavailable.",
            "The abstract field must be the paper abstract in English, not a generated whole-paper summary.",
            "relevance_score is an integer from 0 to 100.",
            "summary_zh is one concise Chinese sentence.",
            "abstract_zh is a faithful Chinese translation of the English abstract.",
            "why_relevant_zh is one concise Chinese sentence explaining relevance.",
        ],
        "document_text": document_text,
        "output_schema": {
            "paper": {
                "title": "paper title",
                "authors": ["author name"],
                "published": "YYYY-MM-DD or empty",
                "abstract": "English abstract",
                "topics": ["topic-id"],
                "relevance_score": 0,
                "summary_zh": "中文一句话总结",
                "abstract_zh": "中文摘要翻译",
                "why_relevant_zh": "中文相关性说明",
            }
        },
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
    ]


def _normalize_pdf_analysis(
    item: dict[str, Any], candidate: dict[str, Any], topics: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    title = fp.normalize_text(item.get("title", ""))
    abstract = fp.normalize_text(item.get("abstract", ""))
    if not title or not abstract:
        raise ValueError("DeepSeek did not return a paper title and English abstract")
    raw_authors = item.get("authors", [])
    if isinstance(raw_authors, str):
        raw_authors = [raw_authors]
    if not isinstance(raw_authors, list):
        raw_authors = []
    authors = [fp.normalize_text(author) for author in raw_authors if fp.normalize_text(author)][:100]
    published = fp.normalize_text(item.get("published", ""))
    if published:
        try:
            dt.date.fromisoformat(published)
        except ValueError:
            published = ""
    try:
        relevance_score = max(0, min(100, int(item.get("relevance_score", 0))))
    except (TypeError, ValueError):
        relevance_score = 0
    raw_topics = item.get("topics", [])
    if not isinstance(raw_topics, list):
        raw_topics = []
    return {
        **{key: value for key, value in candidate.items() if key in PAPER_FIELDS},
        "title": title,
        "authors": authors,
        "published": published,
        "abstract": abstract,
        "topics": [topic_id for topic_id in raw_topics if topic_id in topics],
        "relevance_score": relevance_score,
        "summary_zh": fp.normalize_text(item.get("summary_zh", "")),
        "abstract_zh": fp.normalize_text(item.get("abstract_zh", "")),
        "why_relevant_zh": fp.normalize_text(item.get("why_relevant_zh", "")),
        "deepseek_used": True,
    }


def _analyze_pdf_paper(
    paper: dict[str, Any], topics: dict[str, dict[str, Any]], api_key: str, model: str
) -> dict[str, Any]:
    if not api_key:
        raise ValueError("A DeepSeek API key is required to read a PDF URL")
    token = fp.normalize_text(paper.get("import_token", ""))
    if not token:
        raise ValueError("PDF import token is missing; paste the URL again")
    cached = pdf_import.PDF_IMPORT_CACHE.get(token)
    parsed = fp.call_deepseek_json(_pdf_deepseek_prompt(cached["text"], topics), model=model, api_key=api_key)
    item = parsed.get("paper", {})
    if not item and parsed.get("papers"):
        item = parsed["papers"][0]
    if not isinstance(item, dict) or not item:
        raise ValueError("DeepSeek returned no PDF analysis")
    result = _normalize_pdf_analysis(item, cached["candidate"], topics)
    pdf_import.PDF_IMPORT_CACHE.discard(token)
    return result


def analyze_paper(
    paper: dict[str, Any], topics_payload: list[dict[str, Any]], api_key: str, model: str = "deepseek-chat"
) -> dict[str, Any]:
    topics = fp.normalize_topics_payload({"topics": topics_payload})
    fp.TOPICS = topics
    if isinstance(paper, dict) and paper.get("import_token"):
        return _analyze_pdf_paper(paper, topics, api_key, model)
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


def _backup_before_mutation(prefix: str) -> Path | None:
    sources = {
        "topics.json": fp.CONFIG_PATH,
        "data-papers.json": fp.DATA_PATH,
        "docs-papers.json": fp.DOCS_PATH,
        "run-status.json": fp.STATUS_PATH,
    }
    existing = {name: path for name, path in sources.items() if path.exists()}
    if not existing:
        return None
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_dir = ROOT / ".local_backups" / f"{prefix}-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)
    for name, source in existing.items():
        shutil.copy2(source, backup_dir / name)
    return backup_dir


def validate_topics_payload(topics_payload: Any) -> list[dict[str, Any]]:
    if not isinstance(topics_payload, list) or not 1 <= len(topics_payload) <= 100:
        raise ValueError("topics must contain between 1 and 100 directions")

    normalized: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    used_names: set[str] = set()
    for index, item in enumerate(topics_payload, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"direction {index} must be an object")
        topic_id = fp.normalize_text(item.get("id", "")).lower()
        name = fp.normalize_text(item.get("name", ""))
        description = fp.normalize_text(item.get("description", ""))
        raw_keywords = item.get("keywords", [])
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,119}", topic_id):
            raise ValueError(f"direction {index} has an invalid id")
        if topic_id in used_ids:
            raise ValueError("direction ids must be unique")
        if not name or len(name) > 120:
            raise ValueError(f"direction {index} name must contain 1 to 120 characters")
        name_key = name.casefold()
        if name_key in used_names:
            raise ValueError("direction names must be unique")
        if not isinstance(raw_keywords, list):
            raise ValueError(f"direction {index} keywords must be a list")
        keywords: list[str] = []
        seen_keywords: set[str] = set()
        for raw_keyword in raw_keywords:
            keyword = fp.normalize_text(raw_keyword)
            keyword_key = keyword.casefold()
            if not keyword or keyword_key in seen_keywords:
                continue
            if len(keyword) > 200:
                raise ValueError(f"direction {index} keyword is longer than 200 characters")
            seen_keywords.add(keyword_key)
            keywords.append(keyword)
        if not 1 <= len(keywords) <= 100:
            raise ValueError(f"direction {index} must contain between 1 and 100 keywords")
        if len(description) > 500:
            raise ValueError(f"direction {index} description is longer than 500 characters")
        normalized.append(
            {
                "id": topic_id,
                "name": name,
                "description": description or ", ".join(keywords[:5]),
                "keywords": keywords,
            }
        )
        used_ids.add(topic_id)
        used_names.add(name_key)
    return normalized


def load_topic_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": topic_id,
            "name": topic["name"],
            "description": topic.get("description", ""),
            "keywords": topic.get("keywords", []),
        }
        for topic_id, topic in fp.load_topics().items()
    ]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def save_topics(topics_payload: list[dict[str, Any]]) -> dict[str, Any]:
    topics = validate_topics_payload(topics_payload)
    _backup_before_mutation("before-topic-save")
    _write_json(fp.CONFIG_PATH, {"topics": topics})
    for path in (fp.DATA_PATH, fp.DOCS_PATH):
        if not path.exists():
            continue
        store = fp.read_store(path)
        store["topics"] = topics
        _write_json(path, store)
    fp.TOPICS = {
        item["id"]: {
            "name": item["name"],
            "description": item["description"],
            "keywords": item["keywords"],
        }
        for item in topics
    }
    return {"topics": topics, "count": len(topics)}


def add_paper(paper: dict[str, Any], selected_topics: list[str]) -> dict[str, Any]:
    fp.TOPICS = fp.load_topics()
    valid_topics = [topic_id for topic_id in selected_topics if topic_id in fp.TOPICS]
    if not valid_topics:
        raise ValueError("Select at least one direction")
    incoming = _sanitize_paper(paper)
    incoming["manual_topics"] = list(dict.fromkeys(incoming.get("manual_topics", []) + valid_topics))
    incoming["topics"] = list(dict.fromkeys(incoming.get("topics", []) + valid_topics))
    _backup_before_mutation("before-manual-add")
    existing = fp.read_store(fp.DATA_PATH).get("papers", [])
    merged, stats = fp.merge_papers(existing, [incoming])
    fp.write_outputs(merged)
    keys = set(fp.paper_identity_keys(incoming))
    stored = next((item for item in merged if keys.intersection(fp.paper_identity_keys(item))), incoming)
    return {"paper": stored, **stats}


def delete_paper(paper: dict[str, Any]) -> dict[str, Any]:
    target = _sanitize_paper(paper)
    target_keys = set(fp.paper_identity_keys(target))
    existing = fp.read_store(fp.DATA_PATH).get("papers", [])
    removed = [item for item in existing if target_keys.intersection(fp.paper_identity_keys(item))]
    if not removed:
        raise LookupError("Paper was not found in the current library")

    kept = [item for item in existing if not target_keys.intersection(fp.paper_identity_keys(item))]
    _backup_before_mutation("before-manual-delete")
    fp.write_outputs(kept)
    return {"paper": removed[0], "deleted": len(removed), "total": len(kept)}
