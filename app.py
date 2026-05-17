import asyncio
import json
from typing import Dict, List, Tuple
import time

from hyperliquid.info import Info
from hyperliquid.utils import constants


async def get_liquidity_and_spread(levels: List, mid_price: float) -> Tuple[float, float]:
    """
    Calculate:
      - Bid liquidity (USD notional in top ~20 levels)
      - Ask liquidity
      - Spread %
    """
    if not levels or len(levels) < 2:
        return 0.0, 0.0, 0.0

    bids = levels[0]  # Green side
    asks = levels[1]  # Red side

    bid_liquidity = 0.0
    ask_liquidity = 0.0

    # Best bid and ask
    best_bid = float(bids[0]["px"]) if bids else 0
    best_ask = float(asks[0]["px"]) if asks else 0

    if best_bid == 0 or best_ask == 0:
        return 0.0, 0.0, 0.0

    spread_pct = (best_ask - best_bid) / best_bid * 100

    # Calculate notional liquidity (top levels)
    for level in bids[:15]:  # ~ top 15 levels
        px = float(level["px"])
        sz = float(level["sz"])
        bid_liquidity += px * sz

    for level in asks[:15]:
        px = float(level["px"])
        sz = float(level["sz"])
        ask_liquidity += px * sz

    total_liquidity = bid_liquidity + ask_liquidity

    return total_liquidity, spread_pct, best_bid


async def main():
    # Use mainnet
    info = Info(constants.MAINNET_API_URL, skip_ws=True)

    print("Fetching all perpetual markets...\n")
    meta_and_ctxs = info.meta_and_asset_ctxs()

    if not meta_and_ctxs or len(meta_and_ctxs) != 2:
        print("Failed to fetch meta")
        return

    meta, ctxs = meta_and_ctxs
    volume_map = {asset["name"]: float(ctx.get("dayNtlVlm", 0)) for asset, ctx in zip(meta["universe"], ctxs)}

    results = []

    for asset in meta["universe"]:
        coin = asset["name"]
        vol = volume_map.get(coin, 0)
        if vol <= 1_000_000:
            continue

        try:
            # Get L2 Order Book
            book = info.l2_snapshot(coin)
            
            if not book or "levels" not in book:
                continue

            # Get mid price
            mids = info.all_mids()
            mid = float(mids.get(coin, 0))

            if mid == 0:
                continue

            total_liq, spread_pct, best_bid = await get_liquidity_and_spread(
                book["levels"], mid
            )

            results.append({
                "coin": coin,
                "spread_%": round(spread_pct, 4),
                "liquidity_$": round(total_liq, 0),
                "volume_$": round(vol, 0),
                "best_bid": best_bid,
                "mid": mid
            })

            print(f"{coin:>8} | Vol: ${vol:,.0f} | Liq: ${total_liq:,.0f} | Spread: {spread_pct:6.3f}%")

        except Exception as e:
            print(f"Error on {coin}: {e}")
            continue

        # Be nice to the API (rate limit friendly)
        await asyncio.sleep(0.15)

    # Sort by spread descending
    results.sort(key=lambda x: x["spread_%"], reverse=True)

    print("\n" + "="*80)
    print("TOP COINS WITH > $1M 24H VOLUME (Highest Spread First)")
    print("="*80)

    for r in results[:15]:  # Top 15
        print(f"{r['coin']:>8} | Spread: {r['spread_%']:6.3f}% | "
              f"Vol: ${r['volume_$']:,.0f} | Liq: ${r['liquidity_$']:,.0f} | Mid ~ ${r['mid']:.4f}")


if __name__ == "__main__":
    asyncio.run(main())