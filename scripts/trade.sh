#!/usr/bin/env bash
# trade.sh — Launch the agent in live mode.
# Runs ONLY strategies in strategies/promoted/. Refuses to start if that is empty
# or if the HALT flag is set.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$REPO_ROOT/.halt" ]]; then
    echo "HALT flag is set. Remove $REPO_ROOT/.halt before running."
    exit 1
fi

PROMOTED_COUNT="$(find "$REPO_ROOT/strategies/promoted" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')"
if [[ "$PROMOTED_COUNT" -eq 0 ]]; then
    echo "No promoted strategies found. Run research mode first."
    exit 1
fi

cd "$REPO_ROOT"
python3 - <<'PY'
import pathlib, yaml
cfg = pathlib.Path("config/settings.yaml")
d = yaml.safe_load(cfg.read_text())
d["mode"] = "live"
cfg.write_text(yaml.dump(d, sort_keys=False))
PY

echo "Mode set to live with $PROMOTED_COUNT promoted strategy(ies)."
echo "Start the agent; it will route to skills/strategy/workflows/live-loop.md."
