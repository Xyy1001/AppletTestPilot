"""
Setup functions — inject seed data into the mini program via evaluate_js.
Each function creates a specific data state using wx.setStorageSync calls.
"""

import logging

logger = logging.getLogger(__name__)

# Storage keys matching TestApplet's data model
MERCHANT_KEY = "merchant_v1"
PRODUCTS_KEY = "products_v1"
CART_KEY = "cart_v1"
FAVORITES_KEY = "favorites_v1"
COMMENTS_KEY = "comments_v1"

# Default test merchant
DEFAULT_MERCHANT = {
    "id": "m_test_001",
    "name": "测试商家旗舰店",
    "phone": "13800138000",
    "intro": "这是一个测试商家，用于自动化测试",
    "createdAt": "2025-01-01T00:00:00.000Z",
}

# Default test product
DEFAULT_PRODUCT = {
    "id": "p_test_001",
    "merchantId": "m_test_001",
    "title": "高性能机械键盘",
    "price": 299.00,
    "description": "Cherry MX 青轴，RGB 背光，87 键",
    "images": [],
    "createdAt": "2025-01-01T00:00:00.000Z",
}


def _set_storage(mini, key, value):
    """Helper to set storage via evaluate_js."""
    import json
    js = f"""
    wx.setStorageSync('{key}', {json.dumps(value, ensure_ascii=False)});
    """
    app = getattr(mini, "app", None)
    if app and hasattr(app, "evaluate_js"):
        app.evaluate_js(js)
    elif hasattr(mini, "evaluate_js"):
        mini.evaluate_js(js)
    logger.info("Set storage: %s", key)


def _clear_storage(mini, key):
    js = f"wx.removeStorageSync('{key}');"
    app = getattr(mini, "app", None)
    if app and hasattr(app, "evaluate_js"):
        app.evaluate_js(js)
    elif hasattr(mini, "evaluate_js"):
        mini.evaluate_js(js)


def launch_home(mini):
    """Fresh start — clear all storage."""
    for key in (MERCHANT_KEY, PRODUCTS_KEY, CART_KEY, FAVORITES_KEY, COMMENTS_KEY):
        _clear_storage(mini, key)
    logger.info("Setup: launch_home — fresh start")


def launch_home_with_merchant(mini):
    """Merchant already exists."""
    _set_storage(mini, MERCHANT_KEY, DEFAULT_MERCHANT)
    _clear_storage(mini, PRODUCTS_KEY)
    _clear_storage(mini, CART_KEY)
    _clear_storage(mini, FAVORITES_KEY)
    _clear_storage(mini, COMMENTS_KEY)
    logger.info("Setup: launch_home_with_merchant")


def launch_home_with_merchant_and_product(mini):
    """Merchant + 1 product exist."""
    _set_storage(mini, MERCHANT_KEY, DEFAULT_MERCHANT)
    _set_storage(mini, PRODUCTS_KEY, [DEFAULT_PRODUCT])
    _clear_storage(mini, CART_KEY)
    _clear_storage(mini, FAVORITES_KEY)
    _clear_storage(mini, COMMENTS_KEY)
    logger.info("Setup: launch_home_with_merchant_and_product")


def launch_home_with_merchant_and_product_in_cart(mini):
    """Merchant + product + 1 item in cart."""
    _set_storage(mini, MERCHANT_KEY, DEFAULT_MERCHANT)
    _set_storage(mini, PRODUCTS_KEY, [DEFAULT_PRODUCT])
    _set_storage(mini, CART_KEY, [{"productId": "p_test_001", "quantity": 2}])
    _clear_storage(mini, FAVORITES_KEY)
    _clear_storage(mini, COMMENTS_KEY)
    logger.info("Setup: launch_home_with_merchant_and_product_in_cart")
