"""AppletTestPilot configuration."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import yaml
from dotenv import load_dotenv


@dataclass
class ModelConfig:
    """Configuration for a single LLM/VLM client."""
    model: str = ""
    temperature: float = 0.3
    max_tokens: int = 1024
    max_retries: int = 3


@dataclass
class Config:
    """Configuration for AppletTestPilot."""
    max_tries: int = 3
    screenshot_backend: str = "minium"
    max_step_retries: int = 0

    # Model-specific configurations
    vlm: ModelConfig = field(default_factory=ModelConfig)
    llm_assertion: ModelConfig = field(default_factory=lambda: ModelConfig(temperature=0.3, max_tokens=1024))
    llm_explore: ModelConfig = field(default_factory=lambda: ModelConfig(temperature=0.5, max_tokens=512))
    llm_generate: ModelConfig = field(default_factory=lambda: ModelConfig(temperature=0.7, max_tokens=4096))

    _raw: dict = field(default_factory=dict, repr=False)

    @staticmethod
    def load(path: str | Path) -> "Config":
        path = Path(path)
        env_path = path.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path)

        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        else:
            data = {}

        executor = data.get("executor", {})

        def _parse_model(key: str, defaults: dict) -> ModelConfig:
            mc = data.get(key, {})
            return ModelConfig(
                model=mc.get("model", defaults.get("model", "")),
                temperature=mc.get("temperature", defaults.get("temperature", 0.3)),
                max_tokens=mc.get("max_tokens", defaults.get("max_tokens", 1024)),
                max_retries=mc.get("max_retries", defaults.get("max_retries", 3)),
            )

        return Config(
            max_tries=executor.get("max_tries", 3),
            max_step_retries=executor.get("max_step_retries", 0),
            screenshot_backend=data.get("screenshot_backend", "minium"),
            vlm=_parse_model("vlm", {"temperature": 0.3, "max_tokens": 1024}),
            llm_assertion=_parse_model("llm_assertion", {"temperature": 0.3, "max_tokens": 1024}),
            llm_explore=_parse_model("llm_explore", {"temperature": 0.5, "max_tokens": 512}),
            llm_generate=_parse_model("llm_generate", {"temperature": 0.7, "max_tokens": 4096}),
            _raw=data,
        )
