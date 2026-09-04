"""
Vision model client (GLM-4.1V) — shared by all modules.
"""

import os
import logging
import base64
import io
import json
import re
from typing import Any, Type, Optional
from pydantic import BaseModel
from PIL import Image as PILImage
from pathlib import Path
import dotenv

logger = logging.getLogger(__name__)


def _extract_json_from_text(content: str) -> str:
    """Try multiple strategies to extract JSON from LLM response text."""
    if not content or not content.strip():
        return ""

    # Strategy 1: ```json code block
    m = re.search(r'```json\s*\n?(.*?)\n?```', content, re.DOTALL)
    if m:
        candidate = m.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Strategy 2: any ``` code block
    m = re.search(r'```\s*\n?(.*?)\n?```', content, re.DOTALL)
    if m:
        candidate = m.group(1).strip()
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    # Strategy 3: find JSON object by brace matching
    brace_start = content.find('{')
    if brace_start >= 0:
        depth = 0
        end = brace_start
        for i, ch in enumerate(content[brace_start:], brace_start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        candidate = content[brace_start:end]
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass

    return content.strip()


class VisionClient:
    """Singleton vision model client using GLM-4.1V."""

    def __init__(self):
        env_path = Path(__file__).parent.parent.parent / ".env"
        dotenv.load_dotenv(env_path)

        self.api_key = os.getenv("GUI_GROUNDING_MODEL_API_KEY")
        self.base_url = os.getenv("GUI_GROUNDING_MODEL_BASE_URL",
                                  "https://open.bigmodel.cn/api/paas/v4/")
        self.model = os.getenv("GUI_GROUNDING_MODEL_NAME", "glm-4.1v-thinking-flashx")

        if not self.api_key:
            raise RuntimeError("Missing GUI_GROUNDING_MODEL_API_KEY in environment.")

        self._last_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        try:
            from zai import ZhipuAiClient
            self.client = ZhipuAiClient(api_key=self.api_key)
            self._client_kind = "zai"
            logger.info("Using ZhipuAiClient from 'zai' library")
        except ImportError:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            self._client_kind = "openai"
            logger.info("Using standard OpenAI client as fallback for vision")

    def call_vision(self, image: PILImage.Image, prompt: str,
                    response_format: Optional[dict] = None) -> str:
        """Call vision model. Returns content string.
        Token counts are accumulated on self._last_tokens for retrieval."""
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        b64_image = base64.b64encode(buffer.getvalue()).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{b64_image}"}}
                ]
            }
        ]

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        if "thinking" in (self.model or "").lower():
            if self._client_kind == "zai":
                kwargs["thinking"] = {"type": "enabled"}
            else:
                kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

        response = self.client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        reasoning = getattr(response.choices[0].message, "reasoning_content", None)
        if reasoning:
            logger.debug("Vision model reasoning (first 300 chars): %s", str(reasoning)[:300])

        usage = getattr(response, "usage", None)
        self._last_tokens = {
            "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
            "total_tokens": getattr(usage, "total_tokens", 0) or 0,
        }
        return content or ""

    def extract(self, image: PILImage.Image, prompt: str, schema: Type[BaseModel]) -> Any:
        if schema is str:
            return self.call_vision(image, prompt, response_format=None)
        if schema is int:
            content = self.call_vision(image, prompt, response_format=None).strip()
            try:
                return int(content)
            except ValueError:
                nums = re.findall(r'\d+', content)
                return int(nums[0]) if nums else 0
        if schema is float:
            content = self.call_vision(image, prompt, response_format=None).strip()
            try:
                return float(content)
            except ValueError:
                nums = re.findall(r'[\d.]+', content)
                return float(nums[0]) if nums else 0.0
        if schema is bool:
            content = self.call_vision(image, prompt, response_format=None).strip().lower()
            return content in ("1", "true", "yes", "y", "是")

        if not isinstance(schema, type) or not issubclass(schema, BaseModel):
            raise TypeError(
                f"schema must be a pydantic BaseModel subclass or a primitive type. Got: {schema!r}"
            )

        schema_json = json.dumps(schema.model_json_schema(), indent=2)
        full_prompt = (
            f"{prompt}\n\n"
            f"Return ONLY a valid JSON object matching this schema. "
            f"Do NOT include explanations, markdown, or code blocks.\n"
            f"Schema:\n{schema_json}"
        )

        use_json_mode = "thinking" not in (self.model or "").lower()
        content = self.call_vision(
            image, full_prompt,
            response_format={"type": "json_object"} if use_json_mode else None
        )

        json_str = _extract_json_from_text(content)
        logger.debug("Extracted JSON candidate (first 200 chars): %s", json_str[:200])

        try:
            data = json.loads(json_str)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(
                "Failed to parse vision response as JSON. Error: %s\n"
                "Raw content (first 500 chars): %s",
                e, content[:500],
            )
            raise


    def get_last_tokens(self) -> dict:
        """Return token counts from the most recent vision API call."""
        return getattr(self, "_last_tokens", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})


# Singleton
vision_client = VisionClient()
