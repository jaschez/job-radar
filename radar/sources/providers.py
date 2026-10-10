"""Minimal clients for public applicant-tracking-system (ATS) job board APIs.

Each provider returns a list of normalized dicts:
  {id, title, location, remote, url, posted, department, comp, raw_locations, description}
None needs credentials: these are the endpoints the companies' own careers pages use.

More providers can be plugged in from the config without touching this file:

    sources:
      ats_boards:
        providers:
          my_ats: {path: plugins/my_ats.py}     # module with fetch(slug, with_content=False)
                                                # and optionally describe(slug, job_id)
"""
from __future__ import annotations

import datetime as dt
import html
import re
import xml.etree.ElementTree as ET

import requests

import plugins

UA = {"User-Agent": "Mozilla/5.0 (compatible; job-radar; +https://github.com/jaschez/job-radar)"}
TIMEOUT = 25


def set_contact(contact: str | None):
    """Add a contact to the User-Agent, as polite crawlers do (config `user_agent_contact`)."""
    if contact:
        UA["User-Agent"] = f"Mozilla/5.0 (compatible; job-radar; contact {contact})"


def _get(url, **kw):
    r = requests.get(url, headers=UA, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()


def _ms_to_date(ms):
    if not ms:
        return ""
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def greenhouse(slug: str, with_content: bool = False):
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
                params={"content": "true"} if with_content else None).json()
    out = []
    for j in data.get("jobs", []):
        loc = (j.get("location") or {}).get("name", "")
        offices = [o.get("name", "") for o in j.get("offices", []) or []]
        out.append({
            "id": f"gh:{slug}:{j['id']}", "title": j.get("title", ""), "location": loc,
            "raw_locations": [loc] + offices, "remote": "remote" in loc.lower(),
            "url": j.get("absolute_url", ""),
            "posted": (j.get("first_published") or j.get("updated_at") or "")[:10],
            "department": ", ".join(d.get("name", "") for d in j.get("departments", []) or []),
            "comp": "",
            "description": strip_html(html.unescape(j.get("content", ""))) if with_content else "",
        })
    return out


def lever(slug: str, with_content: bool = False, eu: bool = False):
    base = "https://api.eu.lever.co" if eu else "https://api.lever.co"
    data = _get(f"{base}/v0/postings/{slug}", params={"mode": "json"}).json()
    out = []
    for j in data:
        cat = j.get("categories") or {}
        locs = cat.get("allLocations") or [cat.get("location", "")]
        sal = j.get("salaryRange") or {}
        comp = ""
        if sal.get("min"):
            comp = f"{sal.get('min')}-{sal.get('max')} {sal.get('currency', '')} {sal.get('interval', '')}".strip()
        out.append({
            "id": f"lv:{slug}:{j['id']}", "title": j.get("text", ""),
            "location": " / ".join(l for l in locs if l), "raw_locations": locs,
            "remote": (j.get("workplaceType") == "remote") or any("remote" in (l or "").lower() for l in locs),
            "url": j.get("hostedUrl", ""), "posted": _ms_to_date(j.get("createdAt")),
            "department": cat.get("team", "") or cat.get("department", ""), "comp": comp,
            "description": strip_html(j.get("descriptionPlain") or j.get("description")) if with_content else "",
        })
    return out


def ashby(slug: str, with_content: bool = False):
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
                params={"includeCompensation": "true"}).json()
    out = []
    for j in data.get("jobs", []):
        if j.get("isListed") is False:
            continue
        locs = [j.get("location", "")] + [s.get("location", "") for s in j.get("secondaryLocations", []) or []]
        comp = ((j.get("compensation") or {}).get("scrapeableCompensationSalarySummary")
                or (j.get("compensation") or {}).get("compensationTierSummary") or "")
        out.append({
            "id": f"ab:{slug}:{j.get('id')}", "title": j.get("title", ""),
            "location": " / ".join(l for l in locs if l), "raw_locations": locs,
            "remote": bool(j.get("isRemote")) or j.get("workplaceType") == "Remote",
            "url": j.get("jobUrl", ""), "posted": (j.get("publishedAt") or "")[:10],
            "department": j.get("department", "") or j.get("team", ""), "comp": comp,
            "description": strip_html(j.get("descriptionPlain") or j.get("descriptionHtml")) if with_content else "",
        })
    return out


def workable(slug: str, with_content: bool = False):
    data = _get(f"https://apply.workable.com/api/v1/widget/accounts/{slug}").json()
    out = []
    for j in data.get("jobs", []):
        loc = ", ".join(x for x in [j.get("city", ""), j.get("state", ""), j.get("country", "")] if x)
        locs = [loc] + [", ".join(x for x in [l.get("city", ""), l.get("country", "")] if x)
                        for l in j.get("locations", []) or []]
        out.append({
            "id": f"wk:{slug}:{j.get('shortcode')}", "title": j.get("title", ""), "location": loc,
            "raw_locations": locs, "remote": bool(j.get("telecommuting")),
            "url": j.get("url") or j.get("shortlink", ""), "posted": (j.get("published_on") or "")[:10],
            "department": j.get("department", ""), "comp": "",
            "description": strip_html(j.get("description")) if with_content else "",
        })
    return out


def smartrecruiters(slug: str, with_content: bool = False):
    out, offset = [], 0
    while True:
        data = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
                    params={"limit": 100, "offset": offset}).json()
        for j in data.get("content", []):
            l = j.get("location") or {}
            loc = ", ".join(x for x in [l.get("city", ""), l.get("country", "")] if x)
            out.append({
                "id": f"sr:{slug}:{j.get('id')}", "title": j.get("name", ""),
                "location": loc + (" (remote)" if l.get("remote") else ""), "raw_locations": [loc],
                "remote": bool(l.get("remote")), "url": f"https://jobs.smartrecruiters.com/{slug}/{j.get('id')}",
                "posted": (j.get("releasedDate") or "")[:10],
                "department": (j.get("department") or {}).get("label", ""), "comp": "", "description": "",
            })
        offset += 100
        if offset >= data.get("totalFound", 0) or offset > 1000:
            break
    return out


def recruitee(slug: str, with_content: bool = False):
    data = _get(f"https://{slug}.recruitee.com/api/offers/").json()
    out = []
    for j in data.get("offers", []):
        loc = j.get("location", "") or ", ".join(x for x in [j.get("city", ""), j.get("country", "")] if x)
        out.append({
            "id": f"rc:{slug}:{j.get('id')}", "title": j.get("title", ""), "location": loc,
            "raw_locations": [loc] + [l.get("name", "") for l in j.get("locations", []) or []],
            "remote": bool(j.get("remote")), "url": j.get("careers_url", ""),
            "posted": (j.get("published_at") or "")[:10], "department": j.get("department", ""), "comp": "",
            "description": strip_html(j.get("description")) if with_content else "",
        })
    return out


def personio(slug: str, with_content: bool = False):
    out = []
    for tld in ("de", "com"):
        try:
            r = _get(f"https://{slug}.jobs.personio.{tld}/xml")
        except Exception:  # noqa: BLE001 - try the other domain
            continue
        root = ET.fromstring(r.content)
        for p in root.findall("position"):
            def g(k, p=p):
                return (p.findtext(k) or "").strip()
            offices = [g("office")] + [o.text or "" for o in p.findall("additionalOffices/office")]
            out.append({
                "id": f"ps:{slug}:{g('id')}", "title": g("name"), "location": " / ".join(o for o in offices if o),
                "raw_locations": offices, "remote": "remote" in " ".join(offices).lower(),
                "url": f"https://{slug}.jobs.personio.{tld}/job/{g('id')}", "posted": g("createdAt")[:10],
                "department": g("department"), "comp": "", "description": "",
            })
        break
    return out


BUILTIN = {
    "greenhouse": greenhouse,
    "lever": lever,
    "lever_eu": lambda s, with_content=False: lever(s, with_content, eu=True),
    "ashby": ashby,
    "workable": workable,
    "smartrecruiters": smartrecruiters,
    "recruitee": recruitee,
    "personio": personio,
}


def resolve(provider: str, extra: dict | None = None):
    """The fetch function for a provider name: a plugin from `extra` or a built-in."""
    spec = (extra or {}).get(provider)
    if spec:
        return plugins.load(spec, "sources").fetch
    if provider not in BUILTIN:
        raise KeyError(f"unknown ATS provider: {provider}")
    return BUILTIN[provider]


def fetch(provider: str, slug: str, with_content: bool = False, extra: dict | None = None):
    return resolve(provider, extra)(slug, with_content=with_content)


def describe(job_id: str, extra: dict | None = None) -> str:
    """Full description of one posting, for the evaluation."""
    kind, slug, jid = job_id.split(":", 2)
    try:
        if kind == "gh":
            j = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{jid}").json()
            return strip_html(html.unescape(j.get("content", "")))
        if kind == "lv":
            j = _get(f"https://api.lever.co/v0/postings/{slug}/{jid}").json()
            lists = " ".join(f"{l.get('text', '')}: {strip_html(l.get('content', ''))}" for l in j.get("lists", []))
            return (j.get("descriptionPlain", "") + " " + lists + " " + (j.get("additionalPlain") or "")).strip()
        if kind == "ab":
            for j in ashby(slug, with_content=True):
                if j["id"] == job_id:
                    return j["description"]
        if kind == "wk":
            j = _get(f"https://apply.workable.com/api/v2/accounts/{slug}/jobs/{jid}").json()
            return strip_html(" ".join(j.get(k, "") or "" for k in ("description", "requirements", "benefits")))
        for name, spec in (extra or {}).items():
            mod = plugins.load(spec, "sources")
            if hasattr(mod, "describe") and job_id.startswith(getattr(mod, "ID_PREFIX", name) + ":"):
                return mod.describe(slug, jid)
    except Exception as e:  # noqa: BLE001
        return f"(description unavailable: {e})"
    return ""
