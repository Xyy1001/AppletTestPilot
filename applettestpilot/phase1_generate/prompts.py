"""
Phase 1 — Prompt templates for exploration-based test case generation.
"""

# ── Test Plan: LLM analyzes FRAMEWORK.md → feature-level plan ──

PLAN_SYSTEM = """\
Plan end-to-end tests for a WeChat Mini Program. Every test MUST be complete from start to verification.
Output ONLY a JSON array. Each item:
{"feature":"name","goal":"what this test verifies end-to-end","setup":"launch_home|launch_home_with_merchant|launch_home_with_merchant_and_product|launch_home_with_merchant_and_product_in_cart","depends_on":"merchant|product|cart|","must_include":"step-by-step required actions"}

CRITICAL RULES for EVERY feature:
1. EVERY form MUST end with clicking the save/submit button (保存/保存产品/发布评论/加入购物车)
2. EVERY action MUST have a verification step after it
3. After saving, MUST verify the result (navigate to check, or verify toast/redirect)
4. NEVER skip the save/submit step — it is MANDATORY
5. Phone mini programs have NO cursor, NO hover, NO right-click — don't mention these
6. Tab bar uses ICONS (images), not text labels — "Switch to '购物车'" targets the cart icon

Feature templates (MUST follow these exact required steps):
- Create merchant: Verify home → Click '创建商家'/'去创建商家' → Fill 商家名称 → Fill 手机号 → Fill 简介 → Click '保存' MUST HAPPEN → Verify navigated home → Switch to '我的' → Verify merchant info visible
- Upload product: Verify home → Click '上传产品' → Fill 产品名称 → Fill 价格 → Fill 描述 → Click '保存产品' MUST HAPPEN → Verify navigated home → Verify product card visible → Switch to '我的' → Verify in product list
- Add to cart: Verify home → Click product card → Click '加入购物车' MUST HAPPEN → Switch to '购物车' → Verify product in cart with correct info
- Delete product: Switch to '我的' → Scroll down if needed → Scroll to '<product name>' → Verify product exists → Click '删除' → Click '确定' MUST HAPPEN → Verify product removed → Switch to '首页' → Verify gone from home

Standard features (pick uncovered ones in dependency order):
[{"feature":"Create merchant","goal":"Complete merchant creation with save and verification","setup":"launch_home","depends_on":"","must_include":"Verify home→Click create→Fill all 3 fields→Click save→Verify home→Switch to 我的→Verify name+phone"},
 {"feature":"Upload product","goal":"Complete product upload with save and verification","setup":"launch_home_with_merchant","depends_on":"merchant","must_include":"Verify home→Click upload→Fill all 3 fields→Click save product→Verify home→Verify card→Switch to 我的→Verify list"},
 {"feature":"Add to cart","goal":"Add product to cart and verify in cart tab","setup":"launch_home_with_merchant_and_product","depends_on":"product","must_include":"Verify home→Click product→Click add to cart→Switch to 购物车→Verify item+price"},
 {"feature":"Delete product","goal":"Delete product and verify removal everywhere","setup":"launch_home_with_merchant_and_product","depends_on":"product","must_include":"Switch to 我的→Scroll down if needed→Scroll to product→Verify exists→Click delete→Click confirm→Verify removed→Switch to 首页→Verify gone"}]
"""

# ── Step Proposal: LLM generates ALL steps for one feature ──

PROPOSE_SYSTEM = """\
You are generating a COMPLETE test case for a WeChat Mini Program feature.
Output ALL steps at once as a JSON array. Each step: {"action":"...", "expectation":"..."}

# MANDATORY RULES for EVERY test case
1. MUST include Click save/submit button (保存/保存产品/加入购物车/发布评论) — NEVER skip this
2. MUST include at least ONE verification step after save (Switch to tab / Verify page state)
3. MUST cover the feature end-to-end: navigate → fill → save → verify
4. This is a MOBILE mini program: no cursor, no hover, no right-click

# Action verbs
- Click 'button text'
- Type 'value' into 'field label'
- Switch to 'tab name' (首页/购物车/我的)
- Verify page state
- Go back
- Scroll down / Scroll up — scroll the current page by ~half screen
- Scroll to '<text>' — scroll until the specified text/element is visible

# Step-by-step templates (MUST follow these patterns exactly)
Create merchant: Verify home→Click '创建商家'→Type name→Type phone→Type intro→Click '保存'→Verify home→Switch to '我的'→Verify merchant visible
Upload product: Verify home→Click '上传产品'→Type title→Type price→Type desc→Click '保存产品'→Verify home→Verify product card→Switch to '我的'→Verify in list
Add to cart: Verify home→Click product card→Click '加入购物车'→Switch to '购物车'→Verify product in cart
Delete (single item visible): Switch to '我的'→Click '删除'→Click '确定'→Verify removed→Switch to '首页'→Verify gone
Delete (need to scroll): Switch to '我的'→Scroll down→Scroll to '<product name>'→Click '删除'→Click '确定'→Verify removed→Switch to '首页'→Verify gone

Output ONLY a JSON array. No explanation.
"""

# ── Step-by-step exploration: LLM proposes ONE action at a time ──

EXPLORE_ACTION = """\
You are exploring a WeChat Mini Program to build a test case step by step.
Based on the current page state (VLM description), feature goal, and what
has already been done, propose the VERY NEXT action to take.

# Mobile context — CRITICAL
- This is a WECHAT MINI PROGRAM on a PHONE. No desktop elements.
- NO cursor, NO mouse, NO hover, NO right-click, NO scrollbar.
- Tab bar uses ICONS at the bottom (home/cart/user), NOT text labels.
- If a button/link is not currently visible, use "Scroll down" or "Scroll to 'text'" first.

# Action verbs
- Verify page state — check current page, no UI interaction
- Click 'button text' — tap a button/link with exact text
- Type 'value' into 'field label' — type text into a form field
- Switch to 'tab name' — switch to a tab (首页/购物车/我的)
- Go back — navigate back to previous page
- Scroll down / Scroll up — scroll the page
- Scroll to 'element text' — scroll until a specific element is visible
- DONE — signal that the feature is fully explored and complete

# Rules
- Propose EXACTLY ONE action. Be specific with exact button/field text.
- After save/submit/delete, ALWAYS propose a verification step next.
- NEVER skip the save/submit button (保存/保存产品/加入购物车/确定/etc).
- If the current page is the target page, verify it; if not, navigate to it.
- Consider what has ALREADY been done (see history) and propose the logical next step.
- If all required actions + verifications are done, output DONE.

# Output format
JSON only with one key "action" and one key "expectation":
{"action": "Click '创建商家'", "expectation": "Navigates to vendor join page"}

When the feature is complete:
{"action": "DONE", "expectation": "Feature fully explored"}
"""

# ── Evaluate: LLM judges whether action + expectation passed ──

EVALUATE_SYSTEM = """\
Evaluate whether the test action succeeded by comparing BEFORE and AFTER page screenshots.

# Evaluation criteria
- Dialog/Modal: if action was "Click '删除'" or similar, a confirmation dialog (e.g. "确认删除" with 确定/取消) SHOULD appear
- Navigation: AFTER page shows the expected page title and content text
- Form typing: the typed text is visible in the field, OR the placeholder text disappeared
- Save/submit: page navigated away OR toast/success message appeared, AND data persisted
- Tab switch: bottom tab bar shows the correct tab as active, page content matches expected tab
- Delete/remove: target element no longer appears on the page
- Failure signs: error toasts, unchanged page, wrong page, missing expected elements

# Mobile context
- This is a WECHAT MINI PROGRAM on a PHONE. No desktop elements.
- Ignore mentions of cursors, mouse pointers, hover effects, scrollbars — they don't exist here.
- Tab bar at bottom uses ICONS, not text.

# Output format
JSON only: {"passed": true/false, "reason": "specific explanation based on what changed", "assertion_code": "python code or empty"}

# Assertion code (when passed=true)
Write a Python function that verifies this step. Use session.history[-1].
- For text visibility: collect e.text from state.elements, check with any()
- For input values: also check e.attributes.get('value','')
- For navigation: check page-specific text (NOT just page_id — it may be stale)
- Example: "def postcondition(session):\\n    state = session.history[-1]\\n    texts = [e.text for e in state.elements.values() if e.text]\\n    assert any('创建商家账户' in t for t in texts)"
"""

# ── VLM describe: concise prompt for exploration ──

VLM_DESCRIBE = """Describe this WeChat Mini Program screenshot concisely:
- Page title and all visible text (exact strings)
- Buttons, form fields, placeholders, input values
- Tab bar: which tab is active? (icons: home/cart/user)
- DIALOGS/MODALS are CRITICAL: if you see a popup dialog (e.g. "确认删除", "确定", "取消"),
  describe its title, message text, and ALL buttons inside it explicitly
- Toast, dialog, or empty state?
Keep under 10 lines. Be specific with exact text."""

# ── Bug generation ──

BUG_SYSTEM = """\
You are an expert at creating JavaScript bug injection scripts for WeChat Mini Programs.
Given a test case, create a bug script that subtly breaks a specific function.

# Rules
- Output ONLY JavaScript code inside ```javascript ... ```
- Must have two functions: isConditionMet() and onConditionMet()
- isConditionMet(): check if on the correct page route via getCurrentPages()
- onConditionMet(): monkey-patch a wx.* or app.* method to subtly alter behavior
- The bug should cause the assertion to FAIL so the agent can detect it
- Use the exact function names and storage keys from the framework doc

# Pattern
```javascript
function isConditionMet() {
    var pages = getCurrentPages();
    return pages.length > 0 && pages[pages.length-1].route === 'PAGE_ROUTE';
}
function onConditionMet() {
    var original = TARGET_FUNCTION;
    TARGET_FUNCTION = function(...) {
        // subtle alteration
        original.apply(this, arguments);
    };
}
```
"""

# ── Fix prompt (when validation fails) ──

FIX_SYSTEM = """\
You are an expert QA engineer fixing a failing test case.
Below is a test case that did NOT achieve 100% PASS and its failure log.

# Your task
Analyze the failures and output ONLY the CORRECTED YAML inside ```yaml ... ```.

# Common fixes
- Fix field/button labels to match exact text from framework doc
- Replace unicode icon symbols with word descriptions (e.g. "Click favorite star")
- Adjust expectations to what the page actually shows
- Remove or reorder broken steps
- Fix setup_function if wrong

# CRITICAL
- The YAML MUST start with "name:" (NOT "- name:")
- Output ONE test case, not a list
- Keep steps SIMPLE (5-8 steps)
"""
