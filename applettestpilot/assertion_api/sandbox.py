"""
Sandbox executor for LLM-generated assertion code.
Runs Python code with variable tracing for debugging failures.
"""

import logging
import pprint
import re
import sys
import types
from datetime import date, datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Literal, Optional, Set, Union
from uuid import UUID

from pydantic import BaseModel, EmailStr, HttpUrl, Field, confloat, conint, constr, model_validator
from pydantic.fields import PydanticUndefined

logger = logging.getLogger(__name__)

PRIMITIVE_TYPES = (int, float, str, bool, type(None))


# ═══════════════════════════════════════════════════════════════════════
# LLM-tolerant BaseModel (Symbol)
# ═══════════════════════════════════════════════════════════════════════

class Symbol(BaseModel):
    """Pydantic BaseModel that tolerates LLM errors: None→default, extra fields ignored."""
    model_config = {"extra": "ignore", "populate_by_name": True}

    @model_validator(mode="before")
    @classmethod
    def none_to_default(cls, data: Any) -> dict:
        if not isinstance(data, dict):
            return data
        new_data = {}
        for name, field in cls.model_fields.items():
            val = data.get(name, None)
            if val is None:
                if field.default is not None:
                    new_data[name] = field.default
                else:
                    origin = getattr(field.annotation, "__origin__", None)
                    if origin in (list, dict, set):
                        new_data[name] = origin()
            else:
                new_data[name] = val
        return new_data


def _tolerant_field(*args, **kwargs):
    """Wrapper around pydantic Field that handles LLM passing description as positional arg."""
    positional_param_names = ("description", "title")
    for i, extra in enumerate(args[1:], start=0):
        key = positional_param_names[i] if i < len(positional_param_names) else None
        if key and key not in kwargs:
            kwargs[key] = extra
    return Field(args[0] if args else PydanticUndefined, **kwargs)


# ═══════════════════════════════════════════════════════════════════════
# Variable tracing
# ═══════════════════════════════════════════════════════════════════════

def _compute_delta(old: dict, new: dict) -> dict:
    delta: dict = {}
    old_keys = set(old.keys())
    new_keys = set(new.keys())
    inserts = {k: new[k] for k in new_keys - old_keys}
    if inserts:
        delta["insert"] = inserts
    deletes = [k for k in old_keys - new_keys]
    if deletes:
        delta["delete"] = deletes
    updates = {k: new[k] for k in old_keys & new_keys if old[k] != new[k]}
    if updates:
        delta["update"] = updates
    return delta


def _run_assertion_with_trace(assertion_func: Callable, session: Any) -> tuple[bool, str]:
    """Execute assertion function with sys.settrace-based variable tracing."""
    captured_deltas: list = []
    last_snapshot: dict = {}

    def filter_locals(locals_dict: dict) -> dict:
        filtered = {}
        for k, v in locals_dict.items():
            if isinstance(v, PRIMITIVE_TYPES):
                filtered[k] = v
            elif isinstance(v, (dict, list)):
                filtered[k] = v
            elif isinstance(v, BaseModel):
                filtered[k] = v.model_dump()
            elif hasattr(v, "__class__") and hasattr(v, "page"):
                filtered[k] = f"<{type(v).__name__}>"
        return filtered

    def tracer(frame: types.FrameType, event: str, arg: Any):
        nonlocal last_snapshot
        if event == "line" and frame.f_code.co_name == assertion_func.__name__:
            snapshot = filter_locals(frame.f_locals.copy())
            delta = _compute_delta(last_snapshot, snapshot)
            if delta.get("insert") or delta.get("update") or delta.get("delete"):
                captured_deltas.append((f"line {frame.f_lineno}", delta))
                last_snapshot = snapshot
        return tracer

    try:
        sys.settrace(tracer)
        result = assertion_func(session)
        sys.settrace(None)
        if result is True or result is None:
            return True, "Success"
        if isinstance(result, str) and result.strip():
            return False, result
        return False, f"Assertion failed.\nVariable trace:\n{pprint.pformat(captured_deltas)}"
    except AssertionError as ae:
        sys.settrace(None)
        msg = str(ae) if str(ae).strip() else "AssertionError without message"
        return False, f"{msg}\nVariable trace:\n{pprint.pformat(captured_deltas)}"
    except Exception:
        sys.settrace(None)
        logger.exception("Assertion execution error")
        return False, f"Execution error.\nVariable trace:\n{pprint.pformat(captured_deltas)}"


# ═══════════════════════════════════════════════════════════════════════
# Main executor
# ═══════════════════════════════════════════════════════════════════════

def execute(response: str, session: Any) -> tuple[bool, str]:
    """
    Extract ```python code blocks from response, exec in sandbox,
    find precondition/postcondition function, execute with tracing.
    """
    pattern = r"```python\s+([\s\S]*?)```"
    code_blocks = re.findall(pattern, response, re.MULTILINE)
    code = "\n\n".join(code_blocks)

    if not code.strip():
        code = response.strip()

    code = "from __future__ import annotations\n" + code

    allowed_globals = {
        "__builtins__": __builtins__,
        "Session": type(session),
        "BaseModel": Symbol,
        "Field": _tolerant_field,
        "EmailStr": EmailStr,
        "HttpUrl": HttpUrl,
        "constr": constr,
        "conint": conint,
        "confloat": confloat,
        "Any": Any,
        "Union": Union,
        "Literal": Literal,
        "Optional": Optional,
        "List": List,
        "Set": Set,
        "Dict": Dict,
        "Enum": Enum,
        "UUID": UUID,
        "datetime": datetime,
        "date": date,
    }

    local_vars: dict = {}
    try:
        exec(code, allowed_globals, local_vars)
    except SyntaxError as se:
        return False, f"SyntaxError at line {se.lineno}: {se.msg}"
    except Exception as e:
        return False, f"Error executing generated code: {e}"

    assertion_func = local_vars.get("precondition") or local_vars.get("postcondition")
    if assertion_func is None or not callable(assertion_func):
        return False, "No callable 'precondition' or 'postcondition' function found in generated code."

    return _run_assertion_with_trace(assertion_func, session)
