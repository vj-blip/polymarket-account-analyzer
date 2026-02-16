# Polymarket Account Analyzer - TODO

## Phase 0: Eval Framework ✅
- [x] Typed schemas (GroundTruth, WalletThesis, EvalScore, EvalReport)
- [x] LLM judge scorer
- [x] Baseline analyzer (raw LLM dump)
- [x] Eval runner
- [x] Label helper CLI
- [x] 30 candidate wallets loaded
- [x] 15 wallets labeled with ground truth

## Phase 1: Baseline Score
- [x] Run baseline eval against all 15 labeled wallets
- [x] Record baseline composite score, strategy accuracy, evidence recall
- [ ] Document cost/latency per wallet analysis
- [ ] Identify failure modes (which wallets/strategies does baseline get wrong?)

### Baseline Results (2026-02-16)
- **Model:** gpt-4o-mini (analyzer) + gpt-4o (judge)
- **Composite score:** 0.246
- **Strategy accuracy:** 6.7% (1/15 correct — GamblingIsAllYouNeed=model_based)
- **Evidence recall:** 6.7%
- **Total time:** 74s (~5s/wallet)
- **Key issues:** Model returns "unknown" too often, misclassifies whales as market_makers/arbitrage, one parse failure (SwissMiss: returned "information_edge" not in enum)

## Phase 2: Analysis Skills/Tools
- [ ] **Timing Analyzer** — detect time-of-day patterns, event-driven entries, speed-to-market
- [ ] **Sizing Analyzer** — position sizing consistency, Kelly-like patterns, scaling behavior
- [ ] **Market Selection Analyzer** — category focus, market diversity, correlation patterns
- [ ] **Correlation Analyzer** — cross-market hedging, paired positions, portfolio construction
- [ ] **Flow Analyzer** — buy/sell ratio evolution, accumulation/distribution patterns
- [ ] **Speed Analyzer** — time from market creation to first trade (info edge signal)
- [ ] **Win Pattern Analyzer** — streak analysis, loss recovery, drawdown behavior

## Phase 3: Agent with Tools
- [ ] Build agent that uses skills from Phase 2
- [ ] Run eval, compare to baseline
- [ ] Iterate on tool selection and prompting
- [ ] Optimize cost vs accuracy tradeoff
- [ ] Add chain-of-thought / multi-step reasoning

## Phase 4: Advanced
- [ ] Cross-wallet analysis (detect multi-wallet operators)
- [ ] Temporal analysis (strategy shifts over time)
- [ ] Confidence calibration tuning
- [ ] Add more labeled wallets (target 30+)
- [ ] Benchmark multiple models (Opus vs Sonnet vs GPT-4 vs Grok)

## Current Status
- **Last updated:** 2026-02-16
- **Baseline score:** 0.246 (gpt-4o-mini, 6.7% strategy accuracy)
- **Best agent score:** N/A
