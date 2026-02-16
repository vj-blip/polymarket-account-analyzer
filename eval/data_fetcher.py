"""Fetch wallet data from AlgoArena for analysis and eval."""

from __future__ import annotations
import httpx
from pydantic import BaseModel
from typing import Optional


ALGOARENA_API = "http://34.67.141.159:8000"


class WalletProfile(BaseModel):
    wallet: str
    username: Optional[str] = None
    pnl_total: float = 0
    volume_total: float = 0
    win_rate_30d: Optional[float] = None
    rank: Optional[int] = None


class Trade(BaseModel):
    tx_hash: str
    timestamp: int
    type: str
    side: str
    size: float
    usdc_size: float
    price: float
    title: str
    outcome: str


async def get_top_wallets(limit: int = 50) -> list[WalletProfile]:
    """Get top wallets by PnL from AlgoArena."""
    async with httpx.AsyncClient(timeout=30) as client:
        # Try API first
        try:
            resp = await client.get(f"{ALGOARENA_API}/api/leaderboard", params={"limit": limit})
            resp.raise_for_status()
            data = resp.json()
            return [WalletProfile(**w) for w in data]
        except Exception:
            pass
        
        # Fallback: direct DB query via API
        try:
            resp = await client.get(f"{ALGOARENA_API}/api/profiles", params={"limit": limit, "sort": "-pnl_total"})
            resp.raise_for_status()
            data = resp.json()
            return [WalletProfile(**w) for w in data]
        except Exception:
            return []


async def get_wallet_trades(wallet: str, limit: int = 500) -> list[Trade]:
    """Get recent trades for a wallet."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                f"{ALGOARENA_API}/api/activities/{wallet}",
                params={"limit": limit}
            )
            resp.raise_for_status()
            data = resp.json()
            return [Trade(**t) for t in data]
        except Exception:
            return []


async def get_wallet_profile(wallet: str) -> Optional[WalletProfile]:
    """Get profile for a specific wallet."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(f"{ALGOARENA_API}/api/profile/{wallet}")
            resp.raise_for_status()
            return WalletProfile(**resp.json())
        except Exception:
            return None
