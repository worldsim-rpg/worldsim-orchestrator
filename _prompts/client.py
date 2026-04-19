"""Тонкая обёртка над anthropic.Anthropic для worldsim-агентов."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import anthropic
from dotenv import load_dotenv


@dataclass
class CallLog:
    model: str
    input_tokens: int
    output_tokens: int
    duration_s: float


class AnthropicClient:
    """
    Единый клиент для всех агентов.

    - Читает ANTHROPIC_API_KEY из окружения (или .env рядом с вызовом).
    - Поддерживает WORLDSIM_DEBUG=1 — печатает system/user/response в stderr.
    - Делает простой retry на rate-limit / transient errors.
    """

    def __init__(self, api_key: str | None = None, debug: bool | None = None):
        load_dotenv()
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY не задан. Скопируйте .env.example в .env и "
                "вставьте ключ."
            )
        self._client = anthropic.Anthropic(api_key=key)
        self._debug = debug if debug is not None else os.environ.get("WORLDSIM_DEBUG") == "1"
        self.last_call: CallLog | None = None

    def complete(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        max_retries: int = 3,
    ) -> str:
        """Возвращает текст ответа ассистента. Без структурных проверок."""

        if self._debug:
            _log(f"=== SYSTEM ({model}) ===\n{system}\n=== USER ===\n{user}\n")

        attempt = 0
        start = time.time()
        while True:
            try:
                msg = self._client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                break
            except (anthropic.RateLimitError, anthropic.APIStatusError) as e:
                attempt += 1
                if attempt > max_retries:
                    raise
                delay = 2**attempt
                _log(f"[retry {attempt}] {type(e).__name__}, sleeping {delay}s")
                time.sleep(delay)

        duration = time.time() - start
        text = "".join(block.text for block in msg.content if block.type == "text")

        self.last_call = CallLog(
            model=model,
            input_tokens=msg.usage.input_tokens,
            output_tokens=msg.usage.output_tokens,
            duration_s=duration,
        )

        if self._debug:
            _log(
                f"=== RESPONSE ({msg.usage.input_tokens}→{msg.usage.output_tokens} tok, "
                f"{duration:.1f}s) ===\n{text}\n"
            )

        return text


def _log(msg: str) -> None:
    import sys

    print(msg, file=sys.stderr, flush=True)
