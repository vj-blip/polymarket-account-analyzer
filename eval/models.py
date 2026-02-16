"""Evaluation data models — the schema for ground truth and scoring."""

from __future__ import annotations
from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional


class StrategyType(str, Enum):
    """Known trading strategy archetypes."""
    INFO_EDGE = "info_edge"           # Trades on non-public or early information
    MODEL_BASED = "model_based"       # Quantitative/statistical models
    MARKET_MAKER = "market_maker"     # Provides liquidity, profits from spread
    CONTRARIAN = "contrarian"         # Bets against consensus
    MOMENTUM = "momentum"            # Follows trends/momentum
    HEDGER = "hedger"                # Hedges positions across markets
    ARBITRAGE = "arbitrage"          # Cross-market or cross-platform arb
    WHALE = "whale"                  # Large positions that move markets
    SCALPER = "scalper"              # High-frequency small-profit trades
    UNKNOWN = "unknown"              # Can't determine strategy


class Difficulty(str, Enum):
    EASY = "easy"       # Obvious pattern, high volume, clear strategy
    MEDIUM = "medium"   # Mixed signals, requires deeper analysis
    HARD = "hard"       # Deliberate obfuscation, multi-wallet, deceptive


class EvidencePoint(BaseModel):
    """A specific piece of evidence a good analysis SHOULD find."""
    description: str
    importance: float = Field(ge=0, le=1, description="How critical this evidence is (0-1)")
    category: str = Field(description="e.g. 'timing', 'sizing', 'correlation', 'market_selection'")


class GroundTruth(BaseModel):
    """Ground truth label for a wallet — what we know about it."""
    wallet: str
    username: Optional[str] = None
    primary_strategy: StrategyType
    secondary_strategies: list[StrategyType] = []
    difficulty: Difficulty
    evidence_points: list[EvidencePoint] = []
    notes: str = ""
    
    # Stats for context (from AlgoArena)
    pnl_total: Optional[float] = None
    volume_total: Optional[float] = None
    win_rate_30d: Optional[float] = None
    total_trades: Optional[int] = None


class WalletThesis(BaseModel):
    """What the agent produces — its analysis of a wallet."""
    wallet: str
    primary_strategy: StrategyType
    secondary_strategies: list[StrategyType] = []
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(description="Evidence supporting the thesis")
    reasoning: str = Field(description="Free-form reasoning/narrative")
    signals_to_monitor: list[str] = []
    risk_assessment: str = ""


class EvalScore(BaseModel):
    """Score for a single wallet analysis."""
    wallet: str
    strategy_correct: bool
    strategy_partial: bool = False  # Got secondary but not primary
    evidence_recall: float = Field(ge=0, le=1, description="% of ground truth evidence found")
    false_claims: int = Field(ge=0, description="Hallucinated evidence count")
    specificity: float = Field(ge=0, le=1, description="How concrete vs vague")
    confidence_calibration: float = Field(ge=0, le=1, description="Was confidence appropriate?")
    time_seconds: float = 0
    tokens_used: int = 0
    
    @property
    def composite_score(self) -> float:
        """Weighted composite score (0-1)."""
        weights = {
            'strategy': 0.30,
            'evidence': 0.25,
            'specificity': 0.20,
            'false_claims': 0.15,
            'calibration': 0.10,
        }
        
        strategy_score = 1.0 if self.strategy_correct else (0.5 if self.strategy_partial else 0.0)
        false_claim_score = max(0, 1.0 - (self.false_claims * 0.2))  # -0.2 per false claim
        
        return (
            weights['strategy'] * strategy_score +
            weights['evidence'] * self.evidence_recall +
            weights['specificity'] * self.specificity +
            weights['false_claims'] * false_claim_score +
            weights['calibration'] * self.confidence_calibration
        )


class EvalReport(BaseModel):
    """Aggregate eval results across all ground truth wallets."""
    scores: list[EvalScore]
    model: str
    skills_version: str = "none"
    timestamp: str
    
    @property
    def mean_score(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.composite_score for s in self.scores) / len(self.scores)
    
    @property
    def strategy_accuracy(self) -> float:
        if not self.scores:
            return 0.0
        return sum(1 for s in self.scores if s.strategy_correct) / len(self.scores)
    
    @property
    def mean_evidence_recall(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.evidence_recall for s in self.scores) / len(self.scores)
    
    def summary(self) -> str:
        return (
            f"Eval Report ({self.model}, skills={self.skills_version})\n"
            f"  Wallets evaluated: {len(self.scores)}\n"
            f"  Mean composite score: {self.mean_score:.3f}\n"
            f"  Strategy accuracy: {self.strategy_accuracy:.1%}\n"
            f"  Mean evidence recall: {self.mean_evidence_recall:.1%}\n"
            f"  Total tokens: {sum(s.tokens_used for s in self.scores):,}\n"
            f"  Total time: {sum(s.time_seconds for s in self.scores):.0f}s\n"
        )
