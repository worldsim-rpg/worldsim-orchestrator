"""
Тесты реестра агентов.

Не требуют установленных агент-пакетов (все импорты lazy). Проверяют:
- agents.toml парсится в AgentRegistryFile.
- Каждая фаза встречается не чаще одного раза.
- Все объявленные в agents.toml пакеты/entrypoints существуют в окружении
  (если импортируются — iff они установлены локально через pip -e).
- Самодекларации агентов (MANIFEST / MANIFESTS) согласованы с agents.toml.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from worldsim_schemas import AgentManifest, AgentPhase, AgentRegistryFile
from worldsim_orchestrator.registry import (
    Registry,
    RegistryError,
    load_registry,
)


# --- пути ------------------------------------------------------------------


def _workspace_agents_toml() -> Path:
    """Резолвим agents.toml относительно этого файла (sandbox/repos/...)."""
    here = Path(__file__).resolve()
    # tests/test_registry.py → orchestrator → repos → worldsim-workspace
    repos = here.parents[2]
    return repos / "worldsim-workspace" / "agents.toml"


# --- базовые проверки файла ------------------------------------------------


def test_agents_toml_exists():
    assert _workspace_agents_toml().exists(), (
        "Не найден worldsim-workspace/agents.toml. "
        "Он должен лежать на одном уровне с repos/."
    )


def test_registry_loads():
    reg = load_registry(_workspace_agents_toml())
    assert isinstance(reg, Registry)
    assert len(reg.manifests) >= 1


def test_no_duplicate_phases():
    """Каждую фазу обслуживает ≤1 агента. Иначе — RegistryError."""
    reg = load_registry(_workspace_agents_toml())
    seen: set[AgentPhase] = set()
    for m in reg.manifests:
        assert m.phase not in seen, f"Фаза {m.phase.value} дублируется в agents.toml"
        seen.add(m.phase)


def test_duplicate_phase_rejected():
    """Синтетический реестр с дублем фазы — Registry поднимает RegistryError."""
    m1 = AgentManifest(
        name="a", package="x", entrypoint="run", phase=AgentPhase.SCENE_RENDER
    )
    m2 = AgentManifest(
        name="b", package="y", entrypoint="run", phase=AgentPhase.SCENE_RENDER
    )
    with pytest.raises(RegistryError):
        Registry([m1, m2])


# --- consistency agents.toml ↔ агент-пакетов -------------------------------


def _collect_self_declared_manifests() -> dict[str, AgentManifest]:
    """
    Проходит по agents.toml, для каждого пакета пытается импортировать и
    собрать его MANIFEST / MANIFESTS. Отсутствующие пакеты пропускаются —
    это окей для окружения, где не все агенты установлены.
    """
    reg = load_registry(_workspace_agents_toml())
    out: dict[str, AgentManifest] = {}
    seen_packages: set[str] = set()
    for m in reg.manifests:
        if m.package in seen_packages:
            continue
        seen_packages.add(m.package)
        try:
            mod = importlib.import_module(m.package)
        except ImportError:
            continue
        if hasattr(mod, "MANIFESTS"):
            for sm in mod.MANIFESTS:
                out[sm.name] = sm
        elif hasattr(mod, "MANIFEST"):
            sm = mod.MANIFEST
            out[sm.name] = sm
    return out


def test_self_declared_manifests_match_registry():
    """
    Для каждого установленного агента: его MANIFEST(S) должен совпадать
    с соответствующей записью в agents.toml (name → phase/package/entrypoint).
    """
    reg = load_registry(_workspace_agents_toml())
    declared = _collect_self_declared_manifests()
    if not declared:
        pytest.skip("Ни один агент-пакет не установлен в окружении.")

    by_name = {m.name: m for m in reg.manifests}
    for name, self_m in declared.items():
        assert name in by_name, f"Агент {name} объявил MANIFEST, но его нет в agents.toml"
        canon = by_name[name]
        assert self_m.package == canon.package, f"{name}: package mismatch"
        assert self_m.entrypoint == canon.entrypoint, f"{name}: entrypoint mismatch"
        assert self_m.phase == canon.phase, f"{name}: phase mismatch"


# --- схема файла -----------------------------------------------------------


def test_agent_registry_file_schema():
    """AgentRegistryFile — валидная pydantic-модель и ре-экспорт из пакета."""
    reg_file = AgentRegistryFile(
        schema_version="0.1.0",
        agents=[
            AgentManifest(
                name="x",
                package="foo",
                entrypoint="run",
                phase=AgentPhase.SCENE_RENDER,
            )
        ],
    )
    dumped = reg_file.model_dump()
    assert dumped["agents"][0]["phase"] == "scene_render"
