"""Тесты renderer — без реального терминала, через Rich Console(file=...)."""

import io

import pytest
from rich.console import Console

import worldsim_orchestrator.renderer as renderer_mod


@pytest.fixture(autouse=True)
def patch_console(monkeypatch):
    """Перенаправляем вывод в строковый буфер."""
    buf = io.StringIO()
    fake_console = Console(file=buf, highlight=False)
    monkeypatch.setattr(renderer_mod, "console", fake_console)
    yield buf


def _output(buf: io.StringIO) -> str:
    return buf.getvalue()


# ---------------------------------------------------------------------------
# print_scene
# ---------------------------------------------------------------------------


def test_print_scene_contains_text(patch_console):
    renderer_mod.print_scene("Туман над доками.")
    assert "Туман над доками." in _output(patch_console)


def test_print_scene_with_header(patch_console):
    renderer_mod.print_scene("Текст сцены.", header="Локация: Доки")
    out = _output(patch_console)
    assert "Текст сцены." in out
    assert "Локация: Доки" in out


def test_print_scene_no_header(patch_console):
    renderer_mod.print_scene("Сцена без заголовка.")
    assert "Сцена без заголовка." in _output(patch_console)


# ---------------------------------------------------------------------------
# print_error
# ---------------------------------------------------------------------------


def test_print_error_with_code(patch_console):
    renderer_mod.print_error("Предмет не найден.", code="NO_ITEM")
    out = _output(patch_console)
    assert "NO_ITEM" in out
    assert "Предмет не найден." in out


def test_print_error_no_code(patch_console):
    renderer_mod.print_error("Что-то пошло не так.")
    assert "Что-то пошло не так." in _output(patch_console)


# ---------------------------------------------------------------------------
# print_info
# ---------------------------------------------------------------------------


def test_print_info(patch_console):
    renderer_mod.print_info("Ход 5.")
    assert "Ход 5." in _output(patch_console)


# ---------------------------------------------------------------------------
# print_success
# ---------------------------------------------------------------------------


def test_print_success(patch_console):
    renderer_mod.print_success("Мир создан!")
    assert "Мир создан!" in _output(patch_console)


# ---------------------------------------------------------------------------
# ask_player (only smoke — it's interactive)
# ---------------------------------------------------------------------------


def test_ask_player_exists():
    assert callable(renderer_mod.ask_player)
