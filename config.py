"""Central configuration for the account analyzer system."""

from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# === Paths ===
ROOT = Path(__file__).parent
SKILLS_DIR = ROOT / "skills"
LOGS_DIR = ROOT / "logs"
DATA_DIR = ROOT / "data"
EVAL_DIR = ROOT / "eval"
CURRICULUM_DIR = DATA_DIR / "curriculum"
PERFORMANCE_DIR = DATA_DIR / "performance"
THESES_DIR = DATA_DIR / "theses"

# Ensure dirs exist
for d in [LOGS_DIR / "executor", CURRICULUM_DIR, PERFORMANCE_DIR, THESES_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# === API ===
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
ALGOARENA_API = "http://34.67.141.159:8000"

# === Models per agent ===
# Executor: cheap, runs often
EXECUTOR_MODEL = os.getenv("EXECUTOR_MODEL", "google/gemini-2.5-flash")
# Evaluator: medium, scores theses
EVALUATOR_MODEL = os.getenv("EVALUATOR_MODEL", "google/gemini-2.5-flash")
# Self-improver: smart, writes code and skills
IMPROVER_MODEL = os.getenv("IMPROVER_MODEL", "anthropic/claude-sonnet-4")
# Trainer: smart, designs curriculum
TRAINER_MODEL = os.getenv("TRAINER_MODEL", "anthropic/claude-sonnet-4")
# Judge: smart, evaluates thesis quality
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "anthropic/claude-sonnet-4")
