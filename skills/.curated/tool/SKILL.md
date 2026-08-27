---
name: tool
description: 设计、封装、接入、审查或排查供 AI agent 调用的 tool 时使用。核心是把函数、CLI、API 或 MCP operation 收敛成边界清楚、可校验、可授权、可观察的执行契约；整个 agent runtime 与会话编排归 harness skill。
---

# Tool

这里的 tool 特指 **agent 可调用的执行能力**，不是泛指软件、命令或开发工具。MCP 2025-06-18 将 tool 定义为模型可以发现并调用、用 name、description 与 schema 描述的可执行函数；本 skill 沿用这层含义，并把执行器、权限和生命周期也纳入设计范围。[MCP Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)

## Tool 的组成

下面四部分共同构成一个可用 tool。只给模型一段函数说明但没有执行器，不会产生外部动作；只有 CLI 或 API 而没有 agent 可见声明，也还不是当前 harness 中的 tool。

| 部分 | 职责 |
|---|---|
| 声明 | 稳定的名称、能区分调用时机的 description、机器可校验的输入 schema，以及可选输出 schema |
| 执行器 | 把已校验参数转换为本地函数、CLI argv、HTTP request、MCP call 或其他后端操作 |
| 结果契约 | 返回 agent 完成下一步所需的 observation，并区分成功、业务失败、权限不足、取消与内部错误 |
| 策略边界 | 说明身份、scope、副作用等级、sandbox、审批、超时、并发与审计要求 |

MCP 把 tool 定位为 model-controlled primitive，但同时要求应用清楚展示暴露给模型的能力，并让人能够拒绝调用；因此“模型能提出调用”和“系统允许执行”是两个阶段。[MCP Tools：User Interaction Model](https://modelcontextprotocol.io/specification/2025-06-18/server/tools#user-interaction-model)

## Agent、harness 与 tool

本仓采用下面这组工作边界，避免把模型输出、运行时控制和真实副作用混成一层：

```text
用户目标
   ▼
Agent / model ──提出 tool call──▶ Harness
   ▲                               │ schema / policy / approval / sandbox
   │ observation                   ▼
   └───────────────────────────── Tool
                                   │
                                   ▼
                              外部系统与状态
```

- **Agent** 根据目标选择下一步，并生成 tool call；这个 call 是执行请求。
- **Harness** 决定向模型暴露哪些 tools，校验参数和权限，调度执行，再把结果放回 agent loop。MCP 的 host/client/server 架构也把 context aggregation、安全策略和授权决策放在 host 一侧，把专门能力放在 server 一侧。[MCP Architecture](https://modelcontextprotocol.io/specification/2025-06-18/architecture)
- **Tool** 定义一项能力的输入、执行、副作用和结果，不拥有整个对话、会话恢复或全局 agent loop。
- **外部系统**拥有最终状态和授权；harness 放行后，OAuth scope、文件权限和数据库约束仍可能拒绝请求。
- **Skill** 是注入给 agent 的知识和工作方法。它可以解释何时、怎样调用 tool，但不等于安装了执行器，也不会生成外部系统权限。

角色取决于观察边界。一个 coding-agent CLI 对直接用户而言是 harness；被上层 orchestrator 通过 subprocess 或 SDK 驱动时，整套 runtime 又可以作为父 harness 的 agent-as-tool。整个框架与接入形态见 `harness` skill。

## 能力边界

一个 tool 表达一个用户可理解的动作或查询。拆分依据是语义、权限和失败边界，不是底层函数数量：

- 读取与写入需要不同授权时分开声明。
- 预览与正式提交有不同副作用时分开，或用显式 mode 表达。
- 创建、更新、删除若有不同幂等和恢复语义，不用一个自由文本 action 混在一起。
- description 只说明何时调用和关键限制；长手册、领域背景与低频排障放进 skill reference。
- 参数表达业务对象，不把临时目录、内部 transport 或后端偶然字段暴露成长期 API。

## 输入与结果

输入 schema 既服务模型，也服务执行前校验。参数应使用明确类型、枚举、格式和互斥条件；identity、cwd、session 等已经由 harness 确定的上下文，不要求模型再次猜测。

结果是给 agent 的 observation，不是后端响应的无筛选转储：

- 成功结果保留下一步需要的资源 ID、状态、摘要和可追溯入口。
- 错误区分参数、认证/权限、目标不存在、冲突、限流/暂时故障、用户拒绝、取消与内部错误。
- 结果明确是否可重试；写操作超时后不能直接假定失败，因为第一次请求可能已经生效。
- 大结果使用分页、游标、resource link、artifact 或摘要，原始证据保持可取回。

## 权限与副作用

Tool 声明应让 harness 能在执行前判断风险，而不是等操作发生后从日志猜：

- 标识只读、可逆写入与高风险写入；真正的用户确认由 harness 在临近执行时取得。
- 明确以谁的身份、针对哪个目标、需要哪些 scope 执行。
- 能预演的后端暴露 dry-run；需要去重的写入定义 idempotency key 或稳定幂等语义。
- secret 不进入 description、普通参数、模型可见错误或日志；凭据通过宿主安全存储、受限环境或 stdin 注入。
- 来自 tool server 的 annotation 不能天然视为可信，harness 仍需按来源和本地策略判断。[MCP Tools：Security Considerations](https://modelcontextprotocol.io/specification/2025-06-18/server/tools#security-considerations)

## 执行生命周期

Tool contract 同时说明 timeout、取消传播、进度、资源清理和并发冲突。调用方停止等待不等于后端已经取消；同一资源上的并发写入也不能依赖 tool call 的偶然到达顺序。

可观察记录至少覆盖 tool 名、调用身份、目标、开始/结束时间、结果类型和审批链。日志在进入模型、持久化或外发前处理 secret 与个人数据。

## 接入形态

同一能力可以通过不同 transport 暴露，选择时分别看部署边界和失败语义：

| 形态 | 主要特征 |
|---|---|
| 内置函数 | 与 harness 同进程、类型直接；发布和故障域也与 harness 绑定 |
| CLI adapter | 复用成熟命令和本机凭据；adapter 负责 argv、cwd、stdin、stdout/stderr、退出码、版本与超时 |
| HTTP API adapter | 服务边界清楚；认证、网络故障、限流与服务端幂等成为契约的一部分 |
| MCP server | 提供发现和调用协议，一个 server 可暴露多个 tools；协议不替代业务权限与单个 tool 的语义设计 |
| Agent-as-tool | 对父 harness 是有预算、权限和终止条件的调用，内部仍有自己的 agent loop、session 与 tools |

关于 harness 如何拥有 runtime、会话、工具注册表和 transport，见 `harness` skill。

## References

- [Lark / Feishu CLI 作为 Agent Tool](references/lark.md)：用 Lark CLI 说明 executable、tool adapter、AI Skill 与 OAuth 权限的分层；包含一键安装、Skills 目录布局、Agent 探测和可靠调用契约。

## 边界

普通软件的安装、升级和系统运维归 `software` skill。整个 coding-agent runtime、SDK、session、hooks、tool registry 与 transport 选型归 `harness` skill。本 skill 负责单个或一组 tools 自身的接口、执行、安全和 adapter 质量。
