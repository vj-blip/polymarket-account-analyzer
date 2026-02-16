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
from skills import analyze_timing, analyze_sizing, analyze_markets, analyze_flow, analyze_patterns

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANALYZER_MODEL = "gpt-4o-mini"
JUDGE_MODEL = "gpt-4o"

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


SKILLED_PROMPT = """You are an expert Polymarket trading strategy analyst. You have been given structured analysis from 5 specialized tools that examined a wallet's trading history.

Your job: Synthesize these analyses into a precise strategy classification.

## Strategy Types (pick the BEST match — do NOT default to "unknown"):
- **info_edge**: Trades on early/non-public information. Signs: enters before major events, high win rate on time-sensitive markets, speed-to-market advantage.
- **model_based**: Uses quantitative/statistical models. Signs: high trade count, consistent sizing, systematic entry prices, positive Sharpe, diverse markets, algorithmic patterns.
- **market_maker**: Provides liquidity. Signs: massive volume, thin margins (near 50% win rate, <0.05 edge), trades both sides, very high position count.
- **contrarian**: Bets against consensus. Signs: buys at low odds (<0.3), NO-side bias, wins from underdog bets.
- **momentum**: Follows trends. Signs: buys at high odds (>0.7), YES-side bias, enters after price moves.
- **hedger**: Hedges across markets. Signs: paired positions, opposing bets in correlated markets, low net exposure.
- **arbitrage**: Cross-market or cross-platform arb. Signs: near-simultaneous opposing positions, tiny margins, very high volume.
- **whale**: Large positions that move markets. Signs: very large avg position size (>$100K), few positions relative to volume, high variance.
- **scalper**: High-frequency small-profit trades. Signs: many small positions, quick entries/exits, thin margins, high trade count.
- **unknown**: ONLY if truly unclassifiable after reviewing all evidence.

## Decision Framework:
1. Check SIZING first — is this a whale (huge positions) or scalper (tiny positions)?
2. Check MARKET — specialist or diversified? Sports, politics, crypto?
3. Check FLOW — win rate, profit factor, accumulation patterns
4. Check PATTERNS — is edge consistent? Steady grinder or volatile?
5. Check TIMING — automated (consistent daily) or event-driven (sporadic)?

## Important Rules:
- Be SPECIFIC in evidence — cite numbers from the analysis
- If sizing shows avg position >$100K with few total positions, it's likely a WHALE
- If trade count >10K with consistent sizing and diverse markets, it's likely MODEL_BASED
- If win rate ~50% with massive volume and thin edge, it's likely MARKET_MAKER
- If strong NO-side bias with low entry prices, it's likely CONTRARIAN
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

    # Run all 5 skills
    timing = analyze_timing(positions)
    sizing = analyze_sizing(positions)
    markets = analyze_markets(positions)
    flow = analyze_flow(positions)
    patterns = analyze_patterns(positions)

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
    context += patterns.to_text() + "\n"

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
    
    return WalletThesis(**data)


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
