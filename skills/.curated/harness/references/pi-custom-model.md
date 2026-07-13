# 给 pi 接自定义模型：配置 + 验证

把任意「兼容 OpenAI / Anthropic 的第三方端点」（自建网关、校园/公司平台、Ollama、vLLM、LM Studio…）接进 pi，涉及两件事：**配置**（`models.json` 怎么写）和**验证**（这个端点到底是什么、每个字段真吃不吃）。本文两件都讲，并把每条信息的来源标出来。

**来源标签**（每处用 `>` 就近给出处，全篇无脚注）：

- **【pi】** pi 官方文档 / 源码——**优先引[官方在线文档](https://pi.dev/docs/latest)链接**（`docs/xxx.md` 对应 `pi.dev/docs/latest/xxx`）；官方文档没覆盖的实现细节才回落仓库。**仓库里的 `docs/*.md` 与源码 `@earendil-works/pi-ai`（[earendil-works/pi](https://github.com/earendil-works/pi) monorepo 的 `packages/ai`）同级**，都能给 GitHub 链接就给。
- **【厂】** 上游厂商官方文档（DeepSeek / Qwen / Z.ai 等底模自己的规格）。
- **【台】** 平台文档 / 用户转贴（如 USTC 大模型平台用户指南的模型列表、价目、分层）。
- **【测】** 我方 curl / pi 实测（路由 header、`/model/info`、thinking 开关、图片、枚举探针等）。

> 【pi】本文 §1–§4 的 pi 行为以 [docs/models.md](https://pi.dev/docs/latest/models)、[docs/custom-provider.md](https://pi.dev/docs/latest/custom-provider) 为准，serializer/计费细节文档未覆盖处引 [pi-ai 源码](https://github.com/earendil-works/pi/tree/main/packages/ai/src)；§5.2 的具体端点数据是 2026-07 对 `api.llm.ustc.edu.cn` 与 pi `v0.80.6` 的实测快照，随 ACL / router / 版本变化，引用前复跑。

---

## 1. 自定义模型配在 `models.json`（不在 `/login`）

`/login` 里的 provider 列表是**硬编码的内置 provider**（Amazon Bedrock、Anthropic、DeepSeek… 33 个），**没有“自定义 URL + Key”这一项**——找不到是正常的。任意自定义端点走 `~/.pi/agent/models.json`，热加载（改完打开 `/model` 即生效，不重启）。

> 【pi】[docs/models.md](https://pi.dev/docs/latest/models)「Custom Models」；`/login` 只列内置 provider，自定义走 `models.json`。

最小可用例（OpenAI 兼容端点）：

```json
{
  "providers": {
    "my-gw": {
      "baseUrl": "https://host/v1",
      "api": "openai-completions",
      "apiKey": "sk-xxx",
      "models": [{ "id": "your-model-id" }]
    }
  }
}
```

`id` 之外全部可省（有默认值，见 §2）。配好后该 provider 出现在 `/model` 列表里（不是 `/login`）。需要 OAuth 或非标准流式协议才写 extension 用 `pi.registerProvider()`。

> 【pi】[docs/custom-provider.md](https://pi.dev/docs/latest/custom-provider)（`registerProvider` 用于 OAuth / 非标准协议）；普通 URL+Key 用 `models.json` 即可。

**两种入口一句话**：`openai-completions` 打 `POST /chat/completions`（经典 Chat Completions），`anthropic-messages` 打 `POST /v1/messages`（Claude 风格结构化内容块）。同一个 key 常常两条都能用——但 **baseUrl 拼法、thinking 控制方式、缓存 / 图片 / 工具字段都不同**，见下节对照表。

---

## <a id="models-fields"></a>2. `models.json` 结构与字段

一个 provider 块 = 顶层连接信息 + `models` 数组。

**注释与尾逗号**：`models.json` 先过 `stripJsonComments` 再 `JSON.parse`——**只认 `//` 行注释和尾随逗号，不支持 `/* */` 块注释**（是残缺 JSONC，不是完整 JSONC / JSON5）。想临时停用某个 provider / 模型，逐行加 `//` 注释掉即可；写成 `/* … */` 会让整个 `models.json` 解析失败（报 `Failed to parse models.json`）。

> 【pi】coding-agent [core/model-registry.ts](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/core/model-registry.ts) 用 `JSON.parse(stripJsonComments(content))`；[utils/json.ts](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/utils/json.ts) 的 `stripJsonComments` 自述「Strip `//` line comments and trailing commas」，`/* */` 原样留下 → parse 报错。
> 【测】2026-07-13：用 `/* */` 包 provider 块 → `Failed to parse models.json`；改 `//` 逐行注释 → `pi --list-models` 正常、该 provider 从列表消失。

**Provider 级字段**：

| 字段 | 含义 |
|---|---|
| `baseUrl` | 端点 URL（**带不带 `/v1` 见下面两入口对照**） |
| `api` | wire 协议：`openai-completions` / `openai-responses` / `anthropic-messages` / `google-generative-ai` 等 |
| `apiKey` | 可选。字面量 / `$ENV_VAR` / `!command`；由 `/login`、`auth.json` 或 CLI `--api-key` 提供时可省 |
| `models` | 该 provider 暴露的模型条目数组（**必须显式列，pi 不会自动拉 `GET /v1/models`**） |

> 【pi】[docs/models.md](https://pi.dev/docs/latest/models)「Provider Configuration」+「Value Resolution」（`apiKey` 三形态与解析顺序）。

### 2.1 两入口对照（openai-completions ↔ anthropic-messages）

这是接自定义端点最容易踩的地方，先摆清：

| 维度 | `openai-completions` | `anthropic-messages` |
|---|---|---|
| `baseUrl` 写法 | **带 `/v1`**：`https://host/v1` | **不带 `/v1`**：`https://host` |
| 底层 SDK 拼 path | pi 自己接 `/chat/completions` → `…/v1/chat/completions` | `@anthropic-ai/sdk` 自补 `/v1/messages` |
| 写错的后果 | 少 `/v1` → 404 | 多写 `/v1` → `…/v1/v1/messages` → **404**【测】 |
| thinking 控制 | 靠 `compat.thinkingFormat` 选 serializer（见 §3） | **原生 serializer**，无需 `thinkingFormat` |
| thinking「关」发什么 | 视 format：默认只发 `reasoning_effort`；`deepseek`/`zai` 发 `thinking:{type:"disabled"}` | 统一发 `thinking:{type:"disabled"}` |
| 缓存命中 usage 字段 | `prompt_tokens_details.cached_tokens` | `cache_read_input_tokens` / `cache_creation_input_tokens` |
| 图片消息 | `content` 里 `{type:"image_url", image_url:{url}}`（公网 URL 或 `data:image/png;base64,…`） | `content` 里 `{type:"image", source:{type:"base64", media_type, data}}` |
| 工具 | OpenAI function 格式 → `tool_calls` | Anthropic 格式 → `tool_use` |

> 【pi】baseUrl 拼接：`pi-ai` [openai-completions.ts](https://github.com/earendil-works/pi/blob/main/packages/ai/src/api/openai-completions.ts)`:532-534`（`new OpenAI({baseURL})`，SDK 接 `/chat/completions`）、[anthropic-messages.ts](https://github.com/earendil-works/pi/blob/main/packages/ai/src/api/anthropic-messages.ts)`:854`（`baseURL: model.baseUrl`，Anthropic SDK 自补 `/v1/messages`）；[docs/models.md](https://pi.dev/docs/latest/models)「Anthropic Messages Compatibility」/「OpenAI Compatibility」。
> 【测】2026-07-13：`GET/POST https://api.llm.ustc.edu.cn/v1/messages` → 200；同 key 打 `…/v1/v1/messages` → `404 {"detail":"Not Found"}`。坐实「anthropic 端 baseUrl 不能带 `/v1`」。

两条 anthropic-version 头 pi 会自动带，不用手填。

**配置角度**：只看「配起来省不省心」，`anthropic-messages` 更省事——① thinking 走原生 serializer 自动发对 `thinking:{type:…}`，不用像 openai 侧那样猜 `compat.thinkingFormat`（配错就「off 仍思考 / low 仍不思考」，见 §3.1）；② 缓存 pi **默认自动注入** `cache_control`（`cacheRetention≠none` 即开，见 §4.2），开箱即用、不用手标。但「配着省心」≠「后端真给力」：底模真按档想多久、缓存 / 工具在该端点是否真命中省钱，仍要逐项实测——§5.2 就实测出**此网关 openai 侧缓存全 miss、anthropic 侧反而命中省 ~87%**。按你要的模型 / 功能在哪个入口是一等公民来选。

### 2.2 Model 条目字段（全字段 + 默认值）

| 字段 | 必填 | 默认 | 含义 |
|---|---|---|---|
| `id` | 是 | — | 传给 API 的模型 ID |
| `name` | 否 | `id` | 人读标签，`--model` 模糊匹配也认它 |
| `api` | 否 | 继承 provider | 单模型覆盖 provider 的 `api` |
| `reasoning` | 否 | `false` | 是否支持扩展思考（**只是能力声明**，见 §3） |
| `thinkingLevelMap` | 否 | 省略 | pi 七档 → 厂商档位映射；`null` 隐藏不支持档 |
| `input` | 否 | `["text"]` | `["text"]` 或 `["text","image"]` |
| `contextWindow` | 否 | `128000` | 上下文窗口（token） |
| `maxTokens` | 否 | `16384` | 最大输出 token |
| `cost` | 否 | 全 0 | 每百万 token 费率（见 §4） |
| `compat` | 否 | 继承 provider `compat` | 兼容性覆盖，含 `thinkingFormat`、`maxTokensField` 等；与 provider 级 `compat` 合并 |

> 【pi】[docs/models.md](https://pi.dev/docs/latest/models)「Model Configuration」字段表与默认值。

**要点**：`models` 必须显式列——pi **不会**请求 `GET /v1/models` 自动生成条目。列表接口可帮你发现候选 ID，但常混别名 / 占位 / 无权限模型，每个条目的能力、上下文、输出上限仍要独立核验（见 §5）。`pi --list-models <pattern>` 可查 pi 最终解析出的 context/max-out/reasoning/image 元数据。

> 【pi】[docs/models.md](https://pi.dev/docs/latest/models)「Custom Models」：显式列 `models`，不自动导入 `/v1/models`。

`apiKey` 优先用 `$ENV` 或 `!command`，别把长期 key 写进可分享配置或前端。

---

### 2.3 在 pi 里选 / 切模型

配好后该 provider/model 出现在 `/model` 列表（不是 `/login`）。

- **交互**：`Ctrl+L` 或 `/model`（跨 provider 模糊搜）；`Ctrl+P` / `Shift+Ctrl+P` 循环「收藏 / scoped」模型；`/scoped-models` 配循环集。
- **旗标**：`pi --provider <id> --model <model>`，或合写 `pi --model <id>/<model>`，或带 effort `pi --model <id>/<model>:high`。
- **默认**：`settings.json` 的 `defaultProvider` / `defaultModel`；循环集 `--models "<id>/*,…"` 或 `enabledModels`。

> 【pi】斜杠命令 / 旗标 / 快捷键：[docs/usage.md](https://pi.dev/docs/latest/usage)、[cli/args.ts](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/cli/args.ts)、[core/slash-commands.ts](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/src/core/slash-commands.ts)、[docs/keybindings.md](https://pi.dev/docs/latest/keybindings)。

## <a id="thinking-layers"></a>3. effort / thinking：能力、档位、线格式是三件事

设置入口是 `pi --thinking high`、`pi --model "provider/model:high"`、交互 `Shift+Tab`、`settings.json.defaultThinkingLevel`；七档 `off | minimal | low | medium | high | xhigh | max`。但配自定义模型时要分清**三层**：

| 层 | 字段 | 只负责 | 不负责 |
|---|---|---|---|
| 能力声明 | `reasoning: true` | 让 pi 视为可思考、显示 thinking UI | 不决定请求发哪个 JSON 字段 |
| 档位映射 | `thinkingLevelMap` | 七档 → 厂商档；`null` 隐藏不支持档 | 不决定字段放 `reasoning`/`thinking`/别处 |
| 序列化方言 | `compat.thinkingFormat` | 告诉 `openai-completions` serializer 怎么编码开关 / effort | 不证明后端真支持这些档 |

> 【pi】[docs/models.md](https://pi.dev/docs/latest/models)「Model Configuration」「Thinking Level Map」；三层职责由 `reasoning` / `thinkingLevelMap` / `compat.thinkingFormat` 分担。
> 【pi】源码锚点：档位类型 `packages/ai/src/types.ts`（`ThinkingLevel`/`ModelThinkingLevel`）、`packages/agent/src/types.ts:289`；各家 serializer `packages/ai/src/api/{openai-codex-responses.ts:516-525, anthropic-messages.ts:796-1022, openai-completions.ts:600-668}`；七档→厂商档的 clamp `packages/ai/src/models.ts:408-418`；CLI 旗标 `cli/args.ts`（`--thinking`）。

### 3.1 `thinkingFormat` 各方言发什么（仅 `openai-completions` 用）

`thinkingFormat` 是 **pi 本地枚举**，字符串本身不发给服务端；它决定 serializer 往请求里写哪个字段：

| `thinkingFormat` | pi 生成的关键字段 |
|---|---|
| 不配（默认） | `reasoning_effort`；`off` 仅当 `thinkingLevelMap.off` 映射为字符串才显式发 |
| `deepseek` | `thinking:{type:"enabled"}` / `{type:"disabled"}` + 可选 `reasoning_effort` |
| `zai` | 同上；开启时再带 `clear_thinking:false` + 可选 `reasoning_effort` |
| `qwen` | 顶层 `enable_thinking:boolean` |
| `qwen-chat-template` | `chat_template_kwargs:{enable_thinking, preserve_thinking:true}` |
| `chat-template` | 按 `chatTemplateKwargs` 自定义模板参数 |
| `openrouter` / `together` / `string-thinking` / `ant-ling` | 各自的 `reasoning{}` 或字符串式方言 |

> 【pi】方言取值：[docs/models.md](https://pi.dev/docs/latest/models)「OpenAI Compatibility」的 `thinkingFormat` 行；各方言实际字段：`pi-ai` [openai-completions.ts](https://github.com/earendil-works/pi/blob/main/packages/ai/src/api/openai-completions.ts) 的 `compat.thinkingFormat` 分支（`deepseek` 发 `thinking.type`、`qwen` 发顶层 `enable_thinking`、`zai` 带 `clear_thinking` 等）。

**为什么自定义域名容易错**：pi 按 baseUrl 自动探测兼容性——`api.deepseek.com`、Z.ai 等已知地址能命中厂商规则；**校园 / 公司网关域名通常只落到默认 `openai`**。于是：

- 选 `off` 时默认分支可能什么都不发；底模若默认 thinking=on → 「off 仍思考」。
- 选 `low` 时只发 `reasoning_effort:"low"`；底模真正开关若是 `enable_thinking` 或 `thinking.type` → 「low 仍不思考」。

修法：给该模型显式写对 `compat.thinkingFormat`（具体端点选哪个见 §5，别在这里假设）。

### 3.2 `anthropic-messages` 不用这套枚举

anthropic 端有独立 serializer：`off` 发 `thinking:{type:"disabled"}`；开启时对旧式模型发 budget-based thinking、对 `forceAdaptiveThinking` 模型发 adaptive thinking + `output_config.effort`。所以 **anthropic provider 的模型不用配 `thinkingFormat`**。

> 【pi】`pi-ai` [anthropic-messages.ts](https://github.com/earendil-works/pi/blob/main/packages/ai/src/api/anthropic-messages.ts) 的 thinking serializer（budget / adaptive 两路）。

> 别把档名当算力承诺：`thinkingLevelMap` 只做 pi 七档 → 厂商档的名义映射，不保证后端真按档想更久。要精确反映某底模只有 `high/max` 之类，得显式写 `thinkingLevelMap`。

---

## 4. cost 与缓存计费

### 4.1 cost 字段

`cost` = `{ input, output, cacheRead, cacheWrite }`，**每百万 token 费率**；不填全 0（pi 显示 $0）。可选 `tiers` 做超阈值分档定价。

> 【pi】[docs/models.md](https://pi.dev/docs/latest/models)「Model Configuration」：`cost` = per-million-token rates，默认全 0。

**单位说明**：pi **没有货币概念**——计算就是 `(rate / 1e6) × tokens`，结果一律**前面贴 `$`**、保留 3 位小数显示。你填什么数它照单全收当美元显示；填多少就等于「每百万 token 多少（某币种）」，pi 只负责乘和贴 `$`。

> 【pi】`pi-ai` [models.ts](https://github.com/earendil-works/pi/blob/main/packages/ai/src/models.ts)：`usage.cost.input = (rate.input / 1000000) * usage.input`（output/cacheRead/cacheWrite 同理，求和为 total）；显示层 `$${cost.toFixed(3)}`，无货币换算。

### 4.2 缓存命中谁说了算：服务端 `usage` 自报

pi **不自己判断缓存命不命中**——服务端在每次响应的 `usage` 里报了多少 token 命中缓存，pi 只读数、拆桶、乘费率：

- **openai-completions**：`prompt_tokens` 是总输入（**含**缓存部分）；`prompt_tokens_details.cached_tokens`（DeepSeek 系用 `prompt_cache_hit_tokens`）= 命中数 → `cacheRead`；`cache_write_tokens`（多数厂商不报 → 0）→ `cacheWrite`；`input = prompt_tokens − cacheRead − cacheWrite`（避免重复计）。
- **anthropic-messages**：直接分字段——`cache_read_input_tokens` → cacheRead、`cache_creation_input_tokens` → cacheWrite、`input_tokens` → input。

> 【pi】`pi-ai` [openai-completions.ts](https://github.com/earendil-works/pi/blob/main/packages/ai/src/api/openai-completions.ts) 的 usage 解析（`cached_tokens` 拆 `input`/`cacheRead`）、[anthropic-messages.ts](https://github.com/earendil-works/pi/blob/main/packages/ai/src/api/anthropic-messages.ts) 的 `cache_read_input_tokens` / `cache_creation_input_tokens` 映射。

**推论 / 坑**：整条链全靠**服务端自报**。网关若不报 `cached_tokens`（或报 0），pi 就把全部算成全价 input，哪怕物理上真命中；反过来 pi 也无法验证服务端的缓存账。想确认缓存真省钱，连发两次同长前缀、看 `usage` 的 `cacheRead` 是否跳上去（`/session` 里的 `R` 就是它）。另外 openai 端多数厂商不报 `cache_write_tokens`，写缓存往往折进 `input` 按全价计——所以有的平台价目里只有「缓存命中（读）」折扣、没有单列「写缓存」价。

**跨 provider 横向实测**（2026-07-13，pi `v0.80.6`，紧凑连发两次同前缀、`off`，读 pi 归一后的 `cacheRead`）：

| provider（端点） | 协议 | 底模 | call2 `cacheRead` | 结论 |
|---|---|---|---:|---|
| 官方 DeepSeek `api.deepseek.com` | openai-completions | DeepSeek V4 Pro | **7424**（省 ~99%） | 官方自动缓存、透传 `prompt_cache_hit_tokens` ✅ |
| USTC `…/v1` | openai-completions | **同款** DeepSeek V4 Pro | **0** | 网关不报缓存字段、全价 ❌ |
| MiniMax-cn `api.minimaxi.com/anthropic` | anthropic-messages | MiniMax-M3 | **11541**（≈100%） | pi 自动 `cache_control` 命中 ✅；**首发常冷启动**（同前缀首轮仅 114、次轮才满） |
| USTC（不带 `/v1`） | anthropic-messages | DeepSeek V4 Pro | **7168**（省 ~87%） | pi 自动 `cache_control` 命中 ✅ |

**本质**：能否吃到缓存 = openai 侧「端点是否透传缓存 usage」＋ anthropic 侧「pi 是否自动标 `cache_control` 且服务端认」，**跟底模是谁基本无关**——同一 DeepSeek V4 Pro，官方 openai 端省 ~99%、USTC openai 端一分不省。

> 【测】上表 pi 端到端 `--mode json` 实跑 `cacheRead`（deepseek-v4-pro / MiniMax-M3，2026-07-13，raw HTTP 复核字段）。MiniMax「114→11541」是同一前缀连测的冷 / 热两轮，说明首发未必满命中。
> 【pi】**pi 默认给这俩内置 provider 配的 wire 协议**（§2.2 四选一：`openai-completions` / `openai-responses` / `anthropic-messages` / `google-generative-ai`）——DeepSeek 走 **`openai-completions`**（baseUrl `api.deepseek.com`，[providers/deepseek.ts](https://github.com/earendil-works/pi/blob/main/packages/ai/src/providers/deepseek.ts)）、MiniMax-cn 走 **`anthropic-messages`**（baseUrl `api.minimaxi.com/anthropic`，[providers/minimax-cn.ts](https://github.com/earendil-works/pi/blob/main/packages/ai/src/providers/minimax-cn.ts)）。上表差异根因也在 pi 侧：openai 端 pi 仅对 `api.openai.com` baseUrl 发 `prompt_cache_key`、第三方不发，能否命中全看服务端自动缓存并回报 `cached_tokens`/`prompt_cache_hit_tokens`（[openai-completions.ts](https://github.com/earendil-works/pi/blob/main/packages/ai/src/api/openai-completions.ts)）；anthropic 端 pi **默认自动注入** `cache_control:ephemeral`（`getCacheControl` 默认 `short`、`≠none` 即开，标在 `system`＋末 `user`＋`tools` 三断点），且 `cacheRead` 从 `message_start`／`message_delta` 两处都读（兼容 USTC 这种把 `cache_read` 塞进 `message_delta` 的非标准网关）（[anthropic-messages.ts](https://github.com/earendil-works/pi/blob/main/packages/ai/src/api/anthropic-messages.ts)）。

---

### <a id="context-window"></a>4.3 上下文长度与压缩

**无 `--context-window` 旗标**——上下文窗口是**模型属性** `contextWindow`（见 §2.2，可用 `modelOverrides` 覆盖某模型）。运行期靠：

- **自动压缩**：`settings.json.compaction.{enabled, reserveTokens（默认 16384）, keepRecentTokens（默认 20000）}`，触发条件 `contextTokens > contextWindow − reserveTokens`；手动 `/compact [指令]`。
- **footer 实时用量**：`↑` 输入 `↓` 输出 `R` 缓存读 `W` 缓存写 `CH` 命中率；`/session` 看 token 与成本。
- **`PI_CACHE_RETENTION=long`**：延长直连 provider 的 prompt 缓存（Anthropic 1h / OpenAI 24h）。

> 【pi】[docs/settings.md](https://pi.dev/docs/latest/settings)（`compaction`）、[docs/models.md](https://pi.dev/docs/latest/models)（`modelOverrides.contextWindow`）、[README](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/README.md)（`PI_CACHE_RETENTION`、footer 用量符号）。

## 5. 验证 + 实战

配置只是把字段填对，**端点到底是什么、每个参数真不真吃、模型规格是不是真的**，得靠探针验证。§5.1 是通用方法论（与 pi 无关，换任何工具都能用），§5.2 是一份具体端点的实测快照。

### 5.1 通用探针方法论（逆向刻画一个 LLM 端点）

**证据梯级**（从强到弱用，别反过来）：

1. **部署 / 路由元数据**：受控 router config、LiteLLM `GET /model/info`、模型 UUID、真实 upstream 名；能接触部署端再看镜像 digest / 权重目录 / 启动参数。
2. **官方平台文档 + 上游底模官方文档**：前者证明平台声称提供什么，后者证明底模规格；不能互相替代。
3. **响应头与错误链**：`x-litellm-*`、upstream 异常、fallback 表、内部 model group；能证明网关 / 路由行为，不能证明权重内容。
4. **差分行为探针**：图像 / thinking 开关 / 工具结构 / 长上下文 / 特有 tokenizer；一次回答不够，要多组随机输入 + 对照组。
5. **模型自报身份**：只能当线索——模型可能不知道自己版本、被 system prompt 改名、复述训练语料或幻觉。「它说自己是 X」既不能证真也不能单独证伪。

**一套不会自欺的探针**：

- **身份 / 路由**：先 `GET /v1/models`，再查更强的 `GET /model/info`（LiteLLM 会暴露 `litellm_params.model`、credential 名、固定 `chat_template_kwargs`、协议支持）；跨 OpenAI / Anthropic 两协议比较**响应头 `x-litellm-model-id`**，相同 = 同一 router entry，比对自然语言答案可靠得多。
- **参数是否真吃**：传**合法开 / 合法关 / 非法值**三组。只看 HTTP 200 不够——非法值**报不报错、错从哪来**才是硬证据：错误里带 `DeepseekException` = 一路透传到上游底模校验；错误里带 `litellm.BadRequestError` + fallback 表 = 网关这层（LiteLLM）拦的。非法值报错还会**顺手吐出合法枚举全集**。
- **指纹辨实现**：原生 DeepSeek 返回带 `system_fingerprint`、`prompt_cache_hit_tokens` 等自有字段；经 LiteLLM 归一化的返回会包一层 `provider_specific_fields:{}`——**看到后者基本可判是 LiteLLM 前置代理，不是厂商原生云**。
- **枚举集合比对**：同一个参数（如 `reasoning_effort`）在「疑似上游」和「厂商官方」两处各传非法值，比对报错列出的合法档位集合——**不一致 = 不是同一份校验代码 = 不是同一后端**。
- **图片**：生成**随机多色 / 随机文字**图，至少两组，问题里别泄露答案；1×1 常见色、公开 demo 图易被猜中或记住。空间提示写成 `TL, TR, BL, BR` 或明确顺时针，别把「能看见」和「方位指令失误」混为一谈。
- **工具**：分别测 auto 与 forced `tool_choice`，完成一次「tool call → tool result → final answer」闭环；只生成 JSON 文本不算工具调用。
- **缓存**：同一长前缀连调两次，查明确的 cached-token 字段；延迟下降只能做旁证。
- **极限**：接受 `max_tokens:384000` 不等于能稳定生成 384K；上下文 / 输出上限要真实长请求 + tokenizer 计数 + stop reason 才算验证。
- **故障**：把 ACL、限流、临时下线、后端连接失败与「模型是假」分开；隔时重试 + 看路由元数据。

**网关运营侧泄露清单**（客户端记录审计结果时也应脱敏）：LiteLLM 宽松配置可能在普通 key 可见响应里泄露模型白名单、fallback 路由、credential 名、内部 upstream URL / service DNS、版本、RPM、预算与累计 spend。别把 raw header / body 直接提交进 Git。

### 5.2 实战快照：USTC LiteLLM 网关（2026-07）

以下是对**一个具体校园端点**用上面方法跑出来的结果，**不是 pi 或各底模的永久保证**。USTC 用户指南主推四个底模：DeepSeek-V4-Flash、DeepSeek-V4-Pro、Qwen3.6-35B-A3B、Qwen3.6-27B；`glm-5.2` 是 API 额外开放项。协议页只承诺 OpenAI / Anthropic 兼容，未承诺后者 tool/cache 更优。

> 【台】USTC 用户指南 `models` / `application` / `protocol` 页（OpenAI 节标题带「（推荐）」，Anthropic 节不带）。

**别名 ↔ 真实后端（以 `/model/info` + `x-litellm-model-id` 为准）**：

| 对外 ID | router 后端 | 默认 thinking | 结论 |
|---|---|---:|---|
| `deepseek-v4-pro` | `deepseek-v4-pro` | 开 | Pro |
| `deepseek-v4-flash-ascend` | `deepseek-v4-flash-ascend` | 开 | Flash 的昇腾部署 |
| `qwen-chat` | `qwen36-35b-a3b` | 关 | 35B-A3B 的 chat 别名 |
| `qwen-reasoner` | `qwen36-35b-a3b` | 开 | 35B-A3B 的 reasoner 别名 |
| `qwen3.6-chat` | `qwen36-27b` | 关 | **是 27B，不是 35B** |
| `qwen3.6-reasoner` | `qwen36-27b` | 开 | 27B 的 reasoner 别名 |
| `glm-5.2` | `glm-5.2` | 开 | GLM-5.2 |
| `claude-haiku-4-5` | `qwen36-35b-a3b` | 关 | Claude 名，实际路由到 Qwen |
| `claude-sonnet-4-6` | `qwen36-27b` | 关 | Claude 名，实际路由到 Qwen |

> 【测】2026-07-12/13：`GET /model/info` + 各别名 `x-litellm-model-id` 响应头交叉核对（同别名两协议 model-id 相同 → 同 router entry）。
> ⚠️ **别用名字直觉猜规模**：`qwen3.6-*` 是 27B、`qwen-*` 才是 35B-A3B；`chat`/`reasoner` 只是同一底模的非思考/思考两种模式，不是两个不同模型。

**关键发现：USTC 不是 DeepSeek 官方后端的透传，是自建权重 + LiteLLM**。三证：① `reasoning_effort` 非法值报错列出的合法档，USTC 是 7 档（`none/minimal/low/medium/high/xhigh/max`）、DeepSeek 官方是 5 档（无 `none`/`minimal`）；② `thinking.type` 非法值 USTC 200 静默、官方 400 报错（且官方多一个 `adaptive`）；③ USTC 返回带 LiteLLM 的 `provider_specific_fields:{}`、无官方的 `system_fingerprint`。

> 【测】非法值探针 + 与 `auth.json` 里 DeepSeek 官方 key 的返回逐字对比。
> 【厂】DeepSeek 官方 API 文档的 `thinking` / `reasoning_effort` 与旧 `deepseek-chat`/`deepseek-reasoner` 分流将于 2026-07-24 弃用。

**规格证据**：

| 底模 | reasoning | 图片 | context | max output | 来源 |
|---|---:|---:|---:|---:|---|
| DeepSeek V4 Pro | 是 | 否 | 1M | 384K | 【厂】DeepSeek 官方 +【台】USTC |
| DeepSeek V4 Flash | 是 | 否 | 1M | 384K | 同上（USTC 为 Ascend 部署别名） |
| Qwen3.6-35B-A3B | 是 | 是 | 262,144 | 81,920 | 【厂】Qwen model card +【台】USTC +【测】图片 |
| Qwen3.6-27B | 是 | 是 | 262,144 | 81,920 | 同上 |
| GLM-5.2 | 是 | 否 | 1M | 128K | 【厂】Z.ai 官方页（Text / 1M / 128K / thinking） |

> 【厂】Qwen card 写可扩到 1,010,000，但 USTC 明确提供 262K，故取 262,144；`81,920` 是官方调用示例反复用、网关接受的值。DeepSeek/GLM 的 max output 是官方规格卡直接声明。

**费率（人民币 ¥ / 百万 Token，pi 一律显示 `$`）**：

| 模型 | 输入 | 输出 | 缓存命中 | 来源 |
|---|---:|---:|---:|---|
| deepseek-v4-pro | ¥4 | ¥4 | ¥0.4 | 【台】指南 +【测】`/model/info` |
| deepseek-v4-flash-ascend | ¥2 | ¥2 | ¥0.2 | 同上 |
| qwen-reasoner / qwen3.6-reasoner | ¥1 | ¥1 | ¥0.1 | 同上 |
| glm-5.2 | ¥8 | ¥8 | ¥0.8 | 同上 |

> 【台】USTC 用户指南每模型页明写「输入 | 缓存命中 / 百万 Token」「输出 / 百万 Token」，单位是人民币 ¥。
> 【测】`/model/info` 自报的每-token 费率与之逐一相等（也是网关记账用的值）；输入=输出；`cacheWrite` 无平台单列价，取 `/model/info` 的 cache-creation 值（= cacheRead）。pi 显示 `$` 只是符号，实际数值 = 网关 `x-litellm-response-cost`（人民币），非美元。

**图片 / 工具 / 缓存 / thinking 端到端（经 pi `v0.80.6`）**：

| 项目 | openai-completions | anthropic-messages | 正确解读 |
|---|---|---|---|
| 文本 | 五个模型均通过 | 同左 | 可用性要与身份分开判断 |
| 图片 | 两个 Qwen 正确读随机多色图 | 同样成功 | 只有两种 Qwen 是 VL；DeepSeek/GLM 纯文本 |
| auto tool calling | DeepSeek/Qwen 实际执行 `read` 成功 | 同样成功 | 不能说 Anthropic tool 更好 |
| 强制 `tool_choice` | 某些请求把参数写进 reasoning 而非 `tool_calls` | 某些写进 thinking 而非 `tool_use` | auto 成功不代表 forced 完全兼容 |
| prompt cache | **此网关不报缓存字段** → `cacheRead` 恒 0、全价 | pi 自动加 `cache_control`，紧凑连发即命中（`cacheRead` 7168、省 ~87%） | **反直觉：此端点 anthropic 才省钱、openai 拿不到缓存** |
| thinking `off/high` | 配 `thinkingFormat`（deepseek/zai）后经 pi 正确切换 | 原生 serializer 正确切换 | serializer 差异，非模型能力差异 |

> 【测】2026-07-13 pi `--mode json` 实跑：五模型 `off` 无 reasoning、`high` 有；两个 Qwen 读对随机四色图；`read` 工具闭环成功。thinking 细节：底模都吃顶层 `thinking:{type:"enabled"|"disabled"}`；顶层 `enable_thinking`（`qwen` 格式）被网关 `400 Unsupported parameter` 拒——所以 openai 侧给 DeepSeek 两款 + 两个 Qwen `reasoner` 配 `thinkingFormat:"deepseek"`、GLM 配 `"zai"`；anthropic 侧不配。

> 【测】2026-07-13 缓存实测（deepseek-v4-pro，raw HTTP + pi `v0.80.6` 端到端双验）：**openai 侧此网关二次请求 usage 里 `cached_tokens`/`prompt_cache_hit_tokens` 一个都不报** → pi `cacheRead` 恒 0、全价（pi 对非 `api.openai.com` 的 baseUrl 也不发 `prompt_cache_key`，源码 [openai-completions.ts](https://github.com/earendil-works/pi/blob/main/packages/ai/src/api/openai-completions.ts)）。**anthropic 侧 pi 默认自动注入 `cache_control`**（`system` + 末条 `user` block + `tools` 三个断点，`getCacheControl` 默认 `short`、`≠none` 即开），紧凑连发两次 call2 `cacheRead=7168`、成本 `¥0.030→¥0.004`（省 ~87%）。两个坑：① USTC 建缓存**不报** `cache_creation`（pi `cacheWrite` 恒 0、价目也无「写缓存」列）；② USTC 把 `cache_read` 塞进 SSE 的 `message_delta`（非标准，Anthropic 标准放 `message_start`）——pi `message_start`/`message_delta` 两处都读故仍拿到，但两发间隔一旦拖过 ephemeral 短 TTL 就 miss（首轮因中间插 openai 调用而漏，紧凑重发即命中）。

**最终配置（两协议各 5 个不同底模）**——`openai-completions` 侧带 `thinkingFormat` + `cost`，`anthropic-messages` 侧同样 5 模型但**不带** `thinkingFormat`（原生 serializer）：

```jsonc
// USTC-openai (api: openai-completions, baseUrl: https://api.llm.ustc.edu.cn/v1)
{ "id": "deepseek-v4-pro",          "name": "DeepSeek V4 Pro",  "reasoning": true, "input": ["text"],
  "contextWindow": 1000000, "maxTokens": 384000,
  "cost": { "input": 4, "output": 4, "cacheRead": 0.4, "cacheWrite": 0.4 },
  "compat": { "thinkingFormat": "deepseek" } }
{ "id": "deepseek-v4-flash-ascend",  "name": "DeepSeek V4 Flash", ... "cost": {2/2/0.2/0.2}, "thinkingFormat": "deepseek" }
{ "id": "qwen-reasoner",     "name": "Qwen 3.6 35B-A3B", "input": ["text","image"], "contextWindow": 262144, "maxTokens": 81920,
  "cost": {1/1/0.1/0.1}, "thinkingFormat": "deepseek" }   // 真 35B
{ "id": "qwen3.6-reasoner",  "name": "Qwen 3.6 27B",    "input": ["text","image"], ... "cost": {1/1/0.1/0.1}, "thinkingFormat": "deepseek" }
{ "id": "glm-5.2",           "name": "GLM-5.2", "input": ["text"], "contextWindow": 1000000, "maxTokens": 128000,
  "cost": { "input": 8, "output": 8, "cacheRead": 0.8, "cacheWrite": 0.8 }, "compat": { "thinkingFormat": "zai" } }
```

> 【测】本机 `~/.pi/agent/models.json` 现状即此（`anthropic` 侧同 5 模型、同 `cost`、无 `thinkingFormat`）。

**「这 5 个之外」的别名怎么读**（同一 key 都可调，选型时知道即可）：

- `qwen-chat` / `qwen3.6-chat`：分别是 35B-A3B / 27B 的**固定非思考**模式（`thinking.type` 也开不起来）。想要低延迟纯回答就选它们并标 `reasoning:false`。
- `deepseek-v4-flash`（非 -ascend）：DeepSeek Flash 的另一部署；`deepseek-v4-flash-ascend1`：700K 上下文的变体。
- `smart/default`、`smart/reasoning`：网关侧的**自动择优**路由组（后端可能落到 qwen36-27b / deepseek-v4-pro 等多个），不是单一底模。
- `glm-chat` / `glm-reasoner`：后端是 `glm-5`（注意不是 `glm-5.2`）的非思考 / 思考别名。
- `claude-haiku-4-5` / `claude-sonnet-4-6`：**Claude 名字的空壳别名，实际路由到 Qwen**（见上表）——别被名字骗。

> 【测】以上别名的后端与 thinking 默认值同样出自 `/model/info`。
