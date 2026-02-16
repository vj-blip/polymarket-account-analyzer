"""Trainer agent — designs curriculum, sequences difficulty, adjusts training plan.

The trainer:
1. Reads evaluator performance trends
2. Identifies skill gaps (which strategies are weak)
3. Produces training curriculum: ordered list of wallets by difficulty
4. Adjusts difficulty based on performance
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from agent.llm import call_llm_json
from config import TRAINER_MODEL, CURRICULUM_DIR, PERFORMANCE_DIR, EVAL_DIR


TRAINER_SYSTEM_PROMPT = """You are a training curriculum designer for an AI wallet analyzer.

You will be given:
1. PERFORMANCE DATA — how the analyzer performs on different strategy types
2. AVAILABLE WALLETS — wallets that can be used for training (with metadata)
3. CURRENT CURRICULUM — what's already been trained on

Your job: Design the next training batch.

## Principles
- Start with strategies the analyzer is WORST at
- Progress from easy → medium → hard within each strategy type
- Include some already-mastered strategies to prevent regression
- Target 5-10 wallets per training batch
- Balance coverage across strategy types

## Output Format
Return JSON:
{
    "analysis": "What's weak and why",
    "skill_gaps": ["list of strategy types that need work"],
    "curriculum": [
        {
            "wallet": "0x...",
            "username": "name",
            "expected_strategy": "strategy_type",
            "difficulty": "easy|medium|hard",
            "training_goal": "What the analyzer should learn from this wallet"
        }
    ],
    "notes": "Training notes and expected outcomes"
}"""


def _read_performance_data() -> str:
    """Read performance trends for the trainer."""
    scores_file = PERFORMANCE_DIR / "scores.jsonl"
    if not scores_file.exists():
        return "No performance data yet."

    lines = scores_file.read_text().strip().split("\n")
    scores = [json.loads(line) for line in lines[-100:]]

    # Aggregate by actual strategy
    by_strategy: dict[str, dict] = {}
    for s in scores:
        actual = s.get("actual_strategy", "unknown")
        if actual == "unknown":
            continue
        if actual not in by_strategy:
            by_strategy[actual] = {"correct": 0, "total": 0, "scores": []}
        by_strategy[actual]["total"] += 1
        if s.get("strategy_correct"):
            by_strategy[actual]["correct"] += 1
        by_strategy[actual]["scores"].append(s.get("composite_score", 0))

    summary = "Performance by strategy type:\n"
    for strategy, data in sorted(by_strategy.items(), key=lambda x: x[1]["correct"] / max(x[1]["total"], 1)):
        accuracy = data["correct"] / data["total"] if data["total"] else 0
        avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
        summary += f"  {strategy}: {data['correct']}/{data['total']} ({accuracy:.0%}), avg score {avg_score:.3f}\n"

    return summary


def _read_available_wallets() -> str:
    """Read available wallets for training."""
    # Ground truth wallets
    gt_file = EVAL_DIR / "ground_truth" / "labeled.json"
    if gt_file.exists():
        with open(gt_file) as f:
            labeled = json.load(f)
    else:
        labeled = []

    # Unlabeled candidates
    candidates_file = EVAL_DIR / "ground_truth" / "unlabeled_candidates.json"
    if candidates_file.exists():
        with open(candidates_file) as f:
            unlabeled = json.load(f)
    else:
        unlabeled = []

    summary = f"Labeled wallets ({len(labeled)}):\n"
    for w in labeled:
        summary += f"  {w.get('username', w['wallet'][:12])}: {w.get('primary_strategy', '?')} ({w.get('difficulty', '?')})\n"

    summary += f"\nUnlabeled candidates ({len(unlabeled)}):\n"
    for w in unlabeled[:10]:
        summary += f"  {w.get('username', w['wallet'][:12])}: PnL ${w.get('pnl_total', 0):,.0f}, WR {w.get('win_rate_30d', 'N/A')}\n"

    return summary


def _read_current_curriculum() -> str:
    """Read current training curriculum."""
    curr_file = CURRICULUM_DIR / "current.json"
    if not curr_file.exists():
        return "No curriculum yet."
    with open(curr_file) as f:
        data = json.load(f)
    return json.dumps(data, indent=2)


async def generate_curriculum() -> dict:
    """Generate a new training curriculum based on performance data.
    
    Returns the curriculum dict.
    """
    performance = _read_performance_data()
    wallets = _read_available_wallets()
    current = _read_current_curriculum()

    context = f"""## PERFORMANCE DATA
{performance}

## AVAILABLE WALLETS
{wallets}

## CURRENT CURRICULUM
{current}
"""

    messages = [
        {"role": "system", "content": TRAINER_SYSTEM_PROMPT},
        {"role": "user", "content": f"Design the next training curriculum:\n\n{context}"},
    ]

    result = await call_llm_json(messages, TRAINER_MODEL)

    # Save curriculum
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    curr_file = CURRICULUM_DIR / "current.json"
    with open(curr_file, "w") as f:
        json.dump(result, f, indent=2)

    # Also append to history
    history_file = CURRICULUM_DIR / "history.jsonl"
    with open(history_file, "a") as f:
        f.write(json.dumps(result) + "\n")

    return result


def load_current_curriculum() -> list[dict]:
    """Load the current curriculum wallet list."""
    curr_file = CURRICULUM_DIR / "current.json"
    if not curr_file.exists():
        return []
    with open(curr_file) as f:
        data = json.load(f)
    return data.get("curriculum", [])
