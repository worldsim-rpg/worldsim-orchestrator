"""
GameSettings хранятся per-world. При `new` — спрашиваем игрока,
записываем вместе с остальным каноном.

Env vars:
  WORLDSIM_LANG            — язык интерфейса (дефолт: ru)
  WORLDSIM_MODEL           — модель по умолчанию (дефолт: claude-sonnet-4-6)
  WORLDSIM_MODEL_HEAVY     — «тяжёлая» модель  (дефолт: claude-sonnet-4-6)
  WORLDSIM_SAVES_DIR       — корень сейвов      (дефолт: saves/)
  WORLDSIM_LOG_DIR         — корень логов       (дефолт: logs/ рядом с saves/)
"""

from __future__ import annotations

import os

from worldsim_schemas import GameSettings


def default_settings() -> GameSettings:
    """Берёт дефолты из окружения, если они там есть."""

    return GameSettings(
        language=os.environ.get("WORLDSIM_LANG", "ru"),  # type: ignore[arg-type]
        model_default=os.environ.get("WORLDSIM_MODEL", "claude-sonnet-4-6"),
        model_heavy=os.environ.get("WORLDSIM_MODEL_HEAVY", "claude-sonnet-4-6"),
    )
