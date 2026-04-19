# worldsim-orchestrator

CLI, игровой цикл, валидаторы hard-constraints, персистентность и
единственный "голос" системы перед игроком. Часть мульти-агентной
системы [worldsim](https://github.com/worldsim-rpg/worldsim-workspace).

## Роль

Orchestrator:
1. Разговаривает с игроком (CLI на typer + rich).
2. Парсит free-text в `Intent` (LLM внутри).
3. Проверяет hard-constraints (Python, детерминированно).
4. Собирает контекст для каждого агента (выбирает релевантный срез канона).
5. Последовательно зовёт агентов: npc-mind → world-builder →
   personal-progression → canon-keeper → scene-master.
6. Применяет патчи к сейву на диске.
7. Хранит `game_settings.json` per-world и `session_log.jsonl`.

## Установка

```bash
# Сначала shared пакеты из workspace
pip install -e ../worldsim-workspace/packages/schemas
pip install -e ../worldsim-workspace/packages/prompts

# Потом сам orchestrator
pip install -e .

# И все агент-пакеты
for r in ../worldsim-world-builder ../worldsim-canon-keeper \
         ../worldsim-scene-master ../worldsim-npc-mind \
         ../worldsim-personal-progression; do
  pip install -e "$r"
done
```

## Команды

```bash
python -m worldsim_orchestrator new          # создать новый мир
python -m worldsim_orchestrator play         # играть в последний
python -m worldsim_orchestrator play --world <id>
python -m worldsim_orchestrator worlds       # список миров
python -m worldsim_orchestrator inspect --world <id>
```

## Что внутри

| Файл | Что делает |
|---|---|
| `cli.py` | typer-команды, entry points |
| `settings.py` | загрузка/сохранение `GameSettings` per-world |
| `loop.py` | последовательность шагов хода (см. `docs/loop.md` в workspace) |
| `validators.py` | Python-реализация hard-constraints |
| `persistence.py` | JSON-сейвы, применение `PatchOp` |
| `context.py` | сборка релевантного среза канона для агентного вызова |
| `intent.py` | LLM-парсинг free-text игрока в `Intent` |
| `renderer.py` | печать сцены и меню через rich |

## Тесты

```bash
python -m pytest -q
```

Тесты, требующие LLM, скипаются без `ANTHROPIC_API_KEY`.
