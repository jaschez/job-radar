"""ATS clients normalize each provider's shape to the same dict."""
import pytest

from sources import providers


class R:
    def __init__(self, data):
        self.data = data
        self.content = b""

    def json(self):
        return self.data


SAMPLES = {
    "boards-api.greenhouse.io": {"jobs": [{"id": 7, "title": "Backend Engineer", "location": {"name": "Remote, Spain"},
                                           "offices": [{"name": "Madrid"}], "absolute_url": "https://gh/7",
                                           "first_published": "2026-10-01T10:00:00Z", "departments": [{"name": "Eng"}]}]},
    "api.lever.co": [{"id": "abc", "text": "Data Engineer", "categories": {"allLocations": ["Berlin", "Remote"], "team": "Data"},
                      "workplaceType": "remote", "hostedUrl": "https://lv/abc", "createdAt": 1790000000000,
                      "salaryRange": {"min": 70000, "max": 90000, "currency": "EUR", "interval": "per-year-salary"}}],
    "api.ashbyhq.com": {"jobs": [{"id": "q1", "title": "Platform Engineer", "location": "Remote - Europe",
                                  "secondaryLocations": [{"location": "Dublin"}], "isRemote": True, "jobUrl": "https://ab/q1",
                                  "publishedAt": "2026-09-30T00:00:00Z", "department": "Infra",
                                  "compensation": {"compensationTierSummary": "€80K – €100K"}},
                                 {"id": "hidden", "title": "x", "isListed": False}]},
    "apply.workable.com": {"jobs": [{"shortcode": "W1", "title": "Python Developer", "city": "Valencia", "country": "Spain",
                                     "telecommuting": False, "url": "https://wk/W1", "published_on": "2026-09-29"}]},
}


@pytest.fixture(autouse=True)
def fake_get(monkeypatch):
    def get(url, **kw):
        for host, data in SAMPLES.items():
            if host in url:
                return R(data)
        raise AssertionError(url)
    monkeypatch.setattr(providers, "_get", get)


@pytest.mark.parametrize("provider,expect_id,expect_title", [
    ("greenhouse", "gh:acme:7", "Backend Engineer"), ("lever", "lv:acme:abc", "Data Engineer"),
    ("ashby", "ab:acme:q1", "Platform Engineer"), ("workable", "wk:acme:W1", "Python Developer"),
])
def test_each_provider_normalizes(provider, expect_id, expect_title):
    jobs = providers.fetch(provider, "acme")
    assert jobs[0]["id"] == expect_id and jobs[0]["title"] == expect_title
    assert set(jobs[0]) >= {"id", "title", "location", "raw_locations", "remote", "url", "posted", "department", "comp"}


def test_details_that_matter():
    assert providers.fetch("greenhouse", "acme")[0]["raw_locations"] == ["Remote, Spain", "Madrid"]
    assert providers.fetch("lever", "acme")[0]["comp"].startswith("70000-90000 EUR")
    assert len(providers.fetch("ashby", "acme")) == 1            # unlisted postings are skipped
    assert providers.fetch("workable", "acme")[0]["location"] == "Valencia, Spain"


def test_a_provider_plugin_from_the_workspace(_workspace):
    (_workspace / "plugins").mkdir()
    (_workspace / "plugins" / "my_ats.py").write_text(
        "def fetch(slug, with_content=False):\n    return [{'id': f'my:{slug}:1', 'title': 'Go Engineer'}]\n")
    jobs = providers.fetch("my_ats", "acme", extra={"my_ats": {"path": "plugins/my_ats.py"}})
    assert jobs == [{"id": "my:acme:1", "title": "Go Engineer"}]


def test_unknown_provider_is_an_error():
    with pytest.raises(KeyError):
        providers.fetch("nope", "acme")
