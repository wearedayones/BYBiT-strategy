"""Thin pybit REST helper — cancel all orders and flatten all positions."""
from __future__ import annotations

import argparse, os, sys


def _client():
    from pybit.unified_trading import HTTP
    return HTTP(
        api_key=os.environ["BYBIT_API_KEY"],
        api_secret=os.environ["BYBIT_API_SECRET"],
        testnet=os.environ.get("BYBIT_TESTNET", "true").lower() in ("1", "true", "yes"),
    )


def cancel_orders(client) -> None:
    resp = client.cancel_all_orders(category="linear", settleCoin="USDT")
    print(f"cancel_all_orders: retCode={resp.get('retCode')} retMsg={resp.get('retMsg')}")


def flatten_all(client) -> None:
    positions = client.get_positions(category="linear", settleCoin="USDT")
    rows = positions.get("result", {}).get("list", [])
    closed = 0
    for pos in rows:
        size = float(pos.get("size") or 0)
        if size == 0:
            continue
        close_side = "Sell" if pos["side"] == "Buy" else "Buy"
        client.place_order(
            category="linear", symbol=pos["symbol"],
            side=close_side, orderType="Market", qty=str(size), reduceOnly=True,
        )
        closed += 1
        print(f"closed {pos['symbol']} {pos['side']} size={size}")
    print(f"flatten_all: closed {closed} position(s)")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
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
