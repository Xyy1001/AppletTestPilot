#!/usr/bin/env python3
"""
Test Case Generator for AppletTestPilot.

Uses DeepSeek LLM to auto-generate test cases based on the mini program's
FRAMEWORK.md specification and existing test case patterns.

Usage:
  python generate_test_cases.py --count 5
  python generate_test_cases.py --count 3 --focus cart
  python generate_test_cases.py --count 2 --focus merchant --output-dir my_cases
"""

import sys
import os
import argparse
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("gen")

MODEL = os.getenv("OPENAI_MODEL_NAME", "deepseek-v4-flash")
BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com")
API_KEY = os.getenv("OPENAI_API_KEY", "")

PROJECT_ROOT = Path(__file__).parent
FRAMEWORK_PATH = PROJECT_ROOT / "TestApplet" / "FRAMEWORK.md"
TEST_CASES_DIR = PROJECT_ROOT / "benchmark" / "testapplet" / "test_cases"
SETUP_FUNCTIONS_PATH = PROJECT_ROOT / "benchmark" / "setup_functions.py"


# ═══════════════════════════════════════════════════════════════════════
# Prompt construction
# ═══════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """\
You are an expert QA test engineer for WeChat Mini Programs.
Your task is to generate test cases in YAML format for automated testing.

# Rules
1. Each test case must have: name, setup_function, steps[]
2. Each step must have: action (natural language), expectation (natural language)
3. Use ONLY the page routes, field names, and button labels described in the framework doc.
4. setup_function must be one of the predefined functions listed below.
5. Test cases must be valid YAML that can be parsed by Python's yaml.safe_load().
6. Output ONLY the YAML content in a ```yaml code block. No explanation.

# Setup functions available
- launch_home — fresh start, no data
- launch_home_with_merchant — merchant already exists
- launch_home_with_merchant_and_product — merchant + 1 product
- launch_home_with_merchant_and_product_in_cart — merchant + product + 1 item in cart

# Page routes
- /pages/index/index — Home page (产品展示)
- /pages/vendor/join — Merchant creation form (创建商家账户)
- /pages/vendor/product_edit — Product upload/edit form (产品信息)
- /pages/tabbar/user — User/Merchant center (商家中心)
- /pages/product/detail — Product detail page
- /pages/cart/cart — Shopping cart

# Action verbs
- Verify page state — assertion step, no UI interaction
- Click '<text>' — tap a button/link with that text
- Type '<text>' into '<field>' — type text into a form field
- Switch to '<tab>' — switch to a tab bar page (首页/购物车/我的)
- Go back — navigate back to previous page
- Scroll down / Scroll up — scroll the current page ~half screen
- Scroll to '<text>' — scroll until the specified element is visible

# Expectation patterns
- Page id is '/pages/xxx/xxx' — check current page route
- Page id is not '/pages/xxx/xxx' — verify we left a page
- Navigates to <page description> — navigation occurred
- <field name> shows '<text>' — typed text is visible
- Product '<name>' is visible on <page> — product card exists
- Comment '<text>' appears in the comment list — comment submitted
- Cart shows empty state with '<text>' — empty cart message visible

# Example test case format
```yaml
name: Create Merchant Account
setup_function: launch_home
steps:
- action: Verify page state
  expectation: Page id is '/pages/index/index'
- action: Click '创建商家'
  expectation: Navigates to vendor join page
- action: Verify page state
  expectation: Page id is '/pages/vendor/join'
- action: Type 'Test Store' into '商家名称'
  expectation: Name field shows 'Test Store'
- action: Click '保存'
  expectation: Shows success toast and navigates back to home page
```
"""


def build_user_prompt(framework_text: str, existing_cases: str, count: int, focus: str) -> str:
    prompt = f"""# Framework documentation for the mini program under test

{framework_text}

# Existing test cases (for reference on format and coverage)

{existing_cases}

# Task

Generate {count} NEW test case(s){" focused on " + focus if focus else ""} that are NOT already covered by the existing test cases above.

Requirements:
- Each test case must be a complete end-to-end scenario with verification steps.
- Include at least 4 steps per test case (action + verification pairs).
- Cover edge cases, negative tests, or boundary scenarios that the existing cases miss.
- Use only the page routes, field names, and button labels from the framework doc.
- Follow the exact same YAML format as the examples.

Output ONLY the YAML content inside a ```yaml code block. Do not include any explanation.
"""
    return prompt


# ═══════════════════════════════════════════════════════════════════════
# Generator
# ═══════════════════════════════════════════════════════════════════════

def load_context() -> tuple[str, str]:
    """Load framework doc and existing test cases as context."""
    if not FRAMEWORK_PATH.exists():
        logger.error("FRAMEWORK.md not found at %s", FRAMEWORK_PATH)
        sys.exit(1)

    framework = FRAMEWORK_PATH.read_text(encoding="utf-8")

    # Collect existing test case names and summaries
    existing = []
    if TEST_CASES_DIR.exists():
        for yf in sorted(TEST_CASES_DIR.glob("*.yaml")):
            try:
                text = yf.read_text(encoding="utf-8")
                # Only include name + first 3 steps to save tokens
                lines = text.strip().split("\n")
                summary_lines = []
                for line in lines:
                    if line.strip().startswith("#"):
                        summary_lines.append(line)
                    elif len(summary_lines) < 20:
                        summary_lines.append(line)
                existing.append("\n".join(summary_lines[:30]))
            except Exception:
                pass

    return framework, "\n\n---\n\n".join(existing)


def extract_yaml(response: str) -> str | None:
    """Extract YAML content from LLM response."""
    # Try ```yaml block first
    import re
    m = re.search(r"```yaml\s*\n(.*?)\n```", response, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Try ``` block
    m = re.search(r"```\s*\n(.*?)\n```", response, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Try raw YAML (starts with "name:")
    if response.strip().startswith("name:"):
        return response.strip()
    return None


def validate_yaml(yaml_text: str) -> bool:
    """Check if YAML has the required structure."""
    import yaml
    try:
        data = yaml.safe_load(yaml_text)
        if not isinstance(data, dict):
            return False
        if "name" not in data:
            return False
        if "steps" not in data or not isinstance(data["steps"], list):
            return False
        for step in data["steps"]:
            if "action" not in step or "expectation" not in step:
                return False
        return True
    except Exception:
        return False


def save_test_case(yaml_text: str, index: int, output_dir: Path) -> Path:
    """Save a generated test case to a YAML file."""
    import yaml
    data = yaml.safe_load(yaml_text)
    name = data.get("name", f"generated_{index}")
    # Create a safe filename
    safe_name = name.lower().replace(" ", "_").replace("'", "").replace('"', "")[:60]
    filename = f"gen_{index:02d}_{safe_name}.yaml"
    filepath = output_dir / filename
    filepath.write_text(yaml_text.strip() + "\n", encoding="utf-8")
    return filepath


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Generate test cases using DeepSeek LLM")
    parser.add_argument("--count", type=int, default=3, help="Number of test cases to generate")
    parser.add_argument("--focus", type=str, default=None,
                        help="Focus area: merchant, product, cart, favorite, comment, edge")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output directory (default: benchmark/testapplet/test_cases/)")
    args = parser.parse_args()

    if not API_KEY:
        logger.error("OPENAI_API_KEY not set in .env")
        sys.exit(1)

    output_dir = args.output_dir or TEST_CASES_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load context
    framework, existing_cases = load_context()
    logger.info("Framework: %d chars | Existing cases: %d chars", len(framework), len(existing_cases))

    # Build prompt
    user_prompt = build_user_prompt(framework, existing_cases, args.count, args.focus)
    logger.info("Prompt: %d chars", len(user_prompt))

    # Call DeepSeek
    client = OpenAI(base_url=BASE_URL, api_key=API_KEY)
    logger.info("Calling %s...", MODEL)

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=4096,
    )

    content = response.choices[0].message.content
    logger.info("Response: %d chars", len(content) if content else 0)
    logger.info("=" * 60)
    logger.info("  LLM RESPONSE (raw)")
    logger.info("=" * 60)
    if content:
        logger.info(content)
    logger.info("=" * 60)

    if not content:
        logger.error("Empty response from LLM")
        sys.exit(1)

    # Extract and validate YAML
    yaml_text = extract_yaml(content)
    if not yaml_text:
        logger.error("Could not extract YAML from response")
        sys.exit(1)

    # Split multiple test cases (if LLM returned them separated by ---)
    import re
    cases = re.split(r"\n---\n|\n---\r", yaml_text)
    cases = [c.strip() for c in cases if c.strip() and "name:" in c]

    if not cases:
        cases = [yaml_text]

    saved = 0
    for case_yaml in cases:
        if not validate_yaml(case_yaml):
            logger.warning("Skipping invalid YAML block: %s...", case_yaml[:80])
            continue
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = save_test_case(case_yaml, saved + 1, output_dir)
        logger.info("[%d] Saved: %s", saved + 1, filepath.name)
        saved += 1

    logger.info("=" * 60)
    logger.info("  Generated: %d test case(s)", saved)
    logger.info("  Output  : %s", output_dir)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
