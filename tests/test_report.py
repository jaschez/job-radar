"""Daily and weekly e-mails, and marking after sending."""
import json

import pytest

import db
import report


@pytest.fixture
def con(tmp_path):
    c = db.connect(tmp_path / "t.db")
    for i, (fit, status) in enumerate([("High", "New"), ("Medium", "New"), ("Low", "New")]):
        c.execute("INSERT INTO leads (job_id, company, title, url, passes, status, first_seen) VALUES (?,?,?,?,1,?,?)",
                  (f"gh:a:{i}", "Acme", f"Engineer {i}", f"https://x/{i}", status, "2026-10-10"))
    return c


def evals(tmp_path, *fits):
    (tmp_path / "evals.json").write_text(json.dumps(
        [{"job_id": f"gh:a:{i}", "fit": f, "priority": "P1", "why_fits": "narrative A", "main_gaps": "Go",
          "summary": "Builds APIs", "comp_estimate": "90k", "comp_type": "Estimate", "notes": None}
         for i, f in enumerate(fits)]))


def test_daily_composes_only_with_a_fit_and_marks_after(cfg, con, tmp_path):
    evals(tmp_path, "High", "Medium", "Low")
    assert report.daily(con, cfg, tmp_path, "2026-10-10") == 0
    assert (tmp_path / "email_subject.txt").read_text() == "Job radar 2026-10-10: 2 relevant posting(s), 1 strong"
    assert "Engineer 2" not in (tmp_path / "email.html").read_text()
    assert con.execute("SELECT count(*) FROM leads WHERE status='Notified'").fetchone()[0] == 0
    report.mark(con, tmp_path, "2026-10-10")
    assert con.execute("SELECT count(*) FROM leads WHERE status='Notified'").fetchone()[0] == 2


def test_daily_without_a_fit_sends_nothing(cfg, con, tmp_path):
    evals(tmp_path, "Low")
    assert report.daily(con, cfg, tmp_path, "2026-10-10") == 3


def test_spanish_and_footer_links(cfg, con, tmp_path):
    evals(tmp_path, "High")
    cfg.update(language="es", links=[{"label": "Hoja", "url": "https://sheet"}])
    report.daily(con, cfg, tmp_path, "2026-10-10")
    assert (tmp_path / "email_subject.txt").read_text().startswith("Radar de empleo 2026-10-10: 1 oferta")
    assert "https://sheet" in (tmp_path / "email.html").read_text()


def test_weekly_includes_manual_check_and_reminder(cfg, con, tmp_path):
    evals(tmp_path, "High")
    (tmp_path / "manual_check.json").write_text(json.dumps(
        [{"company": "NoAPI", "title": "Backend", "url": "https://n", "fit": "High", "why": "fits"},
         {"company": "Down", "error": "timeout"}]))
    cfg["weekly_reminder"] = "Update the tracker"
    assert report.weekly(con, cfg, tmp_path, "2026-10-12") == 0
    html = (tmp_path / "weekly_email.html").read_text()
    assert "NoAPI" in html and "Down" in html and "Update the tracker" in html
