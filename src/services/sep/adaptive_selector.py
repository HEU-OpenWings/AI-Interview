from __future__ import annotations

import json
from pathlib import Path

# Resolve relative to this file: src/services/sep/ → up 3 levels → project root → src/data/question_banks/
QUESTION_BANKS_DIR = Path(__file__).parent.parent.parent / "data" / "question_banks"


def load_question_bank(position: str) -> list[dict]:
    path = QUESTION_BANKS_DIR / f"{position}.json"
    if not path.exists():
        path = QUESTION_BANKS_DIR / "backend.json"
    return json.loads(path.read_text(encoding="utf-8"))


def select_next_question(
    theta: float,
    asked_ids: set[str],
    question_bank: list[dict],
    asked_domains: set[str],
) -> dict | None:
    candidates = [q for q in question_bank if q["id"] not in asked_ids]
    if not candidates:
        return None

    # Sort by closeness of difficulty to current ability estimate
    by_info = sorted(candidates, key=lambda q: abs(q["difficulty"] - theta))

    # Prefer questions from domains not yet covered
    uncovered = [q for q in by_info if q["domain"] not in asked_domains]
    return uncovered[0] if uncovered else by_info[0]
