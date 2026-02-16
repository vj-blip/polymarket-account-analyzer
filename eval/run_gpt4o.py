"""Run skilled eval with gpt-4o as analyzer instead of gpt-4o-mini."""
import asyncio
import sys
sys.path.insert(0, '.')

from eval.skilled_analyzer import skilled_analyze, skilled_judge, SKILLED_PROMPT, call_llm, rule_based_hints
from eval.skilled_analyzer import _apply_hard_overrides
from eval.run_eval import evaluate_analyzer
from eval import skilled_analyzer

# Monkey-patch the model
skilled_analyzer.ANALYZER_MODEL = "gpt-4o"

async def main():
    print("🧪 Running SKILLED evaluation with GPT-4O as analyzer")
    print(f"   Analyzer: gpt-4o")
    print(f"   Judge: gpt-4o")
    print()

    report = await evaluate_analyzer(
        analyze_fn=skilled_analyze,
        judge_fn=skilled_judge,
        model="gpt-4o",
        skills_version="v5_gpt4o",
    )

    print(f"\n{'='*60}")
    print(report.summary())

if __name__ == "__main__":
    asyncio.run(main())
