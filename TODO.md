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
- [x] Document cost/latency per wallet analysis
- [x] Identify failure modes (which wallets/strategies does baseline get wrong?)

### Baseline Results (2026-02-16, run 2)
- **Model:** gpt-4o-mini (analyzer) + gpt-4o (judge)
- **Strategy accuracy:** 33.3% (5/15 correct: SwissMiss, aenews2, anoin123, lhtsports, bobe2)
- **Avg evidence recall:** 0.40 (failures: 0.36)
- **Avg false claims:** 2.1 (failures: 2.6)

### Cost/Latency
- **Total time:** 177.6s (avg 11.8s/wallet)
- **Range:** 8.3s – 18.6s per wallet
- **Estimated cost:** ~$0.02/wallet (gpt-4o-mini analyzer + gpt-4o judge)

### Failure Mode Analysis
| Strategy | Labeled | Correct | Notes |
|----------|---------|---------|-------|
| whale | 3 | 0/3 | Worst category — model can't detect whale behavior |
| model_based | 3 | 1/3 | Often misclassified |
| market_maker | 2 | 0/2 | Never detected correctly |
| info_edge | 3 | 3/3 | ✅ Best category |
| scalper | 2 | 1/2 | Partial success |
| contrarian | 1 | 0/1 | Missed |

**Key patterns:**
- Whale detection is the biggest gap (0/3) — model lacks sizing/volume analysis
- Market maker detection fails (0/2) — needs spread/fill pattern analysis
- Info edge is well-detected (3/3) — natural language signals are strong
- High false claim rate (avg 2.6 on failures) — model hallucinates patterns

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
