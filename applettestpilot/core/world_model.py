"""
World Model — the Agent's deep understanding of the mini program under test.

Loads all initialization materials (source code, framework docs, requirements,
design docs) and builds a structured context that the Planner and Oracle can
use for informed decision-making.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class WorldModel:
    """Complete knowledge about the mini program under test.

    Built once at Agent initialization and passed to every Planner call.
    """

    # ── metadata ──
    source_path: str = ""
    app_name: str = ""

    # ── documents ──
    framework_doc: str = ""       # FRAMEWORK.md
    requirements_doc: str = ""    # REQUIREMENTS.md
    design_doc: str = ""          # DESIGN.md

    # ── source code ──
    source_files: dict[str, str] = field(default_factory=dict)  # path → content

    # ── derived knowledge ──
    page_routes: list[str] = field(default_factory=list)
    page_roles: dict[str, str] = field(default_factory=dict)    # route → role
    storage_keys: list[str] = field(default_factory=list)
    toast_messages: dict[str, str] = field(default_factory=dict)  # condition → message
    data_schemas: dict[str, str] = field(default_factory=dict)    # key → schema desc

    # ── flags ──
    loaded: bool = False

    def build_context(self, max_chars: int = 8000) -> str:
        """Build a condensed LLM context string from all loaded materials.

        Priority order: design doc > requirements doc > framework doc > source
        """
        parts: list[str] = []

        # ── 1. Essential design knowledge (most important for action planning) ──
        if self.design_doc:
            # Extract the page element sections and business rules
            parts.append(self.design_doc)

        # ── 2. Requirements summary ──
        if self.requirements_doc:
            parts.append(self.requirements_doc)

        # ── 3. Framework / overview ──
        if self.framework_doc:
            parts.append(self.framework_doc)

        # ── 4. Source code summary (paths + key structures only, not full code) ──
        if self.source_files:
            src_summary = self._build_source_summary()
            if src_summary:
                parts.append(src_summary)

        context = "\n\n---\n\n".join(parts)
        if len(context) > max_chars:
            # Truncate intelligently: keep design doc + requirements, trim framework
            priority = (self.design_doc or "") + "\n\n---\n\n" + (self.requirements_doc or "")
            remaining = max_chars - len(priority)
            if remaining > 500:
                context = priority + "\n\n---\n\n" + (self.framework_doc or "")[:remaining]
            else:
                context = priority[:max_chars]

        return context

    def build_planner_context(self) -> str:
        """Concise action-oriented reference for the Planner. ~600 chars."""
        lines: list[str] = []

        # ── Page routes with form instructions ──
        if self.page_routes:
            lines.append("Pages:")
            for route in self.page_routes:
                role = self.page_roles.get(route, "?")
                hint = ""
                if "join" in route:
                    hint = " -> FILL: name, phone, intro -> click save"
                elif "product_edit" in route:
                    hint = " -> FILL: title, price, desc -> click save"
                elif "detail" in route:
                    hint = " -> click star(fav), +/- qty, add to cart, type comment, submit comment"
                elif "cart" in route:
                    hint = " -> click +/-, remove, clear"
                elif "user" in route:
                    hint = " -> click edit/delete on products, click favorites"
                elif "index" in route:
                    hint = " -> click product cards, star(fav), cart icon, create merchant btn, upload product btn"
                lines.append(f"- {route} [{role}]{hint}")

        # ── Toast messages (condensed) ──
        if self.toast_messages:
            toasts = list(self.toast_messages.keys())[:8]
            lines.append(f"Toasts: {', '.join(toasts)}")

        # ── Key business rules ──
        lines.append("Rules: 1 merchant only; product needs merchant; phone=11 digits optional; price>0 required; cart qty 1-999; delete cascades to cart/fav/comments")

        return "\n".join(lines)

    def _build_source_summary(self) -> str:
        """Build a compressed summary of source files."""
        lines = ["## Source Code Summary"]
        for path, content in sorted(self.source_files.items()):
            # Only include key structural info, not full code
            line_count = content.count('\n') + 1
            has_page = 'Page({' in content
            has_app = 'App({' in content
            tags = []
            if has_app: tags.append("App")
            if has_page: tags.append("Page")
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"- {path} ({line_count} lines){tag_str}")
        return "\n".join(lines)


def load_world_model(source_path: str | Path) -> WorldModel:
    """Load all initialization materials for the mini program at source_path.

    Looks for:
      - FRAMEWORK.md
      - REQUIREMENTS.md (optional)
      - DESIGN.md (optional)
      - src/**/*.{js,json,wxml,wxss} (source files)

    Returns a WorldModel ready for Agent initialization.
    """
    source = Path(source_path).resolve()
    wm = WorldModel(source_path=str(source))

    # ── documents ──
    for name, attr in [("FRAMEWORK.md", "framework_doc"),
                        ("REQUIREMENTS.md", "requirements_doc"),
                        ("DESIGN.md", "design_doc")]:
        doc_path = source / name
        if doc_path.exists():
            setattr(wm, attr, doc_path.read_text(encoding="utf-8"))
            logger.info("Loaded %s (%d chars)", name, len(getattr(wm, attr)))

    # ── source code (js, json, wxml) ──
    src_dir = source / "src"
    if src_dir.exists():
        for pattern in ["*.js", "*.json", "*.wxml"]:
            for f in sorted(src_dir.rglob(pattern)):
                if "node_modules" in str(f):
                    continue
                rel = str(f.relative_to(src_dir)).replace("\\", "/")
                try:
                    content = f.read_text(encoding="utf-8")
                    wm.source_files[rel] = content
                except Exception:
                    pass
        logger.info("Loaded %d source files", len(wm.source_files))

    # ── derived knowledge ──
    _derive_knowledge(wm)

    wm.loaded = True
    return wm


def _derive_knowledge(wm: WorldModel) -> None:
    """Extract structured knowledge from loaded documents."""
    import re

    # ── page routes from app.json ──
    app_json = wm.source_files.get("app.json", "")
    if app_json:
        try:
            data = json.loads(app_json)
            wm.page_routes = [f"/{p}" for p in data.get("pages", [])]
        except json.JSONDecodeError:
            pass

    # ── page roles from DESIGN.md ──
    for route in wm.page_routes:
        if "index" in route:
            wm.page_roles[route] = "home"
        elif "join" in route:
            wm.page_roles[route] = "form (merchant)"
        elif "product_edit" in route:
            wm.page_roles[route] = "form (product)"
        elif "detail" in route:
            wm.page_roles[route] = "detail"
        elif "cart" in route:
            wm.page_roles[route] = "cart"
        elif "user" in route:
            wm.page_roles[route] = "profile"
        else:
            wm.page_roles[route] = "unknown"

    # ── storage keys from app.js ──
    app_js = wm.source_files.get("app.js", "")
    wm.storage_keys = re.findall(r"'(merchant_v1|products_v1|cart_v1|favorites_v1|comments_v1)'", app_js)
    wm.storage_keys = sorted(set(wm.storage_keys))

    # ── toast messages from source ──
    toast_pattern = re.compile(r"wx\.showToast\(\{\s*title:\s*'([^']+)'")
    for content in wm.source_files.values():
        for match in toast_pattern.finditer(content):
            msg = match.group(1)
            if msg not in wm.toast_messages:
                wm.toast_messages[msg] = msg

    # ── data schemas from DESIGN.md ──
    design = wm.design_doc
    if design:
        for key in wm.storage_keys:
            # Find schema in design doc
            pattern = rf'### \d+\.\d+.*?\n.*?{key}'
            m = re.search(pattern, design, re.IGNORECASE)
            if m:
                wm.data_schemas[key] = m.group(0)[:200]
