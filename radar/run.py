"""Daily sweep: download, filter, de-duplicate, close what disappeared and prepare what
Claude evaluates today. No LLM.

Usage: python radar/run.py [--workspace DIR] [--date YYYY-MM-DD] [--max-eval N] [--sources a,b]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import db  # noqa: E402
import filters  # noqa: E402
import sources  # noqa: E402
import workspace  # noqa: E402

TIER_SCORE = {"A": 3, "B": 2, "C": 1, "D": 1}
DEFAULT_SOURCE = "ats_boards"      # what old rows without a `source` came from


def find_dup(con, company, job):
    """Another open posting at the same company with the same title minus geography
    (the same role, posted once per country)."""
    key = filters.title_key(job["title"])
    for r in con.execute("SELECT job_id, title FROM leads WHERE company=? AND passes=1 "
                         "AND status NOT IN ('Closed','Duplicate','Filtered') AND job_id!=?", (company, job["id"])):
        if filters.title_key(r["title"]) == key:
            return r
    return None


def prescore(job, meta, cfg):
    fam_prio = {f["name"]: f.get("priority", 3) for f in cfg.get("role_families") or []}
    s = TIER_SCORE.get((meta or {}).get("tier") or "C", 1)
    s += {1: 2, 2: 1}.get(fam_prio.get(job["family"], 3), 0)
    t = filters.norm(job["title"])
    if any(w in t for w in (cfg.get("prescore") or {}).get("penalized_title_words", ["junior", "entry"])):
        s -= 2
    if job.get("geo_reason", "").startswith("accepted city"):
        s += 1
    if job.get("geo") == "relocate":
        s -= 1      # relocation only pays off with a better fit or salary
    return s


def ingest_board(con, cfg, today, source, board, new_ids, closed):
    """Store one board's jobs; close what it no longer lists."""
    seen = set()
    rank = {"ok": 0, "relocate": 1, "pending": 2, "no": 3}
    classified = sorted((filters.classify(raw, cfg) for raw in board["jobs"]), key=lambda j: rank.get(j["geo"], 9))
    for j in classified:
        company = j.get("company") or board["company"] or ""
        seen.add(j["id"])
        row = con.execute("SELECT * FROM leads WHERE job_id=?", (j["id"],)).fetchone()
        now_passes = filters.passes_cfg(j, cfg)
        score = prescore(j, board.get("meta"), cfg)
        if row:
            upd = {"last_checked": today, "last_seen_open": today, "title": j["title"], "location": j["location"],
                   "comp": j.get("comp") or row["comp"], "geo": j["geo"], "geo_reason": j["geo_reason"],
                   "family": j["family"], "excluded": j["excluded"], "passes": int(now_passes),
                   "source": source, "board": board["key"]}
            # The config may change: what has not been evaluated is classified again.
            if row["status"] == "Filtered" and now_passes and not find_dup(con, company, j):
                upd.update(status="New", prescore=score)
                new_ids.append(j["id"])
            elif row["status"] == "New" and not now_passes:
                upd["status"] = "Filtered"
            elif row["status"] == "New":
                upd["prescore"] = score
            if row["status"] == "Closed":
                upd.update(status="Evaluated" if row["fit"] else "New", closed_on=None)
            sets = ", ".join(f"{k}=?" for k in upd)
            con.execute(f"UPDATE leads SET {sets} WHERE job_id=?", (*upd.values(), j["id"]))
            continue
        # A re-post of the same role is not a new posting.
        dup = find_dup(con, company, j) if now_passes else None
        status = "Duplicate" if dup else ("New" if now_passes else "Filtered")
        con.execute(
            """INSERT INTO leads (job_id, company, title, location, family, geo, geo_reason, excluded, passes,
               url, posted, comp, department, first_seen, last_checked, last_seen_open, status, dup_of, prescore,
               source, board) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (j["id"], company, j["title"], j["location"], j["family"], j["geo"], j["geo_reason"], j["excluded"],
             int(bool(now_passes)), j.get("url", ""), j.get("posted", ""), j.get("comp", ""), j.get("department", ""),
             today, today, today, status, dup["job_id"] if dup else None, score, source, board["key"]))
        if status == "New":
            new_ids.append(j["id"])
    # Closing: only for a board that was read successfully.
    for r in con.execute("SELECT job_id FROM leads WHERE coalesce(source, ?) = ? AND coalesce(board, company) = ? "
                         "AND status != 'Closed'", (DEFAULT_SOURCE, source, board["key"])).fetchall():
        if r["job_id"] not in seen:
            con.execute("UPDATE leads SET status='Closed', closed_on=?, last_checked=? WHERE job_id=?",
                        (today, today, r["job_id"]))
            closed.append(r["job_id"])


def sweep(con, cfg, today, names):
    """Read every board of every source. Returns (boards by (source, key), new ids, closed ids, errors)."""
    boards, new_ids, closed, errors = {}, [], [], []
    for name in names:
        conf = sources.configured(cfg).get(name) or {}
        try:
            result = sources.load(name, cfg).fetch(cfg, conf=conf, con=con)
        except Exception as e:  # noqa: BLE001 - a broken source must not stop the others
            errors.append((name, f"{type(e).__name__}: {e}"[:300]))
            continue
        for board in result:
            boards[(name, board["key"])] = board
            con.execute("INSERT INTO runs VALUES (?,?,?,?,?)",
                        (today, board["key"], int(board.get("jobs") is not None), len(board.get("jobs") or []),
                         board.get("error")))
            if board.get("jobs") is None:
                errors.append((board["key"], board.get("error") or "no data"))
                continue
            ingest_board(con, cfg, today, name, board, new_ids, closed)
        con.commit()
    return boards, new_ids, closed, errors


def describe(cfg, lead) -> str:
    name = lead["source"] or DEFAULT_SOURCE
    conf = sources.configured(cfg).get(name) or {}
    try:
        mod = sources.load(name, cfg)
    except Exception:  # noqa: BLE001
        return ""
    if not hasattr(mod, "describe"):
        return ""
    try:
        return mod.describe(dict(lead), conf=conf) or ""
    except Exception as e:  # noqa: BLE001
        return f"(description unavailable: {e})"


def pick(con, cfg, today, boards, max_eval) -> tuple[list[dict], int]:
    """Today's batch: best pre-scored New postings from boards that are still configured."""
    cooldown = {cd["company"]: cd for cd in cfg.get("cooldowns") or [] if str(cd.get("until", "9999")) >= today}
    live = {(src, key) for src, key in boards}
    pending = [r for r in con.execute("SELECT * FROM leads WHERE status='New' ORDER BY prescore DESC, first_seen ASC")
               if (r["source"] or DEFAULT_SOURCE, r["board"] or r["company"]) in live]
    # Descriptions some sources already brought with the posting; the rest are asked for.
    known = {j["id"]: j["description"] for b in boards.values() for j in (b.get("jobs") or []) if j.get("description")}
    out = []
    for r in pending[:max_eval]:
        meta = boards[(r["source"] or DEFAULT_SOURCE, r["board"] or r["company"])].get("meta") or {}
        out.append({
            "job_id": r["job_id"], "company": r["company"], "title": r["title"], "location": r["location"],
            "family": r["family"], "geo_reason": r["geo_reason"], "url": r["url"], "posted": r["posted"],
            "posted_comp": r["comp"], "company_tier": meta.get("tier"), "company_comp_note": meta.get("comp"),
            "company_hiring_notes": meta.get("hiring_notes"),
            "cooldown": cooldown.get(r["company"], {}).get("note"),
            "description": (known.get(r["job_id"]) or describe(cfg, r))[:3500],
        })
    return out, len(pending)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace")
    ap.add_argument("--date")
    ap.add_argument("--max-eval", type=int)
    ap.add_argument("--sources", help="comma-separated; default: every enabled source")
    args = ap.parse_args()
    workspace.use(args.workspace)
    cfg = workspace.load_config()
    today = args.date or workspace.today(cfg)
    con = db.connect()
    names = args.sources.split(",") if args.sources else sources.enabled(cfg)

    boards, new_ids, closed, errors = sweep(con, cfg, today, names)
    max_eval = args.max_eval or (cfg.get("evaluation") or {}).get("max_per_day", 20)
    to_eval, n_pending = pick(con, cfg, today, boards, max_eval)

    out = workspace.out_dir(today)
    (out / "to_evaluate.json").write_text(json.dumps(to_eval, indent=1, ensure_ascii=False))
    closed_rows = [dict(con.execute("SELECT company,title,url,fit,status FROM leads WHERE job_id=?", (cid,)).fetchone())
                   for cid in closed]
    stats = {
        "date": today,
        "boards_checked": len(boards),
        "fetch_errors": errors,
        "new_relevant_today": len(new_ids),
        "pending_evaluation_total": n_pending,
        "evaluating_today": len(to_eval),
        "closed_today": len(closed),
        "closed_relevant": [c for c in closed_rows if c.get("fit") in ("High", "Medium")],
        "open_relevant_total": con.execute(
            "SELECT count(*) FROM leads WHERE passes=1 AND status NOT IN ('Closed','Duplicate','Filtered')").fetchone()[0],
    }
    (out / "stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in stats.items() if k != "closed_relevant"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
