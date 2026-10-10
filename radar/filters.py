"""Deterministic rules for geography, role family and exclusions. No LLM.

All patterns are regular expressions from the workspace config, matched against
lowercased, accent-free text. This decides what reaches the fit evaluation, not the fit.

Geography verdicts:
  ok        an accepted city, a remote location compatible with the candidate, or an
            accepted country without a city that would force a move
  relocate  the role requires moving somewhere the candidate accepts (lower priority)
  pending   the role requires moving somewhere not considered yet (stored, not announced
            unless geography.include_pending)
  no        out of scope
"""
from __future__ import annotations

import re
import unicodedata


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.lower()).strip()


def _any(patterns, text):
    return any(re.search(p, text) for p in patterns or [])


def geo_verdict(job: dict, cfg: dict) -> tuple[str, str]:
    """Return (verdict, reason)."""
    g = cfg["geography"]
    locs = [norm(l) for l in job.get("raw_locations") or [] if l] or [norm(job.get("location", ""))]
    text = " | ".join(locs)
    title = norm(job.get("title", ""))
    # A title like "Backend Engineer - US" gives the zone away even when the location says Remote.
    if _any(g.get("excluded_patterns"), title):
        return "no", "excluded zone in the title"
    # One string may carry several offices ("Barcelona, Spain; Madrid, Spain").
    parts = [p.strip() for loc in locs for p in re.split(r"[;|]", loc) if p.strip()]
    for loc in parts:
        if _any(g.get("home_city_patterns"), loc):
            return "ok", f"accepted city: {loc}"
        if _any(g.get("remote_ok_patterns"), loc):
            return "ok", f"compatible remote: {loc}"
    reloc = [loc for loc in parts if _any(g.get("relocation_ok_patterns"), loc)]
    pending = [loc for loc in parts if _any(g.get("pending_city_patterns"), loc)]
    for loc in parts:
        # A bare country (no city forcing a move) usually means remote within that country.
        if loc not in pending and loc not in reloc and _any(g.get("accepted_city_patterns"), loc):
            return "ok", f"accepted country: {loc}"
    if reloc:
        return "relocate", f"accepted relocation: {reloc[0]}"
    if pending:
        return "pending", f"relocation not considered: {pending[0]}"
    if job.get("remote") and not _any(g.get("excluded_patterns"), text):
        # Plain "Remote": ambiguous. Let it through, flagged for the evaluation to check.
        if re.search(r"^(fully )?remote$|^remote \(?(global|anywhere|worldwide)\)?$", text) or text in ("remote", ""):
            return "ok", "remote without zone (check the description)"
    return "no", f"location out of scope: {text[:80]}"


def role_family(job: dict, cfg: dict) -> str | None:
    title = norm(job.get("title", ""))
    for fam in cfg.get("role_families") or []:
        if _any(fam["title_patterns"], title):
            return fam["name"]
    return None


def excluded(job: dict, cfg: dict) -> str | None:
    title = norm(job.get("title", ""))
    for rule in cfg.get("exclusions") or []:
        if _any(rule["patterns"], title):
            return rule["reason"]
    return None


def classify(job: dict, cfg: dict) -> dict:
    """Add geo / family / exclusion to the job and say whether it passes."""
    geo, why_geo = geo_verdict(job, cfg)
    fam = role_family(job, cfg)
    exc = excluded(job, cfg)
    active = {f["name"] for f in cfg.get("role_families") or [] if f.get("active", True)}
    passes = geo in ("ok", "relocate", "pending") and fam in active and not exc
    return {**job, "geo": geo, "geo_reason": why_geo, "family": fam or "", "excluded": exc or "", "passes": passes}


def passes_cfg(job: dict, cfg: dict) -> bool:
    """Whether a classified job is worth keeping as New, given the relocation settings."""
    g = cfg["geography"]
    return bool(job["passes"]) and (job["geo"] == "ok"
                                    or (job["geo"] == "relocate" and g.get("include_relocation"))
                                    or (job["geo"] == "pending" and g.get("include_pending")))


GEO_WORDS = re.compile(
    r"\b(remote|remoto|hybrid|spain|espana|germany|deutschland|ireland|republic of ireland|switzerland|austria|"
    r"netherlands|france|portugal|italy|poland|uk|united kingdom|emea|europe|eu|berlin|munich|madrid|barcelona|dublin|"
    r"zurich|amsterdam|london|paris|lisbon|us|usa|americas)\b")


def title_key(title: str) -> str:
    """Duplicate key: the same role posted per country has the same title once geography is removed."""
    t = GEO_WORDS.sub(" ", norm(title))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()
