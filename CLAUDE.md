# CLAUDE.md — worldsim-orchestrator

Правила для Claude Code, работающего в этом репо.

## Что это

Ядро и единственная точка общения с игроком. Всё, что не LLM-роль —
живёт здесь: CLI, цикл хода, валидаторы, сейвы.

## Границы

- ЭТО репо **пишет в канон**: `game_settings.json`, `session_log.jsonl`,
  `timeline.jsonl`. Больше ни во что — остальное через патчи от агентов.
- ЭТО репо **не знает содержания промптов** агентов. Вызовы
  инкапсулированы в их функциях `run(...)`.
- ЭТО репо **не меняет pydantic-схемы**. Они в workspace.

## Что здесь правильно менять

- `cli.py` — команды, UX ввода-вывода.
- `validators.py` — **добавить hard-constraint** (см. `docs/constraints.md`
  в workspace).
- `persistence.py` — способ сохранения, логи.
- `loop.py` — оркестровка вызовов агентов.
- `intent.py` + `prompts/intent_parser.md` — как ввод игрока превращается
  в `Intent`.
- `context.py` — что загружать в контекст агента для конкретной ситуации.

## Что НЕ трогать

- `_schemas/`, `_prompts/` — автоsync из workspace.
- Содержимое других агент-репо — только через их публичный `run(...)`.

## Правило при добавлении нового hard-constraint

1. Дописать функцию в `validators.py` + unit-тест.
2. Обновить таблицу в `worldsim-workspace/docs/constraints.md`.
3. Добавить проверку в `loop.validate_intent(...)` перед вызовом агентов.

## Правило при добавлении нового агента

См. `worldsim-workspace/docs/agent-contract.md`. Кратко:

1. `cd ../worldsim-workspace && ./repo-setup/generate-scaffold.sh <name> <pkg> "<desc>"`.
2. Добавить `MANIFEST` (или `MANIFESTS`) в `__init__.py` нового пакета.
3. Добавить секцию `[[agents]]` в `worldsim-workspace/agents.toml`.
4. Добавить имя в `worldsim-workspace/repo-setup/agents.txt` + `sync-all.sh`.
5. В orchestrator: `pip install -e` локально, либо добавить в `pyproject.toml`.
6. `python -m pytest tests/test_registry.py` — должен пройти.

**`loop.py` НЕ меняется.** Если понадобилось — скорее всего вводится
новая фаза в `AgentPhase`, обсуждается отдельным ADR.
