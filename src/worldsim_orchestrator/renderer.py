"""Вывод сцены и меню в терминал через rich."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

console = Console()


def print_scene(scene_text: str, *, header: str | None = None) -> None:
    panel = Panel(
        Text(scene_text, style="white"),
        title=header,
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(panel)


def print_error(message: str, *, code: str | None = None) -> None:
    prefix = f"[{code}] " if code else ""
    console.print(f"[bold red]{prefix}{message}[/]")


def print_info(message: str) -> None:
    console.print(f"[dim]{message}[/]")


def print_success(message: str) -> None:
    console.print(f"[bold green]{message}[/]")


def ask_player(prompt: str = "> ") -> str:
    return Prompt.ask(prompt).strip()
