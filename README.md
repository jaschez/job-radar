# job-radar

A self-hosted radar for job postings. Every morning it reads the job boards of the
companies you target (and any other source you plug in), keeps the full history in
SQLite, filters by geography, role family and exclusions, has Claude evaluate the best new
postings against your profile, and e-mails you only when something fits. On Mondays it
sends a weekly review.

```
 sources ──► geography / role family / exclusions ──► duplicates ──► SQLite history
 (plugins)                                                           (closures, reopenings)
                                                                           │
 e-mail ◄── report ◄── Claude evaluation against your profile ◄── pre-score (top N/day)
```

## What it does

- **Public ATS boards out of the box.** Greenhouse, Lever (US and EU), Ashby, Workable,
  SmartRecruiters, Recruitee and Personio: the same endpoints the companies' careers
  pages use, no credentials. More providers, and whole new sources (job boards,
  aggregators, national employment services), are plugins.
- **Deterministic filters first.** Geography with five verdicts (accepted city,
  compatible remote, accepted relocation, relocation not considered yet, out of scope),
  role families by title, exclusions by title. All regular expressions in your config.
- **History that never forgets.** A posting that disappears from a board read
  successfully becomes Closed (and reopens if it comes back); a failed read closes
  nothing. Re-posts of the same role in several countries are marked as duplicates.
- **Evaluation against your profile.** Your profile (`profile.md`) and your hard rules
  (minimum compensation, languages, relocation...) go into a generic prompt; Claude
  answers fit, priority, why it fits, gaps, a compensation estimate and notes, in English
  or Spanish. The answer is validated before it touches the database.
- **Weekly review.** Where the fit concentrates, what to prioritise, what closed, and
  optionally a check by hand (Claude Code with web access) of companies without an API.

## Quick start

```bash
git clone https://github.com/jaschez/job-radar && cd job-radar
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

cp -r examples/workspace ~/my-job-radar        # your profile, targets and history live here
cp ~/my-job-radar/secrets.env.example ~/my-job-radar/secrets.env
$EDITOR ~/my-job-radar/{config.yaml,profile.md,companies.yaml,secrets.env}
export RADAR_WORKSPACE=~/my-job-radar

.venv/bin/python tools/probe_ats.py             # find the board slugs of candidate companies
.venv/bin/python radar/run.py                   # a first sweep (no e-mail)
scripts/daily.sh                                # the full daily run
scripts/install-systemd.sh ~/my-job-radar --enable   # every day at 07:30
```

Python 3.10+. The evaluation needs either the Claude Code CLI (`claude`) or an Anthropic
API key; with `evaluation.backend: none` the radar still filters, scores and e-mails.

## The workspace

| Path | What |
|---|---|
| `config.yaml` | geography, role families, exclusions, rules, sources, notifications ([example](examples/workspace/config.yaml)) |
| `profile.md` | the candidate profile the evaluator reads ([template](examples/workspace/profile.md)) |
| `companies.yaml` | target companies and their boards ([example](examples/workspace/companies.yaml)) |
| `candidates.yaml` | companies to probe before adding them |
| `tracker_seed.yaml` | optional rows for the tracker workbook (applications, contacts, plan) |
| `secrets.env` | SMTP and API credentials |
| `plugins/` | your own sources and ATS providers |
| `data/tracker.db`, `out/`, `logs/` | history, daily outputs, logs |

Select it with `RADAR_WORKSPACE` or `--workspace` (default `./workspace`, git-ignored).
Several workspaces can share one checkout, one per person.

## Sources

```yaml
sources:
  ats_boards:                       # built in
    companies_file: companies.yaml
    providers:
      my_ats: {path: plugins/my_ats.py}   # an extra ATS: fetch(slug, with_content=False)
  my_board:                         # a whole new source
    path: plugins/my_board.py
    url: https://...
```

A source returns *boards*: places read in full, so the radar knows what to close when a
posting disappears. The contract is in [`radar/sources/__init__.py`](radar/sources/__init__.py)
and a complete JSON job board example in
[`examples/plugins/example_source.py`](examples/plugins/example_source.py).

## Evaluation, e-mail and extras

| Setting | Options |
|---|---|
| `evaluation.backend` | `claude-cli` (Claude Code, `model: sonnet`), `anthropic-api` (`model: claude-opus-5-5`), `none` |
| `evaluation.rules` | hard rules that override everything (minimum pay, languages, relocation...) |
| `notify.backend` | `smtp`, `claude-gmail` (Claude Code with the Gmail connector), `file` |
| `language` | `en`, `es` |
| `manual_check.enabled` | weekly check by hand of companies without an API (Claude Code with WebFetch) |
| `sheets.enabled` | EXPERIMENTAL: keep a Google Sheets tracker in sync through Claude Code's Sheets connector |

`tools/build_tracker.py` builds a tracker workbook (Dashboard, Companies, Job Leads,
Applications, Networking, Development Plan, Search Config) from the database; upload it
to Google Drive to use it as a sheet.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The ATS clients are tested against recorded response shapes; the `anthropic-api` backend
and the Google Sheets sync have not been run against the live services by the tests.

## License

MIT
