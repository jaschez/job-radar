"""Optional, EXPERIMENTAL: keep a Google Sheets tracker in sync, through Claude Code and
its Google Sheets connector (claude-cli only). Untested against a live spreadsheet.

The sheet layout is the one tools/build_tracker.py creates ("Job Leads" tab, radar id in
column Z). Enable with `sheets: {enabled: true, id: <spreadsheet id>}`. The radar
prepares the operations; Claude applies them and must respect the candidate's columns.

Usage: python radar/sheets.py [--date D] [--workspace W]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import db  # noqa: E402
import llm  # noqa: E402
import workspace  # noqa: E402


def synced_file() -> Path:
    return workspace.data_dir() / "sheet_synced_ids.json"


def load_synced() -> dict:
    """{radar_id: evaluated_at of the version in the sheet}. Accepts the old list format."""
    f = synced_file()
    if not f.exists():
        return {}
    data = json.loads(f.read_text())
    return {k: "v1" for k in data} if isinstance(data, list) else data


def ops(con, today: str) -> dict:
    synced = load_synced()
    append, update = [], []
    for r in con.execute("""SELECT * FROM leads WHERE passes=1 AND fit IN ('High','Medium','Low')
                            AND status NOT IN ('Duplicate','Filtered')"""):
        if r["job_id"] in synced:
            if synced[r["job_id"]] != (r["evaluated_at"] or ""):
                update.append({"radar_id": r["job_id"], "H": r["fit"], "I": r["priority"] or "",
                               "O": r["comp_estimate"] or r["comp"] or "", "P": r["comp_type"] or "",
                               "Q": r["summary"] or "", "R": r["why_fits"] or "", "S": r["main_gaps"] or ""})
            continue
        append.append({"radar_id": r["job_id"], "values": [
            "", r["first_seen"], r["last_checked"], r["company"], r["title"], (r["location"] or "")[:80], r["family"],
            r["fit"], r["priority"] or "", "Closed" if r["status"] == "Closed" else "Open", "No", "", r["url"],
            r["posted"], r["comp_estimate"] or r["comp"] or "", r["comp_type"] or "", r["summary"] or "",
            r["why_fits"] or "", r["main_gaps"] or "", "", "", "", "", "—", "—",
            (r["eval_notes"] or "") + f" [radar:{r['job_id']}]"]})
    close = [r["job_id"] for r in con.execute("SELECT job_id FROM leads WHERE status='Closed' AND closed_on=?", (today,))]
    return {"date": today, "append": append, "update": update, "close": close}


def mark_synced(con, o: dict):
    done = load_synced()
    for x in o["append"] + o["update"]:
        r = con.execute("SELECT evaluated_at FROM leads WHERE job_id=?", (x["radar_id"],)).fetchone()
        done[x["radar_id"]] = (r["evaluated_at"] if r else "") or ""
    synced_file().write_text(json.dumps(done, indent=0))


def run(cfg, out: Path, today: str) -> int:
    sc = cfg.get("sheets") or {}
    if not sc.get("enabled") or (out / "sheet_sync_done.json").exists():
        return 0
    con = db.connect()
    o = ops(con, today)
    (out / "sheet_ops.json").write_text(json.dumps(o, ensure_ascii=False, indent=1))
    prompt = ((ROOT / "radar/prompts/sync_sheet.md").read_text()
              .replace("{SHEET_ID}", sc["id"]).replace("{OPS_FILE}", str(out / "sheet_ops.json"))
              .replace("{DONE_FILE}", str(out / "sheet_sync_done.json")).replace("{DATE}", today))
    try:
        (out / "sheet_sync.log").write_text(
            llm.agent(prompt, model=sc.get("model", "sonnet"), tools=["Read", "Write", "mcp__claude_ai_Google_Sheets"]))
    except llm.LLMError as e:
        print(f"sheet sync failed: {e}")
        return 1
    if not (out / "sheet_sync_done.json").exists():
        print("sheet sync did not confirm (see sheet_sync.log)")
        return 1
    mark_synced(con, o)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--workspace")
    a = ap.parse_args()
    workspace.use(a.workspace)
    cfg = workspace.load_config()
    today = a.date or workspace.today(cfg)
    sys.exit(run(cfg, workspace.out_dir(today), today))


if __name__ == "__main__":
    main()
