# Requirements — 2026-08-medusa-ui-checkout

Status: `clarified`

## R0001 — 游客选择种子商品并加入购物车

游客在 Medusa 商店选择黑色 S 码 T 恤并加入购物车；商品、库存、地区和币种均来自已锁定的真实种子。

- priority: 1
- source: docs/spec/product/ROADMAP.md 9.2

## R0002 — 使用 ARGUS10 并验证实时派生总额

游客在购物车应用 ARGUS10；页面展示的原价、折扣和总额必须由运行时种子价格与折扣比例推导，不得复制固定金额作为预言机。

- priority: 1
- source: docs/spec/product/ROADMAP.md 9.2

## R0003 — 完成游客结账并创建订单

从已应用折扣的购物车填写纯虚构游客地址，选择标准配送与隔离测试用 Manual Payment，提交订单后断言订单确认页、订单号、商品/配送/支付摘要和归零购物车可见。

- priority: 1
- source: iterations/2026-08-medusa-ui-checkout/00-raw/requirements-dump.md

## R0004 — 验证桌面与移动关键状态

在 Chromium 中验证 1440×900 与 390×844 下商品、折扣、总额、结账入口和订单确认关键状态的可见性、布局与可操作性。

- priority: 2
- source: iterations/2026-08-medusa-ui-checkout/00-raw/requirements-dump.md

## Ambiguities

- [resolved] 本轮“游客结账成功”应以订单创建成功为边界，还是以进入结账并确认折扣后购物车总额为边界？推荐完成到订单创建成功，以符合 Roadmap 9.2 的完整结账含义。
  - resolution: 用户明确要求实现 docs 全部需求；PRD §7 要求 UI iteration 端到端，Roadmap 9.2 明确为 guest checkout w/ discount，因此采用订单创建成功边界。2026-08-28 在锁定 Medusa 靶场已实际到达订单确认页并验证购物车归零。
