"""
Thin pybit REST helper for the kill switch.

Reads BYBIT_API_KEY / BYBIT_API_SECRET / BYBIT_TESTNET from the environment and
either cancels all open orders or flattens (market-closes) every open position.

Kept deliberately minimal and dependency-light so kill_switch.sh can rely on it
without the agent or the MCP being involved.
"""
from __future__ import annotations

import argparse
import os
import sys


def _client():
    from pybit.unified_trading import HTTP

    key = os.environ["BYBIT_API_KEY"]
    secret = os.environ["BYBIT_API_SECRET"]
    testnet = os.environ.get("BYBIT_TESTNET", "true").lower() in ("1", "true", "yes")
    return HTTP(api_key=key, api_secret=secret, testnet=testnet)


def cancel_orders(client) -> None:
    """Cancel all open orders for linear perpetuals."""
    resp = client.cancel_all_orders(category="linear", settleCoin="USDT")
    print(f"cancel_all_orders -> retCode={resp.get('retCode')} retMsg={resp.get('retMsg')}")


def flatten_all(client) -> None:
    """Market-close every open linear position."""
    positions = client.get_positions(category="linear", settleCoin="USDT")
    rows = positions.get("result", {}).get("list", [])
    closed = 0
    for pos in rows:
        size = float(pos.get("size", 0) or 0)
        if size == 0:
            continue
        side = pos["side"]                       # "Buy" or "Sell"
        close_side = "Sell" if side == "Buy" else "Buy"
        client.place_order(
            category="linear",
            symbol=pos["symbol"],
            side=close_side,
            orderType="Market",
            qty=str(size),
            reduceOnly=True,
        )
        closed += 1
        print(f"flattened {pos['symbol']} {side} size={size}")
    print(f"flatten_all -> closed {closed} position(s)")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Kill-switch REST helper")
    parser.add_argument("--action", required=True, choices=["cancel_orders", "flatten_all"])
    args = parser.parse_args(argv)

    client = _client()
    if args.action == "cancel_orders":
        cancel_orders(client)
    else:
        flatten_all(client)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
