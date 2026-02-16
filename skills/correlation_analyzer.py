"""Correlation analysis: cross-market hedging, paired positions, portfolio construction."""

from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class CorrelationAnalysis:
    """Results of cross-market correlation analysis."""
    total_positions: int = 0
    unique_markets: int = 0
    # Paired/hedged positions
    same_market_both_sides: int = 0  # Markets where trader has both YES and NO
    hedge_ratio: float = 0.0  # % of markets with both-side positions
    # Temporal clustering (positions opened within same time window across markets)
    temporal_clusters: int = 0  # Groups of 3+ positions within 1 hour
    avg_cluster_size: float = 0.0
    max_cluster_size: int = 0
    # Portfolio construction signals
    simultaneous_open_markets: int = 0  # Peak concurrent markets
    avg_open_markets: float = 0.0
    portfolio_turnover: float = 0.0  # Avg days a position is held
    # Related market pairs (same title root, different conditions)
    related_market_groups: int = 0  # Markets with shared title prefix
    positions_in_related: int = 0  # Positions within related market groups
    related_pct: float = 0.0
    # Opposing bets (YES on one outcome, NO on related)
    opposing_pairs: int = 0
    # Directional consistency within categories
    category_direction: dict[str, dict] = field(default_factory=dict)  # category -> {yes: N, no: N}
    # Signals
    signals: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = ["=== CORRELATION ANALYSIS ==="]
        lines.append(f"Positions: {self.total_positions} across {self.unique_markets} markets")
        lines.append(f"Both-side markets: {self.same_market_both_sides} ({self.hedge_ratio:.1%} of markets)")
        lines.append(f"Temporal clusters (3+ positions/hour): {self.temporal_clusters}")
        if self.temporal_clusters > 0:
            lines.append(f"  Avg cluster size: {self.avg_cluster_size:.1f}, max: {self.max_cluster_size}")
        lines.append(f"Peak concurrent open markets: {self.simultaneous_open_markets}")
        lines.append(f"Avg concurrent open markets: {self.avg_open_markets:.1f}")
        lines.append(f"Related market groups: {self.related_market_groups} ({self.related_pct:.0%} of positions)")
        lines.append(f"Opposing pairs (YES+NO on related markets): {self.opposing_pairs}")
        if self.category_direction:
            lines.append("Direction by category:")
            for cat, dirs in sorted(self.category_direction.items(), key=lambda x: -(x[1].get("yes", 0) + x[1].get("no", 0))):
                y, n = dirs.get("yes", 0), dirs.get("no", 0)
                total = y + n
                if total >= 5:
                    lines.append(f"  {cat}: Yes={y} ({y/total:.0%}), No={n} ({n/total:.0%})")
        if self.signals:
            lines.append(f"Signals: {'; '.join(self.signals)}")
        return "\n".join(lines)


def _normalize_title(title: str) -> str:
    """Extract a root title for grouping related markets.
    
    E.g., "Will Bitcoin hit $100K by March?" and "Will Bitcoin hit $150K by March?"
    should share a common root.
    """
    import re
    t = title.lower().strip()
    # Remove specific numbers/dates that differentiate variants
    t = re.sub(r'\$[\d,]+k?', '$X', t)
    t = re.sub(r'\d{4}', 'YYYY', t)
    t = re.sub(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d+', 'DATE', t)
    # Truncate to first ~60 chars for grouping
    return t[:60]


def _simple_category(title: str) -> str:
    """Quick category for direction analysis."""
    import re
    t = title.lower()
    if re.search(r'\bvs\.?\s|\bvs\b|spread|moneyline|nfl|nba|mlb|nhl|ufc', t):
        return "sports"
    if re.search(r'president|election|trump|biden|congress|senate|democrat|republican', t):
        return "politics"
    if re.search(r'bitcoin|eth|ethereum|crypto|btc|solana|token', t):
        return "crypto"
    if re.search(r'fed\b|inflation|gdp|tariff|interest rate', t):
        return "economics"
    return "other"


def analyze_correlations(positions: list[dict]) -> CorrelationAnalysis:
    """Analyze cross-market correlations, hedging, and portfolio construction.
    
    Args:
        positions: List of position dicts with keys: tb, ap, cp, pnl, ts, t, cid, o
    """
    result = CorrelationAnalysis(total_positions=len(positions))
    if not positions:
        return result

    # --- Basic grouping ---
    by_market: dict[str, list[dict]] = defaultdict(list)
    for p in positions:
        cid = p.get("cid", "unknown")
        by_market[cid].append(p)
    result.unique_markets = len(by_market)

    # --- Both-side detection (YES + NO in same market) ---
    both_side_count = 0
    for cid, mpositions in by_market.items():
        outcomes = set(p.get("o", "").lower() for p in mpositions)
        if "yes" in outcomes and "no" in outcomes:
            both_side_count += 1
    result.same_market_both_sides = both_side_count
    result.hedge_ratio = both_side_count / max(len(by_market), 1)

    # --- Temporal clustering ---
    # Sort all positions by timestamp, find clusters of 3+ within 1 hour
    sorted_positions = sorted(positions, key=lambda p: p.get("ts", 0))
    clusters = []
    current_cluster = []
    for p in sorted_positions:
        ts = p.get("ts", 0)
        if not current_cluster:
            current_cluster = [p]
        elif ts - current_cluster[0].get("ts", 0) <= 3600:  # 1 hour window
            current_cluster.append(p)
        else:
            if len(current_cluster) >= 3:
                # Check it spans multiple markets
                cluster_markets = set(cp.get("cid", "") for cp in current_cluster)
                if len(cluster_markets) >= 2:
                    clusters.append(current_cluster)
            current_cluster = [p]
    # Don't forget last cluster
    if len(current_cluster) >= 3:
        cluster_markets = set(cp.get("cid", "") for cp in current_cluster)
        if len(cluster_markets) >= 2:
            clusters.append(current_cluster)

    result.temporal_clusters = len(clusters)
    if clusters:
        sizes = [len(c) for c in clusters]
        result.avg_cluster_size = sum(sizes) / len(sizes)
        result.max_cluster_size = max(sizes)

    # --- Related market groups (shared title root) ---
    title_groups: dict[str, list[dict]] = defaultdict(list)
    for p in positions:
        root = _normalize_title(p.get("t", ""))
        title_groups[root].append(p)

    # Only count groups with 2+ distinct condition IDs
    related_groups = {
        root: plist for root, plist in title_groups.items()
        if len(set(p.get("cid", "") for p in plist)) >= 2
    }
    result.related_market_groups = len(related_groups)
    result.positions_in_related = sum(len(plist) for plist in related_groups.values())
    result.related_pct = result.positions_in_related / max(len(positions), 1)

    # --- Opposing pairs within related groups ---
    opposing = 0
    for root, plist in related_groups.items():
        # Group by condition ID
        by_cid: dict[str, set] = defaultdict(set)
        for p in plist:
            by_cid[p.get("cid", "")].add(p.get("o", "").lower())
        # Check if any pair has opposing directions
        cids = list(by_cid.keys())
        for i in range(len(cids)):
            for j in range(i + 1, len(cids)):
                outcomes_i = by_cid[cids[i]]
                outcomes_j = by_cid[cids[j]]
                # Opposing: YES in one, NO in another (or vice versa)
                if ("yes" in outcomes_i and "no" in outcomes_j) or \
                   ("no" in outcomes_i and "yes" in outcomes_j):
                    opposing += 1
    result.opposing_pairs = opposing

    # --- Concurrent open markets estimation ---
    # Use timestamps to estimate how many markets are "open" at peak
    # Approximate: for each position, assume it's open for ~7 days (median hold)
    HOLD_DAYS = 7 * 86400  # 7 days in seconds
    events = []
    for p in sorted_positions:
        ts = p.get("ts", 0)
        if ts > 0:
            events.append((ts, 1, p.get("cid", "")))
            events.append((ts + HOLD_DAYS, -1, p.get("cid", "")))
    
    if events:
        events.sort(key=lambda e: (e[0], e[1]))
        current_open: set = set()
        max_open = 0
        open_counts = []
        for ts, delta, cid in events:
            if delta > 0:
                current_open.add(cid)
            else:
                current_open.discard(cid)
            if len(current_open) > max_open:
                max_open = len(current_open)
            open_counts.append(len(current_open))
        result.simultaneous_open_markets = max_open
        result.avg_open_markets = sum(open_counts) / len(open_counts) if open_counts else 0

    # --- Category direction analysis ---
    cat_dir: dict[str, dict[str, int]] = defaultdict(lambda: {"yes": 0, "no": 0})
    for p in positions:
        cat = _simple_category(p.get("t", ""))
        outcome = p.get("o", "").lower()
        if outcome in ("yes", "no"):
            cat_dir[cat][outcome] += 1
    result.category_direction = dict(cat_dir)

    # --- Signals ---
    if result.hedge_ratio > 0.15:
        result.signals.append(
            f"HEDGER: {result.hedge_ratio:.0%} of markets have both YES and NO positions — active hedging")
    elif result.hedge_ratio > 0.05:
        result.signals.append(
            f"PARTIAL_HEDGE: {result.hedge_ratio:.0%} of markets have both sides")

    if result.temporal_clusters > 10:
        result.signals.append(
            f"BATCH_TRADER: {result.temporal_clusters} temporal clusters — enters multiple markets simultaneously")
    
    if result.related_pct > 0.3:
        result.signals.append(
            f"RELATED_MARKET_FOCUS: {result.related_pct:.0%} of positions in related market variants")
    
    if result.opposing_pairs > 5:
        result.signals.append(
            f"CROSS_MARKET_HEDGE: {result.opposing_pairs} opposing pairs across related markets")
    elif result.opposing_pairs > 0:
        result.signals.append(
            f"SOME_HEDGING: {result.opposing_pairs} opposing pair(s) in related markets")

    if result.simultaneous_open_markets > 50:
        result.signals.append(
            f"PORTFOLIO_BUILDER: peak {result.simultaneous_open_markets} concurrent markets — active portfolio management")
    
    # Category direction consistency
    for cat, dirs in cat_dir.items():
        y, n = dirs["yes"], dirs["no"]
        total = y + n
        if total >= 20:
            bias = max(y, n) / total
            if bias > 0.85:
                side = "YES" if y > n else "NO"
                result.signals.append(
                    f"DIRECTIONAL_{cat.upper()}: {bias:.0%} {side}-side in {cat} — strong directional conviction")

    return result
