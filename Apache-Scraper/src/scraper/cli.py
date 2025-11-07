"""Simple CLI to run scraper and transformer"""
import argparse
import os
import json
import yaml
from pathlib import Path

from .jira_client import JiraScraper
from .transform import transform_project_raw_to_jsonl
from .checkpoint import is_downloaded, mark_downloaded


def load_config(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def main():
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config.yaml")
    p.add_argument("--limit", type=int, default=None, help="Limit issues per project (overrides config)")
    p.add_argument("--transform-only", action="store_true")
    args = p.parse_args()

    cfg = load_config(args.config)
    projects = cfg.get("projects", [])
    page_size = cfg.get("page_size", 50)
    max_issues_cfg = cfg.get("max_issues_per_project")
    max_issues = args.limit if args.limit is not None else max_issues_cfg
    raw_dir_base = cfg.get("output_raw_dir", "output/raw")
    jsonl_base = cfg.get("output_jsonl_dir", "output/jsonl")

    scraper = JiraScraper(timeout=cfg.get("http_timeout_seconds", 30),
                         max_retries=cfg.get("max_retries", 5),
                         backoff_factor=cfg.get("backoff_factor", 2))

    if not args.transform_only:
        for project in projects:
            out_dir = os.path.join(raw_dir_base, project)
            print(f"Scraping project {project} -> {out_dir}")
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            count = 0
            try:
                # resume from last page if present
                last_start = 0
                try:
                    from .checkpoint import get_last_start

                    last_start = get_last_start(project)
                except Exception:
                    last_start = 0

                for issues, page_start, total in scraper.fetch_issue_pages_for_project(project, page_size=page_size, max_issues=max_issues, start_at=last_start):
                    for issue in issues:
                        key = issue.get("key")
                        if key and is_downloaded(project, key):
                            continue
                        scraper.save_raw_issue(issue, out_dir)
                        if key:
                            mark_downloaded(project, key)
                        count += 1
                    # after finishing the page, persist the page checkpoint
                    try:
                        from .checkpoint import set_last_start

                        set_last_start(project, page_start + len(issues))
                    except Exception:
                        pass
            except Exception as e:
                print(f"Error scraping {project}: {e}")
            print(f"Finished {project}, saved {count} issues")

    # Transform step
    for project in projects:
        in_dir = os.path.join(raw_dir_base, project)
        out_path = os.path.join(jsonl_base, f"{project}.jsonl")
        if not os.path.exists(in_dir):
            print(f"No raw data for {project}, skipping transform")
            continue
        print(f"Transforming {in_dir} -> {out_path}")
        transform_project_raw_to_jsonl(in_dir, out_path)
        print(f"Wrote JSONL: {out_path}")


if __name__ == '__main__':
    main()
