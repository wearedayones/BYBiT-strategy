#!/usr/bin/env bash
# start.sh — Start the Multi-Agent Liquidity Sweep & Bracket strategy.
# Checks prerequisites, then hands off to the agent.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$REPO_ROOT/.halt" ]]; then
    echo "HALT flag is set. Remove $REPO_ROOT/.halt before starting."
    exit 1
fi

if [[ -z "${BYBIT_API_KEY:-}" || -z "${BYBIT_API_SECRET:-}" ]]; then
    echo "ERROR: BYBIT_API_KEY and BYBIT_API_SECRET must be set."
    echo "       For testnet: export BYBIT_TESTNET=true"
    exit 1
fi

echo "Prerequisites OK. Handing off to agent."
echo "The agent will load AGENTS.md and follow skills/sweep-bracket/SKILL.md."
