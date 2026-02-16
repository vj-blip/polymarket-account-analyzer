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
    """Fetch wallet data and format as text for the baseline (no tools)."""
    from .data_fetcher import ALGOARENA_API
    
    async with httpx.AsyncClient(timeout=30) as client:
        # Get profile
        try:
            resp = await client.get(f"{ALGOARENA_API}/api/profile/{wallet}")
            profile = resp.json() if resp.status_code == 200 else {}
        except Exception:
            profile = {}
        
        # Get activities
        try:
            resp = await client.get(f"{ALGOARENA_API}/api/activities/{wallet}", params={"limit": 200})
            activities = resp.json() if resp.status_code == 200 else []
        except Exception:
            activities = []
    
    # Format as readable text
    text = f"Wallet: {wallet}\n"
    if profile:
        text += f"Username: {profile.get('username', 'unknown')}\n"
        text += f"Total PnL: ${profile.get('pnl_total', 0):,.2f}\n"
        text += f"Total Volume: ${profile.get('volume_total', 0):,.2f}\n"
        text += f"Win Rate (30d): {profile.get('win_rate_30d', 'N/A')}\n"
        text += f"Rank: {profile.get('rank', 'N/A')}\n"
    
    if activities:
        text += f"\nRecent Trades ({len(activities)} shown):\n"
        for a in activities[:100]:  # Cap at 100 for context window
            text += (
                f"  {a.get('type', '?')} {a.get('side', '?')} "
                f"${a.get('usdc_size', 0):,.0f} @ {a.get('price', 0):.2f} "
                f"on \"{a.get('title', '?')}\" [{a.get('outcome', '?')}] "
                f"ts={a.get('timestamp', 0)}\n"
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
