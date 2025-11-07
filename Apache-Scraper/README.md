# Apache Jira Scraper (final deliverable)

This repository implements a resilient, resumable pipeline that scrapes public issue data from Apache Jira and converts it into a JSONL corpus suitable for downstream processing or LLM training.

## Summary

- Scrapes public Apache Jira projects (default: `HADOOP`, `SPARK`, `KAFKA`).
- Stores raw per-issue JSON under `output/raw/<PROJECT>/<ISSUE>.json`.
- Produces a cleaned JSONL corpus `output/jsonl/<PROJECT>.jsonl` with metadata, plain-text description/comments, and derived fields (heuristic summary, keyword labels, QnA samples).
- Resumable: per-page and per-issue checkpointing prevents duplicate downloads and allows safe resume after interruption.

## What is included

- Complete scraper and transformer (Python).
- Robust retry/backoff handling for network failures, HTTP 429 and 5xx errors.
- Per-page checkpointing (`last_start`) and per-issue `downloaded_keys` recorded in `checkpoint.json`.
- ADF-aware HTML/plain-text extraction and heuristic-derived fields (no LLM calls).
- Unit tests and an integration-style resume test.

## Quick start (Windows PowerShell)

1) Create and activate a virtual environment, then install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2) Run a limited scrape (example):

```powershell
python run.py --config config.yaml --limit 10
```

3) Transform-only (if you already have raw files):

```powershell
python run.py --config config.yaml --transform-only
```

4) Tests (from repository root):

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m pytest -q
```

## Architecture & key files

- `run.py` — launcher that ensures `src` is importable and starts the CLI.
- `src/scraper/cli.py` — orchestrates scraping and transform; persists checkpoints.
- `src/scraper/jira_client.py` — Jira scraping client with robust retry/backoff and page fetching.
- `src/scraper/checkpoint.py` — read/write helpers for `checkpoint.json` (per-project `downloaded_keys` and `last_start`).
- `src/scraper/transform.py` — HTML/ADF → plain-text, heuristics (short summary, keyword labels, qna) and JSONL writer.
- `config.yaml` — projects and runtime settings (page_size, timeouts, output paths).

## JSONL schema (one object per line)

- `id`: Jira key (e.g., `HADOOP-1234`)
- `project`, `title`, `status`, `priority`, `assignee`, `reporter`, `labels`
- `created_at`, `updated_at`, `resolved_at`
- `description`: plain-text (ADF/HTML converted)
- `comments`: `[{author, created, body}]` where `body` is plain-text
- `derived`: `{ short_summary, keyword_labels, qna }`
- `raw_meta`: `{ raw_id }`

## Edge cases handled

1. Network failures and timeouts
   - `httpx.RequestError` and timeouts are treated as retryable; retries use exponential backoff + jitter. See `src/scraper/jira_client.py`.

2. HTTP 429 (rate limit)
   - Parses `Retry-After` (seconds or HTTP-date) where available; otherwise falls back to exponential backoff.

3. HTTP 5xx (server errors)
   - Retries with backoff; raises `JiraClientError` after configured retries.

4. Empty or malformed data
   - Raw files that fail JSON parsing are skipped and logged during transformation; `save_raw_issue()` is guarded against non-dict inputs and partial-write errors.

5. Atlassian Document Format (ADF)
   - ADF dicts are rendered to plain text via a recursive extractor to preserve content from structured fields.

6. Pagination inconsistencies & resume
   - Per-page `last_start` and per-issue `downloaded_keys` prevent duplicates and allow resume. See `src/scraper/checkpoint.py` and `src/scraper/cli.py`.

## Tests and validation

- Unit tests: `tests/test_jira_client.py` — covers 429 and 5xx retry behavior.
- Integration-style resume test: `tests/test_resume_integration.py` — verifies resume behavior after a simulated partial run.
- Run tests:

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m pytest -q
```

## Optimization decisions and notes

- Page-level checkpointing reduces rework on resume and is simple to persist (`checkpoint.json`).
- Per-issue file writes make resuming idempotent and easy to audit.
- Backoff + jitter reduces thundering herd issues against Apache Jira.
- For production-scale scraping consider: async HTTP with rate limiting, SQLite-based checkpointing, Parquet export for dataset storage.

## Delivery checklist and how to share

1. Final verification steps before sharing:
   - Run tests and a final smoke-scrape (limited): `python run.py --config config.yaml --limit 50`.
   - Confirm `output/jsonl/*.jsonl` contains expected objects.

2. Git push checklist:
   - Ensure large runtime artifacts are not committed (they are ignored via `.gitignore`).
   - Commit code and README changes.
   - Push to your GitHub repo and share the link with the requested accounts.

3. Accounts to share with (as requested in the assignment):
   - https://github.com/Naman-Bhalla/
   - https://github.com/raun/

Optional: create `DELIVERABLES.md` describing the run used to generate the dataset and any artifacts if you want me to prepare that file.

## Next steps (optional improvements)

- Replace `checkpoint.json` with SQLite for atomic, concurrent-safe checkpoints.
- Add async httpx + a concurrency limiter for higher throughput while respecting rate limits.
- Export to Parquet and add dataset validation.
- Add GitHub Actions workflow to run tests on push.

---

If you want, I can prepare a final `DELIVERABLES.md`, add a small GitHub Actions workflow, or run a final smoke-scrape and post a sample of the JSONL output for your review.

Thank you — the pipeline is ready for final packaging and delivery.
