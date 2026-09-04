const app = getApp();

const SPARK_COLORS = ['#F97316','#22D3EE','#7C3AED','#F43F5E','#22C55E','#FBBF24','#EC4899','#8B5CF6'];

Page({
  data: {
    id: '',
    title: '',
    price: '',
    desc: '',
    images: [],
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
    const merchant = app.getMerchant();
    if (!merchant) {
      wx.showModal({
        title: '提示',
        content: '请先创建商家账户',
        showCancel: false,
        success: () => wx.navigateTo({ url: '/pages/vendor/join' })
      });
      return;
    }

    const id = options.id || '';
    if (id) {
      const product = app.getProductById(id);
      if (product) {
        this.setData({
          id: String(product.id),
          title: product.title || '',
          price: String(product.price || ''),
          desc: product.desc || '',
          images: product.images || []
        });
        wx.setNavigationBarTitle({ title: '编辑产品' });
      }
    }
  },

  onTitle(e) {
    this.setData({ title: e.detail.value });
  },

  onPrice(e) {
    this.setData({ price: e.detail.value });
  },

  onDesc(e) {
    this.setData({ desc: e.detail.value });
  },

  onChooseImages() {
    wx.chooseMedia({
      count: 6,
      mediaType: ['image'],
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const tempFiles = res.tempFiles || [];
        const paths = tempFiles.map((f) => f.tempFilePath).filter(Boolean);
        if (paths.length === 0) return;
        this.saveTempFiles(paths);
      }
    });
  },

  saveTempFiles(paths) {
    const saved = [];
    const next = (i) => {
      if (i >= paths.length) {
        this.setData({ images: this.data.images.concat(saved) });
        return;
      }
      wx.saveFile({
        tempFilePath: paths[i],
        success: (r) => {
          if (r && r.savedFilePath) {
            saved.push(r.savedFilePath);
          }
          next(i + 1);
        },
        fail: () => next(i + 1)
      });
    };
    next(0);
  },

  onRemoveImage(e) {
    const idx = Number(e.currentTarget.dataset.idx);
    const images = this.data.images.filter((_, i) => i !== idx);
    this.setData({ images });
  },

  onSave() {
    const merchant = app.getMerchant();
    if (!merchant) {
      wx.showToast({ title: '请先创建商家账户', icon: 'none' });
      return;
    }

    const title = (this.data.title || '').trim();
    const desc = (this.data.desc || '').trim();
    const priceNum = Number(this.data.price);

    if (!title) {
      wx.showToast({ title: '请输入产品名称', icon: 'none' });
      return;
    }
    if (!Number.isFinite(priceNum) || priceNum <= 0) {
      wx.showToast({ title: '请输入正确价格', icon: 'none' });
      return;
    }

    const product = {
      id: this.data.id ? this.data.id : app.uid('p'),
      merchantId: merchant.id,
      title,
      desc,
      price: Number(priceNum.toFixed(2)),
      images: this.data.images || []
    };

    app.upsertProduct(product);
    wx.showToast({ title: '已保存', icon: 'success' });
    setTimeout(() => {
      wx.navigateBack();
    }, 300);
  }
});

