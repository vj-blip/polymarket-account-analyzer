"""Automated scoring of agent theses against ground truth.

Uses an LLM judge to evaluate specificity, evidence matching, and false claims.
This avoids brittle string-matching and handles natural language variation.
"""

from __future__ import annotations
import json
from pydantic import BaseModel, Field
from .models import GroundTruth, WalletThesis, EvalScore, StrategyType


class JudgeAssessment(BaseModel):
    """What the LLM judge produces when comparing thesis to ground truth."""
    strategy_correct: bool = Field(description="Did the thesis identify the correct primary strategy?")
    strategy_partial: bool = Field(description="Did it identify a secondary strategy but miss the primary?")
    evidence_matches: list[str] = Field(description="Which ground truth evidence points were found")
    evidence_missed: list[str] = Field(description="Which ground truth evidence points were missed")
    false_claims: list[str] = Field(description="Claims in the thesis not supported by data")
    specificity_score: float = Field(ge=0, le=1, description="How concrete and specific (vs vague)")
    confidence_appropriate: float = Field(ge=0, le=1, description="Is the confidence level well-calibrated?")
    reasoning: str = Field(description="Judge's reasoning for the assessment")


JUDGE_PROMPT = """You are an expert evaluator of trading account analyses.

You will be given:
1. A GROUND TRUTH — what we know about this wallet's actual trading strategy
2. A THESIS — what an AI analyst produced about this wallet

Your job: Score how good the thesis is.

## Scoring Criteria

**Strategy Correct:** Did the thesis identify the correct primary strategy type?
The ground truth says: {gt_strategy}. The thesis says: {thesis_strategy}.
Exact match = correct. Close match (e.g., "info_edge" vs description of information advantage) = correct.
Completely wrong = not correct. Got a secondary strategy but missed primary = partial.

**Evidence Matching:** The ground truth lists specific evidence points that a good analysis should find.
For each ground truth evidence point, determine if the thesis found it (even if worded differently).

**False Claims:** List any claims in the thesis that are NOT supported by the wallet's actual data.
Speculative claims clearly marked as speculation are OK. Stated-as-fact claims without evidence = false.

**Specificity:** 
- 0.0 = "This wallet might be doing info trading" (vague)
- 0.5 = "This wallet enters positions before major news events" (somewhat specific)
- 1.0 = "This wallet bought $50K YES on market X exactly 4 hours before resolution, consistent with advance info" (very specific)

**Confidence Calibration:**
- 1.0 = Confidence matches quality of evidence (high confidence + strong evidence, or low confidence + weak evidence)
- 0.0 = Wildly miscalibrated (high confidence with no evidence, or very low confidence with overwhelming evidence)

## Ground Truth
Wallet: {wallet}
Primary Strategy: {gt_strategy}
Secondary Strategies: {gt_secondary}
Key Evidence Points:
{evidence_points}
Notes: {gt_notes}

## Thesis to Evaluate
Primary Strategy: {thesis_strategy}
Confidence: {thesis_confidence}
Evidence Cited:
{thesis_evidence}
Reasoning:
{thesis_reasoning}

Produce your assessment as JSON matching the JudgeAssessment schema."""


def build_judge_prompt(gt: GroundTruth, thesis: WalletThesis) -> str:
    """Build the prompt for the LLM judge."""
    evidence_str = "\n".join(
        f"  - [{ep.category}] {ep.description} (importance: {ep.importance})"
        for ep in gt.evidence_points
    ) or "  (none specified)"
    
    thesis_evidence_str = "\n".join(f"  - {e}" for e in thesis.evidence) or "  (none)"
    
    return JUDGE_PROMPT.format(
        wallet=gt.wallet,
        gt_strategy=gt.primary_strategy.value,
        gt_secondary=", ".join(s.value for s in gt.secondary_strategies) or "none",
        evidence_points=evidence_str,
        gt_notes=gt.notes or "none",
        thesis_strategy=thesis.primary_strategy.value,
        thesis_confidence=thesis.confidence,
        thesis_evidence=thesis_evidence_str,
        thesis_reasoning=thesis.reasoning,
    )


def assessment_to_score(
    wallet: str,
    gt: GroundTruth,
    assessment: JudgeAssessment,
    time_seconds: float = 0,
    tokens_used: int = 0,
    predicted_strategy: str = "",
) -> EvalScore:
    """Convert a judge assessment into a numeric EvalScore."""
    total_evidence = len(gt.evidence_points) or 1
    found_evidence = len(assessment.evidence_matches)
    
    return EvalScore(
        wallet=wallet,
        predicted_strategy=predicted_strategy,
        actual_strategy=gt.primary_strategy.value,
        strategy_correct=assessment.strategy_correct,
        strategy_partial=assessment.strategy_partial,
        evidence_recall=min(1.0, found_evidence / total_evidence),
        false_claims=len(assessment.false_claims),
        specificity=assessment.specificity_score,
        confidence_calibration=assessment.confidence_appropriate,
        time_seconds=time_seconds,
        tokens_used=tokens_used,
    )
