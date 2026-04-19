"""Утилиты сборки промптов и извлечения JSON-ответов."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from .client import AnthropicClient

T = TypeVar("T", bound=BaseModel)


def load_prompt(path: str | Path) -> str:
    """Прочитать .md-файл промпта."""

    return Path(path).read_text(encoding="utf-8")


def render(template: str, **vars: object) -> str:
    """
    Минимальный шаблонизатор: `{{name}}` подставляется значением `vars["name"]`.
    Без Jinja — нам не нужны циклы в промптах.
    """

    def repl(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key not in vars:
            raise KeyError(f"В промпте используется {{{{ {key} }}}}, но значение не передано")
        value = vars[key]
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, indent=2)
        return str(value)

    return re.sub(r"\{\{\s*([^}]+?)\s*\}\}", repl, template)


def extract_json(text: str) -> object:
    """
    Достаёт JSON из ответа LLM. Поддерживает три варианта:
      1. чистый JSON на всю строку;
      2. ```json ... ``` блок;
      3. просто JSON в тексте — берём первый валидный объект/массив.
    """

    text = text.strip()
    # Прямой парс
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # ```json ... ```
    m = re.search(r"```(?:json)?\s*(.+?)```", text, re.DOTALL)
    if m:
        return json.loads(m.group(1).strip())

    # Первый { ... } или [ ... ] по балансу скобок
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == open_ch:
                depth += 1
            elif text[i] == close_ch:
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break

    raise ValueError(f"Не удалось извлечь JSON из ответа LLM:\n{text[:500]}")


def call_json(
    client: AnthropicClient,
    *,
    system: str,
    user: str,
    model: str,
    schema: type[T],
    max_tokens: int = 4096,
    temperature: float = 0.7,
) -> T:
    """Сделать LLM-вызов и вернуть pydantic-модель заявленного типа."""

    raw = client.complete(
        model=model,
        system=system,
        user=user,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    data = extract_json(raw)
    return schema.model_validate(data)
