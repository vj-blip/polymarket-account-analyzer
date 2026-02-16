"""Executor action logger — records every tool call, reasoning step, and result.

Logs to logs/executor/YYYY-MM-DD/wallet_ADDRESS.jsonl
Each line is a JSON object with timestamp, action type, and data.
"""

from __future__ import annotations
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from config import LOGS_DIR


class ExecutorLogger:
    """Logs all executor actions for a single wallet analysis."""

    def __init__(self, wallet: str):
        self.wallet = wallet
        self.start_time = time.time()
        self.entries: list[dict] = []

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.log_dir = LOGS_DIR / "executor" / date_str
        self.log_dir.mkdir(parents=True, exist_ok=True)
        short_addr = wallet[:10]
        self.log_file = self.log_dir / f"wallet_{short_addr}.jsonl"

    def log(self, action: str, data: dict | str | None = None):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_s": round(time.time() - self.start_time, 2),
            "action": action,
            "data": data,
        }
        self.entries.append(entry)
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def log_tool_call(self, tool: str, args: dict | None = None):
        self.log("tool_call", {"tool": tool, "args": args})

    def log_tool_result(self, tool: str, result_summary: str):
        self.log("tool_result", {"tool": tool, "summary": result_summary})

    def log_reasoning(self, text: str):
        self.log("reasoning", text)

    def log_skill_search(self, query: str, found: str | None):
        self.log("skill_search", {"query": query, "found": found})

    def log_skill_run(self, skill: str, result_summary: str):
        self.log("skill_run", {"skill": skill, "summary": result_summary})

    def log_error(self, error: str):
        self.log("error", error)

    def log_thesis(self, thesis: dict):
        self.log("thesis_produced", thesis)

    def get_summary(self) -> dict:
        """Summary stats for this analysis run."""
        tool_calls = [e for e in self.entries if e["action"] == "tool_call"]
        skill_runs = [e for e in self.entries if e["action"] == "skill_run"]
        errors = [e for e in self.entries if e["action"] == "error"]
        return {
            "wallet": self.wallet,
            "total_entries": len(self.entries),
            "tool_calls": len(tool_calls),
            "skill_runs": len(skill_runs),
            "errors": len(errors),
            "elapsed_s": round(time.time() - self.start_time, 2),
            "log_file": str(self.log_file),
        }
