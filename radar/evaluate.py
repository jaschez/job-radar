"""Evaluate the day's postings with Claude and write out/<day>/evals.json.

The prompt (radar/prompts/evaluate.md) is generic. What makes it personal comes from the
workspace: the candidate profile (`evaluation.profile_file`, default profile.md) and the
hard rules (`evaluation.rules`). The answer is validated before anything is written.

Usage: python radar/evaluate.py [--date YYYY-MM-DD] [--workspace DIR]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import i18n  # noqa: E402
import llm  # noqa: E402
import workspace  # noqa: E402

PROMPT = ROOT / "radar" / "prompts" / "evaluate.md"
FITS = {"High", "Medium", "Low", "Reject"}
KEYS = ("job_id", "fit", "priority", "why_fits", "main_gaps", "summary", "comp_estimate", "comp_type", "notes")


def profile(cfg: dict) -> str:
    ev = cfg.get("evaluation") or {}
    p = workspace.file(ev.get("profile_file", "profile.md"))
    return p.read_text(encoding="utf-8").strip() if p.exists() else "(no profile provided)"


def build_prompt(cfg: dict, batch: list[dict]) -> str:
    ev = cfg.get("evaluation") or {}
    fams = [f["name"] for f in cfg.get("role_families") or [] if f.get("active", True)]
    lang = i18n.LANGUAGE_NAMES.get(cfg.get("language", "en"), "English")
    return (PROMPT.read_text(encoding="utf-8")
            .replace("{PROFILE}", profile(cfg))
            .replace("{RULES}", (ev.get("rules") or "None beyond the profile.").strip())
            .replace("{FAMILIES}", ", ".join(fams) or "any")
            .replace("{LANGUAGE}", lang)
            .replace("{COUNT}", str(len(batch)))
            .replace("{POSTINGS}", json.dumps(batch, ensure_ascii=False, indent=1)))


def parse(text: str, batch: list[dict]) -> list[dict]:
    fenced = re.search(r"```(?:json)?\s*(\[.*\])\s*```", text, re.S)
    raw = fenced.group(1) if fenced else text[text.find("["): text.rfind("]") + 1]
    data = json.loads(raw)
    wanted = {x["job_id"] for x in batch}
    return [{k: e.get(k) for k in KEYS} for e in (data if isinstance(data, list) else [])
            if isinstance(e, dict) and e.get("job_id") in wanted and e.get("fit") in FITS]


def run(cfg: dict, out: Path) -> int:
    ev = cfg.get("evaluation") or {}
    backend = ev.get("backend", "claude-cli")
    batch = json.loads((out / "to_evaluate.json").read_text()) if (out / "to_evaluate.json").exists() else []
    if not batch or (out / "evals.json").exists() or backend == "none":
        return 0
    try:
        text = llm.complete(build_prompt(cfg, batch), backend=backend, model=ev.get("model", "sonnet"))
    except llm.LLMError as e:
        print(f"evaluation failed: {e}")
        return 1
    (out / "evaluate.raw.txt").write_text(text)
    try:
        evals = parse(text, batch)
    except ValueError as e:
        print(f"evaluation answer is not valid JSON ({e}); see evaluate.raw.txt")
        return 1
    (out / "evals.json").write_text(json.dumps(evals, ensure_ascii=False, indent=1))
    print(f"evaluated {len(evals)}/{len(batch)}")
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
