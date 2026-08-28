# Requirements — 2026-08-medusa-api-checkout

Status: `clarified`

## R0001 — 通过 Store API 建立黑色 S 码商品购物车

通过真实 Medusa Store API 查询 T-Shirt 与黑色 S 码变体，使用运行时地区创建购物车并加入一件商品；地区、商品与变体 ID 必须来自实际响应或种子状态，不得写死。

- priority: 1
- source: iterations/2026-08-medusa-api-checkout/00-raw/requirements-dump.md

## R0002 — 应用 ARGUS10 并验证 API 派生金额

对真实购物车应用 ARGUS10，并依据运行时种子价格与折扣比例验证折扣金额和购物车总额，不得复制固定金额作为预言机。

- priority: 1
- source: iterations/2026-08-medusa-api-checkout/00-raw/requirements-dump.md

## R0003 — 通过 Store API 完成游客订单

更新纯虚构游客邮箱与配送地址，查询并选择 Standard Shipping，初始化并选择隔离测试用 Manual Payment，完成购物车后验证真实订单、商品规格、配送方式、支付状态与最终金额。

- priority: 1
- source: iterations/2026-08-medusa-api-checkout/00-raw/requirements-dump.md

## R0004 — 拒绝非法促销请求且保持结构化错误

对已含目标商品的购物车提交非法促销请求时，Store API 必须返回结构化客户端错误；自动化不得通过弱化预期或跳过请求获得绿灯。

- priority: 2
- source: iterations/2026-08-medusa-api-checkout/00-raw/requirements-dump.md

## Ambiguities

- [resolved] API 正向链路应只验证购物车折扣，还是必须完成到真实订单创建？推荐完成到订单创建，以满足用户明确要求的完整全栈自动化。
  - resolution: 用户明确要求完成开源项目的完整全栈自动化，并已接受同一 Medusa 业务的 UI 订单创建边界；因此 API 正向链路同样以真实订单创建与最终状态验证为成功边界。
