# 已验证反模式

本文件按 M12 合同只记录真实出现过的失败模式及其规避方式，不收录泛化建议或猜测。

---
tags: [skills, command-path, repository-root]
date: 2026-08-28
source: commit:049ed9f; .agents/skills/*/SKILL.md
---

## 在 Skill 中按文件位置拼接脚本相对路径

六个 Skill 初稿曾使用 `../../../scripts/...`，但 Skill 的执行工作目录是仓库根目录，不是 `SKILL.md` 所在目录；该写法会解析到仓库外。修复方式是所有可执行命令统一写成 `uv run python scripts/<name>.py ...`，并由结构测试直接检查关键命令。反模式判据：任何项目 Skill 以自身文件层级推导运行命令路径。

---
tags: [seed, oracle, self-debug]
date: 2026-08-28
source: commit:116e56e; scripts/target_app_canary.py --corrupt product_price_eur
---

## 只验证种子脚本成功而不验证断言依赖种子真值

种子请求成功不能证明测试 oracle 使用了种子结果。靶场金丝雀先通过真实 Admin API 读取 EUR 价格和促销比例计算总价，再故意只在内存破坏价格；依赖断言随即转红。规避方式：每个可派生预期都必须有反事实破坏用例，禁止把生成器复制出的常量当作验收证据。
