# Polymarket Account Analyzer

AI agent system for forensic analysis of Polymarket trading accounts. Self-improving multi-agent architecture.

## Architecture

Four-agent system with separation of concerns:

```
┌─────────────┐     ┌──────────────┐     ┌──────────┐     ┌───────────┐
│   TRAINER   │────▶│ SELF-IMPROVER│────▶│ EXECUTOR │────▶│ EVALUATOR │
│ (curriculum)│     │ (skills/code)│     │ (analyze) │     │ (scoring) │
└─────────────┘     └──────────────┘     └──────────┘     └───────────┘
       ▲                                       │                │
       └───────────────────────────────────────┴────────────────┘
                         feedback loops
```

- **Executor** — Analyzes wallets. Can run code, cannot write code. Skills are read-only.
- **Self-Improver** — Reads executor logs, writes new skills/code/prompts.
- **Trainer** — Designs curriculum, sequences difficulty, adjusts training plan.
- **Evaluator** — Scores thesis quality, tracks performance over time, detects regressions.

## Development Phases

1. **Phase 0: Eval first** — Ground truth dataset + scoring framework (← we are here)
2. **Phase 1: Onboarding** — Build agents, train in isolation until >70% eval score
3. **Phase 2: Deploy** — Run against real wallets, produce theses
4. **Phase 3: Continuous learning** — Never stop improving

## Data Source

- **AlgoArena** — 2,019 tracked wallets, 1.7M+ trade records
- **API:** http://34.67.141.159:8000

## Tech Stack

- **Agent framework:** PydanticAI
- **Models:** OpenRouter (GLM 5, Kimi 2.5, Claude)
- **Database:** PostgreSQL
- **Infrastructure:** Docker

## Getting Started

```bash
pip install -r requirements.txt
python -m eval.run_eval  # Run baseline evaluation
```
