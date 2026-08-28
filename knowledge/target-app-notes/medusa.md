---
target_app: medusa
verified_at: 2026-08-28
source: "Roadmap 5.0 真实靶场联调"
tags: [medusa, dtc-starter, ui, api, seed]
---

# Medusa 靶应用事实手册

本文只记录在锁定实例上实际核对过的事实。自动化生成技能必须先读取本文，再按“角色 → 标签 → 占位符 → 文本 → testid → CSS”选择定位器；使用后两级时须在页面对象中写明回退原因。

## 锁定版本与运行边界

- Medusa：2.19.0；DTC starter 提交：`cb603dfda0a82e8bb5e81622f295e0ff90ac6913`。
- Node：22.12.0；PostgreSQL：17.6；Redis：7.4.6；所有镜像均在 `target-app/medusa.lock.yaml` 中带 OCI digest。
- Storefront：`http://localhost:8000`；首次访问 `/` 会重定向到 `/dk`。
- Backend、Admin：`http://localhost:9000`；健康路由 `/health`；Admin 入口 `/app`，未登录时转到 `/app/login`。
- Storefront 服务端渲染通过 Compose 内网 `http://backend:9000` 访问后端；浏览器端使用 `http://localhost:9000`。不得把 Compose 服务名写入浏览器侧测试配置。
- Admin API 使用 `POST /auth/user/emailpass` 返回的 Bearer token。Store API 不复用管理员 token，而使用 `x-publishable-api-key`；该 key 只保存在 gitignored、权限为 `0600` 的 `target-app/runtime.env`。
- 本地 PostgreSQL 明确配置 `ssl: false`。这是隔离 Compose 网络的开发边界，也规避 Medusa 对非 localhost 数据库主机误启 SSL 后使迁移等待的问题。
- PostgreSQL 只在回环地址 `127.0.0.1:15432` 暴露给宿主机。迁移完成后，启动脚本幂等创建 `argus_readonly`：授予 public schema 全表 `SELECT`、撤销建表能力、禁止超级用户/建库/建角色/绕过 RLS，并设置 `default_transaction_read_only=on`。健康检查会从该角色自身视角核对全表可读、零 DML 权限，再真实执行一次建表探针并要求数据库拒绝；探针不会留下对象。

## 已验证路由与可见状态

| 场景 | 路由 | 已验证的可见事实 |
| --- | --- | --- |
| 商店首页 | `/dk` | `Medusa Store` 导航、`Menu`、`Account`、`Cart (0)` |
| Shirts 分类 | `/dk/categories/shirts` | `Shirts` 一级标题；`Medusa T-Shirt €10.00` 商品链接 |
| T-Shirt 详情 | `/dk/products/t-shirt` | `Black`、`S` 按钮；选择后出现 `Add to cart` |
| 购物车 | `/dk/cart` | 商品行、数量下拉框、`Summary`、`Add Promotion Code(s)`、`Go to checkout` |
| 地址结算 | `/dk/checkout?step=address` | 购物车页已核对其真实链接；完整字段在 UI 迭代中继续验收 |
| Admin 登录 | `/app/login` | `Email` 标签文本框、`Password` 占位符文本框、`Continue with Email` 按钮 |

2026-08-28 的可见交互核对：选择 `Black` + `S` 后加入购物车，应用 `ARGUS10`；页面展示 `Promotion(s) applied:`、`ARGUS10 (10%)`、`Discount - €1.00` 和 `Total €9.00`。这证明折扣断言依赖真实 Store API 与购物车状态，不是静态页面检查。

## 定位器策略

优先使用下列已验证的语义定位器：

- 导航：`get_by_role("link", name="Medusa Store")`、`get_by_role("link", name=re.compile(r"Cart \\(\\d+\\)"))`。
- 分类/商品：`get_by_role("heading", name="Shirts")`、`get_by_role("link", name=re.compile("Medusa T-Shirt"))`。
- 规格与加购：`get_by_role("button", name="Black")`、`get_by_role("button", name="S")`。移动布局会同时渲染桌面与吸底的两个 `Add to cart`，须用 `get_by_role("button", name="Add to cart").filter(visible=True).first`，禁止依赖 DOM 顺序点击隐藏或重复实例。
- 优惠入口的当前可访问名称未稳定暴露给 role 查询；已验证 `get_by_text("Add Promotion Code(s)", exact=True)` 可见且可点击。输入框无 label/placeholder，可在购物车摘要页面对象内用唯一 `get_by_role("textbox")`，并记录本回退原因。
- 优惠提交与结果：`get_by_role("button", name="Apply")`、`get_by_role("heading", name="Promotion(s) applied:")`、`get_by_text("ARGUS10", exact=False)`。
- 禁止在测试文件里直接写以上定位器；测试只能调用 `automation/web/pages/**` 的页面对象方法。

## Seed 实体参考

完整机器契约在 `shared/testdata/seed-registry.yaml`。以下值由实际 Admin API 响应核对：

| Seed key | 选择条件/值 | 可派生事实 |
| --- | --- | --- |
| `region_europe` | `name=Europe` | currency=`eur`，含 `dk` |
| `currency_eur` / `currency_usd` | `eur` / `usd` | 两种货币均由运行实例返回 |
| `product_tshirt` | `handle=t-shirt` | 标题 `Medusa T-Shirt` |
| `inventory_tshirt_s_black` | `sku=SHIRT-S-BLACK` | variant 与 inventory item 关联存在 |
| `product_price_eur` | EUR 10 | 黑色 S 码价格 |
| `product_price_usd` | USD 15 | 同一变体的 USD 价格 |
| `shipping_standard` | `name=Standard Shipping` | Europe 可用配送选项 |
| `payment_manual` | `pp_system_default` | Europe 已启用的系统支付提供者 |
| `customer_argus` | `argus-customer@example.invalid` | Admin API 幂等创建 |
| `discount_argus10` | `ARGUS10` | order 级 percentage=10、状态 active |
| `discounted_total` | 公式 | `10 × (100 - 10)% = 9.00 EUR` |

## 实际探测记录

以下命令于 2026-08-28 在锁定实例上实际执行，秘密不进入命令行或输出：

```text
make target-app-up
=> Medusa seed 已通过 Admin API 收敛，实体 ID 保持稳定
=> Medusa 已启动：http://localhost:8000；Admin/API：http://localhost:9000

make target-app-healthcheck
=> 靶应用健康检查通过：backend、admin、storefront 连续两次可用
=> 同一检查内：只读角色权限结果为 true/true/true，真实 CREATE TABLE 探针被只读事务或权限边界拒绝

make target-app-reset  # 连续执行两次并比较 seed-state.yaml
=> 两次均收敛；实体 ID 字节一致

make target-app-canary
=> seed 预言机 canary 通过：10 × (100-10)% = 9.00

uv run python scripts/target_app_canary.py --corrupt product_price_eur
=> seed 预言机 canary 失败：EUR 价格不一致：registry=11, live=10
```

Store/Admin 端点 spot-check 使用 `scripts/target_app_seed.py` 的本地、禁代理客户端完成：`GET /admin/regions?fields=+payment_providers.*` 返回 Europe 与 `pp_system_default`；`GET /admin/products?fields=+variants.*,+variants.prices.*,+variants.inventory_items.*` 返回 T-Shirt、EUR 10、USD 15 与库存关联；`GET /admin/promotions?fields=+application_method.*` 返回 `ARGUS10`/10%。
