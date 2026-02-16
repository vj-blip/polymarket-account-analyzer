"""Evaluator agent — scores theses, tracks performance, detects regressions.

The evaluator:
1. Scores each thesis against ground truth (when available)
2. Uses heuristic scoring when no ground truth exists
3. Tracks scores over time in data/performance/
4. Detects regressions after skill updates
"""

from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from eval.models import GroundTruth, WalletThesis, EvalScore, EvalReport
from eval.scorer import build_judge_prompt, assessment_to_score, JudgeAssessment
from agent.llm import call_llm_json
from config import EVALUATOR_MODEL, JUDGE_MODEL, PERFORMANCE_DIR, EVAL_DIR


SCORES_FILE = PERFORMANCE_DIR / "scores.jsonl"
TRENDS_FILE = PERFORMANCE_DIR / "trends.json"


def load_ground_truth() -> dict[str, GroundTruth]:
    """Load ground truth indexed by wallet address."""
    gt_file = EVAL_DIR / "ground_truth" / "labeled.json"
    if not gt_file.exists():
        return {}
    with open(gt_file) as f:
        data = json.load(f)
    return {item["wallet"]: GroundTruth(**item) for item in data}


async def score_thesis(
    thesis: WalletThesis,
    ground_truth: dict[str, GroundTruth] | None = None,
) -> EvalScore:
    """Score a single thesis. Uses LLM judge if ground truth available, heuristic otherwise."""
    if ground_truth is None:
        ground_truth = load_ground_truth()

    gt = ground_truth.get(thesis.wallet)

    if gt:
        # Full LLM judge evaluation against ground truth
        judge_prompt = build_judge_prompt(gt, thesis)
        try:
            raw = await call_llm_json(
                [
                    {"role": "system", "content": "You are an expert evaluator. Respond in valid JSON with fields: strategy_correct, strategy_partial, evidence_matches (list), evidence_missed (list), false_claims (list), specificity_score (0-1), confidence_appropriate (0-1), reasoning (string)."},
                    {"role": "user", "content": judge_prompt},
                ],
                model=JUDGE_MODEL,
            )
            assessment = JudgeAssessment(**raw)
            score = assessment_to_score(
                wallet=thesis.wallet, gt=gt, assessment=assessment
            )
        except Exception as e:
            # Fallback: simple strategy match
            score = EvalScore(
                wallet=thesis.wallet,
                predicted_strategy=thesis.primary_strategy.value,
                actual_strategy=gt.primary_strategy.value,
                strategy_correct=thesis.primary_strategy == gt.primary_strategy,
                evidence_recall=0.0,
                false_claims=0,
                specificity=0.5,
                confidence_calibration=0.5,
            )
    else:
        # Heuristic scoring (no ground truth)
        score = _heuristic_score(thesis)

    # Persist score
    _append_score(score)
    return score


def _heuristic_score(thesis: WalletThesis) -> EvalScore:
    """Score a thesis heuristically when no ground truth is available.
    
    Measures: specificity of evidence, confidence calibration, completeness.
    Cannot measure strategy correctness without ground truth.
    """
    # Specificity: how many evidence points have numbers?
    evidence_with_numbers = sum(
        1 for e in thesis.evidence
        if any(c.isdigit() for c in e) or "$" in e or "%" in e
    )
    specificity = min(1.0, evidence_with_numbers / max(len(thesis.evidence), 1))

    # Completeness: does it have reasoning, signals, risk assessment?
    completeness = 0.0
    if thesis.reasoning and len(thesis.reasoning) > 50:
        completeness += 0.4
    if thesis.signals_to_monitor:
        completeness += 0.3
    if thesis.risk_assessment and len(thesis.risk_assessment) > 10:
        completeness += 0.3

    return EvalScore(
        wallet=thesis.wallet,
        predicted_strategy=thesis.primary_strategy.value,
        actual_strategy="unknown",
        strategy_correct=False,  # Can't know without ground truth
        evidence_recall=completeness,
        false_claims=0,
        specificity=specificity,
        confidence_calibration=0.5,  # Neutral
    )


def _append_score(score: EvalScore):
    """Append score to the running scores file."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **score.model_dump(),
        "composite_score": score.composite_score,
    }
    with open(SCORES_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


async def run_full_eval(
    analyze_fn,
    skills_version: str = "current",
    model: str = "",
) -> EvalReport:
    """Run evaluation against all ground truth wallets."""
    ground_truth = load_ground_truth()
    if not ground_truth:
        print("No ground truth wallets labeled.")
        return EvalReport(
            scores=[], model=model, skills_version=skills_version,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    scores = []
    for wallet, gt in ground_truth.items():
        print(f"  Evaluating {gt.username or wallet[:12]}...", end=" ", flush=True)
        start = time.time()
        try:
            thesis = await analyze_fn(wallet)
            elapsed = time.time() - start
            score = await score_thesis(thesis, ground_truth)
            score.time_seconds = elapsed
            scores.append(score)
            print(f"{'✅' if score.strategy_correct else '❌'} {score.composite_score:.3f} ({elapsed:.1f}s)")
        except Exception as e:
            print(f"💥 {e}")
            scores.append(EvalScore(
                wallet=wallet,
                predicted_strategy="error",
                actual_strategy=gt.primary_strategy.value,
                strategy_correct=False,
                evidence_recall=0, false_claims=0, specificity=0, confidence_calibration=0,
            ))

    report = EvalReport(
        scores=scores,
        model=model,
        skills_version=skills_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Save report
    report_file = PERFORMANCE_DIR / f"eval_{skills_version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(report_file, "w") as f:
        json.dump(report.model_dump(), f, indent=2)

    return report


def get_performance_trend(last_n: int = 10) -> list[dict]:
    """Read recent evaluation scores to detect trends."""
    if not SCORES_FILE.exists():
        return []
    
    lines = SCORES_FILE.read_text().strip().split("\n")
    entries = [json.loads(line) for line in lines[-last_n * 15:]]  # Buffer for multi-wallet evals
    return entries


def detect_regression(current_report: EvalReport, threshold: float = 0.05) -> dict | None:
    """Check if current eval is a regression from previous best.
    
    Returns regression info dict if detected, None if OK.
    """
    # Load previous eval reports
    reports = sorted(PERFORMANCE_DIR.glob("eval_*.json"))
    if len(reports) < 2:
        return None

    # Compare against previous best
    best_score = 0.0
    for rp in reports[:-1]:  # Exclude current
        try:
            with open(rp) as f:
                prev = json.load(f)
            prev_mean = sum(s.get("composite_score", 0) for s in prev.get("scores", [])) / max(len(prev.get("scores", [])), 1)
            best_score = max(best_score, prev_mean)
        except Exception:
            continue

    current_mean = current_report.mean_score
    if current_mean < best_score - threshold:
        return {
            "type": "regression",
            "previous_best": round(best_score, 4),
            "current": round(current_mean, 4),
            "delta": round(current_mean - best_score, 4),
            "skills_version": current_report.skills_version,
        }
    return None
