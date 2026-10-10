"""Weekly check of target companies without a public job board API (claude-cli only).

Claude Code opens each careers page (WebFetch, at most one WebSearch) and writes
out/<day>/manual_check.json, which the weekly e-mail includes. Enable with
`manual_check: {enabled: true, model: sonnet}`; sources that can list such companies
expose manual_targets() (the built-in ats_boards does: active companies without `ats`).

Usage: python radar/manual_check.py [--date D] [--workspace W]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import evaluate  # noqa: E402
import i18n  # noqa: E402
import llm  # noqa: E402
import sources  # noqa: E402
import workspace  # noqa: E402


def targets(cfg) -> list[dict]:
    out = []
    for name in sources.enabled(cfg):
        mod = sources.load(name, cfg)
        if hasattr(mod, "manual_targets"):
            out += mod.manual_targets(cfg, conf=sources.configured(cfg).get(name) or {})
    return out


def run(cfg, out: Path) -> int:
    mc = cfg.get("manual_check") or {}
    dest = out / "manual_check.json"
    if not mc.get("enabled") or dest.exists():
        return 0
    comps = targets(cfg)
    if not comps:
        dest.write_text("[]")
        return 0
    fams = [f["name"] for f in cfg.get("role_families") or [] if f.get("active", True)]
    prompt = ((ROOT / "radar/prompts/manual_check.md").read_text()
              .replace("{PROFILE}", evaluate.profile(cfg))
              .replace("{RULES}", ((cfg.get("evaluation") or {}).get("rules") or "None.").strip())
              .replace("{FAMILIES}", ", ".join(fams) or "any")
              .replace("{COMPANIES}", "\n".join(f"- {c['company']}: {c['careers']}" for c in comps))
              .replace("{OUT_FILE}", str(dest))
              .replace("{LANGUAGE}", i18n.LANGUAGE_NAMES.get(cfg.get("language", "en"), "English")))
    try:
        log = llm.agent(prompt, model=mc.get("model", "sonnet"), tools=["Read", "Write", "WebFetch", "WebSearch"])
    except llm.LLMError as e:
        print(f"manual check failed: {e}")
        return 1
    (out / "manual_check.log").write_text(log)
    try:
        json.loads(dest.read_text())
    except (OSError, ValueError):
        print("manual check produced no valid manual_check.json")
        return 1
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--workspace")
    a = ap.parse_args()
    workspace.use(a.workspace)
    cfg = workspace.load_config()
    sys.exit(run(cfg, workspace.out_dir(a.date or workspace.today(cfg))))


if __name__ == "__main__":
    main()
