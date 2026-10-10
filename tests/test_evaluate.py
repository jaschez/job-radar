"""The evaluation prompt carries the profile, the rules and the postings; the answer is validated."""
import json

import evaluate
import llm

BATCH = [{"job_id": "gh:a:1", "title": "Backend"}, {"job_id": "gh:a:2", "title": "Data"}]


def test_prompt_has_profile_rules_families_and_postings(cfg, _workspace):
    (_workspace / "profile.md").write_text("Five years of Python.")
    p = evaluate.build_prompt(cfg, BATCH)
    assert "Five years of Python." in p and "Minimum total compensation: 70,000" in p
    assert "Backend / Software Engineering, Data / Platform" in p and "Frontend" not in p.split("Role families searched:")[1].split("\n")[0]
    assert '"job_id": "gh:a:2"' in p and "Postings (2)" in p


def test_missing_profile_is_said_not_invented(cfg):
    assert "(no profile provided)" in evaluate.build_prompt(cfg, BATCH)


def test_run_validates_and_writes(cfg, tmp_path, monkeypatch):
    (tmp_path / "to_evaluate.json").write_text(json.dumps(BATCH))
    monkeypatch.setattr(llm, "complete", lambda p, **kw: "```json\n" + json.dumps(
        [{"job_id": "gh:a:1", "fit": "High"}, {"job_id": "gh:zzz", "fit": "High"}, {"job_id": "gh:a:2", "fit": "?"}]) + "\n```")
    cfg["evaluation"]["backend"] = "claude-cli"
    assert evaluate.run(cfg, tmp_path) == 0
    assert [e["job_id"] for e in json.loads((tmp_path / "evals.json").read_text())] == ["gh:a:1"]
