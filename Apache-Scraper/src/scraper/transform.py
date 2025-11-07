import json
import os
import re
import logging
from typing import Dict, Any, List

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def html_to_text(html: str) -> str:
    if not html:
        return ""

    # If Jira returns a structured Atlassian Document Format (ADF) as a dict,
    # extract text nodes recursively instead of passing the dict to BeautifulSoup
    if isinstance(html, dict):
        return _adf_to_text(html)

    # If the value is not a string (e.g., list), convert to string safely
    if not isinstance(html, str):
        html = str(html)

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator="\n").strip()
    # normalize whitespace
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text


def _adf_to_text(node) -> str:
    """Recursively walk Atlassian Document Format (ADF) nodes and extract plain text.

    This is a best-effort extractor that concatenates 'text' fields and visits
    'content' children. It inserts newlines for block nodes like paragraphs and headings.
    """
    parts: List[str] = []

    def _walk(n):
        if n is None:
            return
        if isinstance(n, str):
            parts.append(n)
            return
        if isinstance(n, list):
            for c in n:
                _walk(c)
            return
        if isinstance(n, dict):
            # direct text node
            if 'text' in n and isinstance(n['text'], str):
                parts.append(n['text'])
                return
            # if node has content, recurse
            if 'content' in n:
                for c in n['content']:
                    _walk(c)
            # insert spacing for common block types
            node_type = n.get('type', '')
            if node_type in ('paragraph', 'heading', 'blockquote', 'codeBlock', 'panel'):
                parts.append('\n')
            return
        # fallback
        parts.append(str(n))

    _walk(node)
    text = ''.join(parts)
    # normalize whitespace and multiple newlines
    text = re.sub(r"\s+", ' ', text).strip()
    return text


KEYWORD_LABELS = {
    "performance": ["memory", "OOM", "latency", "throughput"],
    "security": ["vulnerability", "xss", "csrf", "exploit", "security"],
    "build": ["build", "maven", "gradle", "compile", "dependency"],
}


def infer_keyword_labels(text: str) -> List[str]:
    if not text:
        return []
    text_low = text.lower()
    labels = []
    for label, keywords in KEYWORD_LABELS.items():
        for kw in keywords:
            if kw.lower() in text_low:
                labels.append(label)
                break
    return labels


def extract_short_summary(text: str, max_chars: int = 200) -> str:
    if not text:
        return ""
    # simple extractive: first paragraph or first N chars
    paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    if paragraphs:
        first = paragraphs[0]
        if len(first) <= max_chars:
            return first
        return first[:max_chars].rsplit(" ", 1)[0] + "..."
    return text[:max_chars]


def derive_qna(title: str, description: str) -> List[Dict[str, str]]:
    # Very small heuristic: one Q from title, A = first paragraph of description
    qnas = []
    if title and description:
        paragraphs = [p.strip() for p in description.splitlines() if p.strip()]
        answer = paragraphs[0] if paragraphs else ""
        qnas.append({"q": title.strip(), "a": answer})
    return qnas


def transform_issue(raw: Dict[str, Any]) -> Dict[str, Any]:
    fields = raw.get("fields", {})
    description_html = fields.get("description") or ""
    description = html_to_text(description_html)
    comments = []
    comms = fields.get("comment", {}).get("comments", []) if fields.get("comment") else []
    for c in comms:
        comments.append({
            "author": c.get("author", {}).get("displayName"),
            "created": c.get("created"),
            "body": html_to_text(c.get("body", "")),
        })

    combined_text = "\n\n".join([description] + [c.get("body", "") for c in comments])

    transformed = {
        "id": raw.get("key"),
        "project": fields.get("project", {}).get("key"),
        "title": fields.get("summary"),
        "status": fields.get("status", {}).get("name"),
        "priority": fields.get("priority", {}).get("name") if fields.get("priority") else None,
        "assignee": fields.get("assignee", {}).get("displayName") if fields.get("assignee") else None,
        "reporter": fields.get("reporter", {}).get("displayName") if fields.get("reporter") else None,
        "labels": fields.get("labels", []),
        "created_at": fields.get("created"),
        "updated_at": fields.get("updated"),
        "resolved_at": fields.get("resolutiondate"),
        "description": description,
        "comments": comments,
        # derived
        "derived": {
            "short_summary": extract_short_summary(description),
            "keyword_labels": infer_keyword_labels(combined_text),
            "qna": derive_qna(fields.get("summary", ""), description),
        },
        # optional: include pointer to raw file path if present in raw
        "raw_meta": {"raw_id": raw.get("id")},
    }

    return transformed


def transform_project_raw_to_jsonl(raw_dir: str, out_jsonl_path: str):
    os.makedirs(os.path.dirname(out_jsonl_path), exist_ok=True)
    files = sorted([f for f in os.listdir(raw_dir) if f.endswith('.json')])
    with open(out_jsonl_path, 'w', encoding='utf-8') as out_f:
        for fn in files:
            path = os.path.join(raw_dir, fn)
            try:
                with open(path, 'r', encoding='utf-8') as r:
                    raw = json.load(r)
            except Exception as e:
                logger.warning(f"Skipping malformed raw file {path}: {e}")
                continue
            try:
                transformed = transform_issue(raw)
            except Exception as e:
                logger.warning(f"Error transforming {path}, skipping: {e}")
                continue
            out_f.write(json.dumps(transformed, ensure_ascii=False) + '\n')
