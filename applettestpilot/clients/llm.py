"""
LLM client factory and shared utilities for DeepSeek API calls.
"""

import os
import time
import logging
from dataclasses import dataclass
from typing import Any

from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from an LLM call, including content and token usage."""
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


def create_llm_client() -> OpenAI:
    """Create an OpenAI-compatible client configured from environment."""
    env_path = Path(__file__).parent.parent.parent / ".env"
    load_dotenv(env_path)

    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set in .env")
    return OpenAI(base_url=base_url, api_key=api_key)


def get_llm_model() -> str:
    return os.getenv("OPENAI_MODEL_NAME", "deepseek-v4-flash")


def call_llm(
    client: OpenAI,
    system: str,
    user: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    max_retries: int = 3,
    model: str | None = None,
) -> LLMResponse | None:
    """Call LLM with progressive cooldown retry for empty responses.
    Returns LLMResponse with content and token counts, or None on failure."""
    model = model or get_llm_model()
    for attempt in range(max_retries):
        try:
            truncated = user
            if attempt > 0:
                max_chars = 6000 - attempt * 2000
                if len(truncated) > max_chars:
                    truncated = truncated[:max_chars] + "\n\n[... truncated ...]"
            t = max(0.1, temperature - attempt * 0.15)
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": truncated},
                ],
                temperature=t,
                max_tokens=max_tokens,
            )
            content = resp.choices[0].message.content
            usage = getattr(resp, "usage", None)
            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
            total_tokens = getattr(usage, "total_tokens", 0) or 0
            if content and content.strip():
                return LLMResponse(
                    content=content,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                )
            wait = 2 ** attempt
            logger.warning("LLM empty (attempt %d/%d), retry in %ds...", attempt + 1, max_retries, wait)
            time.sleep(wait)
        except Exception as e:
            wait = 2 ** attempt
            logger.warning("LLM error (attempt %d/%d): %s", attempt + 1, max_retries, e)
            time.sleep(wait)
    return None
