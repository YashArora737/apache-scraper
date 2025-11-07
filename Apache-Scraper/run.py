"""Launcher to make the `src` package importable when running from the repo root.

Usage:
  python run.py --config config.yaml --limit 3

This inserts `src` on sys.path then calls the CLI entrypoint.
"""
import os
import sys

ROOT = os.path.dirname(__file__)
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from scraper import cli


if __name__ == '__main__':
    cli.main()
