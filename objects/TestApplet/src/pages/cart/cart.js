const app = getApp();

const SPARK_COLORS = ['#F97316','#22D3EE','#7C3AED','#F43F5E','#22C55E','#FBBF24','#EC4899','#8B5CF6'];

Page({
  data: {
    items: [],
    total: 0,
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
    const { items, total } = app.getCartItemsDetailed();
    this.setData({ items, total });
  },

  onTapProduct(e) {
    const id = e.currentTarget.dataset.id;
    wx.navigateTo({ url: `/pages/product/detail?id=${id}` });
  },

  onMinus(e) {
    const id = e.currentTarget.dataset.id;
    const cur = this.data.items.find((it) => String(it.productId) === String(id));
    if (!cur) return;
    app.setCartQty(id, cur.qty - 1);
    this.refresh();
  },

  onPlus(e) {
    const id = e.currentTarget.dataset.id;
    const cur = this.data.items.find((it) => String(it.productId) === String(id));
    if (!cur) return;
    app.setCartQty(id, cur.qty + 1);
    this.refresh();
  },

  onRemove(e) {
    const id = e.currentTarget.dataset.id;
    app.setCartQty(id, 0);
    this.refresh();
  },

  onClear() {
    app.setCart({});
    this.refresh();
  }
});

