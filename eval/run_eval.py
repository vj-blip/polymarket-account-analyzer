"""Run evaluation: test any analyzer function against ground truth.

Usage:
    python -m eval.run_eval                    # Run baseline (no skills)
    python -m eval.run_eval --model glm-5      # Specific model
    python -m eval.run_eval --skills v1        # With skills version
"""

from __future__ import annotations
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Awaitable

from .models import GroundTruth, WalletThesis, EvalScore, EvalReport
from .scorer import build_judge_prompt, assessment_to_score, JudgeAssessment


GROUND_TRUTH_PATH = Path(__file__).parent / "ground_truth" / "labeled.json"
RESULTS_DIR = Path(__file__).parent / "results"


def load_ground_truth() -> list[GroundTruth]:
    """Load labeled ground truth wallets."""
    with open(GROUND_TRUTH_PATH) as f:
        data = json.load(f)
    return [GroundTruth(**item) for item in data]


async def evaluate_analyzer(
    analyze_fn: Callable[[str], Awaitable[WalletThesis]],
    judge_fn: Callable[[str], Awaitable[JudgeAssessment]],
    model: str = "unknown",
    skills_version: str = "none",
) -> EvalReport:
    """Run a full eval: analyze each ground truth wallet, judge the result, score it.
    
    Args:
        analyze_fn: Takes wallet address, returns WalletThesis
        judge_fn: Takes judge prompt string, returns JudgeAssessment
        model: Model name for reporting
        skills_version: Skills version for reporting
    """
    ground_truth = load_ground_truth()
    
    if not ground_truth:
        print("⚠️  No labeled ground truth found! Label some wallets first.")
        print(f"   See: {GROUND_TRUTH_PATH}")
        return EvalReport(
            scores=[],
            model=model,
            skills_version=skills_version,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    
    scores: list[EvalScore] = []
    
    for gt in ground_truth:
        print(f"\n{'='*60}")
        print(f"Evaluating: {gt.username or gt.wallet} (difficulty: {gt.difficulty})")
        print(f"Ground truth: {gt.primary_strategy.value}")
        
        # Run the analyzer
        start = time.time()
        try:
            thesis = await analyze_fn(gt.wallet)
        except Exception as e:
            print(f"  ❌ Analyzer failed: {e}")
            scores.append(EvalScore(
                wallet=gt.wallet,
                strategy_correct=False,
                evidence_recall=0,
                false_claims=0,
                specificity=0,
                confidence_calibration=0,
            ))
            continue
        elapsed = time.time() - start
        
        print(f"  Thesis: {thesis.primary_strategy.value} (confidence: {thesis.confidence:.2f})")
        print(f"  Time: {elapsed:.1f}s")
        
        # Judge the thesis
        judge_prompt = build_judge_prompt(gt, thesis)
        try:
            assessment = await judge_fn(judge_prompt)
        except Exception as e:
            print(f"  ❌ Judge failed: {e}")
            continue
        
        score = assessment_to_score(
            wallet=gt.wallet,
            gt=gt,
            assessment=assessment,
            time_seconds=elapsed,
            predicted_strategy=thesis.primary_strategy.value if hasattr(thesis.primary_strategy, 'value') else str(thesis.primary_strategy),
        )
        scores.append(score)
        print(f"  Score: {score.composite_score:.3f} (strategy: {'✅' if score.strategy_correct else '❌'})")
    
    report = EvalReport(
        scores=scores,
        model=model,
        skills_version=skills_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    
    # Save results
    RESULTS_DIR.mkdir(exist_ok=True)
    result_file = RESULTS_DIR / f"eval_{model}_{skills_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(result_file, 'w') as f:
        json.dump(report.model_dump(), f, indent=2)
    
    print(f"\n{'='*60}")
    print(report.summary())
    print(f"Results saved to: {result_file}")
    
    return report


if __name__ == "__main__":
    print("Run with: python -m eval.run_eval")
    print("First, label some ground truth wallets in eval/ground_truth/labeled.json")
