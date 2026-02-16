"""Flow analysis: buy/sell ratio, accumulation/distribution, directional bias."""

from __future__ import annotations
from datetime import datetime, timezone
from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class FlowAnalysis:
    """Results of order flow analysis."""
    total_positions: int = 0
    total_volume_bought: float = 0.0
    total_pnl: float = 0.0
    # Win/loss
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    # PnL distribution
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0  # gross profit / gross loss
    expectancy: float = 0.0  # avg pnl per trade
    # Accumulation patterns (multiple entries in same market)
    multi_entry_markets: int = 0  # markets with >1 position
    avg_entries_per_market: float = 0.0
    # Directional flow over time
    monthly_pnl: dict[str, float] = field(default_factory=dict)
    monthly_volume: dict[str, float] = field(default_factory=dict)
    trend_direction: str = ""  # "improving", "declining", "stable"
    # Risk metrics
    max_single_loss: float = 0.0
    max_single_win: float = 0.0
    risk_reward_ratio: float = 0.0  # avg_win / abs(avg_loss)
    # Signals
    signals: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = ["=== FLOW ANALYSIS ==="]
        lines.append(f"Total volume: ${self.total_volume_bought:,.0f}, PnL: ${self.total_pnl:,.0f}")
        lines.append(f"Win rate: {self.win_rate:.1%} ({self.win_count}W/{self.loss_count}L)")
        lines.append(f"Avg win: ${self.avg_win:,.0f}, Avg loss: ${self.avg_loss:,.0f}")
        lines.append(f"Profit factor: {self.profit_factor:.2f}, Expectancy: ${self.expectancy:,.0f}/trade")
        lines.append(f"Risk/reward ratio: {self.risk_reward_ratio:.2f}")
        lines.append(f"Max win: ${self.max_single_win:,.0f}, Max loss: ${self.max_single_loss:,.0f}")
        lines.append(f"Multi-entry markets: {self.multi_entry_markets}, Avg entries/market: {self.avg_entries_per_market:.1f}")
        lines.append(f"Trend: {self.trend_direction}")
        if self.signals:
            lines.append(f"Signals: {'; '.join(self.signals)}")
        return "\n".join(lines)


def analyze_flow(positions: list[dict]) -> FlowAnalysis:
    """Analyze order flow and accumulation patterns."""
    result = FlowAnalysis(total_positions=len(positions))
    if not positions:
        return result

    result.total_volume_bought = sum(p.get("tb", 0) for p in positions)
    pnls = [p.get("pnl", 0) for p in positions]
    result.total_pnl = sum(pnls)

    # Win/loss
    wins = [p for p in positions if p.get("pnl", 0) > 0]
    losses = [p for p in positions if p.get("pnl", 0) <= 0]
    result.win_count = len(wins)
    result.loss_count = len(losses)
    result.win_rate = len(wins) / len(positions) if positions else 0

    if wins:
        win_pnls = [p["pnl"] for p in wins]
        result.avg_win = sum(win_pnls) / len(win_pnls)
        result.max_single_win = max(win_pnls)
    if losses:
        loss_pnls = [p["pnl"] for p in losses]
        result.avg_loss = sum(loss_pnls) / len(loss_pnls)
        result.max_single_loss = min(loss_pnls)

    # Profit factor
    gross_profit = sum(p["pnl"] for p in wins) if wins else 0
    gross_loss = abs(sum(p["pnl"] for p in losses)) if losses else 1
    result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # Expectancy
    result.expectancy = result.total_pnl / len(positions) if positions else 0

    # Risk/reward
    if result.avg_loss != 0:
        result.risk_reward_ratio = result.avg_win / abs(result.avg_loss)

    # Accumulation: multiple entries in same market
    market_entries: dict[str, int] = defaultdict(int)
    for p in positions:
        cid = p.get("cid", "")
        if cid:
            market_entries[cid] += 1
    result.multi_entry_markets = sum(1 for v in market_entries.values() if v > 1)
    if market_entries:
        result.avg_entries_per_market = len(positions) / len(market_entries)

    # Monthly flow
    for p in positions:
        ts = p.get("ts", 0)
        if ts > 0:
            month = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m")
            result.monthly_pnl[month] = result.monthly_pnl.get(month, 0) + p.get("pnl", 0)
            result.monthly_volume[month] = result.monthly_volume.get(month, 0) + p.get("tb", 0)

    # Trend
    if len(result.monthly_pnl) >= 3:
        months = sorted(result.monthly_pnl.keys())
        recent = [result.monthly_pnl[m] for m in months[-3:]]
        older = [result.monthly_pnl[m] for m in months[:3]] if len(months) >= 6 else [result.monthly_pnl[months[0]]]
        avg_recent = sum(recent) / len(recent)
        avg_older = sum(older) / len(older)
        if avg_recent > avg_older * 1.5:
            result.trend_direction = "improving"
        elif avg_recent < avg_older * 0.5:
            result.trend_direction = "declining"
        else:
            result.trend_direction = "stable"
    else:
        result.trend_direction = "insufficient_data"

    # Signals
    if result.profit_factor > 2.0:
        result.signals.append(f"HIGH_PROFIT_FACTOR: {result.profit_factor:.1f}x — strong edge")
    elif result.profit_factor < 0.8:
        result.signals.append(f"LOW_PROFIT_FACTOR: {result.profit_factor:.1f}x — losing strategy overall")

    if result.win_rate > 0.65:
        result.signals.append(f"HIGH_WIN_RATE: {result.win_rate:.0%} — consistent winner")
    elif result.win_rate < 0.35:
        result.signals.append(f"LOW_WIN_RATE: {result.win_rate:.0%} — few wins but possibly large payoffs")

    if result.risk_reward_ratio > 3:
        result.signals.append(f"HIGH_RR: {result.risk_reward_ratio:.1f}x — asymmetric payoffs")
    
    if result.multi_entry_markets > len(market_entries) * 0.3 and len(market_entries) > 5:
        result.signals.append(f"ACCUMULATOR: re-enters {result.multi_entry_markets} markets — builds positions over time")

    if result.max_single_loss and abs(result.max_single_loss) > result.total_volume_bought * 0.1:
        result.signals.append(f"LARGE_DRAWDOWN: single loss ${result.max_single_loss:,.0f} is >{10}% of total volume")

    return result
