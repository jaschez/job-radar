"""The examples are documentation: they must keep working."""
from pathlib import Path

import yaml

import filters
import manual_check
import plugins
from sources import ats_boards

ROOT = Path(__file__).resolve().parents[1]


def test_example_workspace_is_complete():
    cfg = yaml.safe_load((ROOT / "examples/workspace/config.yaml").read_text())
    for key in ("language", "notify", "evaluation", "geography", "role_families", "exclusions", "sources"):
        assert key in cfg, key
    comps = yaml.safe_load((ROOT / "examples/workspace/companies.yaml").read_text())
    assert all(len(c["ats"]) == 2 for c in comps if c.get("ats"))
    assert filters.classify({"title": "Backend Engineer", "location": "Remote - Europe", "remote": True}, cfg)["passes"]


def test_example_source_plugin_follows_the_contract(cfg, monkeypatch):
    mod = plugins.load({"path": str(ROOT / "examples/plugins/example_source.py")}, "sources")

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            return {"jobs": [{"id": 1, "company": "Acme", "title": "Backend Engineer", "location": "Remote - Europe",
                              "remote": True, "url": "https://j/1", "description": "We build APIs"}]}

    monkeypatch.setattr(mod.requests, "get", lambda *a, **k: R())
    [b] = mod.fetch(cfg, conf={"url": "https://jobs.example.test"})
    assert b["key"] == "my_board" and b["jobs"][0]["id"] == "myboard:1" and b["jobs"][0]["company"] == "Acme"


def test_manual_targets_are_active_companies_without_ats(_workspace):
    (_workspace / "companies.yaml").write_text(
        "- {company: A, active: true, ats: [greenhouse, a]}\n"
        "- {company: B, active: true, careers: 'https://b'}\n"
        "- {company: C, active: false, careers: 'https://c'}\n")
    assert ats_boards.manual_targets({}, conf={}) == [{"company": "B", "careers": "https://b"}]
    assert manual_check.targets({"sources": {"ats_boards": {}}}) == [{"company": "B", "careers": "https://b"}]
