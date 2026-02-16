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
- **Key issues:** Misclassifies model_based as whale, info_edge as whale. Model defaults to model_based too often.

### Skilled v2 Results (2026-02-16) — Anti-whale overrides
- **Model:** gpt-4o-mini (analyzer) + gpt-4o (judge)
- **Composite score:** 0.516 (+8% vs v1, +110% vs baseline)
- **Strategy accuracy:** 42.9% (6/14, 1 judge error)
- **Evidence recall:** 45.7%
- **Total time:** 213s (~15s/wallet)
- **Fixed:** lhtsports whale→scalper ✅
- **Improved:** RN1 whale→scalper (closer to model_based), GamblingIsAllYouNeed whale→market_maker (partial)
- **Still failing:** RN1/S-Works model_based detection, aenews2 info_edge detection, judge schema errors on bobe2

## Phase 3: Improve Skilled Analyzer
- [x] Fix whale over-classification (anti-whale overrides for small avg + high count)
- [x] Fix model_based under-detection (RN1, S-Works now correctly classified)
- [x] Fix market_maker detection (near-50% win rate + massive volume + thin edge)
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
- **Best agent score:** 0.631 (skilled v4, market_maker detection fix)

### Skilled v3 Results (2026-02-16) — model_based under-detection fix
- **Model:** gpt-4o-mini (analyzer) + gpt-4o (judge)
- **Composite score:** 0.575 (+11% vs v2, +134% vs baseline)
- **Strategy accuracy:** 66.7% (10/15 correct)
- **Evidence recall:** 42.7%
- **Total time:** 201s (~13s/wallet)
- **Fixed:** S-Works whale→model_based ✅, RN1 already correct ✅
- **Still failing:** SwissMiss (model_based→whale), GamblingIsAllYouNeed (model_based→scalper), aenews2 (info_edge→whale), 0xf705 (contrarian→model_based), 0x8dxd (scalper→market_maker)

### Skilled v4 Results (2026-02-16) — market_maker detection fix
- **Model:** gpt-4o-mini (analyzer) + gpt-4o (judge)
- **Composite score:** 0.631 (+10% vs v3, +156% vs baseline)
- **Strategy accuracy:** 80.0% (12/15 correct)
- **Evidence recall:** 49.3%
- **Total time:** 193s (~13s/wallet)
- **Root cause:** data_fetcher timeout was 30s, too short for large wallets (69K+ positions). Increased to 120s.
- **Fixed:** swisstony (now market_maker ✅), sovereign2013 (now market_maker ✅), GamblingIsAllYouNeed (now model_based ✅), 0x8dxd (now scalper ✅)
- **Still failing:** SwissMiss (model_based→whale), aenews2 (info_edge→model_based), 0xf705 (contrarian→scalper)
