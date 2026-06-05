#!/usr/bin/env bash
# kill_switch.sh — Emergency position flattener.
#
# This script is INTENTIONALLY simple and does not depend on the agent.
# It flips the HALT flag locally, then flattens via a thin REST helper.
# Usage: bash scripts/kill_switch.sh [reason]
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HALT_FILE="$REPO_ROOT/.halt"
LOG_FILE="$REPO_ROOT/.halt.log"
REASON="${1:-manual_trigger}"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "=== KILL SWITCH ACTIVATED at $TIMESTAMP ===" | tee -a "$LOG_FILE"
echo "Reason: $REASON" | tee -a "$LOG_FILE"

# Step 1: Write HALT flag atomically (temp file -> mv). This happens FIRST so
# the agent halts even if the REST calls below fail.
echo "$TIMESTAMP $REASON" > "${HALT_FILE}.tmp"
mv "${HALT_FILE}.tmp" "$HALT_FILE"
echo "HALT flag written to $HALT_FILE" | tee -a "$LOG_FILE"

# Step 2 & 3: Cancel orders and flatten positions via direct REST (no MCP, no agent).
if [[ -z "${BYBIT_API_KEY:-}" || -z "${BYBIT_API_SECRET:-}" ]]; then
    echo "WARNING: BYBIT_API_KEY / BYBIT_API_SECRET not set. Skipping REST flatten." | tee -a "$LOG_FILE"
    echo "         Positions must be closed manually on the exchange." | tee -a "$LOG_FILE"
else
    echo "Cancelling all open orders..." | tee -a "$LOG_FILE"
    python3 "$REPO_ROOT/scripts/_flat_positions.py" --action cancel_orders 2>&1 | tee -a "$LOG_FILE" \
        || echo "WARNING: order cancellation failed — check manually." | tee -a "$LOG_FILE"

    echo "Flattening all positions..." | tee -a "$LOG_FILE"
    python3 "$REPO_ROOT/scripts/_flat_positions.py" --action flatten_all 2>&1 | tee -a "$LOG_FILE" \
        || echo "WARNING: position flatten failed — check manually." | tee -a "$LOG_FILE"
fi

echo "Kill switch complete at $(date -u +%Y-%m-%dT%H:%M:%SZ)." | tee -a "$LOG_FILE"
echo "To resume trading, delete $HALT_FILE manually." | tee -a "$LOG_FILE"
