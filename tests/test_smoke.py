"""Дымовой тест: импорт и CLI help."""

from typer.testing import CliRunner


def test_imports():
    from worldsim_orchestrator import cli, context, intent, loop, persistence, renderer, settings, validators  # noqa: F401


def test_cli_help():
    from worldsim_orchestrator.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "new" in result.stdout
    assert "play" in result.stdout
