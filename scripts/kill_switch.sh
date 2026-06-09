#!/usr/bin/env bash
# kill_switch.sh — Emergency HALT and full flatten.
# Works without the agent. No Python dep in the shell layer.
# Usage: bash scripts/kill_switch.sh [reason]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HALT_FILE="$REPO_ROOT/.halt"
LOG_FILE="$REPO_ROOT/.halt.log"
REASON="${1:-manual_trigger}"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "=== KILL SWITCH at $TS ===" | tee -a "$LOG_FILE"
echo "Reason: $REASON" | tee -a "$LOG_FILE"

# Step 1: HALT flag first (atomic)
echo "$TS $REASON" > "${HALT_FILE}.tmp"
mv "${HALT_FILE}.tmp" "$HALT_FILE"
echo "HALT flag written." | tee -a "$LOG_FILE"

# Step 2 & 3: Cancel orders + flatten positions
if [[ -z "${BYBIT_API_KEY:-}" || -z "${BYBIT_API_SECRET:-}" ]]; then
    echo "WARNING: API keys not set. Flatten positions manually." | tee -a "$LOG_FILE"
else
    echo "Cancelling orders..." | tee -a "$LOG_FILE"
    python3 "$REPO_ROOT/scripts/_flat_positions.py" --action cancel_orders 2>&1 | tee -a "$LOG_FILE" \
        || echo "WARNING: cancel failed — check exchange." | tee -a "$LOG_FILE"

    echo "Flattening positions..." | tee -a "$LOG_FILE"
    python3 "$REPO_ROOT/scripts/_flat_positions.py" --action flatten_all 2>&1 | tee -a "$LOG_FILE" \
        || echo "WARNING: flatten failed — check exchange." | tee -a "$LOG_FILE"
fi

echo "Done. Remove $HALT_FILE manually to resume." | tee -a "$LOG_FILE"
