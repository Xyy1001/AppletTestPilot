"""
Phase 1 — YAML loading, saving, and validation utilities.
"""

import yaml
import logging
from pathlib import Path

from ..models.result import TestCase, TestStep

logger = logging.getLogger(__name__)


def load_test_case(yaml_path: Path) -> TestCase:
    """Load a test case from a YAML file."""
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    steps = [TestStep(action=s["action"], expectation=s["expectation"])
             for s in (data.get("steps") or [])]
    return TestCase(
        test_path=yaml_path.resolve(),
        name=data.get("name", yaml_path.stem),
        setup_function=data.get("setup_function", ""),
        steps=steps,
    )


def save_case_yaml(case_data: dict, case_dir: Path) -> Path:
    """Save a test case dict as case.yaml."""
    case_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = case_dir / "case.yaml"
    yaml_path.write_text(
        yaml.dump(case_data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return yaml_path


def validate_yaml(yaml_text: str) -> dict | None:
    """Check YAML structure and return parsed dict or None."""
    try:
        data = yaml.safe_load(yaml_text)
        if not isinstance(data, dict):
            return None
        if "name" not in data:
            return None
        if "steps" not in data or not isinstance(data["steps"], list):
            return None
        for s in data["steps"]:
            if "action" not in s:
                return None
            if "expectation" not in s:
                s["expectation"] = ""
        return data
    except Exception:
        return None


def extract_yaml(text: str) -> str | None:
    """Extract YAML content from LLM response text."""
    import re
    if not text:
        return None
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, re.DOTALL)
    if m:
        yaml_text = m.group(1).strip()
        if yaml_text.startswith("- name:"):
            yaml_text = yaml_text[2:]
        return yaml_text

    raw = text.strip()
    if raw.startswith("- name:"):
        raw = raw[2:]
    if raw.startswith("name:"):
        return raw
    return None
