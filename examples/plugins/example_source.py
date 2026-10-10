"""Example source plugin: a job board that publishes postings as JSON.

Copy it into your workspace (e.g. plugins/my_board.py), adapt the URL and the mapping,
and enable it in config.yaml:

    sources:
      my_board:
        path: plugins/my_board.py
        url: https://jobs.example.test/api/jobs

The contract is documented in radar/sources/__init__.py: fetch() returns boards, a
board being one place read in full; postings that disappear from a board read
successfully are closed.
"""
import requests

ID_PREFIX = "myboard"


def fetch(cfg, *, conf, con=None, **_):
    try:
        r = requests.get(conf["url"], timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:  # noqa: BLE001 - report the board as failed: nothing gets closed
        return [{"key": "my_board", "company": None, "jobs": None, "error": f"{type(e).__name__}: {e}"}]
    jobs = []
    for j in data.get("jobs", []):
        locs = j.get("locations") or [j.get("location", "")]
        jobs.append({
            "id": f"{ID_PREFIX}:{j['id']}", "company": j.get("company"), "title": j.get("title", ""),
            "location": " / ".join(locs), "raw_locations": locs, "remote": bool(j.get("remote")),
            "url": j.get("url", ""), "posted": (j.get("published") or "")[:10],
            "department": j.get("category", ""), "comp": j.get("salary", ""),
            "description": j.get("description", ""),
        })
    return [{"key": "my_board", "company": None, "jobs": jobs, "error": None, "meta": {}}]


def describe(lead, *, conf):
    return ""      # the description came with the posting; return a fuller one here if the board has it
