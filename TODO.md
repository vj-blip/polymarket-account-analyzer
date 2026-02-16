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
- [x] **Timing Analyzer** — time-of-day patterns, burst trading, consistency, off-hours detection
- [x] **Sizing Analyzer** — position sizing consistency, CV, scaling behavior, entry price distribution
- [x] **Market Analyzer** — category focus, market diversity, HHI concentration, outcome bias
- [x] **Flow Analyzer** — win rate, profit factor, accumulation, risk/reward, monthly trends
- [x] **Pattern Analyzer** — win/loss streaks, drawdown analysis, R² curve, post-loss behavior
- [x] **Skilled Analyzer** — combines all 5 skills → structured LLM prompt → WalletThesis
- [ ] **Correlation Analyzer** — cross-market hedging, paired positions, portfolio construction
- [ ] **Speed Analyzer** — time from market creation to first trade (info edge signal)

### Skilled v1 Results (2026-02-16)
- **Model:** gpt-4o-mini (analyzer) + gpt-4o (judge)
- **Composite score:** 0.479 (+94% vs baseline 0.246)
- **Strategy accuracy:** 26.7% (4/15 correct — up from 1/15)
- **Evidence recall:** 40.0% (up from 6.7%)
- **Total time:** 286s (~19s/wallet)
- **Correct strategies:** RN1=model_based, GamblingIsAllYouNeed=model_based, S-Works=model_based, MCgenius=whale
- **Key issues:** Still misclassifies whales as model_based, market_makers as model_based/scalper, info_edge as whale. Model defaults to model_based too often. Needs better whale/MM heuristics in prompt.

## Phase 3: Improve Skilled Analyzer
- [ ] Fix whale detection (avg position >$100K + low position count should strongly signal whale)
- [ ] Fix market_maker detection (near-50% win rate + massive volume + thin edge)
- [ ] Fix info_edge detection (high win rate on politics/events + sporadic timing)
- [ ] Reduce model_based over-classification bias
- [ ] Try gpt-4o as analyzer (vs gpt-4o-mini) to see accuracy impact
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
- **Skilled v1 score:** 0.479 (gpt-4o-mini + 5 skills, 26.7% strategy accuracy)
- **Best agent score:** 0.479 (skilled v1)
