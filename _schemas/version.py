"""
Версия канона (pydantic-схем).

Подчиняется SemVer:
  MAJOR — ломающее изменение (удаление/переименование поля, смена типа,
          инверсия инварианта). Загрузка сейва с другим MAJOR отказывается.
  MINOR — добавление опционального поля / enum-значения. Старые сейвы
          грузятся с дефолтом, перезаписываются с новой версией.
  PATCH — правки docstring, переименования внутри констант, исправление
          дефолта без семантических последствий.

Любое редактирование `schemas.py` должно сопровождаться bump'ом этой
константы. CI (`repo-setup/check-version-bump.sh`) падает, если
изменения в schemas.py не сопровождаются правкой version.py.

При bump MAJOR заводится миграция — см. `migrations/README.md`.
"""

from __future__ import annotations

SCHEMA_VERSION = "0.1.0"


def _split(v: str) -> tuple[int, int, int]:
    try:
        parts = v.split(".")
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError) as e:
        raise ValueError(f"Невалидная версия схем: {v!r}") from e


def major(v: str) -> int:
    return _split(v)[0]


def is_compatible(file_version: str, current: str = SCHEMA_VERSION) -> bool:
    """
    True если сейв с версией `file_version` можно безопасно загружать в
    текущей версии `current`. Совместимость — по MAJOR.
    """
    return major(file_version) == major(current)


__all__ = ["SCHEMA_VERSION", "is_compatible", "major"]
