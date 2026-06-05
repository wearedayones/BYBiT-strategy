#!/usr/bin/env bash
# research.sh — Launch the agent in research mode.
# Generates, backtests, validates, and gates strategies. Places NO real orders.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$REPO_ROOT/.halt" ]]; then
    echo "HALT flag is set. Remove $REPO_ROOT/.halt before running."
    exit 1
fi

cd "$REPO_ROOT"
python3 - <<'PY'
import pathlib, yaml
cfg = pathlib.Path("config/settings.yaml")
d = yaml.safe_load(cfg.read_text())
d["mode"] = "research"
cfg.write_text(yaml.dump(d, sort_keys=False))
PY

echo "Mode set to research. Start the agent and follow skills/strategy/SKILL.md."
echo "The agent will route to skills/strategy/workflows/research.md."
