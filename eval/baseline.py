"""Baseline analyzer: raw LLM with no skills, no tools — just the prompt.

This establishes the floor. Every improvement should beat this.

Usage:
    python -m eval.baseline
"""

from __future__ import annotations
import asyncio
import json
import os
from dotenv import load_dotenv
import httpx
from openai import AsyncOpenAI

from .models import WalletThesis, StrategyType
from .scorer import JudgeAssessment
from .run_eval import evaluate_analyzer

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DEFAULT_MODEL = "gpt-4o-mini"  # Cheap baseline
JUDGE_MODEL = "gpt-4o"  # Better judge

_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


BASELINE_PROMPT = """You are analyzing a Polymarket trading wallet.

Given the wallet data below, determine:
1. What trading strategy is this wallet using?
2. What evidence supports your thesis?
3. How confident are you?

Strategy types: info_edge, model_based, market_maker, contrarian, momentum, hedger, arbitrage, whale, scalper, unknown

Respond in JSON matching this schema:
{
    "wallet": "<address>",
    "primary_strategy": "<strategy_type>",
    "secondary_strategies": [],
    "confidence": 0.0-1.0,
    "evidence": ["list of evidence points"],
    "reasoning": "your reasoning",
    "signals_to_monitor": ["things to watch"],
    "risk_assessment": "assessment"
}"""


async def call_llm(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
) -> str:
    """Call OpenAI API."""
    resp = await _client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"},
        timeout=120,
    )
    return resp.choices[0].message.content


async def fetch_wallet_data_raw(wallet: str) -> str:
    """Fetch wallet data and format as text for the baseline (no tools).
    
    Includes aggregate stats + top positions to stay within context limits.
    """
    from .data_fetcher import get_wallet_ranking, get_wallet_positions, get_wallet_pnl_history
    from datetime import datetime as dt
    from collections import Counter
    
    # Fetch all data concurrently
    profile, positions, pnl_history = await asyncio.gather(
        get_wallet_ranking(wallet),
        get_wallet_positions(wallet),
        get_wallet_pnl_history(wallet),
    )
    
    text = f"Wallet: {wallet}\n"
    if profile:
        text += f"Total PnL: ${profile.pnl_all_time:,.2f}\n"
        text += f"Rank: {profile.rank or 'N/A'}\n"
    
    # Aggregate stats from positions
    if positions:
        wins = [p for p in positions if p.pnl > 0]
        losses = [p for p in positions if p.pnl <= 0]
        total_invested = sum(p.tb for p in positions)
        total_pnl = sum(p.pnl for p in positions)
        avg_position_size = total_invested / len(positions) if positions else 0
        win_rate = len(wins) / len(positions) if positions else 0
        
        # Category analysis (from market titles)
        categories = Counter()
        for p in positions:
            title_lower = p.t.lower()
            if any(w in title_lower for w in ['spread', 'moneyline', 'over/under', 'nfl', 'nba', 'mlb', 'nhl']):
                categories['sports_betting'] += 1
            elif any(w in title_lower for w in ['president', 'election', 'trump', 'biden', 'vote', 'congress', 'senate']):
                categories['politics'] += 1
            elif any(w in title_lower for w in ['bitcoin', 'eth', 'crypto', 'price']):
                categories['crypto'] += 1
            elif any(w in title_lower for w in ['fed', 'rate', 'inflation', 'gdp', 'economic']):
                categories['economics'] += 1
            else:
                categories['other'] += 1
        
        # Price distribution (how they enter)
        avg_entry_prices = [p.ap for p in positions if p.ap > 0]
        low_odds = len([p for p in avg_entry_prices if p < 0.3])
        mid_odds = len([p for p in avg_entry_prices if 0.3 <= p <= 0.7])
        high_odds = len([p for p in avg_entry_prices if p > 0.7])
        
        text += f"\n--- AGGREGATE STATS ---\n"
        text += f"Total positions: {len(positions)}\n"
        text += f"Win rate: {win_rate:.1%} ({len(wins)}W / {len(losses)}L)\n"
        text += f"Total invested: ${total_invested:,.0f}\n"
        text += f"Total PnL: ${total_pnl:,.0f}\n"
        text += f"Avg position size: ${avg_position_size:,.0f}\n"
        text += f"Avg win: ${sum(p.pnl for p in wins)/len(wins):,.0f}\n" if wins else ""
        text += f"Avg loss: ${sum(p.pnl for p in losses)/len(losses):,.0f}\n" if losses else ""
        text += f"Largest win: ${max(p.pnl for p in wins):,.0f}\n" if wins else ""
        text += f"Largest loss: ${min(p.pnl for p in losses):,.0f}\n" if losses else ""
        text += f"\nMarket categories: {dict(categories.most_common())}\n"
        text += f"Entry price distribution: low(<0.3)={low_odds}, mid(0.3-0.7)={mid_odds}, high(>0.7)={high_odds}\n"
    
    # PnL history (last 30 days)
    if pnl_history:
        text += f"\nDaily PnL (last {min(len(pnl_history), 30)} days):\n"
        for entry in pnl_history[-30:]:
            date = dt.fromtimestamp(entry['t']).strftime('%Y-%m-%d')
            text += f"  {date}: ${entry['p']:,.0f}\n"
    
    # Top 50 positions by |PnL| (keeping prompt manageable)
    if positions:
        sorted_pos = sorted(positions, key=lambda p: abs(p.pnl), reverse=True)
        text += f"\nTop 50 positions by |PnL| (of {len(positions)} total):\n"
        for p in sorted_pos[:50]:
            date = dt.fromtimestamp(p.ts).strftime('%Y-%m-%d') if p.ts else '?'
            win = "W" if p.pnl > 0 else "L"
            text += (
                f"  [{win}] ${p.pnl:+,.0f} | ${p.tb:,.0f} @ {p.ap:.2f}→{p.cp:.2f} "
                f"| \"{p.t}\" [{p.o}] {date}\n"
            )
    
    return text


async def baseline_analyze(wallet: str) -> WalletThesis:
    """Baseline: dump all data into prompt, ask LLM to analyze. No tools, no iteration."""
    wallet_data = await fetch_wallet_data_raw(wallet)
    
    messages = [
        {"role": "system", "content": BASELINE_PROMPT},
        {"role": "user", "content": f"Analyze this wallet:\n\n{wallet_data}"},
    ]
    
    raw = await call_llm(messages)
    data = json.loads(raw)
    return WalletThesis(**data)


async def baseline_judge(prompt: str) -> JudgeAssessment:
    """Use LLM as judge to score a thesis against ground truth."""
    schema_hint = json.dumps({
        "strategy_correct": True,
        "strategy_partial": False,
        "evidence_matches": ["list of matched evidence descriptions"],
        "evidence_missed": ["list of missed evidence descriptions"],
        "false_claims": ["list of false claims"],
        "specificity_score": 0.5,
        "confidence_appropriate": 0.7,
        "reasoning": "your reasoning here"
    }, indent=2)
    messages = [
        {"role": "system", "content": f"You are an expert evaluator. Respond in valid JSON with EXACTLY these snake_case field names:\n{schema_hint}"},
        {"role": "user", "content": prompt},
    ]
    
    raw = await call_llm(messages, model=JUDGE_MODEL)
    return JudgeAssessment(**json.loads(raw))


async def main():
    print("🏁 Running baseline evaluation (no skills, raw LLM)")
    print(f"   Model: {DEFAULT_MODEL}")
    print(f"   Judge: {JUDGE_MODEL}")
    print()
    
    report = await evaluate_analyzer(
        analyze_fn=baseline_analyze,
        judge_fn=baseline_judge,
        model=DEFAULT_MODEL,
        skills_version="baseline",
    )
    
    if not report.scores:
        print("\n⚠️  No scores! Label some ground truth wallets first.")
        print("   1. Pick wallets from eval/ground_truth/unlabeled_candidates.json")
        print("   2. Add labels to eval/ground_truth/labeled.json")
        print("   3. Re-run this script")


if __name__ == "__main__":
    asyncio.run(main())
