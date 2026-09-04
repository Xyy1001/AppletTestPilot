const app = getApp();

const SPARK_COLORS = ['#F97316','#22D3EE','#7C3AED','#F43F5E','#22C55E','#FBBF24','#EC4899','#8B5CF6'];

Page({
  data: {
    products: [],
    favorites: {},
    merchant: null,
    _tapFx: null
  },

  _tap(e) { app.tapFeedback(e); },

  _showTapFx(x, y) {
    const sparks = SPARK_COLORS.map((c, i) => ({
      id: 's' + i, c, d: (i * 0.03).toFixed(2)
    }));
    this.setData({ _tapFx: { x, y, sparks } });
    setTimeout(() => { this.setData({ _tapFx: null }); }, 500);
  },

  onLoad() {
    this.refresh();
  },

  onShow() {
    this.refresh();
  },

  onPullDownRefresh() {
    this.refresh();
    wx.stopPullDownRefresh();
  },

  refresh() {
    const products = app.getProducts();
    const favorites = app.getFavorites();
    const merchant = app.getMerchant();
    this.setData({ products, favorites, merchant });
  },

  onTapProduct(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/product/detail?id=${id}` });
  },

  onToggleFavorite(e) {
    const id = e.currentTarget.dataset.id;
    app.toggleFavorite(id);
    this.setData({ favorites: app.getFavorites() });
  },

  onAddToCart(e) {
    const id = e.currentTarget.dataset.id;
    app.addToCart(id, 1);
    wx.showToast({ title: '已加入购物车', icon: 'success' });
  },

  onGoCreateMerchant() {
    wx.navigateTo({ url: '/pages/vendor/join' });
  },

  onGoUpload() {
    wx.navigateTo({ url: '/pages/vendor/product_edit' });
  }
});

