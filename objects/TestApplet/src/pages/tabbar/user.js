const app = getApp();

const SPARK_COLORS = ['#F97316','#22D3EE','#7C3AED','#F43F5E','#22C55E','#FBBF24','#EC4899','#8B5CF6'];

Page({
  data: {
    merchant: null,
    myProducts: [],
    favorites: [],
    favoritesMap: {},
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

  onShow() {
    this.refresh();
  },

  refresh() {
    const merchant = app.getMerchant();
    const products = app.getProducts();
    const favoritesMap = app.getFavorites();
    const favorites = products.filter((p) => favoritesMap[String(p.id)]);
    const myProducts = merchant ? products.filter((p) => String(p.merchantId) === String(merchant.id)) : [];
    this.setData({ merchant, favorites, favoritesMap, myProducts });
  },

  onCreateMerchant() {
    wx.navigateTo({ url: '/pages/vendor/join' });
  },

  onUploadProduct() {
    wx.navigateTo({ url: '/pages/vendor/product_edit' });
  },

  onEditProduct(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/vendor/product_edit?id=${id}` });
  },

  onDeleteProduct(e) {
    const id = e.currentTarget.dataset.id;
    wx.showModal({
      title: '删除商品',
      content: '确定删除该商品吗？',
      success: (res) => {
        if (!res.confirm) return;
        app.deleteProduct(id);
        this.refresh();
        wx.showToast({ title: '已删除', icon: 'success' });
      }
    });
  },

  onTapFavorite(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/product/detail?id=${id}` });
  },

  onSupport() {
    app.showSupportActions();
  }
});

