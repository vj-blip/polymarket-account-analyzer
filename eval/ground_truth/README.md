# Ground Truth Labels

Each JSON file contains labeled wallet analyses that serve as the eval benchmark.

## How to Label

For each wallet, we need:
1. **primary_strategy** — The main strategy type (see StrategyType enum)
2. **difficulty** — easy/medium/hard
3. **evidence_points** — Specific things a good analysis SHOULD discover
4. **notes** — Why we think this is their strategy

## Strategy Types
- `info_edge` — Trades on non-public or early information
- `model_based` — Uses quantitative/statistical models
- `market_maker` — Provides liquidity, profits from spread
- `contrarian` — Bets against consensus
- `momentum` — Follows trends
- `hedger` — Hedges across markets
- `arbitrage` — Cross-market arbitrage
- `whale` — Large positions that move markets
- `scalper` — High-frequency small-profit trades
- `unknown` — Can't determine

## Process
1. Pull wallet's full trade history from AlgoArena
2. Manually inspect patterns (timing, sizing, market selection)
3. Form thesis and label
4. Have second person verify (optional but ideal)
