"""
Benchmark — standardized task definitions and evaluation metrics.

Defines testing tasks as structured ``BenchmarkTask`` objects so experiments
are reproducible and comparable across Agent versions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskDifficulty(str, Enum):
    EASY = "easy"           # ≤ 4 steps, single page
    MEDIUM = "medium"       # 5-8 steps, 2-3 pages
    HARD = "hard"           # ≥ 9 steps, multi-page flow


@dataclass
class BenchmarkTask:
    """A single benchmark task definition."""
    id: str
    name: str
    description: str
    setup_function: str = "launch_home"
    difficulty: TaskDifficulty = TaskDifficulty.MEDIUM
    min_steps: int = 3
    max_steps: int = 15
    expected_pages: list[str] = field(default_factory=list)
    expected_actions: list[str] = field(default_factory=list)
    bug_injection_target: Optional[str] = None  # step to inject bug on


# ── Standard benchmark task set ────────────────────────────────────────

STANDARD_TASKS: list[BenchmarkTask] = [
    BenchmarkTask(
        id="create_merchant",
        name="Create Merchant Account",
        description="From home page, navigate to vendor join page, fill in merchant details (name, phone, intro), and save. Verify success toast and navigation back.",
        setup_function="launch_home",
        difficulty=TaskDifficulty.EASY,
        min_steps=4, max_steps=8,
        expected_pages=["/pages/index/index", "/pages/vendor/join"],
        expected_actions=["Click", "Type", "Click"],
        bug_injection_target="onSave",
    ),
    BenchmarkTask(
        id="upload_product",
        name="Upload Product",
        description="With an existing merchant, navigate to product edit page, fill in product details (name, price, description), and save.",
        setup_function="launch_home_with_merchant",
        difficulty=TaskDifficulty.EASY,
        min_steps=4, max_steps=10,
        expected_pages=["/pages/index/index", "/pages/vendor/product_edit"],
        expected_actions=["Click", "Type", "Click"],
        bug_injection_target="onSave",
    ),
    BenchmarkTask(
        id="add_to_cart",
        name="Add to Cart",
        description="Browse a product, navigate to detail, increase quantity, and add to cart.",
        setup_function="launch_home_with_merchant_and_product",
        difficulty=TaskDifficulty.MEDIUM,
        min_steps=3, max_steps=8,
        expected_pages=["/pages/index/index", "/pages/product/detail"],
        expected_actions=["Click", "Click", "Click"],
        bug_injection_target="onAddToCart",
    ),
    BenchmarkTask(
        id="toggle_favorite",
        name="Toggle Favorite",
        description="Navigate to product detail, toggle the favorite star, verify state changes.",
        setup_function="launch_home_with_merchant_and_product",
        difficulty=TaskDifficulty.EASY,
        min_steps=2, max_steps=5,
        expected_pages=["/pages/index/index", "/pages/product/detail"],
        expected_actions=["Click", "Click"],
    ),
    BenchmarkTask(
        id="submit_comment",
        name="Submit Comment",
        description="Navigate to product detail, type a comment, submit, verify it appears in the comment list.",
        setup_function="launch_home_with_merchant_and_product",
        difficulty=TaskDifficulty.MEDIUM,
        min_steps=3, max_steps=8,
        expected_pages=["/pages/index/index", "/pages/product/detail"],
        expected_actions=["Click", "Type", "Click"],
        bug_injection_target="onSubmitComment",
    ),
    BenchmarkTask(
        id="delete_product",
        name="Delete Product",
        description="Navigate to user center, find a product, delete it via confirmation modal.",
        setup_function="launch_home_with_merchant_and_product",
        difficulty=TaskDifficulty.MEDIUM,
        min_steps=4, max_steps=10,
        expected_pages=["/pages/index/index", "/pages/tabbar/user"],
        expected_actions=["Switch to", "Click", "Click"],
        bug_injection_target="onDeleteProduct",
    ),
    BenchmarkTask(
        id="edit_product",
        name="Edit Product",
        description="Edit an existing product: change name, price, and save.",
        setup_function="launch_home_with_merchant_and_product",
        difficulty=TaskDifficulty.MEDIUM,
        min_steps=4, max_steps=10,
        expected_pages=["/pages/index/index", "/pages/tabbar/user", "/pages/vendor/product_edit"],
        expected_actions=["Switch to", "Click", "Type", "Click"],
    ),
    BenchmarkTask(
        id="clear_cart",
        name="Clear Cart",
        description="With items in cart, navigate to cart page and clear all items.",
        setup_function="launch_home_with_merchant_and_product_in_cart",
        difficulty=TaskDifficulty.EASY,
        min_steps=2, max_steps=5,
        expected_pages=["/pages/cart/cart"],
        expected_actions=["Switch to", "Click"],
    ),
    BenchmarkTask(
        id="full_flow",
        name="Full E-Commerce Flow",
        description="Complete end-to-end: create merchant → upload product → view detail → add to cart → view cart → clear cart.",
        setup_function="launch_home",
        difficulty=TaskDifficulty.HARD,
        min_steps=12, max_steps=30,
        expected_pages=[
            "/pages/index/index", "/pages/vendor/join",
            "/pages/vendor/product_edit", "/pages/product/detail",
            "/pages/cart/cart",
        ],
        expected_actions=["Click", "Type", "Switch to"],
    ),
]
