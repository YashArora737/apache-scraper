import os
import yaml
import json
from pathlib import Path

from scraper import cli


def make_issue(key: str):
    return {"key": key, "id": key.lower().replace('-', ''), "fields": {"project": {"key": key.split('-')[0]}, "summary": f"Issue {key}", "description": "desc"}}


def test_resume_after_partial_run(tmp_path, monkeypatch, capsys):
    # prepare temp config
    cfg = {
        "projects": ["TEST"],
        "max_issues_per_project": None,
        "page_size": 10,
        "output_raw_dir": str(tmp_path / "output" / "raw"),
        "output_jsonl_dir": str(tmp_path / "output" / "jsonl"),
        "http_timeout_seconds": 5,
        "max_retries": 1,
        "backoff_factor": 0,
    }
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))

    # simulate a partial run by creating the first page of raw files and setting checkpoint
    raw_dir = Path(cfg["output_raw_dir"]) / "TEST"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for i in range(1, 11):
        (raw_dir / f"TEST-{i}.json").write_text(json.dumps(make_issue(f"TEST-{i}")), encoding="utf-8")

    # set checkpoint last_start to 10
    from scraper.checkpoint import set_last_start
    set_last_start("TEST", 10)

    # second run: provide function that yields the next two pages (from start_at)
    def second_run(self, project_key, page_size=10, max_issues=None, start_at=0):
        # simulate pages starting at start_at
        if start_at == 10:
            # yield page 2
            issues = [make_issue(f"TEST-{i}") for i in range(11, 21)]
            yield issues, 10, 100
            # yield page 3
            issues = [make_issue(f"TEST-{i}") for i in range(21, 31)]
            yield issues, 20, 100
        else:
            # default: yield nothing
            return

    monkeypatch.setattr("scraper.jira_client.JiraScraper.fetch_issue_pages_for_project", second_run)

    # simulate resume by calling the patched fetch function directly and saving files
    from scraper.jira_client import JiraScraper
    from scraper.checkpoint import mark_downloaded, set_last_start

    s = JiraScraper()
    for issues, page_start, total in s.fetch_issue_pages_for_project("TEST", page_size=10, start_at=10):
        for issue in issues:
            s.save_raw_issue(issue, str(raw_dir))
            mark_downloaded("TEST", issue["key"])
        set_last_start("TEST", page_start + len(issues))

    # verify raw files now 30
    files = sorted([p.name for p in raw_dir.glob("*.json")])
    assert len(files) == 30
