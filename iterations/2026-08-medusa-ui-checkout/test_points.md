# Test Points — 2026-08-medusa-ui-checkout

Status: `review`

## T0001 — happy (P1)

游客从真实种子商品页选择黑色 S 码 T 恤并加入购物车后，购物车仅出现该变体且初始数量为 1。

- requirements: R0001

## T0002 — boundary (P1)

在数量下界场景中，单次加入黑色 S 码不得产生重复购物车行、错误变体或大于 1 的初始数量。

- requirements: R0001

## T0003 — happy (P1)

输入有效折扣码 ARGUS10 后，折扣与总额按照运行时种子价格和折扣比例实时派生，且总额关系一致。

- requirements: R0002

## T0004 — negative (P1)

输入无效折扣码时页面明确拒绝，购物车折扣和总额保持应用前数值，不得误用 ARGUS10 的优惠。

- requirements: R0002

## T0005 — happy (P1)

游客使用纯虚构地址、标准配送和隔离测试用 Manual Payment 提交订单后，订单确认页展示订单号、商品、配送、支付摘要且购物车归零。

- requirements: R0003

## T0006 — negative (P1)

游客缺少必填地址字段时不能进入可提交订单的终态，不得创建订单或展示成功确认页。

- requirements: R0003

## T0007 — happy (P2)

在 1440×900 Chromium 视口中，商品、折扣、总额、结账入口和订单确认关键状态均可见、布局无重叠且可操作。

- requirements: R0004

## T0008 — boundary (P2)

在 390×844 Chromium 边界视口中，关键状态可通过合理滚动访问，无横向溢出、遮挡或不可点击控件。

- requirements: R0004
