"""Market selection analysis: category focus, diversity, concentration."""

from __future__ import annotations
import re
from collections import Counter
from dataclasses import dataclass, field


# Keyword-based category detection
CATEGORY_RULES = [
    ("sports_betting", [
        # Game formats: "Team A vs. Team B", "Team A vs Team B", "Spread: Team (-X)"
        r"\bvs\.?\s", r"\bvs\b",
        # Common bet types
        r"spread", r"moneyline", r"over/under", r"\bo/u\b", r"total points", r"total goals",
        # Leagues
        r"\bnfl\b", r"\bnba\b", r"\bmlb\b", r"\bnhl\b", r"\bmls\b",
        r"\bncaa\b", r"college", r"premier league", r"la liga", r"serie a",
        r"bundesliga", r"ligue 1", r"champions league", r"europa league",
        r"\bufc\b", r"\bwwe\b", r"boxing", r"tennis", r"golf", r"super bowl",
        # "Will X win" patterns (common Polymarket sports format)
        r"will .+ win on \d{4}", r"will .+ win against",
        r"will .+ win .+ \d{4}", r"will .+ beat",
        # Team names (major)
        r"man city", r"man utd", r"liverpool",
        r"villarreal", r"atletico", r"barcelona", r"real madrid",
        r"lakers", r"celtics", r"warriors", r"yankees", r"dodgers",
        r"seahawks", r"packers", r"patriots", r"bears", r"rams",
        r"chiefs", r"eagles", r"cowboys", r"49ers", r"ravens",
        r"bills", r"dolphins", r"steelers", r"bengals", r"broncos",
        r"knicks", r"nets", r"rockets", r"nuggets", r"heat",
        r"bucks", r"suns", r"clippers", r"spurs", r"mavericks",
        r"oilers", r"penguins", r"capitals", r"blackhawks", r"canadiens",
        r"panthers", r"flames", r"sharks", r"stars", r"wild",
        r"magic", r"raptors", r"pelicans", r"wizards", r"pistons",
        r"timberwolves", r"pacers", r"cavaliers", r"grizzlies",
        # Esports
        r"esport", r"\blol\b", r"league of legends", r"\bdota\b", r"\bcs2?\b",
    ]),
    ("politics", [
        r"president", r"election", r"trump", r"biden", r"vote", r"congress",
        r"senate", r"governor", r"democrat", r"republican", r"poll",
        r"primary", r"nominee", r"cabinet", r"secretary of",
    ]),
    ("crypto", [
        r"\bbitcoin\b", r"\beth\b", r"\bethereum\b", r"crypto", r"\bbtc\b",
        r"solana", r"\bsol\b", r"token", r"defi", r"nft",
    ]),
    ("economics", [
        r"\bfed\b", r"federal reserve", r"interest rate", r"inflation",
        r"\bgdp\b", r"unemployment", r"cpi", r"treasury", r"tariff",
    ]),
    ("entertainment", [
        r"oscar", r"grammy", r"super bowl halftime", r"movie", r"box office",
        r"album", r"streaming", r"netflix", r"disney",
    ]),
    ("science_tech", [
        r"spacex", r"nasa", r"\bai\b", r"artificial intelligence", r"climate",
        r"vaccine", r"fda", r"drug approval",
    ]),
    ("weather", [
        r"hurricane", r"temperature", r"weather", r"snowfall", r"rainfall",
    ]),
]


def _categorize_market(title: str) -> str:
    title_lower = title.lower()
    for category, patterns in CATEGORY_RULES:
        for pattern in patterns:
            if re.search(pattern, title_lower):
                return category
    return "other"


@dataclass
class MarketAnalysis:
    """Results of market selection analysis."""
    total_positions: int = 0
    unique_markets: int = 0  # unique condition IDs
    unique_titles: int = 0
    # Category breakdown
    category_counts: dict[str, int] = field(default_factory=dict)
    category_pnl: dict[str, float] = field(default_factory=dict)
    category_volume: dict[str, float] = field(default_factory=dict)
    dominant_category: str = ""
    category_concentration: float = 0.0  # % of positions in top category
    # Diversity metrics
    herfindahl_index: float = 0.0  # Market concentration (0=diverse, 1=single market)
    markets_per_category: float = 0.0
    # Top markets by volume
    top_markets: list[tuple[str, float, float]] = field(default_factory=list)  # (title, volume, pnl)
    # Outcome preference
    yes_pct: float = 0.0
    no_pct: float = 0.0
    # Signals
    signals: list[str] = field(default_factory=list)

    def to_text(self) -> str:
        lines = ["=== MARKET ANALYSIS ==="]
        lines.append(f"Positions: {self.total_positions} across {self.unique_markets} markets")
        lines.append(f"Categories: {dict(sorted(self.category_counts.items(), key=lambda x: -x[1]))}")
        lines.append(f"Dominant: {self.dominant_category} ({self.category_concentration:.0%})")
        lines.append(f"Herfindahl index: {self.herfindahl_index:.3f} (0=diverse, 1=concentrated)")
        lines.append(f"Outcome bias: Yes={self.yes_pct:.0%}, No={self.no_pct:.0%}")
        if self.category_pnl:
            lines.append(f"PnL by category: { {k: f'${v:,.0f}' for k, v in sorted(self.category_pnl.items(), key=lambda x: -x[1])} }")
        if self.top_markets:
            lines.append("Top 5 markets by volume:")
            for title, vol, pnl in self.top_markets[:5]:
                lines.append(f"  ${vol:,.0f} (PnL: ${pnl:+,.0f}) — {title[:60]}")
        if self.signals:
            lines.append(f"Signals: {'; '.join(self.signals)}")
        return "\n".join(lines)


def analyze_markets(positions: list[dict]) -> MarketAnalysis:
    """Analyze market selection patterns."""
    result = MarketAnalysis(total_positions=len(positions))
    if not positions:
        return result

    # Unique markets
    cids = set(p.get("cid", "") for p in positions if p.get("cid"))
    result.unique_markets = len(cids)
    titles = set(p.get("t", "") for p in positions if p.get("t"))
    result.unique_titles = len(titles)

    # Category analysis
    cat_counts: Counter = Counter()
    cat_pnl: dict[str, float] = {}
    cat_vol: dict[str, float] = {}
    for p in positions:
        cat = _categorize_market(p.get("t", ""))
        cat_counts[cat] += 1
        cat_pnl[cat] = cat_pnl.get(cat, 0) + p.get("pnl", 0)
        cat_vol[cat] = cat_vol.get(cat, 0) + p.get("tb", 0)

    result.category_counts = dict(cat_counts.most_common())
    result.category_pnl = cat_pnl
    result.category_volume = cat_vol

    if cat_counts:
        top_cat, top_count = cat_counts.most_common(1)[0]
        result.dominant_category = top_cat
        result.category_concentration = top_count / len(positions)

    # Herfindahl index (market-level concentration)
    market_volumes: dict[str, float] = {}
    for p in positions:
        cid = p.get("cid", "unknown")
        market_volumes[cid] = market_volumes.get(cid, 0) + p.get("tb", 0)
    total_vol = sum(market_volumes.values()) or 1
    result.herfindahl_index = sum((v / total_vol) ** 2 for v in market_volumes.values())

    # Top markets by volume
    market_pnl: dict[str, float] = {}
    market_titles: dict[str, str] = {}
    for p in positions:
        cid = p.get("cid", "unknown")
        market_pnl[cid] = market_pnl.get(cid, 0) + p.get("pnl", 0)
        market_titles[cid] = p.get("t", "?")
    
    sorted_markets = sorted(market_volumes.items(), key=lambda x: -x[1])
    result.top_markets = [
        (market_titles.get(cid, "?"), vol, market_pnl.get(cid, 0))
        for cid, vol in sorted_markets[:10]
    ]

    # Outcome preference
    outcomes = [p.get("o", "").lower() for p in positions]
    yes_count = sum(1 for o in outcomes if o == "yes")
    no_count = sum(1 for o in outcomes if o == "no")
    total_outcomes = yes_count + no_count or 1
    result.yes_pct = yes_count / total_outcomes
    result.no_pct = no_count / total_outcomes

    # Signals
    if result.category_concentration > 0.8:
        result.signals.append(f"SPECIALIST: {result.category_concentration:.0%} in {result.dominant_category}")
    elif len(cat_counts) >= 4 and result.category_concentration < 0.5:
        result.signals.append(f"DIVERSIFIED: trades across {len(cat_counts)} categories")

    if result.herfindahl_index > 0.1:
        result.signals.append(f"MARKET_CONCENTRATED: HHI={result.herfindahl_index:.3f} — concentrated in few markets")
    elif result.herfindahl_index < 0.01:
        result.signals.append("HIGHLY_DIVERSIFIED: very spread across many markets")

    if result.no_pct > 0.7:
        result.signals.append(f"NO_BIAS: {result.no_pct:.0%} positions are NO — contrarian tendency")
    elif result.yes_pct > 0.7:
        result.signals.append(f"YES_BIAS: {result.yes_pct:.0%} positions are YES")

    if result.unique_markets > 0:
        positions_per_market = len(positions) / result.unique_markets
        if positions_per_market > 3:
            result.signals.append(f"REPEAT_MARKETS: avg {positions_per_market:.1f} positions per market — re-enters markets")

    return result
