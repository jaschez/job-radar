"""The daily sweep: inserts, duplicates, closures, reopening and today's batch."""
import pytest

import db
import run
import sources


@pytest.fixture
def con(tmp_path):
    return db.connect(tmp_path / "t.db")


def jb(i, title="Backend Engineer", location="Remote - Europe", **kw):
    return {"id": f"gh:acme:{i}", "title": title, "location": location, "raw_locations": [location],
            "remote": True, "url": f"https://x/{i}", "posted": "2026-10-01", "department": "", "comp": "", **kw}


def board(jobs, key="Acme", tier="A", error=None):
    return {"key": key, "company": key, "jobs": jobs, "error": error, "meta": {"tier": tier, "comp": "90k"}}


def fake_source(monkeypatch, *boards_by_call):
    calls = list(boards_by_call)

    class Mod:
        @staticmethod
        def fetch(cfg, *, conf, con=None):
            return calls.pop(0)

        @staticmethod
        def describe(lead, *, conf):
            return "full description of " + lead["title"]

    monkeypatch.setattr(sources, "load", lambda name, cfg: Mod)


def status(con, jid):
    return con.execute("SELECT status FROM leads WHERE job_id=?", (jid,)).fetchone()["status"]


def test_new_filtered_and_duplicate(cfg, con, monkeypatch):
    fake_source(monkeypatch, [board([jb(1), jb(2, title="Backend Engineer - Spain"), jb(3, title="Account Executive")])])
    boards, new_ids, closed, errors = run.sweep(con, cfg, "2026-10-10", ["ats_boards"])
    assert new_ids == ["gh:acme:1"]
    assert status(con, "gh:acme:2") == "Duplicate" and status(con, "gh:acme:3") == "Filtered"
    r = con.execute("SELECT source, board FROM leads WHERE job_id='gh:acme:1'").fetchone()
    assert (r["source"], r["board"]) == ("ats_boards", "Acme")


def test_close_only_when_the_board_was_read(cfg, con, monkeypatch):
    fake_source(monkeypatch, [board([jb(1)])], [board(None, error="timeout")], [board([])])
    run.sweep(con, cfg, "2026-10-10", ["ats_boards"])
    run.sweep(con, cfg, "2026-10-11", ["ats_boards"])
    assert status(con, "gh:acme:1") == "New"                 # a failed read closes nothing
    _, _, closed, _ = run.sweep(con, cfg, "2026-10-12", ["ats_boards"])
    assert closed == ["gh:acme:1"] and status(con, "gh:acme:1") == "Closed"


def test_reopens_when_it_comes_back(cfg, con, monkeypatch):
    fake_source(monkeypatch, [board([jb(1)])], [board([])], [board([jb(1)])])
    for day in ("2026-10-10", "2026-10-11", "2026-10-12"):
        run.sweep(con, cfg, day, ["ats_boards"])
    assert status(con, "gh:acme:1") == "New"


def test_old_rows_without_source_or_board_still_close(cfg, con, monkeypatch):
    con.execute("INSERT INTO leads (job_id, company, title, passes, status) VALUES ('gh:acme:old', 'Acme', 'x', 1, 'New')")
    fake_source(monkeypatch, [board([jb(1)])])
    _, _, closed, _ = run.sweep(con, cfg, "2026-10-10", ["ats_boards"])
    assert closed == ["gh:acme:old"]


def test_config_change_reclassifies_unevaluated(cfg, con, monkeypatch):
    fake_source(monkeypatch, [board([jb(1, title="Frontend Developer")])], [board([jb(1, title="Frontend Developer")])])
    run.sweep(con, cfg, "2026-10-10", ["ats_boards"])
    assert status(con, "gh:acme:1") == "Filtered"
    cfg["role_families"][2]["active"] = True
    run.sweep(con, cfg, "2026-10-11", ["ats_boards"])
    assert status(con, "gh:acme:1") == "New"


def test_pick_orders_by_prescore_and_skips_unconfigured_boards(cfg, con, monkeypatch):
    fake_source(monkeypatch, [board([jb(1, title="Junior Backend Engineer")], key="Low", tier="D"),
                              board([jb(2)], key="High", tier="A")])
    boards, *_ = run.sweep(con, cfg, "2026-10-10", ["ats_boards"])
    con.execute("INSERT INTO leads (job_id, company, title, passes, status, prescore) "
                "VALUES ('gh:gone:1', 'Gone', 'x', 1, 'New', 99)")       # company no longer configured
    batch, n_pending = run.pick(con, cfg, "2026-10-10", boards, 5)
    assert [b["job_id"] for b in batch] == ["gh:acme:2", "gh:acme:1"]
    assert batch[0]["company_tier"] == "A" and batch[0]["description"] == "full description of Backend Engineer"
    assert n_pending == 2


def test_cooldown_note_reaches_the_evaluator(cfg, con, monkeypatch):
    cfg["cooldowns"] = [{"company": "Acme", "until": "2026-12-24", "note": "rejected in June"}]
    fake_source(monkeypatch, [board([jb(1)])])
    boards, *_ = run.sweep(con, cfg, "2026-10-10", ["ats_boards"])
    assert run.pick(con, cfg, "2026-10-10", boards, 5)[0][0]["cooldown"] == "rejected in June"


def test_a_broken_source_does_not_stop_the_sweep(cfg, con, monkeypatch):
    def load(name, cfg):
        raise ImportError("bad plugin")
    monkeypatch.setattr(sources, "load", load)
    boards, new_ids, closed, errors = run.sweep(con, cfg, "2026-10-10", ["broken"])
    assert errors and errors[0][0] == "broken"
