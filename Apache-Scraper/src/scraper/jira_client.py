import json
import os
import time
import random
import datetime
from email.utils import parsedate_to_datetime
from typing import Dict, Any, Optional, List, Tuple

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

JIRA_API_BASE = "https://issues.apache.org/jira/rest/api/2"


class JiraClientError(Exception):
    pass


class JiraScraper:
    """Simple resilient Jira scraper using httpx.

    Features:
    - pagination with startAt/maxResults
    - basic retry/backoff for 429/5xx
    - checkpointing is handled externally by storing raw files and returning issue keys
    """

    def __init__(self, timeout: int = 30, max_retries: int = 5, backoff_factor: int = 2):
        self.client = httpx.Client(timeout=timeout)
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def _request(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Request with improved retry/backoff and jitter.

        Handles:
        - HTTP 429 (respect Retry-After numeric or HTTP-date if present)
        - 5xx with exponential backoff + jitter
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = self.client.get(url, params=params)
            except httpx.RequestError as e:
                # network-level error, treat as retryable
                resp = None
                wait_seconds = min(self.backoff_factor ** attempt, 60)
                jitter = random.uniform(0, 1 + 0.1 * attempt)
                time.sleep(wait_seconds + jitter)
                if attempt >= self.max_retries:
                    raise JiraClientError(f"Network error: {e}")
                continue
            if resp is not None and resp.status_code == 200:
                try:
                    return resp.json()
                except Exception as e:
                    raise JiraClientError(f"Invalid JSON response: {e}")

            # Determine wait time
            wait_seconds = None
            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    # Retry-After can be seconds or an HTTP-date
                    if retry_after.isdigit():
                        wait_seconds = int(retry_after)
                    else:
                        try:
                            dt = parsedate_to_datetime(retry_after)
                            wait_seconds = max(0, (dt - datetime.datetime.now(dt.tzinfo)).total_seconds())
                        except Exception:
                            wait_seconds = None
                if wait_seconds is None:
                    wait_seconds = min(self.backoff_factor ** attempt, 60)
            elif 500 <= resp.status_code < 600:
                wait_seconds = min(self.backoff_factor ** attempt, 60)
            else:
                # if resp is None (we handled network error above) or a non-200 status
                if resp is None:
                    raise JiraClientError("No response received")
                raise JiraClientError(f"HTTP {resp.status_code}: {resp.text}")

            # apply jitter
            jitter = random.uniform(0, 1 + 0.1 * attempt)
            sleep_for = wait_seconds + jitter
            time.sleep(sleep_for)

            if attempt >= self.max_retries:
                raise JiraClientError(f"Max retries exceeded for {url}")

    def fetch_issues_for_project(self, project_key: str, page_size: int = 50, max_issues: Optional[int] = None):
        """Yield issue JSON objects for a project using JQL pagination.

        This uses the search endpoint with JQL `project = {project_key}`.
        """
        url = f"{JIRA_API_BASE}/search"
        start_at = 0
        total = None
        fetched = 0

        while True:
            params = {
                "jql": f"project = {project_key} ORDER BY created DESC",
                "startAt": start_at,
                "maxResults": page_size,
                "fields": "*all",
            }

            data = self._request(url, params=params)
            issues = data.get("issues", [])
            total = data.get("total", total)

            if not issues:
                break

            for issue in issues:
                yield issue
                fetched += 1
                if max_issues and fetched >= max_issues:
                    return

            start_at += len(issues)
            if total is not None and start_at >= total:
                break

    def fetch_issue_pages_for_project(self, project_key: str, page_size: int = 50, max_issues: Optional[int] = None,
                                      start_at: int = 0):
        """Yield pages of issues as (issues_list, start_at, total).

        This lets callers persist page-level checkpoints and resume from a given start_at.
        """
        url = f"{JIRA_API_BASE}/search"
        total = None
        fetched = 0
        current = start_at

        while True:
            params = {
                "jql": f"project = {project_key} ORDER BY created DESC",
                "startAt": current,
                "maxResults": page_size,
                "fields": "*all",
            }

            data = self._request(url, params=params)
            issues = data.get("issues", [])
            total = data.get("total", total)

            if not issues:
                break

            # yield the page
            yield issues, current, total

            fetched += len(issues)
            if max_issues and fetched >= max_issues:
                return

            current += len(issues)
            if total is not None and current >= total:
                break

    @staticmethod
    def save_raw_issue(issue: Dict[str, Any], out_dir: str):
        if not isinstance(issue, dict):
            return
        key = issue.get("key")
        if not key:
            return
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, f"{key}.json")
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(issue, f, ensure_ascii=False, indent=2)
        except Exception:
            # if writing fails, remove partial file if created
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
