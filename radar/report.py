"""Store Claude's evaluations in the database and compose the e-mails.

Usage:
  python radar/report.py daily  [--date D] [--workspace W]  -> exit 0 if there is something to send, 3 if not
  python radar/report.py weekly [--date D] [--workspace W]  -> always composes (exit 0)
  python radar/report.py mark   [--date D] [--workspace W]  -> mark today's daily e-mail as sent

Marking comes AFTER sending: if the e-mail fails, today's postings stay pending.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import db  # noqa: E402
import i18n  # noqa: E402
import workspace  # noqa: E402

FIT_ORDER = {"High": 0, "Medium": 1, "Low": 2, "Reject": 3}


def esc(s):
    return html.escape(str(s or ""))


def ingest(con, out: Path, today: str) -> list[dict]:
    f = out / "evals.json"
    if not f.exists():
        return []
    try:
        evals = json.loads(f.read_text())
    except ValueError:
        print("evals.json unreadable: ignored")
        return []
    for e in evals:
        if not isinstance(e, dict) or not e.get("job_id"):
            continue
        con.execute(
            """UPDATE leads SET fit=?, priority=?, why_fits=?, main_gaps=?, summary=?, comp_estimate=?, comp_type=?,
               eval_notes=?, evaluated_at=?, status=CASE WHEN status='New' THEN 'Evaluated' ELSE status END
               WHERE job_id=?""",
            (e.get("fit"), e.get("priority"), e.get("why_fits"), e.get("main_gaps"), e.get("summary"),
             e.get("comp_estimate"), e.get("comp_type"), e.get("notes"), today, e["job_id"]))
    con.commit()
    return evals


def lead_rows(con, ids):
    if not ids:
        return []
    rows = [dict(r) for r in con.execute(f"SELECT * FROM leads WHERE job_id IN ({','.join('?' * len(ids))})", ids)]
    return sorted(rows, key=lambda r: (FIT_ORDER.get(r.get("fit"), 9), r.get("priority") or "P9", r["company"]))


def render_html(rows, t):
    parts = []
    for r in rows:
        parts.append(
            f"<li><b>[{esc(r['fit'])} · {esc(r['priority'])}] {esc(r['company'])} — "
            f"<a href='{esc(r['url'])}'>{esc(r['title'])}</a></b><br>"
            f"<span style='color:#555'>{esc(r['location'])[:120]}</span><br>"
            f"{esc(r['summary'])}<br><i>{t('why')}:</i> {esc(r['why_fits'])}<br>"
            f"<i>{t('gaps')}:</i> {esc(r['main_gaps'])}<br>"
            f"<i>{t('comp')}:</i> {esc(r['comp_estimate'])} ({esc(r['comp_type'])})"
            + (f"<br><i>{t('watch_out')}:</i> {esc(r['eval_notes'])}" if r.get("eval_notes") else "")
            + "</li>")
    return "<ul>" + "".join(parts) + "</ul>"


def render_text(rows, t):
    return "\n\n".join(
        f"[{r['fit']} · {r['priority']}] {r['company']} — {r['title']}\n  {r['url']}\n"
        f"  {r['summary']}\n  {t('why')}: {r['why_fits']}\n  {t('gaps')}: {r['main_gaps']}\n"
        f"  {t('comp')}: {r['comp_estimate']} ({r['comp_type']})" for r in rows)


def footer(cfg, t):
    links = " · ".join(f"<a href='{esc(l['url'])}'>{esc(l['label'])}</a>" for l in cfg.get("links") or [])
    return f"<hr><p style='color:#777;font-size:12px'>{esc(t('footer'))} {links}</p>"


def write_mail(out, cfg, t, subject, html_body, text_body, prefix=""):
    (out / f"{prefix}email_subject.txt").write_text(subject)
    (out / f"{prefix}email.html").write_text(
        f"<div style='font-family:sans-serif;font-size:14px'>{html_body}{footer(cfg, t)}</div>")
    links = "\n".join(f"{l['label']}: {l['url']}" for l in cfg.get("links") or [])
    (out / f"{prefix}email.txt").write_text(text_body + (f"\n\n{links}" if links else ""))


def daily(con, cfg, out, today):
    t = i18n.T(cfg)
    evals = ingest(con, out, today)
    stats = json.loads((out / "stats.json").read_text()) if (out / "stats.json").exists() else {}
    good_ids = [e["job_id"] for e in evals if e.get("fit") in ("High", "Medium")]
    rows = lead_rows(con, good_ids)
    closed = stats.get("closed_relevant", [])
    (out / "daily_ids.json").write_text(json.dumps(good_ids))
    if not rows and not closed:
        return 3       # fetch errors alone stay in the log; they do not deserve an e-mail
    n_high = sum(1 for r in rows if r["fit"] == "High")
    subject = t("daily.subject", day=today, n=len(rows)) + (t("daily.subject_high", n=n_high) if n_high else "")
    intro = t("daily.intro", boards=stats.get("boards_checked", "?"), new=stats.get("new_relevant_today", "?"),
              evaluated=len(evals), queue=max(stats.get("pending_evaluation_total", 0) - len(evals), 0))
    h, txt = [f"<p>{esc(intro)}</p>"], [intro]
    if rows:
        h.append(f"<h3>{esc(t('daily.matching'))}</h3>" + render_html(rows, t))
        txt.append(t("daily.matching").upper() + "\n\n" + render_text(rows, t))
    if closed:
        h.append(f"<h3>{esc(t('daily.closed'))}</h3><ul>" + "".join(
            f"<li>{esc(c['company'])} — {esc(c['title'])}</li>" for c in closed) + "</ul>")
        txt.append(t("daily.closed").upper() + "\n" + "\n".join(f"- {c['company']} — {c['title']}" for c in closed))
    if stats.get("fetch_errors"):
        h.append(f"<p style='color:#a00'>{esc(t('daily.no_data'))}: " + esc(", ".join(e[0] for e in stats["fetch_errors"])) + "</p>")
    write_mail(out, cfg, t, subject, "".join(h), "\n\n".join(txt))
    return 0


def weekly(con, cfg, out, today):
    t = i18n.T(cfg)
    ingest(con, out, today)
    week_ago = (dt.date.fromisoformat(today) - dt.timedelta(days=7)).isoformat()
    open_good = [dict(r) for r in con.execute(
        "SELECT * FROM leads WHERE fit IN ('High','Medium') AND status!='Closed' ORDER BY "
        "CASE fit WHEN 'High' THEN 0 ELSE 1 END, priority, company")]
    new_week = con.execute("SELECT count(*) FROM leads WHERE passes=1 AND first_seen>=?", (week_ago,)).fetchone()[0]
    closed_week = [dict(r) for r in con.execute(
        "SELECT company,title FROM leads WHERE status='Closed' AND closed_on>=? AND fit IN ('High','Medium')", (week_ago,))]
    queue = con.execute("SELECT count(*) FROM leads WHERE status='New'").fetchone()[0]
    by_company = con.execute(
        "SELECT company, count(*) n FROM leads WHERE fit IN ('High','Medium') AND status!='Closed' "
        "GROUP BY company ORDER BY n DESC LIMIT 8").fetchall()
    intro = t("weekly.intro", new=new_week, closed=len(closed_week), open=len(open_good), queue=queue)
    h, txt = [f"<p>{esc(intro)}</p>"], [intro]
    if by_company:
        h.append(f"<p><b>{esc(t('weekly.where'))}:</b> " + esc(", ".join(f"{r['company']} ({r['n']})" for r in by_company)) + "</p>")
    top = [r for r in open_good if r.get("priority") == "P1"][:10] or open_good[:10]
    if top:
        h.append(f"<h3>{esc(t('weekly.priority'))}</h3>" + render_html(top, t))
        txt.append(t("weekly.priority").upper() + "\n\n" + render_text(top, t))
    if closed_week:
        h.append(f"<h3>{esc(t('weekly.closed'))}</h3><ul>" + "".join(
            f"<li>{esc(c['company'])} — {esc(c['title'])}</li>" for c in closed_week) + "</ul>")
    mf = out / "manual_check.json"
    if mf.exists():
        try:
            man = json.loads(mf.read_text())
        except ValueError:
            man = []
        ok = [m for m in man if not m.get("error")]
        err = [m for m in man if m.get("error")]
        if ok:
            h.append(f"<h3>{esc(t('weekly.manual'))}</h3><ul>" + "".join(
                f"<li>[{esc(m.get('fit'))}] {esc(m.get('company'))} — <a href='{esc(m.get('url'))}'>{esc(m.get('title'))}</a> "
                f"({esc(m.get('location'))}). {esc(m.get('why'))}</li>" for m in ok) + "</ul>")
            txt.append(t("weekly.manual").upper() + "\n" + "\n".join(
                f"- [{m.get('fit')}] {m.get('company')} — {m.get('title')} {m.get('url')}" for m in ok))
        if err:
            h.append(f"<p style='color:#777'>{esc(t('weekly.manual_failed'))}: " + esc(", ".join(m.get("company", "?") for m in err)) + "</p>")
    if cfg.get("weekly_reminder"):
        h.append(f"<h3>{esc(t('weekly.reminder'))}</h3><p>{esc(cfg['weekly_reminder'])}</p>")
        txt.append(f"{t('weekly.reminder').upper()}\n{cfg['weekly_reminder']}")
    write_mail(out, cfg, t, t("weekly.subject", day=today), "".join(h), "\n\n".join(txt), prefix="weekly_")
    return 0


def mark(con, out, today):
    f = out / "daily_ids.json"
    ids = json.loads(f.read_text()) if f.exists() else []
    if ids:
        con.execute(f"UPDATE leads SET notified_at=?, status=CASE WHEN status='Evaluated' THEN 'Notified' ELSE status END "
                    f"WHERE job_id IN ({','.join('?' * len(ids))})", (today, *ids))
        con.commit()
    print(f"marked {len(ids)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["daily", "weekly", "mark"])
    ap.add_argument("--date")
    ap.add_argument("--workspace")
    a = ap.parse_args()
    workspace.use(a.workspace)
    cfg = workspace.load_config()
    today = a.date or workspace.today(cfg)
    out = workspace.out_dir(today)
    con = db.connect()
    sys.exit({"daily": daily, "weekly": weekly, "mark": mark}[a.mode](
        *((con, cfg, out, today) if a.mode != "mark" else (con, out, today))))


if __name__ == "__main__":
    main()
