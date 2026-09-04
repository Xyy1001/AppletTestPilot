App({
  globalData: {
    appName: '商城运营和推广SEO',
    theme: {
      bg: '#0B0F1A',
      surface: '#0F172A',
      card: '#111C33',
      primary: '#7C3AED',
      secondary: '#22D3EE',
      accent: '#F97316',
      danger: '#F43F5E',
      success: '#22C55E',
      text: '#F8FAFC',
      muted: '#94A3B8',
      border: 'rgba(148, 163, 184, 0.22)'
    },
    support: {
      phone: '',
      wechat: '',
      email: ''
    }
  },

  onLaunch() {
    this.ensureStorageInitialized();
  },

  /**
   * Lightweight storage init — only fills in missing keys with empty defaults.
   * No demo data is seeded here; the test harness (setup_functions) injects
   * the required pre-conditions for each test case.
   */
  ensureStorageInitialized() {
    if (wx.getStorageSync('products_v1') === '') wx.setStorageSync('products_v1', []);
    if (wx.getStorageSync('favorites_v1') === '') wx.setStorageSync('favorites_v1', {});
    if (wx.getStorageSync('cart_v1') === '') wx.setStorageSync('cart_v1', {});
    if (wx.getStorageSync('comments_v1') === '') wx.setStorageSync('comments_v1', {});
  },

  /**
   * Global tap visual feedback — safe to call from any page's _tap handler.
   */
  tapFeedback(e) {
    if (!e) return;
    try {
      let x, y;
      if (e.detail && typeof e.detail.x !== 'undefined') {
        x = e.detail.x; y = e.detail.y;
      } else if (e.changedTouches && e.changedTouches[0]) {
        x = e.changedTouches[0].x || e.changedTouches[0].clientX;
        y = e.changedTouches[0].y || e.changedTouches[0].clientY;
      }
      if (typeof x === 'undefined') return;
      const pages = getCurrentPages();
      if (!pages || pages.length === 0) return;
      const page = pages[pages.length - 1];
      if (!page || typeof page._showTapFx !== 'function') return;
      page._showTapFx(x, y);
    } catch (_) {
      // ignore taps during page transitions / startup
    }
  },

  uid(prefix) {
    const p = prefix || 'id';
    return `${p}_${Date.now()}_${Math.floor(Math.random() * 1e6)}`;
  },

  getMerchant() {
    return wx.getStorageSync('merchant_v1') || null;
  },

  setMerchant(merchant) {
    wx.setStorageSync('merchant_v1', merchant || null);
  },

  getProducts() {
    return wx.getStorageSync('products_v1') || [];
  },

  getProductById(productId) {
    const list = this.getProducts();
    return list.find((p) => String(p.id) === String(productId)) || null;
  },

  upsertProduct(product) {
    const list = this.getProducts();
    const idx = list.findIndex((p) => String(p.id) === String(product.id));
    if (idx >= 0) {
      list[idx] = { ...list[idx], ...product, updatedAt: Date.now() };
    } else {
      list.unshift({ ...product, createdAt: Date.now(), updatedAt: Date.now() });
    }
    wx.setStorageSync('products_v1', list);
    return list;
  },

  deleteProduct(productId) {
    const list = this.getProducts().filter((p) => String(p.id) !== String(productId));
    wx.setStorageSync('products_v1', list);
    const cart = this.getCart();
    if (cart[productId]) {
      delete cart[productId];
      wx.setStorageSync('cart_v1', cart);
    }
    const fav = this.getFavorites();
    if (fav[productId]) {
      delete fav[productId];
      wx.setStorageSync('favorites_v1', fav);
    }
    return list;
  },

  getFavorites() {
    return wx.getStorageSync('favorites_v1') || {};
  },

  isFavorite(productId) {
    const fav = this.getFavorites();
    return !!fav[String(productId)];
  },

  toggleFavorite(productId) {
    const fav = this.getFavorites();
    const key = String(productId);
    if (fav[key]) {
      delete fav[key];
    } else {
      fav[key] = 1;
    }
    wx.setStorageSync('favorites_v1', fav);
    return fav;
  },

  getCart() {
    return wx.getStorageSync('cart_v1') || {};
  },

  setCart(cart) {
    wx.setStorageSync('cart_v1', cart || {});
  },

  addToCart(productId, qty) {
    const cart = this.getCart();
    const key = String(productId);
    const add = Number(qty || 1);
    const next = (Number(cart[key] || 0) + add);
    cart[key] = Math.max(1, next);
    this.setCart(cart);
    return cart;
  },

  setCartQty(productId, qty) {
    const cart = this.getCart();
    const key = String(productId);
    const next = Number(qty || 0);
    if (next <= 0) {
      delete cart[key];
    } else {
      cart[key] = next;
    }
    this.setCart(cart);
    return cart;
  },

  getCartItemsDetailed() {
    const cart = this.getCart();
    const products = this.getProducts();
    const items = [];
    Object.keys(cart).forEach((productId) => {
      const product = products.find((p) => String(p.id) === String(productId));
      if (!product) {
        return;
      }
      const qty = Number(cart[productId] || 0);
      if (qty <= 0) {
        return;
      }
      const price = Number(product.price || 0);
      items.push({
        productId: product.id,
        title: product.title,
        price,
        cover: (product.images && product.images[0]) ? product.images[0] : '',
        qty,
        subtotal: Number((price * qty).toFixed(2))
      });
    });
    const total = items.reduce((sum, it) => sum + it.subtotal, 0);
    return { items, total: Number(total.toFixed(2)) };
  },

  getCommentsMap() {
    return wx.getStorageSync('comments_v1') || {};
  },

  getComments(productId) {
    const map = this.getCommentsMap();
    return map[String(productId)] || [];
  },

  addComment(productId, comment) {
    const map = this.getCommentsMap();
    const key = String(productId);
    const list = map[key] || [];
    list.unshift({ ...comment, id: this.uid('c'), createdAt: Date.now() });
    map[key] = list;
    wx.setStorageSync('comments_v1', map);
    return list;
  },

  showSupportActions() {
    const { phone, wechat, email } = this.globalData.support || {};
    const actions = [];
    const map = [];
    if (phone) {
      actions.push(`拨打电话 ${phone}`);
      map.push({ type: 'phone', value: phone });
    }
    if (wechat) {
      actions.push(`复制微信 ${wechat}`);
      map.push({ type: 'wechat', value: wechat });
    }
    if (email) {
      actions.push(`复制邮箱 ${email}`);
      map.push({ type: 'email', value: email });
    }
    if (actions.length === 0) {
      wx.showToast({ title: '未配置客服信息', icon: 'none' });
      return;
    }
    wx.showActionSheet({
      itemList: actions,
      success: (res) => {
        const pick = map[res.tapIndex];
        if (!pick) return;
        if (pick.type === 'phone') {
          wx.makePhoneCall({ phoneNumber: pick.value });
          return;
        }
        wx.setClipboardData({ data: pick.value });
      }
    });
  }
});

