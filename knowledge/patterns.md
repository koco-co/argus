# 已验证模式

本文件按 M12 合同只追加可复现、可复用且有证据的事实。重复事实不追加；修正项必须指向被替代条目。

---
tags: [medusa, docker, postgres, ssl]
date: 2026-08-28
source: commit:116e56e; make target-app-up; scripts/target_app_healthcheck.py
---

## 容器内 PostgreSQL 必须显式关闭本地非 TLS 连接的 SSL

Medusa 2.19.0 在容器网络中仅依赖主机名判断数据库是否需要 SSL，会把 `postgres` 误判为远端并导致迁移等待或失败。靶场通过覆盖 `medusa-config.ts` 显式设置 `ssl: false` 后，连续健康探测、reset 与全新重建均通过。可复用结论：Compose 内部的受控 PostgreSQL 必须把 SSL 策略写成显式配置，不能依赖框架的 localhost 猜测。

---
tags: [nextjs, docker, internal-url, storefront]
date: 2026-08-28
source: commit:116e56e; browser:/dk/products/t-shirt; target-app/Dockerfile
---

## 浏览器 URL 与服务端渲染 URL 必须分离

店面浏览器请求需要 `http://localhost:9000`，但 storefront 容器内的 Next.js 服务端渲染必须访问 `http://backend:9000`。使用单一公开 URL 会让容器 SSR 连接宿主回环地址。靶场分别使用 `NEXT_PUBLIC_MEDUSA_BACKEND_URL` 与 `MEDUSA_INTERNAL_BACKEND_URL` 后，商品页、购物车和折扣 UI 均可真实访问。
