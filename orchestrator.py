"""Orchestrator — coordinates the 4-agent self-improving system.

Usage:
    python -m orchestrator train     # Full training loop (curriculum → analyze → eval → improve → repeat)
    python -m orchestrator analyze   # Analyze specific wallets
    python -m orchestrator eval      # Run eval suite only
    python -m orchestrator improve   # Run one improvement cycle only
    python -m orchestrator curriculum # Generate curriculum only
    python -m orchestrator loop      # Continuous training loop (N rounds)
"""

from __future__ import annotations
import asyncio
import argparse
import json
import sys
from datetime import datetime, timezone

from agent.executor.agent import run_analysis
from agent.evaluator.agent import score_thesis, run_full_eval, detect_regression, load_ground_truth
from agent.improver.agent import run_improvement_cycle, rollback_changes
from agent.trainer.agent import generate_curriculum, load_current_curriculum
from eval.models import EvalReport
from config import EXECUTOR_MODEL, PERFORMANCE_DIR


async def cmd_train():
    """Run one full training cycle: curriculum → analyze → eval → improve."""
    print("=" * 60)
    print("🏋️  TRAINING CYCLE")
    print("=" * 60)

    # Step 1: Trainer generates curriculum
    print("\n📋 Step 1: Generating curriculum...")
    curriculum = await generate_curriculum()
    wallets = curriculum.get("curriculum", [])
    print(f"   Skill gaps: {curriculum.get('skill_gaps', [])}")
    print(f"   Training batch: {len(wallets)} wallets")

    if not wallets:
        print("   No wallets in curriculum. Using ground truth wallets.")
        gt = load_ground_truth()
        wallets = [{"wallet": w, "username": gt[w].username} for w in gt]

    # Step 2: Executor analyzes each wallet
    print(f"\n🔍 Step 2: Executor analyzing {len(wallets)} wallets...")
    theses = []
    for i, entry in enumerate(wallets):
        wallet = entry.get("wallet", entry) if isinstance(entry, dict) else entry
        username = entry.get("username", wallet[:12]) if isinstance(entry, dict) else wallet[:12]
        print(f"   [{i+1}/{len(wallets)}] {username}...", end=" ", flush=True)
        try:
            thesis, logger = await run_analysis(wallet)
            theses.append(thesis)
            print(f"→ {thesis.primary_strategy.value} (conf: {thesis.confidence:.2f})")
        except Exception as e:
            print(f"💥 {e}")

    # Step 3: Evaluator scores results
    print(f"\n📊 Step 3: Evaluating {len(theses)} theses...")
    gt = load_ground_truth()
    scores = []
    for thesis in theses:
        score = await score_thesis(thesis, gt)
        scores.append(score)
        if thesis.wallet in gt:
            status = "✅" if score.strategy_correct else "❌"
            print(f"   {status} {thesis.wallet[:12]}: {score.composite_score:.3f} "
                  f"(predicted={score.predicted_strategy}, actual={score.actual_strategy})")

    # Build report
    report = EvalReport(
        scores=scores,
        model=EXECUTOR_MODEL,
        skills_version="current",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    print(f"\n{report.summary()}")

    # Step 4: Check for regression
    regression = detect_regression(report)
    if regression:
        print(f"⚠️  REGRESSION DETECTED: {regression['previous_best']:.3f} → {regression['current']:.3f}")

    # Step 5: Self-improver analyzes and improves
    print("\n🧬 Step 4: Self-improver analyzing failures...")
    improvement = await run_improvement_cycle()
    print(f"   Analysis: {improvement.get('analysis', 'N/A')[:200]}")
    print(f"   Changes: {len(improvement.get('changes', []))}")
    print(f"   Expected impact: {improvement.get('expected_impact', 'N/A')[:200]}")

    # Step 6: Re-eval after improvements
    print("\n🔄 Step 5: Re-evaluating after improvements...")
    async def analyze_only(wallet):
        thesis, _ = await run_analysis(wallet)
        return thesis

    post_report = await run_full_eval(analyze_only, skills_version="post_improve")
    print(f"\n{post_report.summary()}")

    # Check if improvement helped
    delta = post_report.mean_score - report.mean_score
    if delta > 0:
        print(f"✅ Improvement: +{delta:.3f} composite score")
    elif delta < -0.03:
        print(f"⚠️ Degradation: {delta:.3f}. Rolling back...")
        rolled = await rollback_changes()
        print(f"   Rolled back {rolled} files")
    else:
        print(f"→ Neutral change: {delta:+.3f}")

    return post_report


async def cmd_loop(rounds: int = 5):
    """Run multiple training cycles."""
    print(f"🔄 Running {rounds} training rounds\n")
    for i in range(rounds):
        print(f"\n{'#' * 60}")
        print(f"# ROUND {i+1}/{rounds}")
        print(f"{'#' * 60}")
        report = await cmd_train()
        print(f"\n📈 Round {i+1} score: {report.mean_score:.3f}")
        print(f"   Strategy accuracy: {report.strategy_accuracy:.1%}")


async def cmd_eval():
    """Run eval suite only."""
    print("📊 Running evaluation...")
    async def analyze_only(wallet):
        thesis, _ = await run_analysis(wallet)
        return thesis

    report = await run_full_eval(analyze_only, skills_version="eval_run")
    print(f"\n{report.summary()}")
    return report


async def cmd_analyze(wallets: list[str]):
    """Analyze specific wallets."""
    for wallet in wallets:
        print(f"\n🔍 Analyzing {wallet}...")
        try:
            thesis, logger = await run_analysis(wallet)
            print(f"   Strategy: {thesis.primary_strategy.value}")
            print(f"   Confidence: {thesis.confidence:.2f}")
            print(f"   Evidence:")
            for e in thesis.evidence[:5]:
                print(f"     - {e}")
            print(f"   Reasoning: {thesis.reasoning[:300]}")
            summary = logger.get_summary()
            print(f"   Log: {summary['log_file']} ({summary['total_entries']} entries, {summary['elapsed_s']:.1f}s)")
        except Exception as e:
            print(f"   💥 Failed: {e}")


async def cmd_improve():
    """Run one improvement cycle."""
    print("🧬 Running self-improvement cycle...")
    result = await run_improvement_cycle()
    print(f"   Analysis: {result.get('analysis', 'N/A')}")
    print(f"   Changes: {len(result.get('changes', []))}")
    for change in result.get("changes", []):
        print(f"     - {change['type']}: {change['file']} — {change['reason']}")
    print(f"   Expected impact: {result.get('expected_impact', 'N/A')}")


async def cmd_curriculum():
    """Generate curriculum only."""
    print("📋 Generating training curriculum...")
    result = await generate_curriculum()
    print(f"   Skill gaps: {result.get('skill_gaps', [])}")
    print(f"   Wallets: {len(result.get('curriculum', []))}")
    for w in result.get("curriculum", []):
        print(f"     - {w.get('username', w.get('wallet', '?')[:12])}: "
              f"{w.get('expected_strategy', '?')} ({w.get('difficulty', '?')}) — {w.get('training_goal', '')}")


def main():
    parser = argparse.ArgumentParser(description="Polymarket Account Analyzer Orchestrator")
    parser.add_argument("command", choices=["train", "loop", "eval", "analyze", "improve", "curriculum"],
                        help="Command to run")
    parser.add_argument("--wallets", nargs="*", help="Wallet addresses (for analyze command)")
    parser.add_argument("--rounds", type=int, default=5, help="Number of training rounds (for loop command)")
    
    args = parser.parse_args()

    if args.command == "train":
        asyncio.run(cmd_train())
    elif args.command == "loop":
        asyncio.run(cmd_loop(args.rounds))
    elif args.command == "eval":
        asyncio.run(cmd_eval())
    elif args.command == "analyze":
        if not args.wallets:
            print("Provide wallets: python -m orchestrator analyze --wallets 0xABC 0xDEF")
            sys.exit(1)
        asyncio.run(cmd_analyze(args.wallets))
    elif args.command == "improve":
        asyncio.run(cmd_improve())
    elif args.command == "curriculum":
        asyncio.run(cmd_curriculum())


if __name__ == "__main__":
    main()
