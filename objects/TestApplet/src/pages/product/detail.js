const app = getApp();

const SPARK_COLORS = ['#F97316','#22D3EE','#7C3AED','#F43F5E','#22C55E','#FBBF24','#EC4899','#8B5CF6'];

Page({
  data: {
    productId: '',
    product: null,
    favorites: {},
    qty: 1,
    commentText: '',
    comments: [],
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

  onLoad(options) {
    const id = options.id || options.productid || '';
    this.setData({ productId: id });
    this.refresh();
  },

  onShow() {
    this.refresh();
  },

  refresh() {
    const product = app.getProductById(this.data.productId);
    const favorites = app.getFavorites();
    const comments = app.getComments(this.data.productId).map((c) => ({
      ...c,
      createdAtText: this.formatTime(c.createdAt)
    }));
    this.setData({ product, favorites, comments });
  },

  formatTime(ts) {
    if (!ts) return '';
    const d = new Date(ts);
    const pad = (n) => (n < 10 ? `0${n}` : `${n}`);
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
  },

  onToggleFavorite() {
    app.toggleFavorite(this.data.productId);
    this.setData({ favorites: app.getFavorites() });
  },

  onMinusQty() {
    const next = Math.max(1, Number(this.data.qty) - 1);
    this.setData({ qty: next });
  },

  onPlusQty() {
    const next = Math.min(999, Number(this.data.qty) + 1);
    this.setData({ qty: next });
  },

  onAddToCart() {
    app.addToCart(this.data.productId, this.data.qty);
    wx.showToast({ title: '已加入购物车', icon: 'success' });
  },

  onCommentInput(e) {
    this.setData({ commentText: e.detail.value });
  },

  onSubmitComment() {
    const text = (this.data.commentText || '').trim();
    if (!text) {
      wx.showToast({ title: '请输入评论内容', icon: 'none' });
      return;
    }
    app.addComment(this.data.productId, {
      userName: '访客',
      content: text
    });
    this.setData({ commentText: '' });
    this.refresh();
    wx.showToast({ title: '已发布', icon: 'success' });
  }
});
