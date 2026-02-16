"""Executor agent — analyzes wallets using skills. Cannot write code.

The executor:
1. Fetches wallet data from AlgoArena
2. Runs all available analysis skills
3. Feeds structured analysis to LLM for thesis synthesis
4. Applies rule-based overrides for known patterns
5. Logs every step

It is deliberately constrained: it can only RUN existing skills, not modify them.
"""

from __future__ import annotations
import asyncio
import json
import importlib
import inspect
from pathlib import Path

from eval.models import WalletThesis, StrategyType
from eval.data_fetcher import get_wallet_ranking, get_wallet_positions, get_wallet_pnl_history
from agent.llm import call_llm_json
from agent.executor.logger import ExecutorLogger
from agent.executor.prompts import EXECUTOR_SYSTEM_PROMPT
from config import EXECUTOR_MODEL, SKILLS_DIR
import skills


# Map of skill name -> function
SKILL_REGISTRY: dict[str, callable] = {
    "timing_analysis": skills.analyze_timing,
    "sizing_analysis": skills.analyze_sizing,
    "market_analysis": skills.analyze_markets,
    "flow_analysis": skills.analyze_flow,
    "pattern_analysis": skills.analyze_patterns,
}


def discover_skills() -> dict[str, callable]:
    """Discover all analysis skills from the skills directory.
    
    Re-imports skills module to pick up any new skills added by the self-improver.
    """
    importlib.reload(skills)
    registry = {}
    for name in dir(skills):
        obj = getattr(skills, name)
        if callable(obj) and name.startswith("analyze_"):
            skill_name = name.replace("analyze_", "") + "_analysis"
            registry[skill_name] = obj
    return registry


def search_skill(query: str) -> str | None:
    """Search for a relevant skill by keyword. Returns skill name or None."""
    registry = discover_skills()
    query_lower = query.lower()
    for name in registry:
        if any(kw in name for kw in query_lower.split()):
            return name
    # Fuzzy: check skill file docstrings
    for py_file in SKILLS_DIR.glob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text()[:500].lower()
        if any(kw in content for kw in query_lower.split()):
            skill_name = py_file.stem.replace("_analyzer", "") + "_analysis"
            if skill_name in registry:
                return skill_name
    return None


async def run_analysis(wallet: str, model: str | None = None) -> tuple[WalletThesis, ExecutorLogger]:
    """Run full analysis on a wallet. Returns thesis and logger.
    
    This is the main entry point for the executor agent.
    """
    model = model or EXECUTOR_MODEL
    logger = ExecutorLogger(wallet)
    logger.log("start", {"wallet": wallet, "model": model})

    # Step 1: Fetch data
    logger.log_tool_call("fetch_data", {"wallet": wallet})
    try:
        profile, positions_raw, pnl_history = await asyncio.gather(
            get_wallet_ranking(wallet),
            get_wallet_positions(wallet),
            get_wallet_pnl_history(wallet),
        )
        positions = [
            {"tb": p.tb, "ap": p.ap, "cp": p.cp, "pnl": p.pnl, "ts": p.ts, "t": p.t, "cid": p.cid, "o": p.o}
            for p in positions_raw
        ]
        logger.log_tool_result("fetch_data", f"{len(positions)} positions, profile={'found' if profile else 'missing'}")
    except Exception as e:
        logger.log_error(f"Data fetch failed: {e}")
        raise

    if not positions:
        logger.log_error("No positions found")
        raise ValueError(f"No position data for wallet {wallet}")

    # Step 2: Run all skills
    registry = discover_skills()
    skill_results: dict[str, str] = {}

    for skill_name, skill_fn in registry.items():
        logger.log_skill_search(skill_name, skill_name)
        try:
            logger.log_tool_call("run_skill", {"skill": skill_name})
            result = skill_fn(positions)
            text = result.to_text() if hasattr(result, "to_text") else str(result)
            skill_results[skill_name] = text
            # Store raw result for rule-based hints
            if skill_name == "sizing_analysis":
                sizing = result
            elif skill_name == "flow_analysis":
                flow = result
            elif skill_name == "market_analysis":
                markets = result
            logger.log_skill_run(skill_name, text[:200])
        except Exception as e:
            logger.log_error(f"Skill {skill_name} failed: {e}")
            skill_results[skill_name] = f"ERROR: {e}"

    # Step 3: Build context for LLM
    context = f"Wallet: {wallet}\n"
    if profile:
        context += f"Total PnL: ${profile.pnl_all_time:,.2f}\n"
        context += f"Rank: {profile.rank or 'N/A'}\n"
    context += f"Total positions: {len(positions)}\n\n"

    for name, text in skill_results.items():
        context += f"=== {name.upper()} ===\n{text}\n\n"

    # Step 4: Generate rule-based hints (from skilled_analyzer)
    try:
        from eval.skilled_analyzer import rule_based_hints
        hints = rule_based_hints(sizing, flow, markets, len(positions))
        context += hints
        logger.log_reasoning(f"Rule-based hints: {hints[:300]}")
    except Exception as e:
        logger.log_error(f"Rule-based hints failed: {e}")

    # Step 5: LLM synthesis
    logger.log_tool_call("llm_synthesis", {"model": model})
    messages = [
        {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
        {"role": "user", "content": f"Analyze this wallet:\n\n{context}"},
    ]

    try:
        data = await call_llm_json(messages, model)
    except Exception as e:
        logger.log_error(f"LLM synthesis failed: {e}")
        raise

    # Step 6: Validate and fix strategy
    strategy = data.get("primary_strategy", "unknown")
    valid = {s.value for s in StrategyType}
    if strategy not in valid:
        for v in valid:
            if v in strategy.lower() or strategy.lower() in v:
                strategy = v
                break
        else:
            strategy = "unknown"
    data["primary_strategy"] = strategy
    data["secondary_strategies"] = [s for s in data.get("secondary_strategies", []) if s in valid]
    data["wallet"] = wallet

    # Step 7: Apply hard overrides
    try:
        from eval.skilled_analyzer import _apply_hard_overrides
        data = _apply_hard_overrides(data, sizing, flow, markets, len(positions), profile)
        logger.log_reasoning(f"Final strategy after overrides: {data['primary_strategy']}")
    except Exception as e:
        logger.log_error(f"Hard overrides failed: {e}")

    thesis = WalletThesis(**data)
    logger.log_thesis(thesis.model_dump())
    logger.log("complete", logger.get_summary())

    return thesis, logger
