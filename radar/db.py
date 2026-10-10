"""Local job store (SQLite). Rows are never deleted: a posting that disappears becomes
Closed, with a date.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import workspace

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
  job_id TEXT PRIMARY KEY,               -- "<provider>:<board>:<id>" for ATS boards
  company TEXT, title TEXT, location TEXT, family TEXT,
  geo TEXT, geo_reason TEXT, excluded TEXT, passes INTEGER,
  url TEXT, posted TEXT, comp TEXT, department TEXT,
  first_seen TEXT, last_checked TEXT, last_seen_open TEXT,
  status TEXT DEFAULT 'New',             -- New | Evaluated | Notified | Closed | Duplicate | Filtered
  closed_on TEXT, dup_of TEXT,
  prescore REAL,
  fit TEXT, priority TEXT, why_fits TEXT, main_gaps TEXT, summary TEXT,
  comp_estimate TEXT, comp_type TEXT, eval_notes TEXT, evaluated_at TEXT,
  notified_at TEXT
);
CREATE TABLE IF NOT EXISTS runs (
  run_date TEXT, company TEXT, ok INTEGER, n_jobs INTEGER, error TEXT
);
CREATE INDEX IF NOT EXISTS leads_company ON leads(company);
CREATE INDEX IF NOT EXISTS leads_status ON leads(status);
"""

# Columns added after the first schema version, applied idempotently to old databases.
ADDED_COLUMNS = [
    ("leads", "source", "TEXT"),     # the source that found it; NULL in old rows = ats_boards
    ("leads", "board", "TEXT"),      # the board it was read from; NULL in old rows = company
]


def connect(path: Path | None = None) -> sqlite3.Connection:
    p = Path(path) if path else workspace.data_dir() / "tracker.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p, timeout=60)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    for table, col, kind in ADDED_COLUMNS:
        have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        if col not in have:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")
    con.commit()
    return con
