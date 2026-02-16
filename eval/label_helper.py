"""Helper to label wallets for ground truth.

Pulls wallet data from AlgoArena and assists with labeling.

Usage:
    python -m eval.label_helper 0xADDRESS
    python -m eval.label_helper --top 10  # Label top 10 by PnL
"""

from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

import httpx

from .models import GroundTruth, StrategyType, Difficulty, EvidencePoint
from .data_fetcher import ALGOARENA_API


LABELED_PATH = Path(__file__).parent / "ground_truth" / "labeled.json"


async def fetch_wallet_summary(wallet: str) -> dict:
    """Fetch comprehensive wallet data for labeling."""
    async with httpx.AsyncClient(timeout=30) as client:
        # Profile
        try:
            resp = await client.get(f"{ALGOARENA_API}/api/profile/{wallet}")
            profile = resp.json() if resp.status_code == 200 else {}
        except Exception:
            profile = {}
        
        # Activities
        try:
            resp = await client.get(f"{ALGOARENA_API}/api/activities/{wallet}", params={"limit": 500})
            activities = resp.json() if resp.status_code == 200 else []
        except Exception:
            activities = []
    
    # Compute basic stats
    if activities:
        markets = set()
        buy_count = sell_count = 0
        total_size = 0
        timestamps = []
        
        for a in activities:
            markets.add(a.get("title", ""))
            if a.get("side") == "BUY":
                buy_count += 1
            else:
                sell_count += 1
            total_size += float(a.get("usdc_size", 0))
            timestamps.append(int(a.get("timestamp", 0)))
        
        timestamps.sort()
        avg_size = total_size / len(activities) if activities else 0
    else:
        markets = set()
        buy_count = sell_count = 0
        avg_size = 0
        timestamps = []
    
    return {
        "profile": profile,
        "trade_count": len(activities),
        "unique_markets": len(markets),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "avg_trade_size": avg_size,
        "sample_trades": activities[:20],
        "market_names": list(markets)[:20],
    }


def print_wallet_summary(wallet: str, data: dict):
    """Pretty print wallet data for human labeling."""
    p = data["profile"]
    print(f"\n{'='*70}")
    print(f"WALLET: {wallet}")
    print(f"Username: {p.get('username', 'unknown')}")
    print(f"{'='*70}")
    print(f"  PnL Total:    ${p.get('pnl_total', 0):>15,.2f}")
    print(f"  Volume Total: ${p.get('volume_total', 0):>15,.2f}")
    print(f"  Win Rate 30d: {p.get('win_rate_30d', 'N/A')}")
    print(f"  Rank:         {p.get('rank', 'N/A')}")
    print(f"  Trades:       {data['trade_count']}")
    print(f"  Markets:      {data['unique_markets']}")
    print(f"  Buy/Sell:     {data['buy_count']}/{data['sell_count']}")
    print(f"  Avg Size:     ${data['avg_trade_size']:,.0f}")
    
    print(f"\n  Sample Markets:")
    for m in data["market_names"][:10]:
        print(f"    • {m}")
    
    print(f"\n  Sample Trades:")
    for t in data["sample_trades"][:10]:
        print(f"    {t.get('side', '?'):4s} ${t.get('usdc_size', 0):>10,.0f} @ {t.get('price', 0):.3f} | {t.get('title', '?')[:50]}")
    
    print(f"\n{'='*70}")


def load_labeled() -> list[dict]:
    if LABELED_PATH.exists():
        with open(LABELED_PATH) as f:
            return json.load(f)
    return []


def save_labeled(data: list[dict]):
    with open(LABELED_PATH, 'w') as f:
        json.dump(data, f, indent=2)


async def interactive_label(wallet: str):
    """Interactive labeling session for one wallet."""
    data = await fetch_wallet_summary(wallet)
    print_wallet_summary(wallet, data)
    
    print("\nStrategy types:")
    for i, st in enumerate(StrategyType):
        print(f"  {i}: {st.value}")
    
    choice = input("\nPrimary strategy (number or name): ").strip()
    try:
        strategy = list(StrategyType)[int(choice)]
    except (ValueError, IndexError):
        strategy = StrategyType(choice)
    
    diff_input = input("Difficulty (easy/medium/hard): ").strip().lower()
    difficulty = Difficulty(diff_input)
    
    notes = input("Notes (why this strategy?): ").strip()
    
    # Evidence points
    evidence = []
    print("\nAdd evidence points (empty line to stop):")
    while True:
        desc = input("  Evidence: ").strip()
        if not desc:
            break
        cat = input("  Category (timing/sizing/correlation/market_selection/other): ").strip()
        imp = float(input("  Importance (0-1): ").strip())
        evidence.append(EvidencePoint(description=desc, category=cat, importance=imp))
    
    gt = GroundTruth(
        wallet=wallet,
        username=data["profile"].get("username"),
        primary_strategy=strategy,
        difficulty=difficulty,
        evidence_points=evidence,
        notes=notes,
        pnl_total=float(data["profile"].get("pnl_total", 0)),
        volume_total=float(data["profile"].get("volume_total", 0)),
        win_rate_30d=data["profile"].get("win_rate_30d"),
    )
    
    # Save
    labeled = load_labeled()
    labeled.append(gt.model_dump())
    save_labeled(labeled)
    print(f"\n✅ Saved! Total labeled: {len(labeled)}")


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m eval.label_helper 0xADDRESS")
        print("       python -m eval.label_helper --top 10")
        return
    
    if sys.argv[1] == "--top":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        candidates = json.load(open(Path(__file__).parent / "ground_truth" / "unlabeled_candidates.json"))
        for c in candidates[:n]:
            await interactive_label(c["wallet"])
    else:
        await interactive_label(sys.argv[1])


if __name__ == "__main__":
    asyncio.run(main())
