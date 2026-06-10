"""
Логирование для worldsim.

dev-лог  — JSONL, по одному объекту на LLM-вызов.
player-лог — plain text, по одному блоку на ход.

Директория: WORLDSIM_LOG_DIR (дефолт: logs/ рядом с saves/).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _log_root() -> Path:
    """Корень лог-директории — либо из env, либо logs/ рядом с saves/."""
    from .persistence import saves_root  # локальный импорт, нет цикла

    custom = os.environ.get("WORLDSIM_LOG_DIR")
    if custom:
        return Path(custom).resolve()
    return saves_root().parent / "logs"


# --- dev log (JSONL) ---------------------------------------------------------


def append_dev_log(world_id: str, entry: dict) -> None:
    """Дописывает одну строку в <log_root>/dev/<world_id>_dev.jsonl."""
    path = _log_root() / "dev" / f"{world_id}_dev.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# --- player log (plain text) -------------------------------------------------


def append_player_log(world_id: str, turn: int, player_input: str, scene_text: str) -> None:
    """Дописывает блок хода в <log_root>/player/<world_id>_player.txt."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    header = f"═══ Ход {turn} — {ts} ═══"
    block = f"{header}\n> {player_input}\n\n{scene_text}\n\n"

    path = _log_root() / "player" / f"{world_id}_player.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(block)
