"""Job sources: built-in modules and workspace plugins, chosen in the config.

    sources:
      ats_boards: {companies_file: companies.yaml}     # built-in: public ATS job boards
      my_board: {path: plugins/my_board.py, ...}       # your own, in the workspace
      other: {module: some_package.board}              # or any importable module

Job markets differ by country and by trade: the built-in source reads the public APIs of
applicant tracking systems (Greenhouse, Lever, Ashby, Workable, SmartRecruiters,
Recruitee, Personio) for a list of target companies. Job boards, aggregators or national
employment services are plugins; nothing else in the radar knows about any of them.

Contract for a source module:

    def fetch(cfg, *, conf, con=None) -> list[dict]
        Returns BOARDS. A board is one place that was read in full:
          {"key": "Grafana Labs",          # unique within the source; closures are per board
           "company": "Grafana Labs",      # default company for its jobs (None for aggregators)
           "jobs": [...] | None,           # None when the read failed
           "error": None | "message",
           "meta": {"tier": "A", "comp": "...", "hiring_notes": "...", "careers": "..."}}
        A job dict: id (unique across sources, e.g. "myboard:123"), title, location,
        raw_locations (list), remote (bool), url, posted (YYYY-MM-DD), department, comp,
        and optionally company and description.

    def describe(lead, *, conf) -> str        # optional: full description for the evaluation

    def manual_targets(cfg, *, conf) -> list[dict]   # optional: {company, careers} entries
                                                      # to check by hand (weekly manual check)

A posting that disappears from a board that was read successfully becomes Closed; a
board whose read failed closes nothing.
"""
from __future__ import annotations

import plugins


def configured(cfg: dict) -> dict:
    return cfg.get("sources") or {"ats_boards": {}}


def enabled(cfg: dict) -> list[str]:
    return [name for name, conf in configured(cfg).items() if (conf or {}).get("enabled", True)]


def load(name: str, cfg: dict):
    conf = configured(cfg).get(name) or {}
    if conf.get("path") or conf.get("module"):
        return plugins.load(conf, "sources")
    return plugins.load(name, "sources")
