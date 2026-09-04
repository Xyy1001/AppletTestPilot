const app = getApp();

const SPARK_COLORS = ['#F97316','#22D3EE','#7C3AED','#F43F5E','#22C55E','#FBBF24','#EC4899','#8B5CF6'];

Page({
  data: {
    name: '',
    phone: '',
    intro: '',
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
    const merchant = app.getMerchant();
    if (merchant) {
      this.setData({
        name: merchant.name || '',
        phone: merchant.phone || '',
        intro: merchant.intro || ''
      });
    }
  },

  onName(e) {
    this.setData({ name: e.detail.value });
  },

  onPhone(e) {
    this.setData({ phone: e.detail.value });
  },

  onIntro(e) {
    this.setData({ intro: e.detail.value });
  },

  onSave() {
    const name = (this.data.name || '').trim();
    const phone = (this.data.phone || '').trim();
    const intro = (this.data.intro || '').trim();

    if (!name) {
      wx.showToast({ title: '请输入商家名称', icon: 'none' });
      return;
    }
    if (phone && !/^\d{11}$/.test(phone)) {
      wx.showToast({ title: '手机号需为11位数字', icon: 'none' });
      return;
    }

    const existing = app.getMerchant();
    const merchant = {
      id: existing ? existing.id : app.uid('m'),
      name,
      phone,
      intro,
      updatedAt: Date.now()
    };
    if (!existing) {
      merchant.createdAt = Date.now();
    } else {
      merchant.createdAt = existing.createdAt;
    }

    app.setMerchant(merchant);
    wx.showToast({ title: '已保存', icon: 'success' });
    setTimeout(() => {
      wx.navigateBack();
    }, 300);
  }
});

