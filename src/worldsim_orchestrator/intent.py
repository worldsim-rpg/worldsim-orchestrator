"""
Парсинг free-text игрока в Intent через LLM.

Это единственный LLM-вызов, который делает сам orchestrator — остальное
инкапсулировано в агент-пакеты.
"""

from __future__ import annotations

import json
from pathlib import Path

from worldsim_prompts import AnthropicClient, call_json, load_prompt
from worldsim_schemas import Intent

from .context import TurnContext

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "intent_parser.md"


def parse_intent(
    raw_text: str,
    ctx: TurnContext,
    *,
    client: AnthropicClient,
    model: str,
) -> Intent:
    """Превращает ввод игрока в `Intent`. Падает, если ответ невалиден."""

    system = load_prompt(_PROMPT_PATH)
    user = json.dumps(
        {"player_input": raw_text, "context": ctx.to_dict()},
        ensure_ascii=False,
        indent=2,
    )

    return call_json(
        client,
        system=system,
        user=user,
        model=model,
        schema=Intent,
        max_tokens=500,
        temperature=0.2,
    )
