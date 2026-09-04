# TestApplet 框架说明书

> 本文档为 AppletTestPilot 自主测试智能体提供被测小程序的完整架构参考

---

## 1. 概述

TestApplet 是一个**本地数据模式**的微信小程序商城。所有数据存储在 `wx.Storage` 中，不联网。

```
AppID: (无 — 本地离线项目，不注册云端)
编译根目录: src/
页面数量: 6
TabBar: 3 个 (首页 / 购物车 / 我的)
```

---

## 2. 数据模型 (app.js 全局存储)

| 存储 Key | 读写方法 | 数据类型 | 说明 |
|----------|---------|---------|------|
| `merchant_v1` | `getMerchant()` / `setMerchant(m)` | `{id, name, phone, intro, createdAt, updatedAt}` 或 `null` | 商家账户 |
| `products_v1` | `getProducts()` / `upsertProduct(p)` / `deleteProduct(id)` | `[{id, merchantId, title, desc, price, images, createdAt, updatedAt}]` | 产品列表 |
| `cart_v1` | `getCart()` / `setCart(c)` / `addToCart(id,qty)` / `setCartQty(id,qty)` | `{productId: quantity}` | 购物车 |
| `favorites_v1` | `getFavorites()` / `toggleFavorite(id)` | `{productId: 1}` | 收藏 |
| `comments_v1` | `getCommentsMap()` / `getComments(id)` / `addComment(id, c)` | `{productId: [{id, userName, content, createdAt}]}` | 评论 |

**Merchant 结构**:
```json
{
  "id": "m_xxxxxxxxxxxxx",
  "name": "测试商家旗舰店",
  "phone": "13800138000",
  "intro": "主营高品质外设",
  "createdAt": 1700000000000,
  "updatedAt": 1700000000000
}
```

**Product 结构**:
```json
{
  "id": "p_xxxxxxxxxxxxx",
  "merchantId": "m_xxxxxxxxxxxxx",
  "title": "高性能机械键盘",
  "desc": "87键 RGB Cherry轴",
  "price": 299.00,
  "images": [],
  "createdAt": 1700000000000,
  "updatedAt": 1700000000000
}
```

---

## 3. 页面路由与导航

| 路由 | 页面标题 | TabBar | 进入方式 |
|------|---------|--------|---------|
| `pages/index/index` | 商品 | 首页 Tab | 启动默认页 / Tab 切换 |
| `pages/cart/cart` | 购物车 | 购物车 Tab | Tab 切换 |
| `pages/tabbar/user` | 我的 | 我的 Tab | Tab 切换 |
| `pages/vendor/join` | 创建商家账户 | 否 | `wx.navigateTo` 从 index 或 user |
| `pages/vendor/product_edit` | 上传产品 / 编辑产品 | 否 | `wx.navigateTo` 从 index 或 user |
| `pages/product/detail` | 商品详情 | 否 | `wx.navigateTo` 携带 `?id=` 参数 |

**导航方式**:
- Tab 间切换: `wx.switchTab` → 仅用于 3 个 TabBar 页面
- 页面跳转: `wx.navigateTo` → vendor/join, vendor/product_edit, product/detail
- 返回: `wx.navigateBack` → 从子页面返回上一页

---

## 4. 各页面详细说明

### 4.1 首页 — `pages/index/index`

**URL**: `/pages/index/index`

**有商户前 (merchant == null)**:
```
┌──────────────────────────────────┐
│  商品展示                         │
│  本地数据模式，无需联网            │
│                    [创建商家] btn │
├──────────────────────────────────┤
│  暂无商品                         │
│  先在"我的"里创建商家账户并上传产品  │
│             [去创建商家] btn      │
└──────────────────────────────────┘
```

**有商户后 (merchant != null)**:
- 右上角按钮变为 **[上传产品]**（`bindtap="onGoUpload"`）
- 如果有产品，显示产品卡片网格（`bindtap="onTapProduct"`）
- 每个产品卡片有：图片、标题、价格、收藏星标(`catchtap`)、购物车图标(`catchtap`)

**关键交互元素**:
| 元素文本 | 标签 | 条件 | 触发 |
|---------|------|------|------|
| "创建商家" | `<button>` | `!merchant` | `onGoCreateMerchant` → navigateTo `/pages/vendor/join` |
| "去创建商家" | `<button>` | `!merchant` | 同上 |
| "上传产品" | `<button>` | `merchant` | `onGoUpload` → navigateTo `/pages/vendor/product_edit` |
| "去上传产品" | `<button>` | `merchant` | 同上 |
| 产品标题 (动态) | `<view class="p-title">` | `products.length > 0` | `onTapProduct` → navigateTo `/pages/product/detail?id=X` |

---

### 4.2 创建商家 — `pages/vendor/join`

**URL**: `/pages/vendor/join`

**页面布局**:
```
┌──────────────────────────────────┐
│  创建商家账户                      │
│  信息仅保存在本机，不会联网提交      │
├──────────────────────────────────┤
│  商家名称                         │
│  [  例如：某某品牌官方店  ] input   │
│                                  │
│  手机号                           │
│  [  选填（11位数字）      ] input   │
│                                  │
│  简介                             │
│  [  一句话介绍你的商家...   ] textarea│
│                                  │
│             [保存] btn            │
└──────────────────────────────────┘
```

**3 个表单字段**:
| 字段 | 标签文本 | input 类型 | placeholder | bindinput | 验证 |
|------|---------|-----------|-------------|-----------|------|
| name | 商家名称 | `<input>` | 例如：某某品牌官方店 | `onName` | 必填，非空 |
| phone | 手机号 | `<input type="number" maxlength="11">` | 选填（11位数字） | `onPhone` | 选填，若填则必须11位数字 |
| intro | 简介 | `<textarea maxlength="200">` | 一句话介绍你的商家/主营产品 | `onIntro` | 选填 |

**保存行为** (`onSave`):
1. 验证 name 非空
2. 验证 phone 格式（选填则需 11 位数字）
3. 调用 `app.setMerchant(merchant)` 写入存储
4. `wx.showToast({ title: '已保存', icon: 'success' })`
5. 300ms 后 `wx.navigateBack()` 返回上一页

**编辑模式**: 如果已有 merchant，`onLoad` 会预填 name/phone/intro

---

### 4.3 上传/编辑产品 — `pages/vendor/product_edit`

**URL**: `/pages/vendor/product_edit` (新建) 或 `/pages/vendor/product_edit?id=X` (编辑)

**页面布局**:
```
┌──────────────────────────────────┐
│  产品信息 (或: 编辑产品)            │
│  仅本地保存，不会联网上传           │
├──────────────────────────────────┤
│  产品名称                         │
│  [  例如：高对比暗色主题键盘 ] input │
│                                  │
│  价格                             │
│  [  例如：199.00          ] input │
│                                  │
│  描述                             │
│  [  介绍一下产品亮点、规格等  ] textarea│
│                                  │
│  图片  [选择图片] btn              │
│  (图片网格 or "未选择图片")        │
│                                  │
│             [保存产品] btn         │
└──────────────────────────────────┘
```

**表单字段**:
| 字段 | 标签文本 | input 类型 | bindinput | 验证 |
|------|---------|-----------|-----------|------|
| title | 产品名称 | `<input>` | `onTitle` | 必填，非空 |
| price | 价格 | `<input type="digit">` | `onPrice` | 必填，> 0 |
| desc | 描述 | `<textarea maxlength="500">` | `onDesc` | 选填 |
| images | 图片 | `<button bindtap="onChooseImages">` | — | 选填 |

**保存行为** (`onSave`):
1. 验证 merchant 存在
2. 验证 title 非空
3. 验证 price 为有效正数
4. 调用 `app.upsertProduct(product)` 写入存储
5. `wx.showToast({ title: '已保存', icon: 'success' })`
6. 300ms 后 `wx.navigateBack()` 返回上一页

---

### 4.4 商品详情 — `pages/product/detail`

**URL**: `/pages/product/detail?id=<productId>`

**页面布局**:
```
┌──────────────────────────────────┐
│  [产品图片]                        │
│  产品标题              [☆ 收藏]    │
│  ¥ 价格           高对比暗色系      │
│  ─────────────────────────────── │
│  产品描述文本...                    │
├──────────────────────────────────┤
│  数量              [-] 1 [+]      │
│             [加入购物车] btn        │
├──────────────────────────────────┤
│  评论 (N 条)                      │
│  [  写下你的评价…           ] input │
│             [发布评论] btn         │
│  ─────────────────────────────── │
│  访客          2025-01-01 12:00  │
│  评论内容...                      │
└──────────────────────────────────┘
```

**交互元素**:
| 元素 | 触发 |
|------|------|
| 收藏星标 `☆/★` | `onToggleFavorite` — 切换收藏状态 |
| `[-]` / `[+]` | `onMinusQty` / `onPlusQty` — 调整数量 (1-999) |
| "加入购物车" button | `onAddToCart` — 添加当前数量到购物车 |
| 评论 input | `onCommentInput` — 输入评论 |
| "发布评论" button | `onSubmitComment` — 保存评论并刷新列表 |

---

### 4.5 购物车 — `pages/cart/cart`

**URL**: `/pages/cart/cart` (TabBar 页面)

**空购物车**:
```
┌──────────────────────────────────┐
│  购物车为空                        │
│  去首页挑选一些商品吧               │
└──────────────────────────────────┘
```

**有商品时**:
```
┌──────────────────────────────────┐
│  [图] 产品标题                     │
│       ¥ 价格         [移除]       │
│       小计 ¥ X      [-] 2 [+]     │
│                                   │
│  ─────────────────────────────── │
│  合计    ¥ XXX       [清空] btn   │
└──────────────────────────────────┘
```

**交互元素**:
| 元素 | 触发 |
|------|------|
| `[-]` / `[+]` | `onMinus` / `onPlus` — 调整数量并刷新 |
| "移除" | `onRemove` — `setCartQty(id, 0)` |
| "清空" button | `onClear` — `setCart({})` |
| 产品图片/标题 | `onTapProduct` → navigateTo detail |

---

### 4.6 我的 (商家中心) — `pages/tabbar/user`

**URL**: `/pages/tabbar/user` (TabBar 页面)

**无商户时**:
```
┌──────────────────────────────────┐
│  商家中心                          │
│  创建账户、上传产品、管理展示        │
│  ─────────────────────────────── │
│  未创建商家账户                     │
│          [创建商家账户] btn         │
├──────────────────────────────────┤
│  收藏 (0 个)                      │
│  暂无收藏                          │
├──────────────────────────────────┤
│  快捷客服                          │
│  电话/微信/邮箱（本地配置）    [联系]│
└──────────────────────────────────┘
```

**有商户时**:
- 显示商户名称 + 手机号
- **[上传产品]** 按钮
- **我的产品** 列表：每个产品有 [编辑] [删除]
- **收藏** 列表：点击跳转商品详情
- **[联系]** 客服按钮 → `showSupportActions()`

**交互元素**:
| 元素 | 触发 |
|------|------|
| "创建商家账户" button | `onCreateMerchant` → navigateTo `/pages/vendor/join` |
| "上传产品" button | `onUploadProduct` → navigateTo `/pages/vendor/product_edit` |
| "编辑" | `onEditProduct` → navigateTo `/pages/vendor/product_edit?id=X` |
| "删除" | `onDeleteProduct` → `wx.showModal` 确认 → `app.deleteProduct(id)` |
| 收藏行 | `onTapFavorite` → navigateTo `/pages/product/detail?id=X` |
| "联系" button | `onSupport` → `app.showSupportActions()` |

---

## 5. 页面状态流转图

```
                    启动
                      │
                      ▼
              ┌───────────────┐
     ┌───────│  /pages/index │◄──────────────────┐
     │       │     (首页)     │                    │
     │       └───┬───────┬───┘                    │
     │           │       │                        │
     │  [创建商家]│       │ [点击产品]              │
     │           ▼       ▼                        │
     │  ┌──────────┐  ┌─────────────────┐         │
     │  │ vendor/  │  │ product/detail  │         │
     │  │  join    │  │  (商品详情)      │         │
     │  │(创建商家)│  └────────┬────────┘         │
     │  └────┬─────┘           │                  │
     │       │ [保存]          │ [加入购物车]      │
     │       │ navigateBack    │                  │
     │       └─────────────────┤                  │
     │                         ▼                  │
     │                  ┌──────────────┐          │
     │                  │  /pages/cart │          │
     │                  │   (购物车)    │          │
     │                  └──────────────┘          │
     │                                            │
     │  ┌──────────────────────┐                  │
     │  │  /pages/tabbar/user  │                  │
     └──│     (商家中心)        │──────────────────┘
        └──────┬───────────────┘
               │ [上传产品] / [编辑]
               ▼
        ┌──────────────┐
        │ vendor/      │
        │ product_edit │
        │ (产品编辑)   │
        └──────┬───────┘
               │ [保存产品]
               │ navigateBack
               └──────► 返回上一页
```

---

## 6. 关键业务规则

### 6.1 商户创建
- 名称**必填**，为空时 toast "请输入商家名称"
- 手机号**选填**，但若填写必须为 11 位数字
- 保存成功后 toast "已保存" → 300ms → navigateBack

### 6.2 产品管理
- 产品名称**必填**，为空时 toast "请输入产品名称"
- 价格**必填**，必须为正数，否则 toast "请输入正确价格"
- 必须先创建商户才能上传产品（否则弹窗提示并跳转创建商户页）

### 6.3 购物车
- 数量范围 1-999
- onMinus 最低为 1
- onPlus 最高为 999
- 移除 (`onRemove`) 等效于 `setCartQty(id, 0)`
- 清空 (`onClear`) 等效于 `setCart({})`

### 6.4 评论
- 评论人固定为 "访客"
- 内容为空时 toast "请输入评论内容"
- 提交后清空输入框，刷新评论列表

---

## 7. Agent 交互指南

### 7.1 输入操作模式

| 自然语言模式 | 实际执行 |
|-------------|---------|
| `Click '创建商家'` | 查找文本为"创建商家"的可点击元素 → click |
| `Type '测试旗舰店' into '商家名称'` | 查找 label 为"商家名称"的相邻 input → input(text) |
| `Type '13800138000' into phone field` | 查找手机号相关 input → input(text) |
| `Go back` | `mini.navigateBack()` → capture_state |
| `Scroll down` | `wx.pageScrollTo({scrollTop: current+300})` → capture_state |
| `Scroll up` | `wx.pageScrollTo({scrollTop: 0})` → capture_state |
| `Scroll to '商品名称'` | 查找包含该文本的元素 → scroll_into_view → capture_state |

### 7.2 验证模式

```
期望: "Page id is '/pages/vendor/join'" → fast path: 直接读 page.page_id
期望: "Page contains '创建商家账户'" → 视觉模型生成 postcondition
期望: "Name field shows typed text" → 视觉模型 extract 或 text-contains fallback
```

### 7.3 时序要点

- 每次 `navigateTo` 后需要 **0.5s 等待** 让页面加载完成
- 每次 `input` 后可以**立即验证**（bindinput 实时更新）
- `navigateBack` 后需要等待确保返回完成
- Toast 消息 ("已保存") 会在 300ms 后触发 navigateBack

---

## 8. 测试数据参考（供 LLM 生成用例时参考）

> APP 启动时 Storage 为空，以下为推荐的测试数据示例。Phase 1 探索时 LLM 可参照这些数据生成输入操作。

### 8.1 商家示例

```json
{
  "id": "m_test_001",
  "name": "测试商家旗舰店",
  "phone": "13800138000",
  "intro": "主营高品质外设与数码配件，欢迎选购"
}
```

### 8.2 产品示例

```json
[
  {
    "id": "p_test_001",
    "merchantId": "m_test_001",
    "title": "高性能机械键盘",
    "desc": "Cherry MX 青轴，RGB 背光，87 键紧凑布局，全键无冲",
    "price": 299.00,
    "images": []
  },
  {
    "id": "p_test_002",
    "merchantId": "m_test_001",
    "title": "无线降噪耳机",
    "desc": "ANC 主动降噪，40h 续航，蓝牙 5.3，低延迟游戏模式",
    "price": 199.00,
    "images": []
  },
  {
    "id": "p_test_003",
    "merchantId": "m_test_001",
    "title": "USB-C 扩展坞",
    "desc": "7 合 1：HDMI 4K、USB-A×3、USB-C PD 100W、SD/TF 读卡器",
    "price": 149.00,
    "images": []
  }
]
```

### 8.3 购物车示例

```json
{ "p_test_002": 2 }
```

### 8.4 收藏示例

```json
{ "p_test_001": 1 }
```

### 8.5 评论示例

```json
{
  "p_test_001": [
    { "id": "c_001", "userName": "访客", "content": "键盘手感很好，RGB 灯效也很炫酷！", "createdAt": 1700000000000 },
    { "id": "c_002", "userName": "数码爱好者", "content": "打字声音清脆，办公室用也很合适", "createdAt": 1700000000000 }
  ]
}
```

### 8.6 推荐的测试流程

```
1. launch_home                    → 首页空态：验证"暂无商品"+"去创建商家"按钮
2. 创建商家 → launch_home_with_merchant       → 首页显示"上传产品"按钮
3. 上传产品 → launch_home_with_merchant_and_product → 首页显示产品卡片
4. 收藏/取消收藏                    → 产品详情页点击收藏星标
5. 加入购物车                       → 产品详情页调整数量 + 加入购物车
6. launch_home_with_merchant_and_product_in_cart → 购物车显示商品
7. 编辑产品                         → 修改名称/价格/描述后保存
8. 删除产品                         → 确认删除后产品消失
9. 提交评论                         → 评论出现在产品详情页
10. 清空购物车                       → 购物车恢复空态
```

### 8.7 边界与异常测试建议

- 商家名称为空 → toast "请输入商家名称"
- 手机号非 11 位数字 → toast "手机号需为11位数字"
- 产品名称为空 → toast "请输入产品名称"
- 价格为 0 或负数 → toast "请输入正确价格"
- 无商家时直接访问 `/pages/vendor/product_edit` → 弹窗提示并跳转创建页
- 产品详情页 id 不存在 → 显示"商品不存在"
- 购物车数量 +/- 边界 (1-999)
