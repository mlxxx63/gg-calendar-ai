from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings

# If you already have openai usage elsewhere, reuse that approach.
# This implementation uses the OpenAI Python SDK v1 style.
from openai import OpenAI


class ParsedIntent(BaseModel):
    start: str = Field(..., description="ISO8601 datetime with timezone offset")
    end: str = Field(..., description="ISO8601 datetime with timezone offset")
    duration_minutes: int = Field(..., ge=5, le=480)


def _default_window_now_local() -> tuple[str, str]:
    """
    Fallback window if the AI fails: next 7 days, in UTC.
    You can later change this to user timezone if you store it.
    """
    now = datetime.now(timezone.utc)
    start = now.isoformat()
    end = (now + timedelta(days=7)).isoformat()
    return start, end


def parse_intent_with_llm(prompt: str) -> ParsedIntent:
    """
    Converts natural language scheduling request into a structured time window + duration.
    The output MUST be validated by ParsedIntent.
    """
    client = OpenAI(api_key=settings.OPENAI_API_KEY)

    # We pass "now" so the model can interpret "tomorrow", "next week", etc.
    now_utc = datetime.now(timezone.utc).isoformat()

    system = (
        "You are a scheduling intent parser. "
        "Return ONLY valid JSON with keys: start, end, duration_minutes. "
        "All datetimes must be ISO8601 with timezone offset. "
        "Choose a reasonable window if the user is vague (e.g., tomorrow = 1 day window; "
        "next week = 7 day window)."
    )

    user = (
        f"Now (UTC): {now_utc}\n"
        f"User request: {prompt}\n\n"
        "Return JSON only."
    )

    resp = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        temperature=0.0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )

    raw = resp.choices[0].message.content.strip()

    # Defensive parsing: attempt JSON load, then validate Pydantic
    try:
        data = json.loads(raw)
        return ParsedIntent(**data)
    except (json.JSONDecodeError, ValidationError):
        # fallback: safe default window, 30 min duration
        s, e = _default_window_now_local()
        return ParsedIntent(start=s, end=e, duration_minutes=30)
