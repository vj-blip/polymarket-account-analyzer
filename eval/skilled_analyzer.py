"""Skilled analyzer: uses analysis tools to produce structured evidence before LLM classification.

Instead of dumping raw data into the prompt, we:
1. Run all 5 analysis skills on the position data
2. Feed structured analysis results to the LLM
3. Let the LLM synthesize a strategy thesis from real patterns

This should dramatically improve strategy accuracy and evidence quality.
"""

from __future__ import annotations
import asyncio
import json
import os
from dotenv import load_dotenv
from openai import AsyncOpenAI

from .models import WalletThesis, StrategyType
from .scorer import JudgeAssessment
from .data_fetcher import get_wallet_ranking, get_wallet_positions, get_wallet_pnl_history
from .run_eval import evaluate_analyzer

import sys
sys.path.insert(0, str(__file__).rsplit("/eval/", 1)[0])
from skills import analyze_timing, analyze_sizing, analyze_markets, analyze_flow, analyze_patterns, analyze_correlations

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANALYZER_MODEL = "gpt-4o-mini"
JUDGE_MODEL = "gpt-4o"

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


SKILLED_PROMPT = """You are an expert Polymarket trading strategy analyst. You have been given structured analysis from 6 specialized tools that examined a wallet's trading history.

Your job: Synthesize these analyses into a precise strategy classification.

## Strategy Types (pick the BEST match — do NOT default to "unknown"):
- **info_edge**: Trades on early/non-public information. Signs: enters before major events, high win rate on time-sensitive markets, speed-to-market advantage.
- **model_based**: Uses quantitative/statistical models. Signs: high trade count (usually >2000), consistent sizing (low CV), systematic entry prices, positive Sharpe, diverse markets, algorithmic patterns.
- **market_maker**: Provides liquidity on both sides. Signs: VERY high position count (>10K), massive volume, thin margins (win rate 45-55%, edge <0.05), small avg position size (<$10K), trades both YES and NO sides frequently.
- **contrarian**: Bets against market consensus. Signs: buys at 50/50 odds when market is uncertain, trades both sides of directional markets (e.g., crypto "dip to X" AND "above Y"), moderate edge from going against crowd sentiment. Can also show: low odds entries (<0.3), NO-side bias, crypto price prediction specialist.
- **momentum**: Follows trends. Signs: buys at high odds (>0.7), YES-side bias, enters after price moves.
- **hedger**: Hedges across markets. Signs: paired positions, opposing bets in correlated markets, low net exposure.
- **arbitrage**: Cross-market or cross-platform arb. Signs: near-simultaneous opposing positions, tiny margins, very high volume.
- **whale**: Makes very large concentrated bets. Signs: avg position >$50K, total positions typically <3000, high size variance, large max positions ($500K+). Whales may ALSO be profitable — profit doesn't rule out whale.
- **scalper**: High-frequency small-profit trades with DIRECTIONAL EDGE. Signs: many positions (5K-25K), small avg size (<$100K), win rate 53-60% (better than coin flip but not exceptional), moderate edge. Key difference from market_maker: scalpers have directional edge (WR >53%), market makers have near-50% WR.
- **unknown**: ONLY if truly unclassifiable after reviewing all evidence.

## KEY HEURISTICS (apply carefully — these are strong signals, not absolute rules):

### Whale vs Model_based vs Info_edge (all can have large positions):
- **WHALE**: Large avg position ($50K+), LOW win rate (<55%) or LOW profit factor (<1.5), often sports-focused, high variance. The key: whales bet BIG but WITHOUT a consistent statistical edge. They may win some big bets but lose many too.
- **MODEL_BASED**: High trade count (>2000), CONSISTENT EDGE (win rate >55%, PF >1.2), LOW CV (<1.5), diverse markets. The key: systematic, repeatable alpha from quantitative models.
- **INFO_EDGE**: Large positions WITH HIGH WIN RATE (>65%) or HIGH PROFIT FACTOR (>2.0), trades politics/news/crypto/events (NOT just sports). The key: they win because they KNOW something — information advantage on specific events. Info_edge traders CAN have large positions and high CV — that's fine, they bet big on things they know. DON'T confuse them with whales just because positions are large.

### CRITICAL: Info_edge vs Whale disambiguation:
- Info_edge REQUIRES politics/news/crypto/geopolitical event markets — NOT sports!
- Sports traders with high win rates are SKILLED WHALES, not info_edge. Sports don't have "insider information" the way politics/news do.
- If avg position >$30K AND high win rate AND trades politics/news/crypto → INFO_EDGE
- If avg position >$30K AND high win rate AND trades SPORTS → WHALE (skilled sports whale)
- Whales who trade sports can still have 60-70% win rates — that's sports skill, not info edge.

### Market Maker detection:
If total positions > 10,000 AND avg position < $10,000 AND win rate 45-55% AND edge < 0.05 → strongly consider **market_maker**. They profit from volume/spread, not directional bets.

### DO NOT DEFAULT TO model_based:
model_based requires EVIDENCE: consistent sizing (CV < 1.0), diverse markets, high trade count (>2000), AND measurable statistical edge. Large profitable traders are NOT automatically model_based.

### Whale vs others — the VARIANCE test:
If avg position > $50K AND (CV > 1.5 OR Sharpe < 0.5 OR win_rate < 0.5 OR positions < 1000) → strongly consider **whale**. A trader with large positions BUT high Sharpe and consistent edge is more likely model_based or info_edge.

## Decision Framework:
1. **FIRST: Apply hard rules above** — check whale and market_maker thresholds
2. Check SIZING — position sizes, distribution, CV
3. Check MARKET — specialist or diversified? Category focus?
4. Check FLOW — win rate, profit factor, edge magnitude
5. Check PATTERNS — is edge consistent? Steady grinder or volatile?
6. Check TIMING — automated (consistent daily) or event-driven (sporadic)?
7. Check CORRELATION — hedging across markets? Batch entries? Portfolio construction?

## Important Rules:
- Be SPECIFIC in evidence — cite numbers from the analysis
- Look for WHALE_SIZING and VERY_LARGE_AVG signals — these are strong whale indicators
- Set confidence based on how clear the signals are (0.3=ambiguous, 0.7=likely, 0.9=obvious)

Respond in JSON:
{
    "wallet": "<address>",
    "primary_strategy": "<strategy_type>",
    "secondary_strategies": [],
    "confidence": 0.0-1.0,
    "evidence": ["specific evidence points with numbers"],
    "reasoning": "synthesis of all analyses",
    "signals_to_monitor": ["what to watch"],
    "risk_assessment": "assessment"
}"""


async def call_llm(messages: list[dict], model: str = ANALYZER_MODEL) -> str:
    resp = await _client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        timeout=120,
    )
    return resp.choices[0].message.content


def rule_based_hints(sizing, flow, markets, num_positions: int) -> str:
    """Generate rule-based classification hints from hard thresholds.
    
    Returns a string of strong hints to prepend to the LLM context.
    These override the LLM's tendency to default to model_based.
    """
    hints = []
    
    avg_pos = sizing.avg_position_size
    cv = sizing.coefficient_of_variation
    whale_pct = sizing.whale_count / max(num_positions, 1)
    win_rate = getattr(flow, 'win_rate', None) or 0.5
    profit_factor = getattr(flow, 'profit_factor', None) or 1.0
    
    # Detect strong edge (used to distinguish info_edge from whale)
    has_strong_edge = win_rate > 0.65 or profit_factor > 2.0
    has_moderate_edge = win_rate > 0.55 and profit_factor > 1.2
    
    # Category analysis
    cat_counts = getattr(markets, 'category_counts', {})
    top_cats = list(cat_counts.keys())[:5] if cat_counts else []
    cat_values = list(cat_counts.values())[:5] if cat_counts else []
    total_cat = sum(cat_values) if cat_values else 1
    politics_focus = any('politic' in str(c).lower() or 'news' in str(c).lower() or 'election' in str(c).lower() for c in top_cats)
    has_non_sports = any(c in top_cats for c in ['politics', 'entertainment', 'crypto', 'economics', 'science_tech', 'weather'])
    # Sports-dominant = sports is the #1 category with >40% of positions
    sports_is_top = len(top_cats) > 0 and 'sport' in str(top_cats[0]).lower()
    sports_pct = (cat_values[0] / total_cat) if sports_is_top and total_cat > 0 else 0
    sports_dominant = sports_is_top and sports_pct > 0.40
    
    # === SPORTS WHALE detection (HIGHEST PRIORITY for large sports bettors) ===
    # Sports + large positions = whale, REGARDLESS of win rate
    # Sports bettors with high win rates are skilled whales, not info_edge
    if avg_pos > 50_000 and num_positions < 5000 and sports_dominant:
        hints.append(
            f"⚠️ SPORTS WHALE: avg position ${avg_pos:,.0f}, {num_positions} positions, "
            f"SPORTS-FOCUSED markets. Sports traders with large positions are whales — "
            f"high win rate in sports means skilled betting, NOT information edge. "
            f"Info_edge requires politics/news/crypto/event markets where early information "
            f"matters. Win rate {win_rate:.0%} does NOT change this classification for sports."
        )
    
    # === INFO EDGE detection (ONLY for non-sports event markets) ===
    low_entry = getattr(sizing, 'avg_entry_price', 0.5) < 0.45 or getattr(sizing, 'low_odds_pct', 0) > 0.30
    politics_count = sum(v for c, v in cat_counts.items() if any(kw in str(c).lower() for kw in ['politic', 'news', 'election']))
    politics_pct = politics_count / total_cat if total_cat > 0 else 0
    
    if avg_pos > 30_000 and has_strong_edge and has_non_sports and not sports_dominant:
        hints.append(f"⚠️ STRONG INFO EDGE SIGNAL: avg position ${avg_pos:,.0f} with win rate {win_rate:.0%} and profit factor {profit_factor:.1f}. Large positions WITH a strong consistent edge on event markets (politics/news/crypto) strongly suggests information advantage, NOT whale.")
        if politics_focus:
            hints.append(f"  → Politics/news focus confirms info edge — these markets reward early/insider information.")
    elif has_non_sports and not sports_dominant and politics_pct > 0.25 and low_entry and profit_factor > 1.1:
        hints.append(
            f"⚠️ INFO EDGE SIGNAL (news-focused): {politics_pct:.0%} politics/news markets, "
            f"avg entry price {getattr(sizing, 'avg_entry_price', 0.5):.2f}, "
            f"low-odds entries {getattr(sizing, 'low_odds_pct', 0):.0%}, PF {profit_factor:.1f}. "
            f"News/politics focus + early entry (low prices) = info edge trader who gets in before markets move. "
            f"NOT whale — whales bet BIG without timing advantage; info_edge traders bet BIG because they KNOW the outcome.")
    elif avg_pos > 30_000 and has_moderate_edge and has_non_sports and not sports_dominant and num_positions > 100:
        hints.append(f"⚠️ POSSIBLE INFO EDGE: avg position ${avg_pos:,.0f} with win rate {win_rate:.0%}, profit factor {profit_factor:.1f}, trading event markets. Consider info_edge over whale.")
    
    # === WHALE detection (non-sports or general): large avg + low edge ===
    if avg_pos > 50_000 and not has_strong_edge and not sports_dominant:
        if num_positions < 3000:
            hints.append(f"⚠️ STRONG WHALE SIGNAL: avg position ${avg_pos:,.0f} (>$50K) with only {num_positions} positions (<3000) and win rate {win_rate:.0%}. Large bets WITHOUT strong edge = whale.")
        if cv > 1.5:
            hints.append(f"⚠️ WHALE VARIANCE: CV={cv:.2f} (>1.5) with avg ${avg_pos:,.0f} and mediocre win rate {win_rate:.0%}.")
    if sizing.whale_count > 0 and whale_pct > 0.10 and not has_strong_edge:
        hints.append(f"⚠️ WHALE SIZING: {sizing.whale_count} positions >$100K ({whale_pct:.0%} of total) without consistent edge.")
    if sizing.max_position_size > 500_000 and not has_strong_edge:
        hints.append(f"⚠️ MEGA POSITION: max position ${sizing.max_position_size:,.0f} without strong edge — classic whale.")
    
    # === MODEL_BASED detection: consistent edge, especially in sports ===
    # Sports traders with consistent edge are using quantitative models, NOT info_edge
    # (info_edge requires politics/news/crypto where early information matters)
    if num_positions > 2000 and has_moderate_edge:
        edge = win_rate - 0.5
        if edge > 0.05 or profit_factor > 1.3:
            if sports_dominant:
                hints.append(
                    f"⚠️ SPORTS MODEL_BASED SIGNAL: {num_positions} positions, sports-dominant, "
                    f"win rate {win_rate:.0%}, PF {profit_factor:.1f}. Sports + consistent statistical edge "
                    f"= quantitative sports model. NOT info_edge (sports don't have insider info), "
                    f"NOT scalper (edge too strong/consistent), NOT market_maker (directional edge)."
                )
            elif cv < 1.5:
                hints.append(
                    f"⚠️ MODEL_BASED SIGNAL: {num_positions} positions with consistent edge "
                    f"(win rate {win_rate:.0%}, PF {profit_factor:.1f}), low CV ({cv:.2f}). "
                    f"High trade count with statistical edge = systematic quantitative trading. "
                    f"NOT whale (too many positions), NOT market_maker (edge too strong)."
                )
    
    # Very high count sports trading (>10K positions) with ANY positive edge = model_based
    # At this scale, even a thin edge (52-55% WR) is clearly systematic/algorithmic
    if sports_dominant and num_positions > 10_000 and win_rate > 0.52 and profit_factor > 1.0:
        if not any('SPORTS MODEL_BASED' in h for h in hints):
            hints.append(
                f"⚠️ SPORTS MODEL_BASED (high volume): {num_positions} positions (>10K), "
                f"sports-dominant, WR {win_rate:.0%}, PF {profit_factor:.1f}. "
                f"Extremely high position count with consistent positive edge at scale = "
                f"algorithmic sports model. Even thin edge (52-55%) at this volume is clearly "
                f"systematic/quantitative, NOT scalper or market_maker."
            )
    
    # Sports + moderate edge + high count but doesn't meet the above threshold
    if sports_dominant and num_positions > 500 and win_rate > 0.55 and profit_factor > 1.1:
        if not any('SPORTS MODEL_BASED' in h for h in hints):
            hints.append(
                f"⚠️ POSSIBLE SPORTS MODEL: sports-dominant with {num_positions} positions, "
                f"WR {win_rate:.0%}, PF {profit_factor:.1f}. Consistent edge in sports suggests "
                f"quantitative modeling (statistical/EV models). Consider model_based. "
                f"High CV ({cv:.2f}) may be caused by occasional large positions but does NOT "
                f"disqualify model_based — sports quant traders sometimes size up on high-confidence bets."
            )
    
    # === MARKET MAKER detection: VERY specific — near-50% WR + thin edge + huge volume ===
    # Tightened: requires very thin edge AND very high position count
    # EXCEPTION: crypto-dominant wallets are more likely scalpers (execution timing on short-timeframe markets)
    crypto_top = len(top_cats) > 0 and 'crypto' in str(top_cats[0]).lower()
    crypto_pct = (cat_values[0] / total_cat) if crypto_top and total_cat > 0 else 0
    crypto_dominant_hint = crypto_top and crypto_pct > 0.60
    
    if num_positions > 20_000 and avg_pos < 150_000:
        edge = abs(win_rate - 0.5)
        if edge < 0.03 and profit_factor < 1.15:
            if crypto_dominant_hint:
                hints.append(
                    f"⚠️ CRYPTO SCALPER SIGNAL: {num_positions} positions (>20K), "
                    f"avg ${avg_pos:,.0f}, win rate {win_rate:.0%} (edge {edge:.1%}), "
                    f"PF {profit_factor:.2f}, CRYPTO-DOMINANT ({crypto_pct:.0%}). "
                    f"Near-50% WR + crypto focus = scalper/arb on short-timeframe markets "
                    f"(e.g., Bitcoin Up/Down). They profit from execution timing, not liquidity provision. "
                    f"Consider SCALPER over market_maker."
                )
            else:
                hints.append(
                    f"⚠️ STRONG MARKET MAKER SIGNAL: {num_positions} positions (>20K), "
                    f"avg ${avg_pos:,.0f}, win rate {win_rate:.0%} (edge {edge:.1%}), "
                    f"PF {profit_factor:.2f}. Near-50% WR + razor-thin edge + massive volume = market maker."
                )
    elif num_positions > 40_000 and avg_pos < 150_000:
        hints.append(
            f"⚠️ POSSIBLE MARKET MAKER: {num_positions} positions (>40K), "
            f"avg ${avg_pos:,.0f}. Extreme volume suggests liquidity provision."
        )
    
    # === SCALPER detection: high frequency + small positions + moderate edge ===
    # Distinguished from market_maker by having SOME edge and smaller positions
    if num_positions > 5000 and avg_pos < 100_000:
        edge = win_rate - 0.5
        if 0.03 < edge < 0.15 and num_positions < 25_000:
            hints.append(
                f"⚠️ SCALPER SIGNAL: {num_positions} positions, avg ${avg_pos:,.0f}, "
                f"win rate {win_rate:.0%}. High-frequency small-profit trades with moderate edge. "
                f"Scalper differs from market_maker: scalpers have directional edge (WR >53%), "
                f"market makers have near-50% WR."
            )
    
    # Contrarian detection: NO-side bias + low entry prices
    no_pct = getattr(markets, 'no_pct', 0) or 0
    if no_pct > 0.60:
        hints.append(f"⚠️ CONTRARIAN SIGNAL: {no_pct:.0f}% NO-side positions — consistently betting against consensus.")
    
    # === ANTI-WHALE: small positions + high count = NOT whale ===
    if avg_pos < 10_000 and num_positions > 3000:
        hints.append(
            f"⚠️ NOT A WHALE: avg position ${avg_pos:,.0f} (<$10K) with {num_positions} positions. "
            f"Whales make LARGE concentrated bets ($50K+). This is high-frequency small-position trading. "
            f"Consider model_based, scalper, or market_maker instead."
        )
    elif avg_pos < 50_000 and num_positions > 10_000:
        hints.append(
            f"⚠️ UNLIKELY WHALE: avg position ${avg_pos:,.0f} with {num_positions} positions (>10K). "
            f"Whales have fewer, larger positions. This volume pattern suggests systematic trading."
        )
    
    if not hints:
        return ""
    
    return "\n\n## 🔍 RULE-BASED PRE-CLASSIFICATION HINTS (strong signals — weight these heavily):\n" + "\n".join(hints) + "\n"


async def skilled_analyze(wallet: str) -> WalletThesis:
    """Analyze a wallet using all 5 skills to build structured evidence."""
    # Fetch raw data
    profile, positions_raw, pnl_history = await asyncio.gather(
        get_wallet_ranking(wallet),
        get_wallet_positions(wallet),
        get_wallet_pnl_history(wallet),
    )

    # Convert Position objects to dicts for skills
    positions = [
        {"tb": p.tb, "ap": p.ap, "cp": p.cp, "pnl": p.pnl, "ts": p.ts, "t": p.t, "cid": p.cid, "o": p.o}
        for p in positions_raw
    ]

    # Run all 6 skills
    timing = analyze_timing(positions)
    sizing = analyze_sizing(positions)
    markets = analyze_markets(positions)
    flow = analyze_flow(positions)
    patterns = analyze_patterns(positions)
    correlations = analyze_correlations(positions)

    # Generate rule-based hints
    hints = rule_based_hints(sizing, flow, markets, len(positions))

    # Build context
    context = f"Wallet: {wallet}\n"
    if profile:
        context += f"Total PnL: ${profile.pnl_all_time:,.2f}\n"
        context += f"Rank: {profile.rank or 'N/A'}\n"
    context += f"Total positions: {len(positions)}\n\n"

    context += timing.to_text() + "\n\n"
    context += sizing.to_text() + "\n\n"
    context += markets.to_text() + "\n\n"
    context += flow.to_text() + "\n\n"
    context += patterns.to_text() + "\n\n"
    context += correlations.to_text() + "\n"
    context += hints

    messages = [
        {"role": "system", "content": SKILLED_PROMPT},
        {"role": "user", "content": f"Analyze this wallet based on the skill outputs:\n\n{context}"},
    ]

    raw = await call_llm(messages)
    data = json.loads(raw)
    
    # Validate strategy type
    strategy = data.get("primary_strategy", "unknown")
    valid = {s.value for s in StrategyType}
    if strategy not in valid:
        # Try fuzzy match
        for v in valid:
            if v in strategy.lower() or strategy.lower() in v:
                strategy = v
                break
        else:
            strategy = "unknown"
    data["primary_strategy"] = strategy
    
    # Validate secondary strategies
    data["secondary_strategies"] = [s for s in data.get("secondary_strategies", []) if s in valid]
    
    # Post-classification hard overrides for clear misclassifications
    data = _apply_hard_overrides(data, sizing, flow, markets, len(positions), profile)

    return WalletThesis(**data)


def _apply_hard_overrides(data: dict, sizing, flow, markets, num_positions: int, profile=None) -> dict:
    """Override LLM classification when rule-based signals are unambiguous.
    
    CONSERVATIVE: only override when signals are very clear to avoid false positives.
    """
    predicted = data.get("primary_strategy", "unknown")
    avg_pos = sizing.avg_position_size
    cv = sizing.coefficient_of_variation
    win_rate = getattr(flow, 'win_rate', None) or 0.5
    profit_factor = getattr(flow, 'profit_factor', None) or 1.0
    sharpe = getattr(profile, 'sharpe_score', None) if profile else None
    
    # Category analysis
    cat_counts = getattr(markets, 'category_counts', {})
    top_cats = list(cat_counts.keys())[:5] if cat_counts else []
    cat_values = list(cat_counts.values())[:5] if cat_counts else []
    total_cat = sum(cat_values) if cat_values else 1
    has_non_sports = any(c in top_cats for c in ['politics', 'entertainment', 'crypto', 'economics', 'science_tech', 'weather'])
    sports_is_top = len(top_cats) > 0 and 'sport' in str(top_cats[0]).lower()
    sports_pct = (cat_values[0] / total_cat) if sports_is_top and total_cat > 0 else 0
    sports_dominant = sports_is_top and sports_pct > 0.40
    has_politics_news = any(c in str(top_cats).lower() for c in ['politic', 'news', 'election', 'crypto'])
    
    def _do_override(new_strategy: str, reason: str):
        if predicted not in data.get("secondary_strategies", []):
            data.setdefault("secondary_strategies", []).append(predicted)
        data["primary_strategy"] = new_strategy
        data["evidence"] = data.get("evidence", []) + [reason]
    
    # === SPORTS WHALE OVERRIDE ===
    # Sports + large positions + low count = whale, even with high win rate
    # Sports bettors don't have "information edge" — they have skill or luck
    if predicted != "whale" and avg_pos > 100_000 and num_positions < 5000 and sports_dominant:
        _do_override("whale",
            f"OVERRIDE {predicted}→whale: avg ${avg_pos:,.0f}, {num_positions} positions, "
            f"SPORTS-DOMINANT markets. Large sports bettors are whales regardless of win rate.")
    
    # === GENERAL WHALE OVERRIDE (non-sports, conservative) ===
    # Only for very large positions + few trades + weak edge + NOT politics/news
    if predicted != "whale" and avg_pos > 300_000 and num_positions < 2500 and not has_politics_news:
        if win_rate < 0.55 or (sharpe is not None and sharpe < 0):
            _do_override("whale",
                f"OVERRIDE {predicted}→whale: avg ${avg_pos:,.0f}, {num_positions} positions, "
                f"win rate {win_rate:.0%}, Sharpe {sharpe} — large bets without edge, not politics/news")
    
    # === INFO_EDGE RESCUE ===
    # If classified as whale but trades politics/news/crypto → info_edge
    # Two tiers:
    #   1. Exceptional edge (WR>75% or PF>3.0) → always rescue
    #   2. Politics-HEAVY focus (>30% of positions) + profitable + low entry prices → rescue
    #      Info_edge traders often have moderate WR because they take many positions,
    #      but their real signal is MARKET SELECTION (news/politics events) + early entry.
    if predicted == "whale" and has_politics_news and not sports_dominant:
        politics_count = sum(v for c, v in cat_counts.items() if any(kw in str(c).lower() for kw in ['politic', 'news', 'election']))
        politics_pct = politics_count / total_cat if total_cat > 0 else 0
        low_entry = getattr(sizing, 'avg_entry_price', 0.5) < 0.45 or getattr(sizing, 'low_odds_pct', 0) > 0.30
        
        if win_rate > 0.75 or profit_factor > 3.0:
            _do_override("info_edge",
                f"OVERRIDE whale→info_edge: win rate {win_rate:.0%}, PF {profit_factor:.1f}, "
                f"trades politics/news/crypto markets — exceptional accuracy suggests information advantage")
        elif politics_pct > 0.25 and profit_factor > 1.1 and low_entry:
            _do_override("info_edge",
                f"OVERRIDE whale→info_edge: {politics_pct:.0%} politics/news markets, "
                f"PF {profit_factor:.1f}, avg entry {getattr(sizing, 'avg_entry_price', 'N/A'):.2f}, "
                f"low-odds {getattr(sizing, 'low_odds_pct', 0):.0%}. "
                f"News-focused + early entry + profitable = information edge trader")
    
    # === MODEL_BASED RESCUE ===
    # If classified as whale but has high trade count + consistent edge → model_based
    if predicted == "whale" and num_positions > 500 and cv < 1.2:
        if win_rate > 0.55 and profit_factor > 1.2:
            _do_override("model_based",
                f"OVERRIDE whale→model_based: {num_positions} positions, CV {cv:.2f}, "
                f"win rate {win_rate:.0%}, PF {profit_factor:.1f} — too consistent for whale")
    
    # === MODEL_BASED RESCUE (sports-specific, relaxed CV) ===
    # Sports model traders can have high CV from occasional large bets while core behavior
    # is systematic. Key signals: high position count + consistent win rate + sports focus.
    # CV is less informative for sports models because occasional big bets inflate it.
    if predicted == "whale" and sports_dominant and num_positions > 2000:
        if win_rate > 0.58 and profit_factor > 1.05 and avg_pos < 50_000:
            _do_override("model_based",
                f"OVERRIDE whale→model_based: sports-dominant, {num_positions} positions, "
                f"WR {win_rate:.0%}, PF {profit_factor:.1f}, avg ${avg_pos:,.0f}. "
                f"High position count + consistent edge in sports = quantitative model. "
                f"CV {cv:.2f} inflated by outlier positions, not indicative of whale behavior.")
    
    # === MODEL_BASED RESCUE (strong Sharpe, moderate count) ===
    # A sports trader with fewer positions (500-2000) but exceptional Sharpe (>0.8) and 
    # strong win rate is using a quantitative model, not blindly whale-betting.
    # Whales have inconsistent returns; high Sharpe = systematic edge.
    if predicted == "whale" and sports_dominant and 500 <= num_positions <= 2000:
        if sharpe is not None and sharpe > 0.8 and win_rate > 0.60:
            _do_override("model_based",
                f"OVERRIDE whale→model_based: sports, {num_positions} positions, "
                f"Sharpe {sharpe:.2f} (>0.8), WR {win_rate:.0%}. "
                f"High Sharpe + strong win rate = consistent quantitative edge, not whale.")
    
    # === MODEL_BASED RESCUE (sports, moderate count, strong edge without Sharpe) ===
    # Sports traders with 500-2000 positions, strong win rate (>60%), and meaningful
    # profit factor (>1.2) have a quantitative edge — not just whale-betting.
    # Whales bet big without consistent edge; these traders have repeatable alpha.
    if predicted == "whale" and sports_dominant and 500 <= num_positions <= 2000:
        if win_rate > 0.60 and profit_factor > 1.2 and avg_pos < 100_000:
            _do_override("model_based",
                f"OVERRIDE whale→model_based: sports, {num_positions} positions, "
                f"WR {win_rate:.0%} (>60%), PF {profit_factor:.1f} (>1.2), avg ${avg_pos:,.0f}. "
                f"Moderate position count + strong consistent edge = quantitative sports model, "
                f"not whale. Whales bet big WITHOUT edge; this trader has repeatable alpha.")
    
    # === ANTI-WHALE: Small avg position + high count = NOT whale ===
    # Whales have large positions. If avg < $10K and many positions, it's model_based/scalper/MM
    if predicted == "whale" and avg_pos < 10_000 and num_positions > 3000:
        # Determine best alternative based on edge and count
        edge = win_rate - 0.5
        if num_positions > 20_000 and abs(edge) < 0.03:
            new_strat = "market_maker"
            reason = f"OVERRIDE whale→market_maker: avg ${avg_pos:,.0f} (<$10K), {num_positions} positions (>20K), edge {edge:.1%} — too small and numerous for whale"
        elif num_positions > 2000 and edge > 0.03 and cv < 1.5:
            new_strat = "model_based"
            reason = f"OVERRIDE whale→model_based: avg ${avg_pos:,.0f} (<$10K), {num_positions} positions, win rate {win_rate:.0%}, CV {cv:.2f} — systematic small positions, not whale"
        elif num_positions > 5000 and 0.03 < edge < 0.15:
            new_strat = "scalper"
            reason = f"OVERRIDE whale→scalper: avg ${avg_pos:,.0f} (<$10K), {num_positions} positions, win rate {win_rate:.0%} — high-frequency small bets with moderate edge"
        else:
            new_strat = "model_based"
            reason = f"OVERRIDE whale→model_based: avg ${avg_pos:,.0f} (<$10K), {num_positions} positions — too small for whale"
        _do_override(new_strat, reason)
    
    # === ANTI-WHALE: Medium avg but very high count ===
    # Even with avg $10K-$50K, if position count is very high (>10K), it's not whale behavior
    if predicted == "whale" and avg_pos < 50_000 and num_positions > 10_000:
        edge = win_rate - 0.5
        if edge > 0.03 and cv < 2.0:
            _do_override("model_based",
                f"OVERRIDE whale→model_based: {num_positions} positions (>10K) with avg ${avg_pos:,.0f} (<$50K), "
                f"win rate {win_rate:.0%}, CV {cv:.2f} — high-frequency systematic trading, not whale")
    
    # === MODEL_BASED → INFO_EDGE for politics/news-heavy wallets with early entry ===
    # Model_based is systematic quant trading; info_edge is news/event-driven with timing advantage.
    # Key distinction: politics/news markets + low entry prices = getting in early on events they KNOW about.
    if predicted == "model_based" and has_politics_news and not sports_dominant:
        politics_count = sum(v for c, v in cat_counts.items() if any(kw in str(c).lower() for kw in ['politic', 'news', 'election']))
        politics_pct = politics_count / total_cat if total_cat > 0 else 0
        low_entry = getattr(sizing, 'avg_entry_price', 0.5) < 0.45 or getattr(sizing, 'low_odds_pct', 0) > 0.30
        if politics_pct > 0.25 and low_entry and profit_factor > 1.1:
            _do_override("info_edge",
                f"OVERRIDE model_based→info_edge: {politics_pct:.0%} politics/news markets, "
                f"avg entry {getattr(sizing, 'avg_entry_price', 'N/A'):.2f}, "
                f"low-odds {getattr(sizing, 'low_odds_pct', 0):.0%}, PF {profit_factor:.1f}. "
                f"News-focused + early entry = information edge, not systematic quant model.")

    # === INFO_EDGE → MODEL_BASED for high position count or moderate edge ===
    # True info_edge traders have EXCEPTIONAL accuracy (WR >75% or PF >3.0) on few bets
    # Model_based traders have MODERATE but consistent edge across many positions
    # EXCEPTION: politics/news-heavy wallets with early entry ARE info_edge even with many positions
    #   Info_edge traders on Polymarket can take thousands of positions across news events.
    #   The key signal is MARKET SELECTION (politics/news) + EARLY ENTRY (low prices), not position count.
    if predicted == "info_edge" and not sports_dominant:
        is_exceptional = win_rate > 0.75 or profit_factor > 3.0
        politics_count_ie = sum(v for c, v in cat_counts.items() if any(kw in str(c).lower() for kw in ['politic', 'news', 'election']))
        politics_pct_ie = politics_count_ie / total_cat if total_cat > 0 else 0
        low_entry_ie = getattr(sizing, 'avg_entry_price', 0.5) < 0.45 or getattr(sizing, 'low_odds_pct', 0) > 0.30
        has_news_signal = politics_pct_ie > 0.25 and low_entry_ie and profit_factor > 1.1
        
        if not is_exceptional and not has_news_signal and num_positions > 500:
            _do_override("model_based",
                f"OVERRIDE info_edge→model_based: {num_positions} positions with WR {win_rate:.0%}, "
                f"PF {profit_factor:.1f}. True info_edge has exceptional accuracy (WR>75% or PF>3.0) "
                f"or strong politics/news focus with early entry. "
                f"This is moderate consistent edge across many positions = systematic/quantitative.")
    
    # === CONTRARIAN DETECTION ===
    # Contrarian traders bet against consensus. Key signals:
    # - Crypto-focused (price prediction markets: "dip to", "above", "below")
    # - Entry prices near 0.50 (buying when market is uncertain/split)
    # - Moderate edge, both sides of directional bets
    # - NOT sports-dominant (sports has clear favorites, not contrarian plays)
    crypto_cats = sum(v for c, v in cat_counts.items() if 'crypto' in str(c).lower())
    crypto_pct = crypto_cats / total_cat if total_cat > 0 else 0
    avg_entry = getattr(sizing, 'avg_entry_price', 0.5)
    
    if predicted in ("scalper", "model_based") and not sports_dominant and crypto_pct > 0.60:
        # Crypto-specialist with entry near 0.50 = contrarian (betting against market consensus)
        if 0.45 <= avg_entry <= 0.55 and 500 < num_positions < 5000:
            _do_override("contrarian",
                f"OVERRIDE {predicted}→contrarian: {crypto_pct:.0%} crypto markets, "
                f"avg entry {avg_entry:.2f} (near 0.50 = buying at uncertainty), "
                f"{num_positions} positions. Crypto price prediction specialist "
                f"entering at consensus-split prices = contrarian strategy.")
    
    # === INFO_EDGE → MODEL_BASED for sports-dominant ===
    # Info_edge requires politics/news/crypto markets. Sports with consistent edge = model_based.
    if predicted == "info_edge" and sports_dominant:
        if win_rate > 0.55 and profit_factor > 1.1:
            _do_override("model_based",
                f"OVERRIDE info_edge→model_based: sports-dominant markets with WR {win_rate:.0%}, "
                f"PF {profit_factor:.1f}. Info_edge requires politics/news/crypto where early "
                f"information matters. Sports edge comes from quantitative models, not insider info.")
    
    # === SCALPER → MODEL_BASED for sports with strong edge ===
    if predicted == "scalper" and sports_dominant and win_rate > 0.58:
        _do_override("model_based",
            f"OVERRIDE scalper→model_based: sports-dominant, WR {win_rate:.0%} (>58%), "
            f"PF {profit_factor:.1f}. Strong consistent edge in sports = quantitative model, "
            f"not just high-frequency scalping.")
    
    # === SCALPER → MODEL_BASED for very high-count systematic sports trading ===
    # Scalpers are opportunistic; model_based is systematic. Key signals:
    # 1. Very high count + low CV = algorithmic
    # 2. Extremely high count (>20K) + sports + any positive edge = systematic quant model
    #    (nobody manually scalps 20K+ sports positions — that's an algorithm)
    if predicted == "scalper" and sports_dominant and num_positions > 15_000:
        if cv < 0.5:
            _do_override("model_based",
                f"OVERRIDE scalper→model_based: {num_positions} positions (>15K), CV {cv:.2f} (<0.5), "
                f"sports-dominant. Extremely high volume + very consistent sizing = systematic "
                f"quantitative model, not opportunistic scalping.")
        elif num_positions > 20_000 and win_rate > 0.51 and profit_factor > 1.0:
            _do_override("model_based",
                f"OVERRIDE scalper→model_based: {num_positions} positions (>20K), "
                f"sports-dominant, WR {win_rate:.0%}, PF {profit_factor:.1f}. "
                f"Nobody manually scalps 20K+ sports bets — this volume requires "
                f"algorithmic/quantitative execution. CV {cv:.2f} is high but irrelevant "
                f"at this scale; the sheer volume indicates systematic model-based trading.")
    
    # === MARKET_MAKER → MODEL_BASED for sports with real edge ===
    if predicted == "market_maker" and sports_dominant:
        edge = win_rate - 0.5
        if edge > 0.03 and profit_factor > 1.05:
            _do_override("model_based",
                f"OVERRIDE market_maker→model_based: sports-dominant, WR {win_rate:.0%} "
                f"(edge {edge:.1%}), PF {profit_factor:.1f}. Market makers have near-zero edge; "
                f"this trader has directional edge from sports modeling.")
    
    # === MARKET_MAKER → MODEL_BASED rescue for wallets with real directional edge ===
    # Market makers have near-zero edge (WR ~50%, PF ~1.0). If classified as market_maker
    # but has meaningful directional edge, it's model_based (systematic quant trading at scale)
    if predicted == "market_maker" and win_rate > 0.53 and profit_factor > 1.05:
        _do_override("model_based",
            f"OVERRIDE market_maker→model_based: WR {win_rate:.0%}, PF {profit_factor:.1f}. "
            f"Market makers have near-zero directional edge (WR ~50%). This trader has "
            f"meaningful edge = systematic quantitative trading at high volume.")
    
    # === MARKET MAKER OVERRIDE (very tight) ===
    # Only override when: massive count + near-exactly-50% WR + very thin edge
    # EXCEPTION: crypto-dominant wallets with ~50% WR are more likely scalpers/arb
    # (e.g., Bitcoin Up/Down short-timeframe traders who profit from execution timing)
    crypto_dominant = any('crypto' in str(c).lower() for c in top_cats[:1]) and len(top_cats) > 0 and (cat_values[0] / total_cat > 0.60 if cat_values else False)
    if predicted != "market_maker" and num_positions > 30_000 and avg_pos < 150_000:
        edge = abs(win_rate - 0.5)
        if edge < 0.02 and profit_factor < 1.10:
            if crypto_dominant:
                # Crypto-focused near-50% WR = scalper/arb, not market maker
                # They profit from execution timing on short-timeframe crypto markets
                _do_override("scalper",
                    f"OVERRIDE {predicted}→scalper: {num_positions} positions, "
                    f"avg ${avg_pos:,.0f}, win rate {win_rate:.0%}, PF {profit_factor:.2f}, "
                    f"CRYPTO-DOMINANT — short-timeframe crypto trading with execution edge, not market making")
            else:
                _do_override("market_maker",
                    f"OVERRIDE {predicted}→market_maker: {num_positions} positions, "
                    f"avg ${avg_pos:,.0f}, win rate {win_rate:.0%}, PF {profit_factor:.2f} — "
                    f"razor-thin edge + massive volume = market maker")
    
    return data


async def skilled_judge(prompt: str) -> JudgeAssessment:
    """Use LLM as judge."""
    schema_hint = json.dumps({
        "strategy_correct": True,
        "strategy_partial": False,
        "evidence_matches": [],
        "evidence_missed": [],
        "false_claims": [],
        "specificity_score": 0.5,
        "confidence_appropriate": 0.7,
        "reasoning": ""
    }, indent=2)
    messages = [
        {"role": "system", "content": f"You are an expert evaluator. Respond in valid JSON with EXACTLY these snake_case field names:\n{schema_hint}"},
        {"role": "user", "content": prompt},
    ]
    raw = await call_llm(messages, model=JUDGE_MODEL)
    return JudgeAssessment(**json.loads(raw))


async def main():
    print("🛠️  Running SKILLED evaluation (5 analysis tools)")
    print(f"   Analyzer: {ANALYZER_MODEL}")
    print(f"   Judge: {JUDGE_MODEL}")
    print()

    report = await evaluate_analyzer(
        analyze_fn=skilled_analyze,
        judge_fn=skilled_judge,
        model=ANALYZER_MODEL,
        skills_version="v1_skilled",
    )

    print(f"\n{'='*60}")
    print(report.summary())


if __name__ == "__main__":
    asyncio.run(main())
