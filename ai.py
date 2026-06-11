"""
Генерация персонализированных рекомендаций через OpenRouter API.
"""

import requests

from config import (
    AI_PROMPT_MAX_LENGTH,
    OPENROUTER_API_KEY,
    OPENROUTER_API_URL,
    OPENROUTER_MODELS,
)


def _build_prompt(niche: str) -> str:
    return f"""Ты — консультант по автоворонкам в Telegram для экспертов.

Пользователь написал: «{niche}»

СТРОГИЕ ПРАВИЛА:
- Ответ СТРОГО не длиннее {AI_PROMPT_MAX_LENGTH} символов (включая пробелы).
- Можно использовать форматирование Telegram: **жирный**, маркированные списки.
- Кратко: что автоматизировать, какая воронка, точки роста, какой бот.
- Пиши на русском, по делу, без воды."""


def generate_funnel(niche: str) -> str:
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY не задан в .env")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/tg-bot-vizitka",
        "X-Title": "TG Bot Vizitka",
    }

    prompt = _build_prompt(niche)
    last_error: Exception | None = None

    for model in OPENROUTER_MODELS:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 350,
        }
        try:
            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=45,
            )
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            last_error = exc
            print(f"AI: модель {model} недоступна — {exc}")
            continue

    raise RuntimeError(f"Все модели OpenRouter недоступны: {last_error}")
