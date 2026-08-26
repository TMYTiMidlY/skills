# DeepSeek Harness（dsh）Plugin 调研记录

本文件按日期记录 DSH 社区 Plugin 的检索与源码调研，保留调研时间、目标、候选仓库、证据边界和阶段状态。已经稳定且适合指导开发的内容再整理进 [DeepSeek Harness Plugin 开发](dsh-plugin.md)；仍在核验的观察留在这里，避免把阶段判断写成长期事实。

## <a id="2026-08-26-subscription-auth-surfaces"></a>2026-08-26 · 订阅登录与交互界面

本次从 DSH 官方的模型与凭据实现出发，检索社区中提供订阅登录、模型路由以及 Web / TUI 交互界面的 Plugin。第一轮先固定候选集合和后续核验问题，不在这里写具体架构结论或选型建议。

**调研时间：** 2026-08-26（Asia/Shanghai）

**调研目标：**

- 核对 DSH 官方 Authorization、Credentials 与 `llm-pi-ai` 的现有边界。
- 搜索能让 DSH 使用 Codex、Claude、Copilot、Kimi、OpenRouter、xAI 等订阅或 OAuth 凭据的社区 Plugin。
- 关注 Web 与 TUI 登录入口、Provider 激活、Token 保存与刷新、Adapter 复用和模型目录之间的关系。
- 为后续逐仓库源码核验建立同一批候选与一致的比较口径。

### <a id="2026-08-26-candidates"></a>初步关注的仓库

| 仓库 | 本轮关注点 |
|---|---|
| [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness/tree/b150a551b8d465e31e418e1b2eaf5e79bbb7d28e) | 官方 Authorization、Credentials、`llm-pi-ai` 与 Web composition 的对照基线 |
| [V1ki/dsh-plugin-subscriptions](https://github.com/V1ki/dsh-plugin-subscriptions/tree/08b9b7cc30e72e8eedd559ac01af9fc576157453) | 面向多个订阅 Provider 的 Web 设置页、模型路由与附加工具 |
| [weijiafu14/pi2dsh](https://github.com/weijiafu14/pi2dsh/tree/bf8e74fd8146fb6cf74895c536792e086650fa5e) | Pi Plugin 与 Provider 进入 DSH 的兼容层，以及登录能力如何映射到 DSH |
| [Yan-Zero/dsh-codex](https://github.com/Yan-Zero/dsh-codex/tree/e3e54e206f7c829503c7e6eed378643ba0416792) | Codex 订阅登录、模型请求与 Web / CLI / TUI 入口 |
| [WSL043/dsh-codex-subscription](https://github.com/WSL043/dsh-codex-subscription/tree/c8899beac69c40bcfc850c9dc497fd042806f879) | Codex 订阅的产品化设置、额度、搜索、图片和诊断能力 |
| [ziyou979/dsh-llm-oauth](https://github.com/ziyou979/dsh-llm-oauth/tree/362312e5d01cccb5fc74fda130875d500dbaf78c) | 基于 Pi Provider catalog 的多 Provider OAuth Plugin |
| [yhyfhgs/dsh-model-hub](https://github.com/yhyfhgs/dsh-model-hub/tree/f55ac188ef24f9604e77ed127a025962c8a37c2f) | Provider 登录、模型目录、路由管理以及自带 Provider 的实现 |
| [edge-sky/dsh-oauth-adapter](https://github.com/edge-sky/dsh-oauth-adapter/tree/559a757351093b42b695c36f77d81f8cbfe05a03) | 为 DSH Web 提供 OAuth 账户交互界面的轻量 Plugin |
| [XMoon/dsh-pi-tui](https://github.com/XMoon/dsh-pi-tui/tree/76c8c96df3457720f59a9e450687f280d875e9f5) | 基于 Pi TUI 的 DSH 终端界面及其登录入口 |
| [ccch1mneyyy/dsh-TUI](https://github.com/ccch1mneyyy/dsh-TUI/tree/5f7d2fb9974d4575953795ced9e7feae2b241d0e) | 基于 Ink / React 的另一套 DSH 终端界面及其 Plugin 生态 |
| [ccch1mneyyy/dsh-auth](https://github.com/ccch1mneyyy/dsh-auth/tree/fba02bcf7fb57e3d9885f73882d5835ccdf526c4) | `dsh-TUI` 携带的订阅认证 Plugin |

> 仓库链接固定到本次调研所读的 commit。除 GitHub 源码与仓库元数据外，本轮还核对了本地只读 checkout；尚未进行真实账号 OAuth、Token 刷新和模型调用的端到端验证。

### <a id="2026-08-26-follow-up"></a>后续核验口径

下一轮逐仓库核对以下问题，完成后再补阶段结论：

- Provider 覆盖范围及其对应的 API Key、订阅或 OAuth 计费关系。
- 登录入口是否调用 DSH 官方 Authorization flow，还是由 Plugin 自行实现。
- Token 使用 credential record、credential reference 还是独立文件；写入权限、原子性、并发刷新和退出登录行为。
- 模型请求是否复用官方 `PiAiAdapter`、直接复用 Pi，或自行维护协议转换。
- Web / TUI 如何承载 URL、device code、文本、secret、select、取消与失败状态。
- 登录后 Provider profile、模型目录和会话模型选择如何激活，是否会与官方 route 冲突。
- 发布版本、测试、CI、兼容范围，以及供应商条款与账号风险的说明。

**阶段状态：** 已形成上述候选集合；具体实现差异、完成度判断和选型结论暂不写入，等待下一轮统一整理。
