"""Built-in source: the public job boards of a list of target companies.

Config:
    sources:
      ats_boards:
        companies_file: companies.yaml     # in the workspace
        workers: 12                        # boards read in parallel
        providers: {}                      # extra ATS providers (see providers.py)

companies.yaml is a list of companies. Fields the radar uses:
    company: Grafana Labs
    active: true                 # only active companies are read and evaluated
    ats: [greenhouse, grafanalabs]   # [provider, board slug]; omit for "check by hand"
    tier: A                      # A-D, raises or lowers the pre-score
    careers: https://...         # for the weekly manual check of companies without ATS
    comp, hiring_notes           # passed to the evaluator as context
Any other fields are yours (notes, categories...) and are ignored by the code.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import yaml

import workspace
from sources import providers

META = ("tier", "comp", "hiring_notes", "careers")


def companies(conf: dict) -> list[dict]:
    p = workspace.file(conf.get("companies_file", "companies.yaml"))
    if not p.exists():
        return []
    return yaml.safe_load(p.read_text(encoding="utf-8")) or []


def _read(c: dict, extra: dict):
    provider, slug = c["ats"]
    last = None
    for attempt in range(3):      # retries: one hiccup must not close every posting
        try:
            return providers.fetch(provider, slug, extra=extra), None
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"[:300]
            time.sleep(10 * (attempt + 1))
    return None, last


def fetch(cfg: dict, *, conf: dict, con=None, **_) -> list[dict]:
    providers.set_contact(cfg.get("user_agent_contact"))
    targets = [c for c in companies(conf) if c.get("active") and c.get("ats")]
    extra = conf.get("providers") or {}
    with ThreadPoolExecutor(int(conf.get("workers", 12))) as ex:
        results = list(ex.map(lambda c: _read(c, extra), targets))
    return [{"key": c["company"], "company": c["company"], "jobs": jobs, "error": err,
             "meta": {k: c.get(k) for k in META}}
            for c, (jobs, err) in zip(targets, results)]


def describe(lead: dict, *, conf: dict) -> str:
    return providers.describe(lead["job_id"], conf.get("providers"))


def manual_targets(cfg: dict, *, conf: dict) -> list[dict]:
    return [{"company": c["company"], "careers": c.get("careers")}
            for c in companies(conf) if c.get("active") and not c.get("ats") and c.get("careers")]
