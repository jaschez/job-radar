"""Geography, role family and exclusions decide what reaches the evaluation."""
import pytest

import filters


def job(title="Backend Engineer", location="Remote - Europe", remote=True, **kw):
    return {"id": "x:1", "title": title, "location": location, "raw_locations": [location], "remote": remote, **kw}


@pytest.mark.parametrize("loc,verdict", [
    ("Remote - Europe", "ok"), ("Spain", "ok"), ("Valencia, Spain", "ok"), ("Remote, Spain", "ok"),
    ("Berlin, Germany", "relocate"), ("Madrid, Spain", "pending"), ("San Francisco, CA", "no"),
    ("Remote - US", "no"),
])
def test_geography(cfg, loc, verdict):
    assert filters.geo_verdict(job(location=loc, remote="remote" in loc.lower()), cfg)[0] == verdict


def test_a_region_in_the_title_wins_over_a_remote_location(cfg):
    assert filters.geo_verdict(job(title="Backend Engineer - US", location="Remote"), cfg)[0] == "no"


def test_several_offices_in_one_string(cfg):
    v, why = filters.geo_verdict(job(location="Berlin, Germany; Valencia, Spain", remote=False), cfg)
    assert v == "ok" and "valencia" in why


@pytest.mark.parametrize("title,family", [
    ("Senior Backend Engineer", "Backend / Software Engineering"), ("Data Engineer", "Data / Platform"),
    ("Frontend Developer", "Frontend"), ("Account Executive", None),
])
def test_role_family(cfg, title, family):
    assert filters.role_family(job(title=title), cfg) == family


def test_inactive_family_and_exclusions_do_not_pass(cfg):
    assert filters.classify(job(title="Frontend Developer"), cfg)["passes"] is False
    assert filters.classify(job(title="Backend Engineering Manager"), cfg)["excluded"] == "management or staff+"
    assert filters.classify(job(title="Backend Engineer"), cfg)["passes"] is True


def test_relocation_settings(cfg):
    berlin = filters.classify(job(location="Berlin, Germany", remote=False), cfg)
    assert filters.passes_cfg(berlin, cfg) is True
    cfg["geography"]["include_relocation"] = False
    assert filters.passes_cfg(berlin, cfg) is False


def test_title_key_ignores_geography():
    assert filters.title_key("Backend Engineer - Spain (Remote)") == filters.title_key("Backend Engineer, Germany")
