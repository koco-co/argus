# Medusa API 正式迭代原始需求

## 用户原始目标

用户要求使用 Argus 框架完成真实开源测试项目的“完整的全栈自动化代码”，且全部验收通过后才结束 Goal。这里的全栈明确要求在已验收的 Web 游客结账之外，完成独立的 API 自动化链路，不能用 fixture 或静态检查冒充正式 iteration。

用户已经接受同一锁定 Medusa 靶场的 UI 业务边界：先选择黑色 S 码 T 恤，再加入购物车，应用 `ARGUS10`，填写纯虚构游客地址，选择 Standard Shipping 与 Manual Payment，最后创建订单并验证购物车归零。API iteration 应验证同一业务语义，保证 Web 与 API 两层对同一真实后端行为形成互补证据。

## 正式 API 范围

- 通过 Medusa Store API 查询运行时商品与黑色 S 码变体，使用真实地区创建购物车并加入一件商品；运行时 ID 必须来自响应或种子状态，不得写死。
- 应用真实促销码 `ARGUS10`，根据 `shared/testdata/seed-registry.yaml` 中的价格与折扣比例验证折扣金额和购物车总额。
- 通过 Store API 更新游客邮箱与配送地址、查询并选择 Standard Shipping、初始化并选择隔离测试用 Manual Payment，完成购物车并验证真实订单响应、商品规格、配送方式、支付状态与最终金额。
- 覆盖至少一个不会削弱正向要求的负向 API 行为：无效促销请求必须返回结构化客户端错误，并且不得通过修改预期值获得绿灯。
- API 自动化必须生成同步 httpx client、Pydantic request/response model、pytest 用例及 R→A→nodeid 追踪；测试运行时不得读取 `iterations/**`。

## 来源

- 用户明确要求：“成功使用这个框架完成了开源测试项目的完整的全栈自动化代码，全部验收通过后才运行终止”。
- 已接受的 UI 业务语义：`iterations/2026-08-medusa-ui-checkout/requirements.yaml` 与其 M9 验收记录。
- 框架交付要求：`docs/spec/product/ROADMAP.md` 9.3 与 `docs/spec/product/PRD.md` §4.4、§7。
