# AGENT.md - Polymarket Account Analyzer

## Project Overview
AI-powered trading strategy analyzer for Polymarket wallets. Uses an eval-driven approach: label wallets → baseline → build skills → improve scores.

## Development Loop
This project has an autonomous development cron. Each cycle:
1. Read `TODO.md` for current task
2. Work on the next unchecked item
3. Run tests/eval if applicable
4. Update TODO.md with progress
5. Commit changes
6. Post progress to #polymarket-tracker

## Key Files
- `eval/models.py` — Data schemas
- `eval/scorer.py` — LLM judge
- `eval/baseline.py` — Baseline analyzer (the floor)
- `eval/run_eval.py` — Eval runner
- `eval/ground_truth/labeled.json` — 15 labeled wallets
- `TODO.md` — Project roadmap

## Data
- AlgoArena API: http://34.67.141.159:8000
- 1,810+ wallets, 1.7M+ trade records
- Top wallets: $578K to $9.3M PnL

## Rules
- Always run eval after changes to measure impact
- Never skip the baseline — it's the floor to beat
- Commit after each meaningful change
- Post progress to #polymarket-tracker (C0AC3KGKTAS)
- Keep costs reasonable — use Sonnet for iteration, Opus for final eval
