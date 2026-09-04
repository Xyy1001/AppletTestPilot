# TestApplet 设计文档

> 本文档描述 TestApplet 的技术架构、组件树、数据流和交互契约，供 Agent 精确理解每个页面的元素布局和操作方式。

---

## 1. 技术栈

| 层 | 技术 |
|----|------|
| 视图层 | WXML + WXSS（暗色主题） |
| 逻辑层 | JavaScript (ES6, Page/App 实例) |
| 数据层 | `wx.Storage` (StorageSync API) |
| 导航 | `wx.navigateTo` / `wx.navigateBack` / `wx.switchTab` |
| 基础库 | 3.5.0+ |
| AppID | (无 — 本地离线模式) |

---

## 2. 页面路由与导航图

```
                    ┌─────────────────┐
          ┌─────────│  /pages/index   │──────────┐
          │         │    (首页 Tab)    │          │
          │         └───────┬─────────┘          │
          │ navigateTo      │ navigateTo          │ switchTab
          ▼                 ▼                     │
  ┌───────────────┐  ┌──────────────────┐        │
  │ /vendor/join  │  │ /product/detail  │        │
  │  (创建商家)    │  │   (商品详情)      │        │
  └───────┬───────┘  └────────┬─────────┘        │
          │ navigateBack      │                   │
          └──────────┬────────┘                   │
                     ▼                            ▼
              ┌──────────────┐          ┌──────────────────┐
              │ 返回上一页     │          │ /pages/cart/cart │
              └──────────────┘          │   (购物车 Tab)    │
                                        └──────────────────┘

  ┌──────────────────┐          ┌──────────────────┐
  │ /vendor/         │          │ /pages/tabbar/   │
  │   product_edit   │◄─────────│     user          │
  │   (上传/编辑产品) │navigateTo│   (我的 Tab)       │
  └──────────────────┘          └──────────────────┘
```

---

## 3. 各页面元素清单（Agent 操作参考）

### 3.1 首页 — `/pages/index/index`

**页面角色**: home | **Tab 页**: 是 | **需要商家**: 否

#### 无商家时 (merchant == null)

| 元素 | 类型 | 文本/标识 | 操作 | 触发事件 |
|------|------|----------|------|---------|
| 页面标题 | text | "商品展示" | — | — |
| 副标题 | text | "本地数据模式，无需联网" | — | — |
| 创建商家按钮 | button | "创建商家" | Click | `onGoCreateMerchant` → `/pages/vendor/join` |
| 空态标题 | text | "暂无商品" | — | — |
| 引导文案 | text | "先在\"我的\"里创建商家账户并上传产品" | — | — |
| 去创建商家按钮 | button | "去创建商家" | Click | `onGoCreateMerchant` → `/pages/vendor/join` |

#### 有商家 + 无产品时 (merchant != null, products.length == 0)

| 元素 | 类型 | 文本/标识 | 操作 |
|------|------|----------|------|
| 上传产品按钮 | button | "上传产品" | Click → `/pages/vendor/product_edit` |
| 去上传产品按钮 | button | "去上传产品" | Click → `/pages/vendor/product_edit` |

#### 有产品时 (products.length > 0)

| 元素 | 类型 | 文本/标识 | 操作 |
|------|------|----------|------|
| 产品卡片 | view | 动态产品标题 | Click → `/pages/product/detail?id=X` |
| 产品图片 | image | /images/cart.jpg (默认) | — |
| 产品标题 | view.p-title | 产品名称 | — |
| 产品价格 | view.price | "¥ 299.00" | — |
| 收藏星标 | view.icon-btn | star_on/star_off.png | catchtap → `onToggleFavorite` |
| 购物车图标 | view.icon-btn | /images/icon-cart.png | catchtap → `onAddToCart` |

---

### 3.2 创建商家 — `/pages/vendor/join`

**页面角色**: form | **Tab 页**: 否 | **需要商家**: 否

| 元素 | 类型 | 文本/标识 | 操作 |
|------|------|----------|------|
| 页面标题 | text | "创建商家账户" | — |
| 副标题 | text | "信息仅保存在本机，不会联网提交" | — |
| 名称标签 | text | "商家名称" | — |
| 名称输入框 | input | placeholder="例如：某某品牌官方店" | Type + bindinput=`onName` |
| 手机号标签 | text | "手机号" | — |
| 手机号输入框 | input | placeholder="选填（11位数字）" type=number maxlength=11 | Type + bindinput=`onPhone` |
| 简介标签 | text | "简介" | — |
| 简介输入框 | textarea | placeholder="一句话介绍你的商家/主营产品" maxlength=200 | Type + bindinput=`onIntro` |
| 保存按钮 | button | "保存" | Click → `onSave` |

**保存行为**: 验证 name 非空 → 验证 phone(选填11位数字) → `app.setMerchant(merchant)` → toast "已保存" → 300ms → `wx.navigateBack()`

---

### 3.3 上传/编辑产品 — `/pages/vendor/product_edit`

**页面角色**: form | **Tab 页**: 否 | **需要商家**: 是

| 元素 | 类型 | 文本/标识 | 操作 |
|------|------|----------|------|
| 页面标题 | text | "产品信息" (或 "编辑产品") | — |
| 副标题 | text | "仅本地保存，不会联网上传" | — |
| 产品名称标签 | text | "产品名称" | — |
| 产品名称输入框 | input | placeholder="例如：高对比暗色主题键盘" | Type + bindinput=`onTitle` |
| 价格标签 | text | "价格" | — |
| 价格输入框 | input | placeholder="例如：199.00" type=digit | Type + bindinput=`onPrice` |
| 描述标签 | text | "描述" | — |
| 描述输入框 | textarea | placeholder="介绍一下产品亮点、规格等" maxlength=500 | Type + bindinput=`onDesc` |
| 选择图片按钮 | button | "选择图片" | Click → `onChooseImages` |
| 保存按钮 | button | "保存产品" | Click → `onSave` |

**保存行为**: 验证 merchant 存在 → 验证 title 非空 → 验证 price>0 → `app.upsertProduct(product)` → toast "已保存" → 300ms → `wx.navigateBack()`

---

### 3.4 商品详情 — `/pages/product/detail`

**页面角色**: detail | **Tab 页**: 否 | **需要商家**: 否

| 元素 | 类型 | 文本/标识 | 操作 |
|------|------|----------|------|
| 产品大图 | image.hero | /images/cart.jpg (默认) | — |
| 产品标题 | view.title | 动态 | — |
| 收藏星标 | view.fav | star_on/star_off | Click → `onToggleFavorite` |
| 产品价格 | view.price | "¥ 299.00" | — |
| 产品描述 | view.desc | 动态文本 | — |
| 减号按钮 | view.qty-btn | "-" | Click → `onMinusQty` |
| 数量显示 | view.qty-value | 数字 (1-999) | — |
| 加号按钮 | view.qty-btn | "+" | Click → `onPlusQty` |
| 加入购物车按钮 | button.btn-primary | "加入购物车" | Click → `onAddToCart` |
| 评论标题 | text | "评论 (N 条)" | — |
| 评论输入框 | input | placeholder="写下你的评价…" | Type + bindinput=`onCommentInput` |
| 发布评论按钮 | button.btn-ghost | "发布评论" | Click → `onSubmitComment` |
| 评论列表 | view.comment | 每条: userName + time + content | — |

**无产品时**: 显示"商品不存在"+"可能已被删除"

---

### 3.5 购物车 — `/pages/cart/cart`

**页面角色**: cart | **Tab 页**: 是 | **需要商家**: 否

#### 空购物车

| 元素 | 类型 | 文本 |
|------|------|------|
| 标题 | text | "购物车为空" |
| 引导 | text | "去首页挑选一些商品吧" |

#### 有商品时

| 元素 | 类型 | 文本/标识 | 操作 |
|------|------|----------|------|
| 商品图片 | image.cover | 产品首图或默认 | Click → `/pages/product/detail?id=X` |
| 商品名称 | view.name | 动态 | Click → detail |
| 单价 | view.price | "¥ 299.00" | — |
| 移除按钮 | view.remove | "移除" | Click → `onRemove` |
| 小计 | text | "小计 ¥ XXX" | — |
| 减号 | view.qty-btn | "-" | Click → `onMinus` |
| 数量 | view.qty-value | 数字 | — |
| 加号 | view.qty-btn | "+" | Click → `onPlus` |
| 合计 | view.title | "¥ XXX" | — |
| 清空按钮 | button.btn-danger | "清空" | Click → `onClear` |

---

### 3.6 我的/商家中心 — `/pages/tabbar/user`

**页面角色**: profile | **Tab 页**: 是 | **需要商家**: 否

#### 无商家

| 元素 | 类型 | 文本 | 操作 |
|------|------|------|------|
| 标题 | text | "商家中心" | — |
| 副标题 | text | "创建账户、上传产品、管理展示" | — |
| 空态提示 | text | "未创建商家账户" | — |
| 创建按钮 | button | "创建商家账户" | Click → `/pages/vendor/join` |

#### 有商家

| 元素 | 类型 | 文本/标识 | 操作 |
|------|------|----------|------|
| 商家名称 | view.merchant-name | 动态 | — |
| 手机号 | text | "手机号：138..." | — |
| 上传产品按钮 | button | "上传产品" | Click → `/pages/vendor/product_edit` |
| 产品列表 | view.p-row | 每个产品: 图片+标题+价格 | — |
| 编辑按钮 | view.p-action | "编辑" | Click → `/pages/vendor/product_edit?id=X` |
| 删除按钮 | view.p-action.danger | "删除" | Click → Modal确认 → `onDeleteProduct` |

#### 收藏区

| 元素 | 类型 | 文本 | 操作 |
|------|------|------|------|
| 收藏项 | view.fav-row | 图片+标题+价格 | Click → `/pages/product/detail?id=X` |

#### 客服区

| 元素 | 类型 | 文本 | 操作 |
|------|------|------|------|
| 联系按钮 | button | "联系" | Click → `onSupport` |

---

## 4. 数据模型 Schema

### 4.1 Merchant

```json
{
  "id": "m_<timestamp>_<random>",
  "name": "商家名称 (必填, string)",
  "phone": "11位数字 (选填, string)",
  "intro": "简介 (选填, string ≤200字)",
  "createdAt": "毫秒时间戳 (number)",
  "updatedAt": "毫秒时间戳 (number)"
}
```

Storage Key: `merchant_v1`

### 4.2 Product

```json
{
  "id": "p_<timestamp>_<random>",
  "merchantId": "m_<id>",
  "title": "产品名称 (必填, string)",
  "desc": "描述 (选填, string ≤500字)",
  "price": "价格 (必填, number >0, 保留两位小数)",
  "images": "图片路径数组 (选填, string[])",
  "createdAt": "毫秒时间戳 (number)",
  "updatedAt": "毫秒时间戳 (number)"
}
```

Storage Key: `products_v1` (数组)

### 4.3 Cart

```json
{
  "<productId>": "数量 (number, 1-999)"
}
```

Storage Key: `cart_v1`

### 4.4 Favorites

```json
{
  "<productId>": 1
}
```

Storage Key: `favorites_v1`

### 4.5 Comments

```json
{
  "<productId>": [
    {
      "id": "c_<timestamp>_<random>",
      "userName": "访客 (固定)",
      "content": "评论内容 (string)",
      "createdAt": "毫秒时间戳 (number)"
    }
  ]
}
```

Storage Key: `comments_v1`

---

## 5. 关键业务规则

| 规则 | 说明 |
|------|------|
| 单商家限制 | 同一时刻仅允许一个商家；再次创建会覆盖 |
| 商家依赖 | 上传产品前必须先有商家，否则弹窗阻止 |
| 价格验证 | 必须为正数 (>0)，否则 toast "请输入正确价格" |
| 手机号格式 | 非空时必须为 11 位纯数字 |
| 购物车数量 | 范围 1-999，- 最低为1，+ 最高为999 |
| 删除级联 | 删除产品自动清除该产品的购物车项、收藏、评论 |
| navigateBack 时序 | 保存操作后 300ms 自动返回；弹窗确认后立即操作 |
| 评论人固定 | 始终为"访客" |

---

## 6. Toast 消息汇总

| 触发条件 | Toast 文本 | 图标 |
|---------|-----------|------|
| 商家名称为空 | "请输入商家名称" | none |
| 手机号格式错误 | "手机号需为11位数字" | none |
| 商家保存成功 | "已保存" | success |
| 产品名称为空 | "请输入产品名称" | none |
| 价格不正确 | "请输入正确价格" | none |
| 产品保存成功 | "已保存" | success |
| 加入购物车成功 | "已加入购物车" | success |
| 评论内容为空 | "请输入评论内容" | none |
| 评论发布成功 | "已发布" | success |
| 产品删除成功 | "已删除" | success |
| 无客服信息 | "未配置客服信息" | none |
| 无商家去上传 | 弹窗 "请先创建商家账户" | — |
