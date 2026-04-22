# 优化维度

## 可选维度

按推荐优先级：

1. **readme** — README 补齐（安装、用法、badge）
2. **broken-links** — 修复死链
3. **typo** — 拼写 / 语法错误
4. **deps** — 依赖升级（minor / patch）
5. **types** — 类型标注
6. **lint** — lint 修复（按仓库已有配置）
7. **tests** — 补充测试
8. **docs** — 补充 docstring
9. **dead-code** — 删除死代码
10. **security** — 修复明显安全问题

维度不是固定的，agent 可以根据仓库实际情况自行判断和扩展。

## 选择规则

1. 读 attempts.log，跳过 exhausted 维度（同方向连续 3 次 fail）
2. 取可用维度中优先级最高的
3. 所有维度都完成或 exhausted → done / stuck

## 禁做清单

- 架构重构 / 大规模重命名
- 删除功能 / 改变公共 API
- 纯风格统一（整文件格式化）

敏感文件（CI 配置、LICENSE、secrets）的保护由 FGPAT 权限和 branch protection 在外部保证，不在 runbook 中重复约束。
