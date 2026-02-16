"""Pattern analysis: win/loss streaks, drawdown behavior, recovery patterns."""

from __future__ import annotations
from datetime import datetime, timezone
from dataclasses import dataclass, field


@dataclass
class PatternAnalysis:
    """Results of win/loss pattern analysis."""
    total_positions: int = 0
    # Streak analysis
    max_win_streak: int = 0
    max_loss_streak: int = 0
    avg_win_streak: float = 0.0
    avg_loss_streak: float = 0.0
    current_streak: int = 0  # positive=wins, negative=losses
    # Drawdown
    max_drawdown: float = 0.0  # largest peak-to-trough in cumulative PnL
    max_drawdown_pct: float = 0.0  # as % of peak
    drawdown_duration_positions: int = 0  # positions to recover from max drawdown
    # Recovery
    recoveries_from_loss: int = 0  # how many times recovered from 3+ loss streak
    avg_recovery_length: float = 0.0  # positions to recover from a loss streak
    # Behavior after losses
    size_after_loss_ratio: float = 0.0  # position size after loss / avg size
    size_after_win_ratio: float = 0.0
    # Edge consistency
    first_half_winrate: float = 0.0
    second_half_winrate: float = 0.0
    edge_trend: str = ""  # "improving", "declining", "stable"
    # PnL curve shape
    pnl_curve_r2: float = 0.0  # R² of linear fit — high=steady, low=volatile
    # Signals
    signals: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = ["=== PATTERN ANALYSIS ==="]
        lines.append(f"Max win streak: {self.max_win_streak}, Max loss streak: {self.max_loss_streak}")
        lines.append(f"Avg win streak: {self.avg_win_streak:.1f}, Avg loss streak: {self.avg_loss_streak:.1f}")
        lines.append(f"Max drawdown: ${self.max_drawdown:,.0f} ({self.max_drawdown_pct:.1%} of peak)")
        lines.append(f"Drawdown recovery: {self.drawdown_duration_positions} positions")
        lines.append(f"Recoveries from 3+ losses: {self.recoveries_from_loss}")
        lines.append(f"Size after loss ratio: {self.size_after_loss_ratio:.2f}x, after win: {self.size_after_win_ratio:.2f}x")
        lines.append(f"Edge trend: 1st half WR={self.first_half_winrate:.1%}, 2nd half WR={self.second_half_winrate:.1%} → {self.edge_trend}")
        lines.append(f"PnL curve R²: {self.pnl_curve_r2:.3f} (1.0=perfectly linear)")
        if self.signals:
            lines.append(f"Signals: {'; '.join(self.signals)}")
        return "\n".join(lines)


def _compute_streaks(results: list[bool]) -> tuple[int, int, float, float, int]:
    """Compute max/avg win and loss streaks, and current streak."""
    if not results:
        return 0, 0, 0, 0, 0
    
    win_streaks = []
    loss_streaks = []
    current = 0
    is_win = results[0]
    streak_len = 0

    for r in results:
        if r == is_win:
            streak_len += 1
        else:
            if is_win:
                win_streaks.append(streak_len)
            else:
                loss_streaks.append(streak_len)
            is_win = r
            streak_len = 1
    # Final streak
    if is_win:
        win_streaks.append(streak_len)
    else:
        loss_streaks.append(streak_len)

    current_streak = streak_len if is_win else -streak_len
    max_w = max(win_streaks) if win_streaks else 0
    max_l = max(loss_streaks) if loss_streaks else 0
    avg_w = sum(win_streaks) / len(win_streaks) if win_streaks else 0
    avg_l = sum(loss_streaks) / len(loss_streaks) if loss_streaks else 0
    return max_w, max_l, avg_w, avg_l, current_streak


def analyze_patterns(positions: list[dict]) -> PatternAnalysis:
    """Analyze win/loss patterns and behavioral tendencies."""
    result = PatternAnalysis(total_positions=len(positions))
    if len(positions) < 2:
        return result

    # Sort by timestamp
    sorted_pos = sorted(positions, key=lambda p: p.get("ts", 0))
    results = [p.get("pnl", 0) > 0 for p in sorted_pos]

    # Streaks
    max_w, max_l, avg_w, avg_l, current = _compute_streaks(results)
    result.max_win_streak = max_w
    result.max_loss_streak = max_l
    result.avg_win_streak = avg_w
    result.avg_loss_streak = avg_l
    result.current_streak = current

    # Drawdown analysis
    cumulative = []
    running = 0.0
    for p in sorted_pos:
        running += p.get("pnl", 0)
        cumulative.append(running)

    peak = cumulative[0]
    max_dd = 0.0
    max_dd_peak = peak
    dd_start = 0
    max_dd_start = 0
    max_dd_end = 0
    for i, val in enumerate(cumulative):
        if val > peak:
            peak = val
            dd_start = i
        dd = peak - val
        if dd > max_dd:
            max_dd = dd
            max_dd_peak = peak
            max_dd_start = dd_start
            max_dd_end = i

    result.max_drawdown = max_dd
    result.max_drawdown_pct = max_dd / max_dd_peak if max_dd_peak > 0 else 0

    # Recovery from max drawdown
    if max_dd > 0:
        recovery_count = 0
        for i in range(max_dd_end, len(cumulative)):
            recovery_count += 1
            if cumulative[i] >= max_dd_peak:
                break
        result.drawdown_duration_positions = recovery_count

    # Recovery from loss streaks (3+)
    loss_streak = 0
    recovery_lengths = []
    in_recovery = False
    recovery_len = 0
    for r in results:
        if not r:
            loss_streak += 1
            if in_recovery:
                in_recovery = False
        else:
            if loss_streak >= 3:
                in_recovery = True
                recovery_len = 0
                result.recoveries_from_loss += 1
            if in_recovery:
                recovery_len += 1
            loss_streak = 0
    if recovery_lengths:
        result.avg_recovery_length = sum(recovery_lengths) / len(recovery_lengths)

    # Behavior after wins/losses (sizing changes)
    sizes = [p.get("tb", 0) for p in sorted_pos]
    avg_size = sum(sizes) / len(sizes) if sizes else 1

    after_loss_sizes = []
    after_win_sizes = []
    for i in range(1, len(sorted_pos)):
        prev_pnl = sorted_pos[i-1].get("pnl", 0)
        curr_size = sorted_pos[i].get("tb", 0)
        if prev_pnl <= 0:
            after_loss_sizes.append(curr_size)
        else:
            after_win_sizes.append(curr_size)

    if after_loss_sizes and avg_size > 0:
        result.size_after_loss_ratio = (sum(after_loss_sizes) / len(after_loss_sizes)) / avg_size
    if after_win_sizes and avg_size > 0:
        result.size_after_win_ratio = (sum(after_win_sizes) / len(after_win_sizes)) / avg_size

    # Edge consistency: first half vs second half win rate
    mid = len(results) // 2
    first_half = results[:mid]
    second_half = results[mid:]
    result.first_half_winrate = sum(first_half) / len(first_half) if first_half else 0
    result.second_half_winrate = sum(second_half) / len(second_half) if second_half else 0
    
    if result.second_half_winrate > result.first_half_winrate + 0.05:
        result.edge_trend = "improving"
    elif result.second_half_winrate < result.first_half_winrate - 0.05:
        result.edge_trend = "declining"
    else:
        result.edge_trend = "stable"

    # PnL curve linearity (R²)
    n = len(cumulative)
    if n >= 10:
        x_mean = (n - 1) / 2
        y_mean = sum(cumulative) / n
        ss_xy = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(cumulative))
        ss_xx = sum((i - x_mean) ** 2 for i in range(n))
        ss_yy = sum((y - y_mean) ** 2 for y in cumulative)
        if ss_xx > 0 and ss_yy > 0:
            r = ss_xy / (ss_xx * ss_yy) ** 0.5
            result.pnl_curve_r2 = r ** 2

    # Signals
    if result.max_win_streak >= 10:
        result.signals.append(f"LONG_WIN_STREAKS: {result.max_win_streak} consecutive wins")
    if result.max_loss_streak >= 10:
        result.signals.append(f"LONG_LOSS_STREAKS: {result.max_loss_streak} consecutive losses")

    if result.pnl_curve_r2 > 0.9:
        result.signals.append(f"STEADY_GRINDER: R²={result.pnl_curve_r2:.2f} — very consistent returns")
    elif result.pnl_curve_r2 < 0.3 and n >= 20:
        result.signals.append(f"VOLATILE_RETURNS: R²={result.pnl_curve_r2:.2f} — erratic PnL curve")

    if result.max_drawdown_pct > 0.5:
        result.signals.append(f"SEVERE_DRAWDOWN: {result.max_drawdown_pct:.0%} peak-to-trough")

    if result.size_after_loss_ratio > 1.3:
        result.signals.append(f"MARTINGALE_TENDENCY: sizes up {result.size_after_loss_ratio:.1f}x after losses")
    elif result.size_after_loss_ratio < 0.7 and result.size_after_loss_ratio > 0:
        result.signals.append(f"RISK_REDUCER: sizes down to {result.size_after_loss_ratio:.1f}x after losses")

    if result.edge_trend == "improving":
        result.signals.append("IMPROVING_EDGE: win rate increasing over time")
    elif result.edge_trend == "declining":
        result.signals.append("DECLINING_EDGE: win rate decreasing over time")

    return result
