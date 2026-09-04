"""
Unified GUI State — the single source of truth for the Agent's world model.

Every observation cycle produces one ``GUIState``.  This is the unit of
reasoning for the Planner, Oracle, Memory, and Analyzer.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UIElement:
    """A single interactive / visible element on the current page."""
    tag: str = ""
    text: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    visible: bool = True
    clickable: bool = False
    semantic_role: str = ""       # e.g. "button", "input", "tab", "link", "label"
    attributes: dict = field(default_factory=dict)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)


@dataclass
class PageInfo:
    """Structured summary of the current logical page."""
    route: str = ""               # e.g. /pages/index/index
    title: str = ""               # navigation bar title
    semantic_role: str = ""       # e.g. "home", "form", "detail", "cart", "profile"
    business_function: str = ""   # e.g. "product_browsing", "merchant_creation"
    risk_level: str = "low"       # "low" | "medium" | "high" (payment, deletion, …)
    requires_merchant: bool = False
    is_tab_page: bool = False
    is_modal: bool = False        # native dialog / action-sheet


@dataclass
class GUIState:
    """Complete snapshot of the mini program at a point in time.

    This is the central data structure passed between Agent modules.
    """
    # ── identity ──
    state_id: str = ""            # unique id for this snapshot
    timestamp: float = field(default_factory=time.perf_counter)

    # ── page ──
    page: PageInfo = field(default_factory=PageInfo)

    # ── visual ──
    screenshot_bytes: bytes = b""
    vlm_description: str = ""     # natural-language description from VLM

    # ── structural ──
    elements: list[UIElement] = field(default_factory=list)
    text_on_screen: list[str] = field(default_factory=list)

    # ── navigation context ──
    prev_action: str = ""         # the action that led to this state
    prev_state_id: str = ""

    # ── runtime signals ──
    console_logs: list[str] = field(default_factory=list)
    network_logs: list[str] = field(default_factory=list)

    # ── meta ──
    step_index: int = 0
    is_terminal: bool = False
    is_error: bool = False
    error_message: str = ""

    @classmethod
    def from_env_observation(cls, obs: dict, step_index: int = 0,
                             prev_action: str = "", prev_state_id: str = "",
                             vlm_description: str = "") -> "GUIState":
        """Build a GUIState from a raw ``MiniProgramEnv.observe()`` dict."""
        elements = []
        texts: list[str] = []
        for raw in obs.get("elements_raw", []):
            el = UIElement(
                tag=raw.get("tag", ""),
                text=raw.get("text", ""),
                x=raw.get("x", 0), y=raw.get("y", 0),
                width=raw.get("w", 0), height=raw.get("h", 0),
                visible=raw.get("visible", True),
                attributes=raw.get("attrs", {}),
            )
            # Heuristic semantic-role tagging
            tag_lower = el.tag.lower()
            text_lower = el.text.lower()
            if tag_lower in ("button",) or "btn" in text_lower:
                el.clickable = True
                el.semantic_role = "button"
            elif tag_lower in ("input", "textarea"):
                el.semantic_role = "input"
            elif tag_lower in ("image",) and ("tab" in text_lower or "icon" in text_lower):
                el.semantic_role = "tab"
            elif tag_lower in ("text", "view") and el.text:
                el.semantic_role = "label"

            elements.append(el)
            if el.text:
                texts.append(el.text)
            # Include typed values so the Oracle can verify input actions
            if isinstance(el.attributes, dict):
                val = el.attributes.get("value", "")
                if val and str(val) not in (el.text or ""):
                    texts.append(str(val))

        route = obs.get("page_route", "/")
        page = PageInfo(
            route=route,
            title=obs.get("page_title", "") or "",
            is_tab_page=route in ("/pages/index/index", "/pages/cart/cart", "/pages/tabbar/user"),
            is_modal=False,
        )
        _tag_page_semantics(page)

        return cls(
            state_id=f"s{step_index}_{int(time.perf_counter() * 1e6)}",
            timestamp=obs.get("timestamp", time.perf_counter()),
            page=page,
            screenshot_bytes=obs.get("screenshot_bytes", b""),
            vlm_description=vlm_description,
            elements=elements,
            text_on_screen=texts,
            prev_action=prev_action,
            prev_state_id=prev_state_id,
            step_index=step_index,
        )


def _tag_page_semantics(page: PageInfo) -> None:
    """Heuristically tag a page's semantic role and business function."""
    r = page.route
    if r == "/pages/index/index":
        page.semantic_role = "home"
        page.business_function = "product_browsing"
    elif r == "/pages/vendor/join":
        page.semantic_role = "form"
        page.business_function = "merchant_creation"
    elif r == "/pages/vendor/product_edit":
        page.semantic_role = "form"
        page.business_function = "product_management"
    elif r == "/pages/product/detail":
        page.semantic_role = "detail"
        page.business_function = "product_detail"
    elif r == "/pages/cart/cart":
        page.semantic_role = "cart"
        page.business_function = "cart_management"
    elif r == "/pages/tabbar/user":
        page.semantic_role = "profile"
        page.business_function = "merchant_center"
    elif "modal" in (page.title or "").lower():
        page.semantic_role = "modal"
        page.is_modal = True
    page.requires_merchant = page.business_function in (
        "product_management", "product_detail", "cart_management", "merchant_center"
    )
    page.risk_level = "high" if page.business_function in ("product_management", "cart_management") else "low"
