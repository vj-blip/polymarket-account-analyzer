"""Shared LLM client for all agents. Uses OpenAI API (works with OpenRouter too)."""

from __future__ import annotations
import json
import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

# Use OpenRouter if key available, otherwise OpenAI
_openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
_openai_key = os.getenv("OPENAI_API_KEY", "")

if _openrouter_key:
    _client = AsyncOpenAI(api_key=_openrouter_key, base_url="https://openrouter.ai/api/v1")
else:
    _client = AsyncOpenAI(api_key=_openai_key)

# Model mapping: if using OpenAI directly, map generic names to OpenAI models
_OPENAI_MODEL_MAP = {
    "google/gemini-2.5-flash": "gpt-4o-mini",
    "anthropic/claude-sonnet-4": "gpt-4o",
    "zhipu/glm-5": "gpt-4o-mini",
}


def _resolve_model(model: str) -> str:
    """Resolve model name — pass through for OpenRouter, map for OpenAI."""
    if _openrouter_key:
        return model
    return _OPENAI_MODEL_MAP.get(model, model)


async def call_llm(
    messages: list[dict],
    model: str,
    json_mode: bool = False,
    temperature: float = 0.3,
    max_tokens: int = 4096,
) -> str:
    """Call LLM and return the response text."""
    kwargs = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    
    resp = await _client.chat.completions.create(
        model=_resolve_model(model),
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=180,
        **kwargs,
    )
    return resp.choices[0].message.content


async def call_llm_json(messages: list[dict], model: str, **kwargs) -> dict:
    """Call LLM and parse JSON response."""
    raw = await call_llm(messages, model, json_mode=True, **kwargs)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw)
