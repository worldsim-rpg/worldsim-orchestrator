"""CLI: new / play / worlds / inspect."""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Generator

import typer
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from worldsim_prompts import AnthropicClient
from worldsim_schemas import WorldInspiration

from .loop import run_turn, show_welcome_scene
from .persistence import (
    WorldSnapshot,
    list_worlds,
    load_initial_snapshot,
    load_world,
    new_world_id,
    save_initial_snapshot,
    save_world,
)
from .renderer import ask_player, console, print_error, print_info, print_scene, print_success
from .settings import default_settings

_AGENT_LABELS: dict[str, str] = {
    "intent-parser":        "разбираю действие",
    "npc-mind":             "думаю за NPC",
    "world-builder":        "обновляю мир",
    "personal-progression": "прогресс игрока",
    "canon-keeper":         "проверяю канон",
    "scene-master":         "рендерю сцену",
}
_TURN_STEPS = 5  # intent + world + progression + canon + scene (npc опционально)


@contextmanager
def _thinking(client: AnthropicClient) -> Generator[None, None, None]:
    """Обёртка вокруг run_turn: прогресс-бар по шагам через перехват client.complete."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        BarColumn(bar_width=20),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("думаю…", total=_TURN_STEPS)

        original_complete = client.complete

        def _tracked(**kwargs):  # type: ignore[no-untyped-def]
            label = _AGENT_LABELS.get(client._log_agent or "", "думаю…")
            progress.update(task, description=label, advance=1)
            return original_complete(**kwargs)

        client.complete = _tracked  # type: ignore[method-assign]
        try:
            yield
        finally:
            client.complete = original_complete  # type: ignore[method-assign]

app = typer.Typer(help="worldsim — текстовая RPG с генерацией мира на лету.")


@app.command()
def new() -> None:
    """Создать новый мир из вдохновения игрока."""

    console.print("[bold]Новый мир[/]\n")
    genre = ask_player("Жанр (например: морское тёмное фэнтези)")
    tone_line = ask_player("Интонация — слова через запятую (например: меланхоличное, таинственное)")
    themes_line = ask_player("Темы — через запятую (например: упадок, вера, долг)")
    references = ask_player("Референсы (опционально, например: Китеж, Берсерк)")
    scale = ask_player("Масштаб [village/town/city/region]") or "town"
    harshness = ask_player("Суровость [cozy/neutral/grim]") or "neutral"
    magic_level = ask_player("Уровень магии [none/low/medium/high]") or "low"
    free_notes = ask_player("Свободные заметки (или Enter)")

    inspiration = WorldInspiration(
        genre=genre,
        tone=[s.strip() for s in tone_line.split(",") if s.strip()],
        themes=[s.strip() for s in themes_line.split(",") if s.strip()],
        references=[s.strip() for s in references.split(",") if s.strip()],
        scale=scale,  # type: ignore[arg-type]
        harshness=harshness,  # type: ignore[arg-type]
        magic_level=magic_level,  # type: ignore[arg-type]
        free_notes=free_notes or None,
    )

    client = AnthropicClient()
    settings = default_settings()

    # world-builder запускается лениво — падает с нормальной ошибкой если не установлен
    try:
        from .loop import _import_agent
    except Exception as e:
        print_error(str(e))
        raise typer.Exit(1)

    world_init = _import_agent("worldsim_world_builder", "run_world_init")
    canon_validate = _import_agent("worldsim_canon_keeper", "validate")

    print_info("Генерирую мир… это может занять минуту.")
    snapshot: WorldSnapshot = world_init(
        {"inspiration": inspiration.model_dump(), "world_id": new_world_id(), "settings": settings.model_dump()},
        client=client,
        model=settings.model_heavy,
    )

    # Canon validation с ретраем
    for _ in range(2):
        v = canon_validate(
            {"snapshot_mode": "fresh_init", "snapshot": _full_snapshot_dump(snapshot)},
            client=client,
            model=settings.model_heavy,
        )
        if v.get("ok"):
            break
        print_info("Канон правит противоречия…")

    save_world(snapshot)
    save_initial_snapshot(snapshot)
    print_success(f"Мир создан: {snapshot.meta.id} — «{snapshot.meta.title}»")

    show_welcome_scene(snapshot, client=client)

    # Пускаем в игру сразу
    _play_loop(snapshot, client)


@app.command()
def play(world: str | None = typer.Option(None, "--world", help="ID мира")) -> None:
    """Играть в существующий мир (по умолчанию — последний созданный)."""

    worlds = list_worlds()
    if not worlds:
        print_error("Нет ни одного сейва. Сначала `python -m worldsim_orchestrator new`.")
        raise typer.Exit(1)

    world_id = world or worlds[-1]["id"]
    try:
        snapshot = load_world(world_id)
    except FileNotFoundError as e:
        print_error(str(e))
        raise typer.Exit(1)

    client = AnthropicClient()
    with console.status("[dim]загружаем мир…[/]"):
        show_welcome_scene(snapshot, client=client)
    _play_loop(snapshot, client)


@app.command()
def worlds() -> None:
    """Показать список сохранённых миров."""

    items = list_worlds()
    if not items:
        print_info("Миров пока нет.")
        return

    table = Table(title="Миры")
    table.add_column("id", style="cyan")
    table.add_column("title", style="white")
    table.add_column("tick", style="dim", justify="right")
    for w in items:
        table.add_row(w["id"], w["title"], w["tick"])
    console.print(table)


@app.command()
def inspect(world: str = typer.Option(..., "--world", help="ID мира")) -> None:
    """Сырой дамп канона мира (для отладки)."""

    snapshot = load_world(world)
    console.print_json(json.dumps(_full_snapshot_dump(snapshot), ensure_ascii=False))


# --- helpers --------------------------------------------------------------


def _play_loop(snapshot: WorldSnapshot, client: AnthropicClient) -> None:
    print_info("Команды: /save — сохранить  /restart — начать сначала  /quit — выйти")
    while True:
        try:
            raw = ask_player()
        except (KeyboardInterrupt, EOFError):
            console.print()
            print_info("Пока.")
            return

        if raw in ("/quit", "/exit"):
            save_world(snapshot)
            print_info("Мир сохранён. До встречи.")
            return

        if raw == "/save":
            save_world(snapshot)
            print_success("Сохранено.")
            continue

        if raw == "/restart":
            initial = load_initial_snapshot(snapshot.meta.id)
            if initial is None:
                print_error("Начальный снапшот не найден — мир создан до версии с /restart.")
                continue
            confirm = ask_player("Начать сначала? Весь прогресс будет утерян [y/N]")
            if confirm.strip().lower() != "y":
                print_info("Отменено.")
                continue
            # Мутируем snapshot in-place чтобы не выходить из цикла
            snapshot.meta = initial.meta
            snapshot.settings = initial.settings
            snapshot.locations = initial.locations
            snapshot.characters = initial.characters
            snapshot.factions = initial.factions
            snapshot.secrets = initial.secrets
            snapshot.arcs = initial.arcs
            snapshot.plot_state = initial.plot_state
            snapshot.player_progression = initial.player_progression
            save_world(snapshot)
            print_success("Мир сброшен до начала.")
            with console.status("[dim]загружаем мир…[/]"):
                show_welcome_scene(snapshot, client=client)
            continue

        if not raw:
            continue

        with _thinking(client):
            scene = run_turn(snapshot, raw, client=client)
        if scene:
            print_scene(scene)


def _full_snapshot_dump(snapshot: WorldSnapshot) -> dict:
    return {
        "meta": snapshot.meta.model_dump(),
        "settings": snapshot.settings.model_dump(),
        "locations": {k: v.model_dump() for k, v in snapshot.locations.items()},
        "characters": {k: v.model_dump() for k, v in snapshot.characters.items()},
        "factions": {k: v.model_dump() for k, v in snapshot.factions.items()},
        "secrets": {k: v.model_dump() for k, v in snapshot.secrets.items()},
        "arcs": {k: v.model_dump() for k, v in snapshot.arcs.items()},
        "plot_state": snapshot.plot_state.model_dump(),
        "player_progression": snapshot.player_progression.model_dump(),
    }
