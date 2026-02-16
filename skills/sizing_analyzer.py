"""Position sizing analysis: consistency, scaling behavior, size distribution."""

from __future__ import annotations
import statistics
from dataclasses import dataclass, field


@dataclass
class SizingAnalysis:
    """Results of position sizing analysis."""
    total_positions: int = 0
    total_volume: float = 0.0
    avg_position_size: float = 0.0
    median_position_size: float = 0.0
    std_position_size: float = 0.0
    min_position_size: float = 0.0
    max_position_size: float = 0.0
    # Size buckets
    micro_count: int = 0    # < $100
    small_count: int = 0    # $100 - $1K
    medium_count: int = 0   # $1K - $10K
    large_count: int = 0    # $10K - $100K
    whale_count: int = 0    # > $100K
    # Consistency metrics
    coefficient_of_variation: float = 0.0  # std/mean — low = consistent sizing
    size_concentration: float = 0.0  # top 10% of positions as % of total volume
    # Scaling behavior
    avg_win_size: float = 0.0
    avg_loss_size: float = 0.0
    win_loss_size_ratio: float = 0.0  # >1 means larger positions on wins
    # Entry price patterns
    avg_entry_price: float = 0.0
    low_odds_pct: float = 0.0   # entry < 0.3
    mid_odds_pct: float = 0.0   # 0.3-0.7
    high_odds_pct: float = 0.0  # > 0.7
    # Signals
    signals: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = ["=== SIZING ANALYSIS ==="]
        lines.append(f"Total volume: ${self.total_volume:,.0f} across {self.total_positions} positions")
        lines.append(f"Position size: avg=${self.avg_position_size:,.0f}, median=${self.median_position_size:,.0f}, max=${self.max_position_size:,.0f}")
        lines.append(f"CV (consistency): {self.coefficient_of_variation:.2f} (lower=more consistent)")
        lines.append(f"Size distribution: micro={self.micro_count}, small={self.small_count}, medium={self.medium_count}, large={self.large_count}, whale={self.whale_count}")
        lines.append(f"Top 10% concentration: {self.size_concentration:.1%} of volume")
        lines.append(f"Avg win size: ${self.avg_win_size:,.0f}, Avg loss size: ${self.avg_loss_size:,.0f}, ratio: {self.win_loss_size_ratio:.2f}")
        lines.append(f"Entry prices: low(<0.3)={self.low_odds_pct:.1%}, mid(0.3-0.7)={self.mid_odds_pct:.1%}, high(>0.7)={self.high_odds_pct:.1%}")
        if self.signals:
            lines.append(f"Signals: {'; '.join(self.signals)}")
        return "\n".join(lines)


def analyze_sizing(positions: list[dict]) -> SizingAnalysis:
    """Analyze position sizing patterns."""
    result = SizingAnalysis(total_positions=len(positions))
    if not positions:
        return result

    sizes = [p.get("tb", 0) for p in positions if p.get("tb", 0) > 0]
    if not sizes:
        return result

    result.total_volume = sum(sizes)
    result.avg_position_size = statistics.mean(sizes)
    result.median_position_size = statistics.median(sizes)
    result.min_position_size = min(sizes)
    result.max_position_size = max(sizes)
    result.std_position_size = statistics.stdev(sizes) if len(sizes) > 1 else 0

    # CV
    if result.avg_position_size > 0:
        result.coefficient_of_variation = result.std_position_size / result.avg_position_size

    # Size buckets
    for s in sizes:
        if s < 100:
            result.micro_count += 1
        elif s < 1000:
            result.small_count += 1
        elif s < 10000:
            result.medium_count += 1
        elif s < 100000:
            result.large_count += 1
        else:
            result.whale_count += 1

    # Concentration: top 10% of positions by size
    sorted_sizes = sorted(sizes, reverse=True)
    top_n = max(1, len(sorted_sizes) // 10)
    result.size_concentration = sum(sorted_sizes[:top_n]) / result.total_volume

    # Win vs loss sizing
    wins = [p for p in positions if p.get("pnl", 0) > 0 and p.get("tb", 0) > 0]
    losses = [p for p in positions if p.get("pnl", 0) <= 0 and p.get("tb", 0) > 0]
    if wins:
        result.avg_win_size = statistics.mean(p["tb"] for p in wins)
    if losses:
        result.avg_loss_size = statistics.mean(p["tb"] for p in losses)
    if result.avg_loss_size > 0:
        result.win_loss_size_ratio = result.avg_win_size / result.avg_loss_size

    # Entry price distribution
    entries = [p.get("ap", 0) for p in positions if 0 < p.get("ap", 0) <= 1]
    if entries:
        result.avg_entry_price = statistics.mean(entries)
        result.low_odds_pct = sum(1 for e in entries if e < 0.3) / len(entries)
        result.mid_odds_pct = sum(1 for e in entries if 0.3 <= e <= 0.7) / len(entries)
        result.high_odds_pct = sum(1 for e in entries if e > 0.7) / len(entries)

    # Signals
    if result.coefficient_of_variation < 0.5:
        result.signals.append("CONSISTENT_SIZING: low CV suggests systematic/model-based approach")
    elif result.coefficient_of_variation > 2.0:
        result.signals.append("HIGHLY_VARIABLE_SIZING: high CV — mixes small and very large bets")

    if result.whale_count > 0 and result.whale_count / len(sizes) > 0.1:
        result.signals.append(f"WHALE_SIZING: {result.whale_count} positions >$100K ({result.whale_count/len(sizes):.0%})")

    if result.size_concentration > 0.5:
        result.signals.append(f"CONCENTRATED: top 10% of positions = {result.size_concentration:.0%} of volume")

    if result.win_loss_size_ratio > 1.5:
        result.signals.append("LARGER_ON_WINS: sizes up on winning trades — possible conviction scaling")
    elif result.win_loss_size_ratio < 0.7 and result.win_loss_size_ratio > 0:
        result.signals.append("LARGER_ON_LOSSES: sizes up on losing trades — possible averaging down")

    if result.low_odds_pct > 0.5:
        result.signals.append(f"LOW_ODDS_BUYER: {result.low_odds_pct:.0%} entries below 0.30 — hunting longshots")
    elif result.high_odds_pct > 0.5:
        result.signals.append(f"HIGH_ODDS_BUYER: {result.high_odds_pct:.0%} entries above 0.70 — buying favorites")
    elif result.mid_odds_pct > 0.6:
        result.signals.append(f"MID_ODDS_FOCUS: {result.mid_odds_pct:.0%} entries in 0.30-0.70 — near-tossup markets")

    if result.avg_position_size > 100000:
        result.signals.append(f"VERY_LARGE_AVG: ${result.avg_position_size:,.0f} average position")

    return result
