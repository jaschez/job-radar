"""Find which ATS board slugs exist for candidate companies and how many postings pass the
filter today. Reads <workspace>/candidates.yaml:

    - {company: Grafana Labs, guesses: [[greenhouse, grafanalabs]]}
    - {company: Temporal, guesses: [[greenhouse, temporaltechnologies], [ashby, temporal]]}

and writes <workspace>/candidates_probe.json. Copy the hits into companies.yaml.

Usage: python tools/probe_ats.py [--workspace W]
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "radar"))
import filters  # noqa: E402
import workspace  # noqa: E402
from sources import providers  # noqa: E402


def probe(c, cfg):
    for provider, slug in c.get("guesses") or []:
        try:
            jobs = providers.fetch(provider, slug)
        except Exception:  # noqa: BLE001 - wrong guess
            continue
        cl = [filters.classify(j, cfg) for j in jobs]
        ok = [j for j in cl if j["passes"] and j["geo"] == "ok"]
        return {"company": c["company"], "provider": provider, "slug": slug, "total": len(jobs),
                "eng_total": sum(1 for j in cl if j["family"]),
                "relocation": sum(1 for j in cl if j["family"] and not j["excluded"] and j["geo"] in ("relocate", "pending")),
                "ok": [{k: j[k] for k in ("title", "location", "family", "url", "comp", "posted")} for j in ok]}
    return {"company": c["company"], "provider": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace")
    workspace.use(ap.parse_args().workspace)
    cfg = workspace.load_config()
    cands = yaml.safe_load(workspace.file("candidates.yaml").read_text(encoding="utf-8")) or []
    with ThreadPoolExecutor(16) as ex:
        res = list(ex.map(lambda c: probe(c, cfg), cands))
    workspace.file("candidates_probe.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    found = [r for r in res if r.get("provider")]
    print(f"ATS found: {len(found)}/{len(res)}")
    for r in sorted(found, key=lambda r: -len(r["ok"])):
        print(f"{r['company'][:26]:26} {r['provider']:15} {r['slug'][:22]:22} total={r['total']:4} "
              f"eng={r['eng_total']:3} OK={len(r['ok']):3} relocation={r['relocation']:3}")
    print("--- no ATS detected:", ", ".join(r["company"] for r in res if not r.get("provider")))


if __name__ == "__main__":
    main()
