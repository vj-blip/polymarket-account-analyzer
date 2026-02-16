"""Timing analysis: time-of-day patterns, event-driven entries, speed-to-market."""

from __future__ import annotations
from datetime import datetime, timezone
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class TimingAnalysis:
    """Results of timing pattern analysis."""
    total_positions: int = 0
    # Time-of-day distribution (hour -> count)
    hour_distribution: dict[int, int] = field(default_factory=dict)
    peak_hours: list[int] = field(default_factory=list)  # Top 3 hours
    off_hours_pct: float = 0.0  # % trades outside 8am-10pm UTC
    # Day-of-week distribution
    day_distribution: dict[str, int] = field(default_factory=dict)
    weekend_pct: float = 0.0
    # Speed patterns
    avg_days_between_trades: float = 0.0
    burst_trading_episodes: int = 0  # Clusters of >5 trades in 1 hour
    # Consistency
    active_days: int = 0
    total_span_days: int = 0
    daily_consistency: float = 0.0  # active_days / total_span
    # Summary signals
    signals: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = ["=== TIMING ANALYSIS ==="]
        lines.append(f"Total positions: {self.total_positions}")
        if self.peak_hours:
            lines.append(f"Peak trading hours (UTC): {self.peak_hours}")
        lines.append(f"Off-hours trading: {self.off_hours_pct:.1%}")
        lines.append(f"Weekend trading: {self.weekend_pct:.1%}")
        lines.append(f"Avg days between trades: {self.avg_days_between_trades:.1f}")
        lines.append(f"Burst episodes (>5 trades/hr): {self.burst_trading_episodes}")
        lines.append(f"Active days: {self.active_days}/{self.total_span_days} ({self.daily_consistency:.1%} consistency)")
        if self.signals:
            lines.append(f"Signals: {'; '.join(self.signals)}")
        return "\n".join(lines)


def analyze_timing(positions: list[dict]) -> TimingAnalysis:
    """Analyze timing patterns from position data.
    
    Args:
        positions: List of position dicts with keys: tb, ap, cp, pnl, ts, t, cid, o
    """
    result = TimingAnalysis(total_positions=len(positions))
    if not positions:
        return result

    # Filter positions with valid timestamps
    timed = [p for p in positions if p.get("ts", 0) > 0]
    if not timed:
        return result

    timestamps = sorted(p["ts"] for p in timed)
    datetimes = [datetime.fromtimestamp(ts, tz=timezone.utc) for ts in timestamps]

    # Hour distribution
    hours = Counter(dt.hour for dt in datetimes)
    result.hour_distribution = dict(sorted(hours.items()))
    result.peak_hours = [h for h, _ in hours.most_common(3)]

    # Off-hours (before 8am or after 10pm UTC)
    off_hours = sum(1 for dt in datetimes if dt.hour < 8 or dt.hour >= 22)
    result.off_hours_pct = off_hours / len(datetimes)

    # Day of week
    days = Counter(dt.strftime("%A") for dt in datetimes)
    result.day_distribution = dict(days.most_common())
    weekend = sum(1 for dt in datetimes if dt.weekday() >= 5)
    result.weekend_pct = weekend / len(datetimes)

    # Time span and consistency
    unique_days = set(dt.date() for dt in datetimes)
    result.active_days = len(unique_days)
    if len(timestamps) >= 2:
        span = (timestamps[-1] - timestamps[0]) / 86400
        result.total_span_days = max(1, int(span))
        result.daily_consistency = result.active_days / result.total_span_days
    else:
        result.total_span_days = 1
        result.daily_consistency = 1.0

    # Average days between trades
    if len(timestamps) >= 2:
        gaps = [(timestamps[i+1] - timestamps[i]) / 86400 for i in range(len(timestamps)-1)]
        result.avg_days_between_trades = sum(gaps) / len(gaps)

    # Burst trading detection: >5 trades in same hour-bucket
    hour_buckets = Counter((dt.date(), dt.hour) for dt in datetimes)
    result.burst_trading_episodes = sum(1 for count in hour_buckets.values() if count > 5)

    # Generate signals
    if result.daily_consistency > 0.8:
        result.signals.append("HIGHLY_CONSISTENT: trades almost every day — suggests automated/systematic")
    elif result.daily_consistency < 0.1:
        result.signals.append("SPORADIC: very few active days — suggests event-driven or opportunistic")

    if result.off_hours_pct > 0.4:
        result.signals.append("OFF_HOURS_HEAVY: >40% trades outside business hours — bot or non-US timezone")
    
    if result.burst_trading_episodes > 10:
        result.signals.append(f"BURST_TRADER: {result.burst_trading_episodes} episodes of rapid-fire trading")

    if result.weekend_pct > 0.35:
        result.signals.append("WEEKEND_ACTIVE: significant weekend trading")
    elif result.weekend_pct < 0.05 and len(datetimes) > 50:
        result.signals.append("WEEKDAY_ONLY: almost no weekend trades — may follow business/sports schedule")

    if result.avg_days_between_trades < 0.1 and len(timestamps) > 100:
        result.signals.append("HIGH_FREQUENCY: trades multiple times per day on average")

    return result
