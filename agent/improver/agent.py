"""Self-improver agent — reads executor logs and eval scores, writes better skills.

The self-improver:
1. Reads executor logs to find failure patterns
2. Reads evaluator scores to identify weak areas
3. Generates or updates skill code and prompts
4. Validates changes don't break anything
"""

from __future__ import annotations
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from agent.llm import call_llm, call_llm_json
from config import IMPROVER_MODEL, LOGS_DIR, SKILLS_DIR, PERFORMANCE_DIR


IMPROVE_SYSTEM_PROMPT = """You are a self-improving AI engineer. Your job is to make a wallet analysis system better.

You will be given:
1. EXECUTOR LOGS — what the executor did during recent analyses (tool calls, reasoning, errors)
2. EVAL SCORES — how the executor performed (strategy accuracy, evidence recall, etc.)
3. CURRENT SKILLS — the Python analysis skills the executor uses

Your job: identify failure patterns and produce IMPROVED code.

## What You Can Do
- Create new skill files (Python modules with an analyze_* function)
- Modify existing skill code to fix bugs or improve analysis
- Update the executor's system prompt to improve classification
- Update rule-based override logic

## Constraints
- Skills must be Python files in the skills/ directory
- Each skill must have an `analyze_<name>(positions: list[dict]) -> <DataClass>` function
- The dataclass must have a `to_text() -> str` method
- Don't break existing skill interfaces
- Be conservative: fix specific identified problems, don't rewrite everything

## Output Format
Return JSON:
{
    "analysis": "What's going wrong and why",
    "changes": [
        {
            "type": "create_skill" | "update_skill" | "update_prompt",
            "file": "relative/path/to/file.py",
            "content": "full file content",
            "reason": "why this change"
        }
    ],
    "expected_impact": "What should improve and by how much"
}"""


def _read_recent_logs(n_wallets: int = 10) -> str:
    """Read the most recent executor logs."""
    log_base = LOGS_DIR / "executor"
    if not log_base.exists():
        return "No executor logs found."

    # Get most recent date directories
    date_dirs = sorted(log_base.iterdir(), reverse=True)
    
    all_logs = []
    for date_dir in date_dirs[:3]:  # Last 3 days
        for log_file in sorted(date_dir.glob("*.jsonl"), reverse=True):
            lines = log_file.read_text().strip().split("\n")
            entries = [json.loads(line) for line in lines if line]
            all_logs.append({
                "file": log_file.name,
                "entries": entries,
            })
            if len(all_logs) >= n_wallets:
                break
        if len(all_logs) >= n_wallets:
            break

    if not all_logs:
        return "No executor logs found."

    # Summarize logs
    summary = []
    for log in all_logs:
        wallet_entries = log["entries"]
        errors = [e for e in wallet_entries if e.get("action") == "error"]
        thesis = [e for e in wallet_entries if e.get("action") == "thesis_produced"]
        skill_searches = [e for e in wallet_entries if e.get("action") == "skill_search"]
        
        s = f"--- {log['file']} ---\n"
        s += f"  Total steps: {len(wallet_entries)}\n"
        if errors:
            s += f"  ERRORS ({len(errors)}):\n"
            for e in errors:
                s += f"    - {e['data']}\n"
        
        # Skills searched but not found
        missing_skills = [e for e in skill_searches if e["data"].get("found") is None]
        if missing_skills:
            s += f"  Missing skills searched:\n"
            for e in missing_skills:
                s += f"    - Searched for: {e['data']['query']}\n"
        
        if thesis:
            t = thesis[0]["data"]
            s += f"  Thesis: {t.get('primary_strategy', '?')} (conf: {t.get('confidence', '?')})\n"
        
        summary.append(s)

    return "\n".join(summary)


def _read_recent_scores() -> str:
    """Read recent evaluation scores."""
    scores_file = PERFORMANCE_DIR / "scores.jsonl"
    if not scores_file.exists():
        return "No evaluation scores found."

    lines = scores_file.read_text().strip().split("\n")
    recent = [json.loads(line) for line in lines[-50:]]

    if not recent:
        return "No evaluation scores found."

    # Aggregate by strategy
    by_strategy: dict[str, list] = {}
    for s in recent:
        actual = s.get("actual_strategy", "unknown")
        by_strategy.setdefault(actual, []).append(s)

    summary = "Recent evaluation scores:\n"
    total_correct = sum(1 for s in recent if s.get("strategy_correct"))
    summary += f"  Overall accuracy: {total_correct}/{len(recent)} ({total_correct/len(recent):.0%})\n"
    summary += f"  Avg composite: {sum(s.get('composite_score', 0) for s in recent)/len(recent):.3f}\n\n"

    for strategy, scores in sorted(by_strategy.items()):
        correct = sum(1 for s in scores if s.get("strategy_correct"))
        avg_score = sum(s.get("composite_score", 0) for s in scores) / len(scores)
        summary += f"  {strategy}: {correct}/{len(scores)} correct, avg score {avg_score:.3f}\n"
        # Show misclassifications
        wrong = [s for s in scores if not s.get("strategy_correct")]
        for w in wrong[:2]:
            summary += f"    - Predicted: {w.get('predicted_strategy', '?')}, Actual: {w.get('actual_strategy', '?')}\n"

    return summary


def _read_current_skills() -> str:
    """Read current skill files for context."""
    skill_summaries = []
    for py_file in sorted(SKILLS_DIR.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text()
        # Just first 30 lines for context
        lines = content.split("\n")[:30]
        skill_summaries.append(f"--- {py_file.name} ({len(content)} bytes) ---\n" + "\n".join(lines) + "\n...")

    return "\n\n".join(skill_summaries) if skill_summaries else "No skills found."


async def run_improvement_cycle() -> dict:
    """Run one self-improvement cycle.
    
    Returns dict with analysis, changes made, and expected impact.
    """
    # Gather context
    logs = _read_recent_logs()
    scores = _read_recent_scores()
    current_skills = _read_current_skills()

    context = f"""## EXECUTOR LOGS (recent analyses)
{logs}

## EVALUATION SCORES
{scores}

## CURRENT SKILLS
{current_skills}
"""

    # Ask the improver to analyze and propose changes
    messages = [
        {"role": "system", "content": IMPROVE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Analyze the executor's recent performance and propose improvements:\n\n{context}"},
    ]

    result = await call_llm_json(messages, IMPROVER_MODEL)

    # Apply changes
    changes_applied = []
    for change in result.get("changes", []):
        change_type = change.get("type", "")
        file_path = change.get("file", "")
        content = change.get("content", "")
        reason = change.get("reason", "")

        if not file_path or not content:
            continue

        # Security: only allow changes to skills/ and agent/executor/prompts.py
        target = Path(file_path)
        allowed_prefixes = ["skills/", "agent/executor/prompts"]
        if not any(str(target).startswith(p) for p in allowed_prefixes):
            print(f"  ⚠️ Skipping unauthorized change to {file_path}")
            continue

        full_path = Path(__file__).parent.parent.parent / target
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Backup existing file
        if full_path.exists():
            backup = full_path.with_suffix(full_path.suffix + ".bak")
            backup.write_text(full_path.read_text())

        full_path.write_text(content)
        changes_applied.append({
            "type": change_type,
            "file": file_path,
            "reason": reason,
        })
        print(f"  ✏️ {change_type}: {file_path} — {reason}")

    # Update skills/__init__.py if new skills were added
    if any(c["type"] == "create_skill" for c in changes_applied):
        _regenerate_skills_init()

    # Log the improvement cycle
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "analysis": result.get("analysis", ""),
        "changes": changes_applied,
        "expected_impact": result.get("expected_impact", ""),
    }
    log_file = PERFORMANCE_DIR / "improvement_log.jsonl"
    with open(log_file, "a") as f:
        f.write(json.dumps(log_entry) + "\n")

    return log_entry


def _regenerate_skills_init():
    """Regenerate skills/__init__.py based on discovered skill files."""
    imports = []
    exports = []
    
    for py_file in sorted(SKILLS_DIR.glob("*_analyzer.py")):
        module_name = py_file.stem
        func_name = f"analyze_{module_name.replace('_analyzer', '')}"
        imports.append(f"from .{module_name} import {func_name}")
        exports.append(f'    "{func_name}",')

    content = '"""Analysis skills for Polymarket wallet analysis."""\n\n'
    content += "\n".join(imports)
    content += "\n\n__all__ = [\n"
    content += "\n".join(exports)
    content += "\n]\n"

    init_file = SKILLS_DIR / "__init__.py"
    init_file.write_text(content)
    print(f"  🔄 Regenerated skills/__init__.py with {len(imports)} skills")


async def rollback_changes():
    """Rollback the most recent changes (restore .bak files)."""
    count = 0
    for bak in SKILLS_DIR.glob("*.bak"):
        original = bak.with_suffix("")
        original.write_text(bak.read_text())
        bak.unlink()
        count += 1
        print(f"  ↩️ Rolled back {original.name}")
    
    for bak in (Path(__file__).parent.parent / "executor").glob("*.bak"):
        original = bak.with_suffix("")
        original.write_text(bak.read_text())
        bak.unlink()
        count += 1
        print(f"  ↩️ Rolled back {original.name}")

    if count:
        _regenerate_skills_init()
    return count
