"""Simple checkpoint manager to track downloaded issue keys per project.

This writes a small JSON file `checkpoint.json` at the repo root by default.
"""
import json
import threading
from pathlib import Path
from typing import Dict, Any

_LOCK = threading.Lock()


def load_checkpoint(path: str = "checkpoint.json") -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"projects": {}}
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"projects": {}}


def save_checkpoint(data: Dict[str, Any], path: str = "checkpoint.json") -> None:
    p = Path(path)
    with _LOCK:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_downloaded(project: str, issue_key: str, path: str = "checkpoint.json") -> bool:
    data = load_checkpoint(path)
    proj = data.get("projects", {}).get(project, {})
    keys = proj.get("downloaded_keys", [])
    return issue_key in keys


def mark_downloaded(project: str, issue_key: str, path: str = "checkpoint.json") -> None:
    data = load_checkpoint(path)
    projects = data.setdefault("projects", {})
    proj = projects.setdefault(project, {})
    keys = proj.setdefault("downloaded_keys", [])
    if issue_key not in keys:
        keys.append(issue_key)
    save_checkpoint(data, path)


def get_last_start(project: str, path: str = "checkpoint.json") -> int:
    """Return last startAt (page offset) for project, default 0."""
    data = load_checkpoint(path)
    proj = data.get("projects", {}).get(project, {})
    return int(proj.get("last_start", 0))


def set_last_start(project: str, start_at: int, path: str = "checkpoint.json") -> None:
    data = load_checkpoint(path)
    projects = data.setdefault("projects", {})
    proj = projects.setdefault(project, {})
    proj["last_start"] = int(start_at)
    save_checkpoint(data, path)
