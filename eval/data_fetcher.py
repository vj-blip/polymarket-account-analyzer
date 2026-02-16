"""Fetch wallet data from AlgoArena for analysis and eval."""

from __future__ import annotations
import httpx
from pydantic import BaseModel
from typing import Optional


ALGOARENA_API = "http://34.67.141.159:8000"


class WalletProfile(BaseModel):
    wallet: str
    username: Optional[str] = None
    pnl_all_time: float = 0
    volume_pnl_ratio: Optional[float] = None
    trades_l30: Optional[int] = None
    rank: Optional[int] = None
    closed_winrate: Optional[float] = None
    sharpe_score: Optional[float] = None


class Position(BaseModel):
    """A resolved or open position from /api/algos/positions/{wallet}."""
    tb: float = 0           # total bought (USDC)
    ap: float = 0           # average price
    cp: float = 0           # current/close price
    pnl: float = 0          # profit/loss
    ts: int = 0             # timestamp
    t: str = ""             # market title
    cid: str = ""           # condition id
    o: str = ""             # outcome


async def get_top_wallets(limit: int = 50) -> list[WalletProfile]:
    """Get top wallets by PnL from AlgoArena rankings."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(
                f"{ALGOARENA_API}/api/rankings/table",
                params={"limit": limit},
            )
            resp.raise_for_status()
            data = resp.json()
            rankings = data.get("rankings", data) if isinstance(data, dict) else data
            return [WalletProfile(**r) for r in rankings]
        except Exception:
            return []


async def get_wallet_positions(wallet: str) -> list[Position]:
    """Get all positions (resolved + open) for a wallet."""
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.get(f"{ALGOARENA_API}/api/algos/positions/{wallet}")
            resp.raise_for_status()
            data = resp.json()
            return [Position(**p) for p in data]
        except Exception:
            return []


async def get_wallet_pnl_history(wallet: str) -> list[dict]:
    """Get daily PnL time series for a wallet."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(f"{ALGOARENA_API}/api/algos/pnl/{wallet}")
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return []


async def get_wallet_ranking(wallet: str) -> Optional[WalletProfile]:
    """Get ranking info for a specific wallet (searches rankings table)."""
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(f"{ALGOARENA_API}/api/wallets/{wallet}/pnl")
            resp.raise_for_status()
            data = resp.json()
            current = data.get("current", {})
            return WalletProfile(
                wallet=wallet,
                pnl_all_time=current.get("pnl_all_time", 0),
                rank=current.get("rank"),
            )
        except Exception:
            return None
