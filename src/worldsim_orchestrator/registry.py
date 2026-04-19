"""
Реестр агентов: единственная точка, где orchestrator знает, какой пакет
какой фазе соответствует.

Каноничный файл — `worldsim-workspace/agents.toml`. Orchestrator ищет его
либо через env `WORLDSIM_AGENTS_TOML`, либо relative от текущего репо
(`../worldsim-workspace/agents.toml`).

API:
    reg = load_registry()
    manifest = reg.for_phase(AgentPhase.WORLD_UPDATE)
    result = reg.call(AgentPhase.WORLD_UPDATE, payload, client=..., settings=...)

Для опциональных фаз (manifest.optional=True) `.call()` возвращает None,
если пакет не установлен. Для обязательных — поднимает AgentUnavailable.
"""

from __future__ import annotations

import os
import tomllib
from importlib import import_module
from pathlib import Path
from typing import Any

from worldsim_schemas import AgentManifest, AgentPhase, AgentRegistryFile


class AgentUnavailable(RuntimeError):
    """Поднимается если обязательный агент-пакет не установлен."""


class RegistryError(RuntimeError):
    """Проблема в самом agents.toml (дубликат фазы, битый манифест)."""


def _default_registry_path() -> Path:
    """
    Поиск agents.toml. Порядок:
    1. env WORLDSIM_AGENTS_TOML.
    2. ../worldsim-workspace/agents.toml относительно этого файла.
    3. cwd/worldsim-workspace/agents.toml.
    """
    env = os.environ.get("WORLDSIM_AGENTS_TOML")
    if env:
        return Path(env)

    here = Path(__file__).resolve()
    # orchestrator/src/worldsim_orchestrator/registry.py → up 4 → repos/
    repos_dir = here.parents[3]
    candidate = repos_dir / "worldsim-workspace" / "agents.toml"
    if candidate.exists():
        return candidate

    cwd_candidate = Path.cwd() / "worldsim-workspace" / "agents.toml"
    if cwd_candidate.exists():
        return cwd_candidate

    raise RegistryError(
        "Не найден agents.toml. Укажи путь через WORLDSIM_AGENTS_TOML "
        "или запускай orchestrator из sandbox/."
    )


class Registry:
    def __init__(self, manifests: list[AgentManifest]) -> None:
        self._manifests = manifests
        self._by_phase: dict[AgentPhase, AgentManifest] = {}
        for m in manifests:
            if m.phase in self._by_phase:
                raise RegistryError(
                    f"Фаза {m.phase.value} уже занята агентом "
                    f"{self._by_phase[m.phase].name}, дубликат: {m.name}"
                )
            self._by_phase[m.phase] = m

    @property
    def manifests(self) -> list[AgentManifest]:
        return list(self._manifests)

    def for_phase(self, phase: AgentPhase) -> AgentManifest | None:
        return self._by_phase.get(phase)

    def _import_entrypoint(self, manifest: AgentManifest):
        try:
            mod = import_module(manifest.package)
        except ImportError as e:
            if manifest.optional:
                return None
            raise AgentUnavailable(
                f"Агент «{manifest.name}» (пакет {manifest.package}) не "
                f"установлен. См. worldsim-workspace/docs/setup.md"
            ) from e

        fn = getattr(mod, manifest.entrypoint, None)
        if fn is None:
            raise AgentUnavailable(
                f"Пакет {manifest.package} не экспортирует "
                f"{manifest.entrypoint}. Проверь контракт агента."
            )
        return fn

    def call(
        self,
        phase: AgentPhase,
        payload: dict,
        *,
        client,
        settings,
    ) -> Any:
        """
        Вызвать агента фазы. Модель выбирается по manifest.model_tier.
        Если фаза optional и пакет не установлен — вернёт None.
        Если фаза не объявлена в реестре — RegistryError.
        """
        manifest = self._by_phase.get(phase)
        if manifest is None:
            raise RegistryError(f"Фаза {phase.value} не объявлена в agents.toml")

        fn = self._import_entrypoint(manifest)
        if fn is None:
            return None

        model = (
            settings.model_heavy
            if manifest.model_tier == "heavy"
            else settings.model_default
        )
        return fn(payload, client=client, model=model)


def load_registry(path: Path | None = None) -> Registry:
    """Прочитать agents.toml и построить Registry."""
    resolved = path or _default_registry_path()
    try:
        data = tomllib.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise RegistryError(f"Не удалось прочитать {resolved}: {e}") from e

    try:
        parsed = AgentRegistryFile.model_validate(data)
    except Exception as e:
        raise RegistryError(f"Невалидный agents.toml: {e}") from e

    return Registry(parsed.agents)
