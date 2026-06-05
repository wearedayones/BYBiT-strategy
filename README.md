# bybit-quant-agent

A minimal quantitative trading agent for Bybit. The MCP handles all exchange work —
klines, market data, account, positions, order placement, websocket streams,
copy-trading. This repo keeps only what can't be safely outsourced: the **thinking**
(`skills/`) and the **math that defines truth** (`engine/`).

> The MCP executes, but it never decides. `engine/` stays pure Python with tests,
> because the moment the gate's math runs through the LLM or an external tool,
> "it passed" stops meaning anything.

## Layout

```
bybit-quant-agent/
├── AGENTS.md               # modes, MCP auth, hard risk limits, kill switch
├── config/
│   ├── settings.yaml       # mode, symbols, timeframe, research budget
│   └── acceptance.yaml     # the gate: min OOS Sharpe, max DD, PBO ceiling, …
├── skills/strategy/        # the thinking
│   ├── SKILL.md            # router: pick family → pick workflow
│   ├── references/         # futures · spot · copy-trading · trading-bots
│   ├── workflows/          # research.md · live-loop.md
│   └── subagents/          # trade-validator.md
├── engine/                 # deterministic — what MCP and the LLM must NOT compute
│   ├── backtest.py         # consumes MCP klines; fees + slippage + funding
│   ├── validation.py       # CPCV + purge/embargo + deflated Sharpe + PBO + regime
│   └── gate.py             # acceptance.yaml → promote/reject + champion/challenger + decay
├── strategies/
│   ├── spec.py             # schema with a REQUIRED thesis field
│   ├── promoted/           # saved passers (live runs only these)
│   └── candidates.jsonl    # every trial + result (feeds trial-aware PBO/DSR)
├── scripts/                # research.sh · trade.sh · kill_switch.sh
└── tests/                  # test_validation.py · test_backtest.py
```

## The two design upgrades

1. **`engine/validation.py`** — CPCV (combinatorial purged cross-validation) +
   deflated Sharpe ratio + probability of backtest overfitting. This is the integrity
   gate against luck and multiple-testing.
2. **`strategies/spec.py`** — a **required `thesis` field** enforces hypothesis-first
   research. No thesis (or boilerplate) → the spec won't construct.

`engine/gate.py` absorbs champion-vs-challenger and decay monitoring — promoting a
challenger over an incumbent and retiring a decayed strategy are just the same gate run
on fresh data.

## Quick start

```bash
pip install -e ".[dev]"
pytest                          # run the engine test suite

export BYBIT_API_KEY="..."      # see AGENTS.md for full auth + MCP setup
export BYBIT_API_SECRET="..."
export BYBIT_TESTNET="true"

bash scripts/research.sh        # find & validate strategies
bash scripts/trade.sh           # run promoted strategies live
bash scripts/kill_switch.sh     # emergency flatten + HALT
```

See `AGENTS.md` for modes, hard risk limits, and the kill switch contract.
