#!/usr/bin/env bash
# Daily run: sweep -> evaluation -> e-mail if something is relevant; on the weekly review
# day (config `weekly_review_day`, 1 = Monday, default) also the manual check and the
# weekly e-mail. Idempotent within the day. Workspace: $RADAR_WORKSPACE (default ./workspace).
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export RADAR_WORKSPACE="${RADAR_WORKSPACE:-$REPO/workspace}"
PY="$REPO/.venv/bin/python"; [ -x "$PY" ] || PY=python3
read -r TODAY DOW WEEKLY_DAY < <("$PY" -c "
import sys, datetime as dt; sys.path.insert(0, '$REPO/radar'); import workspace
cfg = workspace.load_config(); d = workspace.today(cfg)
print(d, dt.date.fromisoformat(d).isoweekday(), cfg.get('weekly_review_day', 1))") || exit 1
OUT="$RADAR_WORKSPACE/out/$TODAY"
mkdir -p "$OUT" "$RADAR_WORKSPACE/logs"
exec >>"$RADAR_WORKSPACE/logs/$TODAY.log" 2>&1
echo "== $(date -Is) daily $TODAY"

exec 9>"$RADAR_WORKSPACE/.radar.lock"
flock -n 9 || { echo "another run is in progress"; exit 0; }

if [ ! -s "$OUT/to_evaluate.json" ]; then
  "$PY" "$REPO/radar/run.py" --date "$TODAY" || { echo "run.py failed"; exit 1; }
fi
"$PY" "$REPO/radar/evaluate.py" --date "$TODAY" || echo "evaluation failed; the report goes without it"

if [ ! -f "$OUT/.sent_daily" ]; then
  "$PY" "$REPO/radar/report.py" daily --date "$TODAY"
  RC=$?
  if [ $RC -eq 0 ]; then
    "$PY" "$REPO/radar/notify.py" "$OUT/" && "$PY" "$REPO/radar/report.py" mark --date "$TODAY" && touch "$OUT/.sent_daily"
  else
    echo "no daily e-mail (rc=$RC)"
  fi
fi

"$PY" "$REPO/radar/sheets.py" --date "$TODAY" || echo "sheet sync failed"

if [ "$DOW" = "$WEEKLY_DAY" ] && [ ! -f "$OUT/.sent_weekly" ]; then
  "$PY" "$REPO/radar/manual_check.py" --date "$TODAY" || echo "manual check failed"
  "$PY" "$REPO/radar/report.py" weekly --date "$TODAY" && \
    "$PY" "$REPO/radar/notify.py" "$OUT/weekly_" && touch "$OUT/.sent_weekly"
fi
echo "== end $(date -Is)"
