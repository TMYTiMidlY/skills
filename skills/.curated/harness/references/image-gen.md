# Codex 订阅生图接入

本篇介绍通过 Codex 订阅生成、编辑图片时的调用路径、输入输出、组件选择和验证方法，并以 CLIProxyAPI（CPA）说明具体接口用法。公共 OpenAI Images API 只作为明确标注的对照；它的参数规范不能直接当作订阅后端的承诺。

Codex 内置工具的参数、思考程度、启用条件和认证机制见 [Codex 生图运行时](codex.md#image-runtime)及[订阅登录凭据](codex.md#subscription-auth)。这里讨论如何接入图片能力，不重复实现一个 Agent、MCP server 或账户管理平台。

## <a id="routes"></a>Codex 订阅生图的调用路径

外部接口名称不能说明内部如何生成图片。判断一个组件时，应沿请求追踪到实际目标端点，同时确认是否存在主模型编排和 Codex 进程。

### <a id="routes-images"></a>订阅 Images 端点

直连方式由客户端准备图片请求，使用订阅认证访问图片后端，再解析返回的图片数据。所核 Codex 实现使用以下路径：

```text
调用方 → 图片客户端 → /backend-api/codex/images/generations
                     或 /backend-api/codex/images/edits
       ← 图片结果   ← 图片后端
```

这条图片请求本身不要求启动 Codex CLI、app-server 或额外的文字模型。调用方可以是程序库、HTTP 代理或宿主插件；它们仍需负责认证、输入处理和结果交付。

> Codex 客户端的 JSON POST 见 [ImagesClient](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/codex-api/src/endpoint/images.rs#L35-L79)。这些是所核订阅路径，不是公共 `api.openai.com/v1/images/*` 的使用授权或长期兼容承诺。

### <a id="routes-responses"></a>订阅 Responses 路径

另一种方式向 Codex 的 Responses 端点发送请求，由主模型调用 `image_generation` 图片工具。组件需要处理主模型的输出事件，并从图片工具结果中提取图片。

```text
调用方 → 适配组件 → /backend-api/codex/responses
                     ├─ 主模型
                     └─ image_generation 图片工具
       ← 图片结果   ← Responses 事件或最终结果
```

该方式可以完全通过 HTTP 实现，不一定启动本地 Codex Agent，但它保留了主模型这一层。请求的顶层模型、图片工具模型及它们各自的参数不能混为一组配置。

> Sub2API 的一个实例见 [图片 Responses 请求构造](https://github.com/Wei-Shaw/sub2api/blob/98d86915becae9fe9491a91ffc6defd5235c8d2b/backend/internal/service/openai_images_responses.go#L358-L444)：主模型写在顶层，图片模型、尺寸和质量写入 `image_generation` 工具。代码能证明转换方式，不能代替特定账户的真实验收。

### <a id="routes-agent"></a>Codex Agent 包装

Agent 包装方式由外层工具启动或连接 Codex，让 Codex 理解要求、调用内置图片工具、检查结果并回复。外层一次调用可能包含多次模型请求和多次生图。

因此，外层工具耗时不能直接当作图片后端耗时。排查额外等待、提示词改写和重画行为时，查看 [Codex 的思考程度](codex.md#image-reasoning)及[生图计时边界](codex.md#image-timing)。原生 Images、Responses 和 Agent 包装分别提供不同的控制方式，不据此直接判断底层图片模型孰强孰弱。

## <a id="edit-inputs"></a>Codex 订阅生图的编辑入口

编辑图片同时涉及用户意图、上传格式和下游接口。JSON、base64、multipart 是通用数据格式；具体字段、图片数量和遮罩语义则属于特定入口。

### <a id="edit-images-json"></a>订阅 Images 端点的 JSON 参考图

所核 Codex 图片客户端以 JSON 表达参考图，`images` 是数组，每项包含 `image_url`。内置工具先取得获准使用的参考图片，再构造下游请求；调用内置工具时的参数并不是这个 JSON 请求体。

| 对象 | 表达方式 | 核对重点 |
|---|---|---|
| 内置工具的参考图选择 | 本地参考图路径或最近会话图片选择参数 | 当前工具 schema、会话可见性和读取权限 |
| 下游图片请求 | `images: [{"image_url": "data:<mime>;base64,<data>"}]` | 端点实际接受的引用类型和数据大小 |
| 用户的编辑意图 | 提示词说明目标图、参考作用和保留条件 | 不把“参考风格”自动解释成逐像素编辑 |

base64 将二进制编码为文本，不是加密，也不会提高画质。编码后的体积约为原字节数的 4/3，即增加约三分之一，另有少量填充和封装开销。网络体积、解码后字节数和解码后的像素内存需要分别考虑。

> Codex 的 [编辑请求结构](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/codex-api/src/images.rs#L18-L36)及[参考图分支](https://github.com/openai/codex/blob/73a1148c9c775c2a4616ce5096291740a00ed68a/codex-rs/ext/image-generation/src/tool.rs#L419-L487)说明了该客户端的构造方式。完整工具契约见 [Codex 图片请求的构造](codex.md#image-request)。base64 的编码规则见 [RFC 4648](https://www.rfc-editor.org/info/rfc4648/#section-4)。

不能因为这里使用 JSON，就把它称为 Codex 独有格式。公共 Images 编辑接口也有 JSON 入口，区别仍需落实到认证、端点和具体参数。

### <a id="edit-responses-input"></a>订阅 Responses 路径的图片输入

Responses 适配器可以把图片放入消息的 `input_image` 内容块，并把编辑操作和输出要求写入图片工具配置。它不应直接照搬订阅 Images 请求的整个 `images` 数组。

核对时分别查看输入图片、编辑目标、工具的 `action`、遮罩引用和主模型指令。组件可能对上传图片进行压缩、缩放或格式转换，也可能改写提示词；这些行为应明确说明，而不能隐藏在“兼容 Images API”的标签后面。

> 所核 Sub2API 将上传图片转为 data URL，生成 `input_image` 消息，并为图片工具设置 `action`，见 [请求转换](https://github.com/Wei-Shaw/sub2api/blob/98d86915becae9fe9491a91ffc6defd5235c8d2b/backend/internal/service/openai_images_responses.go#L367-L444)。这是该版本适配器的行为，不代表所有订阅 Responses 客户端都采用相同转换。

### <a id="edit-cpa-conversion"></a>CLIProxyAPI 的编辑格式转换

CPA 对外可以接受 JSON 编辑或 multipart 文件上传。multipart 将文字字段和文件内容分成多个部分放在同一条请求中，不表示批量任务或同时生成多张图。

| 入口 | 图片字段 | CPA 所核原生分支的处理 |
|---|---|---|
| JSON 编辑 | `images` 数组中的引用 | 图片请求准备层保留主体，规范模型及流式字段 |
| multipart 编辑 | `image` 或 `image[]` 文件字段 | 文件转成 data URL，再构造 `images[].image_url` |
| multipart 遮罩 | `mask` 文件字段 | 转换为 `mask.image_url`；转换本身不验证精确编辑效果 |

使用 HTTP 客户端构建 multipart 时，让客户端生成 boundary，即各部分之间的分隔标识。不要手工填写一个缺少 boundary 或与请求体不一致的 `Content-Type`。CPA 的具体调用示例见 [JSON 编辑](#cpa-edit-json)和 [multipart 编辑](#cpa-edit-multipart)。

> multipart 定义见 [RFC 7578](https://www.rfc-editor.org/info/rfc7578/#section-4)；CPA 转换见 [文件和字段处理](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L527-L640)。公共编辑接口同样支持 multipart 和 JSON，见 [OpenAI 编辑接口定义](https://github.com/openai/openai-openapi/blob/21cb7e98d8166a691a0eb8679a90419eb816cf35/openapi.json#L4189-L4193)。某个库只接收 multipart，不等于公共 API 只有 multipart。

### <a id="edit-masks"></a>遮罩参数的入口差异

遮罩用于表达需要修改的区域，但“有 mask 字段”“能转发 mask”和“实现符合预期的区域编辑”是不同层次的支持。

| 检查对象 | 需要确认的内容 |
|---|---|
| 调用入口 | 是否暴露遮罩参数；使用文件、URL 还是 file ID |
| 格式转换 | 是否真实传递遮罩，还是改成额外参考图和文字说明 |
| 后端契约 | 遮罩格式、尺寸、透明通道和参考图对应关系 |
| 结果 | 修改区域是否正确，保留区域是否满足要求 |

公开 API 的遮罩要求不能未经核对就套到订阅端点。反过来，某个代理本地拒绝遮罩，也不能证明所有订阅入口均不支持。需要精确区域编辑时，单独验收；语义编辑成功不等于其他像素完全不变。

> CPA 的 [原生透传测试源码](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images_test.go#L181-L315)覆盖了引用及遮罩字段处理。这里核对的是测试断言，不是后端对 file ID、遮罩或多图的真实验收。

## <a id="model-parameters"></a>公共 API 对照中的模型参数

比较参数之前，先分清模型公开能力、工具暴露范围、适配器处理和服务端实际执行结果。本章以公共 API 作为对照，不能将其字段表直接解释成 Codex 订阅端点的保证。

### <a id="model-identifiers"></a>GPT Image 2.5 的模型标识

OpenAI 于 2026-09-08 公布 ChatGPT Images 2.5，并宣布向 ChatGPT、ChatGPT Work 和 Codex 各档位提供。同时，公共 API 发布以下模型：

| 公共 API 模型 | 官方定位 | 日期快照 |
|---|---|---|
| `gpt-image-2.5-flare` | 较快的高质量日常生成，包含质量和编辑改进 | `gpt-image-2.5-flare-2026-09-08` |
| `gpt-image-2.5-sunburst` | 注重精细创作和编辑控制，生成时间较长 | `gpt-image-2.5-sunburst-2026-09-08` |

截至 2026-09-10，官方模型页仍列出上述 2.5 型号和日期快照。因此，“2.5 已发布”和“Codex 请求里仍写 `gpt-image-2`”可以同时成立：Codex 稳定版 0.153.4、近期核对的 0.154.0 alpha 版本及当日主线，内置工具仍填写旧名称，具体版本见[Codex 请求构造](codex.md#image-request)。这不能证明订阅实际仍运行旧图片模型，也不能反过来证明每个订阅请求已经映射到 Flare 或 Sunburst。

> 2026-09-10 核对的公共 API 阅读入口：[Flare 模型页](https://developers.openai.com/api/docs/models/gpt-image-2.5-flare)、[Sunburst 模型页](https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst)。公共 API 可以显式选择这两个型号；内置订阅工具、CPA 模型路由和服务端内部映射是不同的控制位置，不能直接把同一名称替换进所有入口。

> 发布范围见 [ChatGPT Images 2.5 公告](https://openai.com/index/introducing-chatgpt-images-2-5/)；公共模型枚举见 [OpenAPI 模型定义](https://github.com/openai/openai-openapi/blob/21cb7e98d8166a691a0eb8679a90419eb816cf35/openapi.json#L26415-L26443)。Codex 的客户端门控及其与公告范围的差异见 [内置工具启用条件](codex.md#image-availability)。公告不替代客户端和账户的实际可用性检查。

### <a id="public-size"></a>公共 API 的尺寸规则

公共 GPT Image 2 和 2.5 支持独立的 `size="WIDTHxHEIGHT"`，不只有旧模型常见的三个标准尺寸。2.5 公开指南列出的约束如下：

| 项目 | 公共 API 的要求 |
|---|---|
| 宽、高 | 都是 16 的倍数 |
| 宽高比 | 介于 1:3 和 3:1 |
| 单边 | 不超过 3840 像素 |
| 总像素 | 655,360 至 8,294,400 |
| 实验范围 | 超过 `2560×1440` 总像素量的分辨率 |

`1920×1080` 中的 1080 不是 16 的倍数，不能把它直接作为符合上述规则的显式尺寸示例。`2048×1152` 满足该比例和倍数要求；若最终文件必须是 `1920×1080`，可以在生成后明确执行缩放，并分别记录原始尺寸和交付尺寸。不要把后处理文件宣称为模型直接生成的原始结果。

> 自定义尺寸适用模型和倍数规则见 [Python SDK v3.10.0 参数定义](https://github.com/openai/openai-python/blob/v3.10.0/src/openai/types/image_generate_params.py#L104-L130)；边长、总像素和实验范围见 [GPT Image 2.5 生成指南](https://developers.openai.com/api/docs/guides/image-generation#size-and-quality-options)。在线指南是持续更新的阅读入口，使用新模型或升级组件时应重新核对其当前限制。

对于所核 Codex 内置工具，模型只能在 prompt 中表达画幅或目标像素，执行器另行补入 `size:"auto"`。这说明入口控制不同，不能说明订阅模型的能力较弱；具体调用见 [Codex 请求构造](codex.md#image-request)。

### <a id="public-quality"></a>公共 API 的质量档位

图片 `quality` 表达图片请求的质量选项，Codex 的 reasoning effort 表达主模型的思考程度，不能将两者绑定成同一个档位。

| 对象 | 所核控制方式 | 判断边界 |
|---|---|---|
| 公共 GPT Image 2 | `low`、`medium`、`high`、`auto` | 不自动获得 2.5 的新增枚举 |
| 公共 GPT Image 2.5 | 上述选项，以及 `xhigh`、`max` | 适用于对应公共模型及日期快照 |
| 所核 Codex 内置图片工具 | 执行器设置 `quality:"auto"` | 工具没有独立 quality 形参 |
| CPA 原生 JSON 分支 | 可以保留调用方的 quality 字段 | 透传不证明订阅后端接受或遵从所有值 |

返回的 quality 元数据是服务端报告值，不是独立测得的视觉质量。不同档位的耗时、细节和成本收益，需要在同入口、同类任务及可比较条件下验证，不能从枚举名称量化推导。

> 公共质量枚举见 [OpenAPI 生成参数](https://github.com/openai/openai-openapi/blob/21cb7e98d8166a691a0eb8679a90419eb816cf35/openapi.json#L26449-L26476)。effort 的直接作用和重画等间接影响见 [Codex 思考程度](codex.md#image-reasoning)。官方 API-key fallback 脚本还有自己的本地校验，不能拿该脚本的旧限制替代公共 API 能力，见 [fallback 入口](codex.md#image-api-fallback)。

### <a id="subscription-output"></a>订阅入口的实际执行结果

检查参数是否生效时，分别记录请求值、响应报告值、原始文件的实际属性及后处理结果。文件名、接口别名和 prompt 中的“4K”都不能替代像素检查。

| 观察位置 | 可以证明什么 | 不能证明什么 |
|---|---|---|
| 请求 JSON | 客户端发出了哪些字段 | 后端全部执行了这些字段 |
| 响应元数据 | 服务端报告了哪些属性 | 文件一定与元数据一致，或模型身份已可核验 |
| 原始图片解码 | 实际格式、尺寸、透明通道等 | 所有视觉要求均已满足 |
| 交付文件 | 最终提供给下游的内容 | 它一定未经缩放、裁剪或重新编码 |

留存的 2026-09-09 独立 HTTP 实测中，调用 Codex 订阅 Images 端点，请求模型字段为 `gpt-image-2`。显式请求 `size=1024x1024`，实际 PNG 为 `1254×1254`；其中一次编辑请求指定 `quality=low`，响应报告 `medium`。这是显式接口参数与实际返回值的比较。

> 依据为留存的当日脱敏验收记录，包含请求值、响应元数据及 PNG 尺寸检查；不是本文整理期间重新执行的测试。请求中的模型字符串不能确认服务端实际模型映射，这组结果不代表当前 2.5 的参数遵从程度。

另有 2026-07-14 的 Codex Desktop 用户报告：`1024×1024` 写在自然语言 prompt 中，记录的六次成功输出均为 `1254×1254`。这是内置工具的自然语言尺寸要求，不是显式 `size` 参数测试，也不是上述 quality 比较的来源。

> 来源：[Codex Desktop 用户报告](https://github.com/openai/codex/issues/33050)。该报告早于 2.5，属于用户观察，不是官方能力规范；其有限样本不能用于估计长期成功率。

这两类记录都说明需要核对实际输出，但不能据此判断底层图片模型做不到目标尺寸或确定其能力上限。

## <a id="lifecycle"></a>图片请求的执行过程

生图可能持续较长时间并消费额度。下面是接入时需要检查的执行契约，不代表 Codex、CPA 或其他组件已经统一实现这些保护。

### <a id="lifecycle-timeout"></a>超时的覆盖范围

全程超时应覆盖实际需要限制的阶段，而不只是等待响应头。先列出认证读取、输入加载、上传、后端等待、响应读取、解码和保存，再确认各阶段怎样停止等待及释放资源。

如果定时器只触发网络请求的 AbortSignal，而程序仍在等待一个不接受取消的认证读取，调用可能继续占用并发槽位。故障注入应包含这种情况，并检查后续请求是否能够继续执行。

> 所核 CPA 原生图片分支创建的 HTTP client 使用零 timeout，见 [原生请求执行](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L335-L376)。调用方的超时可限制自己的等待，但不等于 CPA 对所有调用方施加了同一全程期限。

### <a id="lifecycle-cancel"></a>取消的传播范围

取消需要沿调用方、代理、认证组件和上游连接逐层传播。调用方断开、代理停止读取、远端停止生成是不同事件。

验收时记录本地请求是否结束、连接是否关闭、任务是否还在运行、临时文件是否清理以及槽位是否释放。即使本地取消成功，也不能保证后端没有生成图片或没有消耗额度。

### <a id="lifecycle-replay"></a>请求重发的触发条件

一次超时或断线可能发生在图片已经生成之后。结果不确定时再次请求，可能增加生成次数；请求 ID 主要用于追踪，不能自动当成服务端支持的幂等键。

| 重发来源 | 核对内容 |
|---|---|
| 调用方 SDK | 默认重试哪些错误，能否关闭，是否重放 POST |
| 代理执行器 | 额外轮次、同轮账户候选、模型回退及错误继续规则 |
| 认证组件 | 401 后是否刷新并重新发送原请求 |
| HTTP 客户端 | 是否跟随重定向，307／308 是否保留方法和可重放请求体 |
| 外层 Agent | 是否在收到不明确错误后自行重新调用工具 |

只有确认前次未执行，或后端提供可用的去重、查询和恢复语义时，才能据此设计安全重试。否则应将“不确定是否已生成”交还调用方，而不是把所有网络错误标成可无条件重试。

> CPA 的额外轮次和执行路径见 [账户执行器](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/cliproxy/auth/conductor_execution.go#L132-L158)；HTTP client 构造见 [代理客户端](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/helps/proxy_helpers.go#L28-L61)。不同层的控制含义见 [CPA 配置](#cpa-config)。

### <a id="lifecycle-concurrency"></a>并发请求的调度

并发限制控制同时运行多少请求，队列控制超出的请求如何等待。是否需要队列取决于调用方式，不是图片接口的必备能力。

| 方式 | 超额请求 | 重启后的等待任务 | 需要说明的行为 |
|---|---|---|---|
| 直接拒绝 | 返回忙或限流错误 | 无等待任务 | 谁负责再次提交 |
| 内存队列 | 保存在进程内等待 | 通常丢失 | 排队上限、取消、等待超时 |
| 持久任务 | 保存到持久存储 | 可按设计恢复 | 去重、状态一致性、失败恢复及清理 |

本地槽位释放也不证明上游任务已经停止。验证并发上限时，应把取消后仍可能运行的远端请求纳入风险分析。

### <a id="lifecycle-async"></a>异步任务的结果恢复

异步接口通常先返回任务标识，再让调用方查询状态和取得图片。它解决连接等待方式，并不自动保证任务持久化或图片永久保存。

检查任务是否在重启后仍可查询、已完成图片保存多久、取消作用于哪个阶段、重复提交怎样处理、失败后是否能取回已有结果。不要把普通同步请求断开后的“再试一次”写成结果恢复。

## <a id="access-control"></a>图片服务的访问控制

接入组件使用的上游身份与它向调用方开放的权限是两层边界。检查本机端口之外，还要检查文件、URL、日志和后台请求。

### <a id="access-local"></a>本机接口的调用认证

绑定 loopback 可以限制远程网络访问，但不能阻止所有其他本机程序调用。若组件提供本机 key，应使用独立、不可预测的值，并限制其存储和分发范围。

浏览器调用还涉及 Host、Origin、跨站请求和 CORS。它们与 API key 解决不同问题，不能互相替代。是否需要这些限制，应结合实际监听方式和客户端类型检查，而不是默认本机服务无需保护。

### <a id="access-files"></a>参考图片的读取权限

接受本地路径的组件必须明确路径由谁解析、在哪台机器读取、允许读取哪些目录。接受图片附件的组件也应校验会话或资源授权，不能把任意附件标识当作访问许可。

文件扩展名和 MIME 声明不是内容验证。先控制读取范围和大小，再按实际字节检查格式；保存输出时还要防止意外覆盖和路径逃逸。

### <a id="access-targets"></a>上游请求的目标限制

凭据只能发送到获准的认证或服务目标。调用方能够提供参考图 URL、上游地址或代理配置时，应分别审查这些字段是否可把请求引向非预期位置。

远程图片获取应考虑重定向、内部地址、下载大小和凭据转发。模型目录更新、版本检查等后台请求也应单独列出；减少其中一种请求，不等于整个组件没有其他网络行为。

### <a id="access-logs"></a>日志中的敏感数据

日志应保留足以区分错误阶段的状态、时间和安全关联标识，同时避免记录完整凭据、图片数据、提示词及未经处理的上游错误正文。

检查正常日志、错误日志、调试开关、反向代理日志和 SDK 日志各自的行为。关闭一个请求日志选项并不保证所有输出都消失；排障时也不应要求用户把完整登录文件或环境变量粘贴到聊天中。

## <a id="artifacts"></a>图片产物的交付

生图成功需要形成调用方可使用的图片，而不仅是收到“成功”文字。校验、返回和持久化分别处理，避免显示了预览却丢失原图。

### <a id="artifact-validation"></a>图片内容的校验

按层次检查返回值，既验证数据有效性，也限制资源消耗。

| 层次 | 检查内容 |
|---|---|
| HTTP 和业务结果 | 状态码、错误对象、有效图片条目是否存在 |
| 编码 | base64 是否有效，编码长度及解码后字节数是否超限 |
| 文件格式 | 文件签名、声明 MIME、实际解码格式是否一致 |
| 图像解码 | 是否完整可解码，像素数量是否在本地资源预算内 |
| 图片属性 | 实际尺寸、透明通道、输出格式是否符合交付要求 |
| 视觉结果 | 构图、文字、编辑目标和需要保留的内容是否正确 |

PNG 文件头及 IHDR 检查可以识别部分错误，但不等于完整图片解码验证。限制压缩文件大小也不等于限制解码后的内存。保护应放在正常执行路径中，不能只存在于 smoke 测试里。

> 一个检查文件头和尺寸的实现见 [pi-gpt-image 图片处理](https://github.com/drgnchan/pi-gpt-image/blob/181adf16902eae2bc69a348ef588e58fb905b72b/src/codex-image.ts#L90-L222)。该例先整体读取网络响应，再做图片大小检查；不能将其后置限制描述为网络接收阶段的硬上限。

### <a id="artifact-return"></a>图片结果的返回形式

返回形式应满足后续调用，而不是只方便服务内部表示。base64、文件路径、附件和下载链接各有不同的可用范围。

| 形式 | 需要核对的内容 |
|---|---|
| 图片数据 | 消费端能否处理格式和体积，是否需要再次解码 |
| 本地路径 | 路径在哪台机器，调用方是否拥有读取权限 |
| 宿主附件 | 是否实际登记到当前会话，能否继续编辑或下载原图 |
| URL | 是否可达、是否需要认证、何时失效，是否公开暴露图片 |

MCP 支持图片等内容块，但客户端是否展示、交给模型或持久化由宿主决定，见 [MCP 工具结果的内容块](mcp.md#tool-result-blocks)。不能把“返回了文件名”或“界面显示了缩略图”当成原图已经可靠交付。

### <a id="artifact-persistence"></a>图片文件的持久化

明确区分原始生成文件、预览图和后处理交付文件。保存时选择明确的输出目录，避免默认覆盖，并记录原图到交付图之间的缩放、裁剪或重编码。

临时目录、会话附件和长期项目资源的有效期不同。任务完成前确认调用方实际能取回文件；清理时只处理本次创建的实例和临时材料，不删除共享登录或其他任务的产物。

## <a id="components"></a>Codex 订阅生图组件的评估

这里的组件指使用 Codex 订阅身份发起图片请求并交付结果的软件，包括程序库、HTTP 代理和宿主插件。比较它们的接入方式和工程边界，不是比较底层图片模型。

### <a id="component-interfaces"></a>组件提供的接口

先确定调用方需要哪种入口，再核对生成、编辑、参考图和返回图片是否全部匹配。库函数、HTTP 服务、宿主插件和 MCP server 不是可互换的包装标签。

| 入口 | 主要核对内容 |
|---|---|
| 程序库 | 可调用接口、认证注入、取消信号、运行时及依赖 |
| 独立服务 | 启动配置、本机认证、请求格式、进程和连接管理 |
| 宿主插件 | 宿主版本、认证能力、附件授权、工具注册和产物保存 |
| MCP 适配 | 工具输入、实际执行后端、错误语义及图片内容交付 |

有 HTTP API 不证明核心模块容易嵌入；有源码也不等于已经有稳定库接口。若要改接入形态，单独核算适配和维护工作。

### <a id="component-routes"></a>图片请求的实际路径

从外部处理函数追到请求构造、认证注入、HTTP 目标和响应解析，检查是否因模型名、认证类型、mask 或错误而切换分支。

源码检查还应覆盖进程启动和回退逻辑，不能只搜索 `/images/generations` 字符串。搜索结果和 README 用于发现候选；对路径分类有冲突时，以对应版本的完整调用链为依据。

### <a id="component-reuse"></a>核心代码的复用条件

将复用成本拆成可检查的问题，避免凭代码行数或依赖数量直接判断成熟度。

| 维度 | 核对问题 |
|---|---|
| 模块边界 | 能否单独调用图片模块，还是必须启动整套程序 |
| 认证 | 能否由宿主提供凭据，谁负责刷新和写回 |
| 生命周期 | 超时、取消、重试和资源清理能否按调用方要求控制 |
| 依赖 | 是否引入额外数据库、账户路由、管理界面或编译工具链 |
| 许可证 | 是否有明确许可，分发和修改有哪些义务，依赖是否另有条件 |
| 维护责任 | 协议变化、字段适配和错误处理最终由谁维护 |

软件许可证解决代码复用问题，不代替上游服务条款、账户权限、额度和内容政策。完整工具契约设计转用 `tool` skill；本篇不实现新的工具服务。

### <a id="component-maintenance"></a>图片功能的维护情况

维护状况应围绕准备使用的分支和图片能力评估。star、下载量和最近 push 可以提供线索，但不能单独证明代码质量或维护响应。

| 观察项 | 能说明什么 | 需要避免的误读 |
|---|---|---|
| 默认分支最近提交 | 主线近期是否变化 | push 可能来自其他分支 |
| 固定时间窗的主线提交 | 更新频率 | 自动同步、合并和版本号变化不等于功能修复 |
| 图片相关修复 | 目标能力是否持续适配 | 全仓活跃不等于图片模块活跃 |
| 发布与源码对应 | 运行包能否追溯到已读代码 | 主分支功能可能尚未发布 |
| 相关测试 | 是否考虑请求路径、编辑和错误场景 | 测试数量多不等于覆盖目标能力；mock 不证明后端可用 |
| issue 和维护者 | 响应、修复及单人维护风险 | 关闭 issue 不一定表示修复，未统计不能写成已评估 |

需要量化时，写清时间窗、分支、统计口径和是否只计算第一父链；需要判断长期可用性时，继续查看相关修复和问题处理，而不是按提交数排序。

### <a id="component-examples"></a>代表组件的比较

下表保留能说明不同接入方式的源码快照，不是当前推荐排名。升级后需重新检查变化；除 CPA 的注明历史记录外，不把源码阅读写成真实生图验证。

| 组件 | 形态 | 所核提交 | 订阅图片路径 | 生成／编辑 | 认证来源 |
|---|---|---|---|---|---|
| CLIProxyAPI | HTTP 代理，也有 SDK 接入面 | `7fac6b15`，v7.2.155 | 指定模型走原生 Images，另有 Responses 分支 | JSON 生成；JSON、multipart 编辑 | CPA 凭据与刷新机制，接入前明确所有权 |
| openai-oauth | Node.js 库及开发服务器 | `ec7dab2f` | 原生 Images | 生成；所核公开编辑入口要求 multipart | 可读取 Codex 文件，提供刷新选项 |
| pi-gpt-image | pi 宿主扩展 | `181adf16` | 原生 Images | 所核工具仅生成，无编辑工具 | 向 pi 请求 `openai-codex` 托管认证 |
| Sub2API | 网关产品 | `98d86915` | 所核 OAuth 图片分支转 Responses | 生成和编辑转换 | 网关管理账户认证 |

| 组件 | 复用时的具体注意点 | 许可证 | 证据范围 |
|---|---|---|---|
| CLIProxyAPI | 核心嵌入成本未验证；配置、重试和服务生命周期需单独检查 | MIT | 固定源码；有[有限历史实测](#cpa-observations) |
| openai-oauth | 库传递 Request.signal；所核 Node 适配器没有把下游断开接入该信号；共享文件刷新需协调 | Apache-2.0 | 代码阅读，未进行图片真实调用 |
| pi-gpt-image | 与 pi 的认证和附件接口耦合；输出 PNG、检查文件头及尺寸、不覆盖保存；无独立 HTTP 编辑接口 | MIT | 固定源码阅读，未进行图片真实调用 |
| Sub2API | 包含完整网关功能；主模型和图片工具的参数及事件处理都要维护；抽出模块成本未验证 | LGPL-3.0 | 图片转换源码阅读，未进行图片真实调用 |

> 来源：[CPA 原生执行器](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L84-L120)、[openai-oauth 编辑入口](https://github.com/EvanZhouDev/openai-oauth/blob/ec7dab2fcd8dab9da970a7a2b5dc34046c94905e/packages/openai-oauth/src/images.ts#L4-L39)及 [Node 请求适配](https://github.com/EvanZhouDev/openai-oauth/blob/ec7dab2fcd8dab9da970a7a2b5dc34046c94905e/packages/openai-oauth/src/shared.ts#L138-L216)、[pi 工具注册及托管认证](https://github.com/drgnchan/pi-gpt-image/blob/181adf16902eae2bc69a348ef588e58fb905b72b/extensions/index.ts#L74-L158)、[Sub2API 图片转换](https://github.com/Wei-Shaw/sub2api/blob/98d86915becae9fe9491a91ffc6defd5235c8d2b/backend/internal/service/openai_images_responses.go#L358-L444)。许可分别见 [CPA](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/LICENSE#L1-L22)、[openai-oauth](https://github.com/EvanZhouDev/openai-oauth/blob/ec7dab2fcd8dab9da970a7a2b5dc34046c94905e/LICENSE#L1-L25)、[pi-gpt-image](https://github.com/drgnchan/pi-gpt-image/blob/181adf16902eae2bc69a348ef588e58fb905b72b/LICENSE#L1-L21)及 [Sub2API](https://github.com/Wei-Shaw/sub2api/blob/98d86915becae9fe9491a91ffc6defd5235c8d2b/LICENSE#L1-L24)。

## <a id="verification"></a>生图能力的验证

验收应能区分接口实现、运行配置和真实服务能力。下面的检查表适用于评估接入是否可靠，不意味着每次使用都要重新消耗额度完成全套测试。

### <a id="verification-evidence"></a>验证证据的分类

每条结论就近注明版本、入口和验证方式，避免把证据强度混写。

| 证据 | 可以支持的结论 | 不能替代的验证 |
|---|---|---|
| 文档声明 | 项目声称提供某项能力 | 实际请求分支及当前账户权限 |
| 固定版本源码 | 该实现怎样构造、转换和处理请求 | 服务端真实接受、画质或成功率 |
| 测试源码 | 作者编写了哪些断言 | 测试已经通过 |
| 已运行 mock | 本地特定路径在模拟条件下的行为 | 真实后端兼容和计费语义 |
| 真实调用 | 指定条件下该次请求的实际结果 | 全部参数、长期稳定性、其他模型或账户 |

发布包应对应源码版本，运行条件应能说明认证来源和重试策略。一次成功不能推导性能优势；测试通过也不证明未覆盖的异常不存在。

### <a id="verification-checklist"></a>生图接口的验收检查表

先做不消费图片额度的检查，再经明确授权进行必要真实调用。涉及错误和资源耗尽的场景，优先用不读取真实凭据的模拟测试。

| 检查范围 | 示例检查 | 通过标准 |
|---|---|---|
| 身份与准入 | 缺 key、错误 key、不同来源调用 | 拒绝发生在图片请求之前，错误不泄露凭据 |
| 请求路径 | 生成、编辑、模型切换分支 | 实际目标与声称的 Images／Responses 路径一致 |
| 基础生成 | 单次非流式请求 | 有有效图片数据，能解码并交付 |
| 编辑 | JSON、multipart、参考图作用 | 输入格式正确，语义修改达到要求 |
| 特殊能力 | 多图、mask、file ID、透明、流式、新模型 | 每项单独注明实测或未验证，不靠字段存在推断 |
| 输入异常 | JSON null、错误引用、伪图片、畸形认证数据 | 错误归到正确阶段，不误报成已联系上游的故障 |
| 生命周期 | 认证等待、慢上传、断流、取消 | 等待、连接、文件和并发槽位按契约结束 |
| 重发 | SDK、401、账户候选、重定向 | 知道各层会否再次提交，不将不确定结果盲目重发 |
| 产物 | 错误 MIME、损坏数据、超大像素、目标已存在 | 执行路径实际校验，限制生效，不意外覆盖 |
| 运行维护 | 到期、配置更新、重启、停止 | 认证与任务归属明确，旧结果和临时资源按约定处理 |

保留脱敏的验证条件和结论即可，不需要把秘密、完整提示词、图片 base64 或大量运行标识放进长期知识文档。

## <a id="cpa"></a>CLIProxyAPI 生图接口

本章说明 CPA v7.2.155、提交 `7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974` 的 Codex 订阅图片路径。操作示例按该固定版本的源码编写，不适用于所有 OpenAI 兼容代理；生成和编辑会使用所配置账户的图片额度，真实验收范围另见[实测记录](#cpa-observations)。

### <a id="cpa-version"></a>运行版本的确认

先确认发行包、构建提交和实际图片路由，再复制配置或替换模型名。可以使用对应平台的官方发行包；是否从源码构建与能否调用图片接口是不同问题。

截至 2026-09-10，CPA 官方最新稳定版仍为 **v7.2.155**，主线仍为 `7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974`，与本章使用的源码相同。因此下面的原生模型匹配范围并非仅保留旧测试记录，而是该日期再次核对的源码状态。

该版本的原生分支精确识别规范化后的 `gpt-image-1.5` 和 `gpt-image-2`，不是按所有 `gpt-image-*` 前缀匹配。**不能仅将示例中的模型名改为 `gpt-image-2.5-flare` 或 `gpt-image-2.5-sunburst`，就声称仍走同一个已核对的 Codex 原生分支。**是否经其他 provider、别名或 Responses 路径调用成功，需要另查实际路由；这里不推断所有 CPA 路径均不支持 2.5，也不把公共 API 发布当作订阅直连已经验证的证据。

> 版本入口见 [v7.2.155 发布](https://github.com/router-for-me/CLIProxyAPI/releases/tag/v7.2.155)；原生匹配见 [模型判定](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L643-L667)。原生执行失败直接返回，见 [分支选择](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L84-L87)，不能声称该失败自动回退 Responses。

### <a id="cpa-config"></a>本机实例的配置

运行前先完成 [Codex 凭据复用和 CPA 适配](codex.md#auth-sharing)。本机调用方 key 与上游订阅凭据不同：前者保护 CPA 端口，后者由 CPA 用来访问上游。

以下是基础配置模板，`8317` 仅为可替换的示例端口；确认没有冲突，并替换所有占位符。配置及凭据文件应只允许预期的运行用户读取。

```yaml
host: "127.0.0.1"
port: 8317
auth-dir: "<CPA_AUTH_DIR>"
api-keys:
  - "<CPA_LOCAL_KEY>"
```

`auth-dir` 使用 CPA 专属目录，不指向或软链接原始 Codex 凭据目录。还要核对其他认证来源；“独立扁平凭据、仅提供访问令牌和账户 ID、未配置其他刷新来源”的短期示例，才由原凭据持有者续期后重新同步。不能笼统推断所有 CPA 配置只要没有 refresh token 就不可能通过其他来源更新认证。

访问限制及后台行为单独配置，不把下面各项都称为每次生图必需：

| 目标 | 所核设置及条件 | 注意点 |
|---|---|---|
| 不启用管理 API | `remote-management.secret-key` 为空；没有 `MANAGEMENT_PASSWORD`；不用 `-password` 或自动设置管理密码的 TUI 路径 | `allow-remote:false` 只限制远程管理，不等于关闭；启动会加载工作目录 `.env` |
| 不提供控制面板 | `remote-management.disable-control-panel:true` | 面板与管理 API 分开核对 |
| 跳过请求日志 middleware | `commercial-mode:true` | 不代表基础应用日志也消失 |
| 减少文件及调试日志 | `logging-to-file:false`、`debug:false` | 仍需核对实际正常和错误输出 |
| 不更新远程模型目录 | 启动参数 `-local-model` | 不保证没有其他后台网络请求 |

针对图片重发，可明确设置下面的策略值，但必须连同凭据级覆盖和其他重发来源一起理解：

```yaml
request-retry: 0
max-retry-credentials: 1
max-retry-interval: 0
```

这里分别限制额外重试轮次、同轮候选数量和等待间隔，不是“关闭所有自动重发”。401 后的认证更新、模型或凭据策略、Go HTTP 客户端的重定向仍是独立事项。只有在特定单账户、无其他继续规则及认证刷新路径的条件下，才能据此描述那次测试的重发范围。

> 基础字段及 loader 见 [配置加载](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/config/config_load.go#L64-L81)。`config.example.yaml` 的示例端口、目录和重试值，不是手写 YAML 省略字段后的全部运行时默认。管理入口见 [管理路由判定](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/api/server.go#L233-L239)及[环境管理密码处理](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/api/handlers/management/handler.go#L313-L318)；请求日志 middleware 见 [服务器初始化](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/api/server.go#L136-L168)。

### <a id="cpa-checks"></a>服务的运行检查

在已知的运行目录和环境下启动，避免意外加载另一份 `.env` 或隐式管理密码。启动命令中的路径由实际安装位置决定：

```bash
"<CPA_BINARY>" -config "<CPA_CONFIG_FILE>"
```

核对启动信息中的版本、配置、监听地址和错误。以下示例假定 `CPA_BASE_URL` 为 `http://127.0.0.1:8317`，`CPA_LOCAL_KEY` 已通过受控方式注入当前进程环境；不要把真实 key 写进聊天或共享命令记录。

先检查受保护路由在无 key 时被拒绝：

```bash
curl --silent --show-error --max-time 10 \
  -o /dev/null -w 'HTTP %{http_code}\n' \
  "$CPA_BASE_URL/v1/models"
```

配置了调用方 key 时，此检查应得到 401。随后带 key 检查接口；通过标准输入提供认证头，避免把展开后的 key 直接放进 curl 参数：

```bash
printf 'Authorization: Bearer %s\n' "$CPA_LOCAL_KEY" |
  curl --silent --show-error --fail-with-body --max-time 10 \
    -H @- "$CPA_BASE_URL/v1/models"
```

模型列表可读只证明这条访问链已通，不证明所选订阅模型具备生图权限。停止时只结束本次启动的实例，检查活动请求和临时文件；不要用宽泛的进程名匹配结束其他实例，也不要删除共享登录。

> 配置启动参数见 [main.go](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/cmd/server/main.go#L95-L111)。这些检查不发起图片生成；真正的生成和编辑需要另外执行下面的请求。

### <a id="cpa-parameters"></a>图片接口的参数

下表描述 CPA 对外入口及所核原生分支的处理，不将字段可透传等同于订阅后端的完整支持。

| 字段 | 调用方式及所核处理 | 能力边界 |
|---|---|---|
| `model` | 示例使用 `gpt-image-2`；入口缺省时该版本可采用此值 | 显式填写便于追踪；2.5 不能套用已验证原生分支 |
| `prompt` | 非空文字 | 约束是否遵从仍需看结果 |
| `n` | 示例为 1；原生准备层可保留其他值 | `n=1` 不是该分支统一的本地硬限制；其他张数未作真实保证 |
| `size`、`quality`、`background` | 原生准备层可保留调用方值 | CPA 不等同于内置工具固定 `auto`；也不保证上游遵从 |
| `images` | JSON 编辑参考图数组 | 内置工具的五张限制不能直接移植为 CPA 的硬限制 |
| `image`、`image[]` | multipart 文件字段 | 该版本若存在 `image[]` 文件，优先使用它，不与 `image` 文件合并 |
| `mask` | JSON 对象或 multipart 文件；相关表单引用可转换 | 字段转换不等于精确 mask 编辑已验收 |
| `file_id` 引用 | 原生 JSON 路径可透传相关字段 | 不证明该 ID 的上传、授权和订阅引用链已经可用 |
| `response_format` | 可随请求进入相关处理；历史验收消费 `b64_json` | 原生成功体直接转发，不承诺所有输出格式都被本地重建 |
| `stream` | 原生路径有流式转发实现 | 本章操作例和历史验收均为非流式；分块转发不自动保证客户端完整支持 partial 图片事件 |

Images 请求准备层主要规范模型和流式字段，并保留主体；共用处理仍可能添加缓存等元数据，不应绝对写成“最终 HTTP 请求只改两个字段”。

> 生成入口见 [JSON 处理](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/api/handlers/openai/openai_images_handlers.go#L599-L654)，编辑原生提前路由见 [编辑处理](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/api/handlers/openai/openai_images_handlers.go#L891-L940)。后续其他分支对引用数量或 file ID 的拒绝规则，不能套到这个已经返回的原生分支。

### <a id="cpa-generate"></a>生成图片

把请求保存为 `generate.json`，避免复杂 prompt 的 shell 引号改变内容。下面的参数组合用于展示一次非流式调用，不是推荐所有任务都用 low 质量。

```json
{
  "model": "gpt-image-2",
  "prompt": "生成一张简洁的几何插画：浅色背景上的绿色茶壶，没有文字。",
  "n": 1,
  "size": "auto",
  "quality": "low"
}
```

以下请求会消费所配置账户的图片额度：

```bash
printf 'Authorization: Bearer %s\n' "$CPA_LOCAL_KEY" |
  curl --silent --show-error --fail-with-body --max-time 180 \
    -H @- -H 'Content-Type: application/json' \
    "$CPA_BASE_URL/v1/images/generations" \
    --data-binary @generate.json --output response.json
```

示例不启用 curl 重试，也不跟随重定向；这只控制调用方到 CPA 的这一段。180 秒只限制当前客户端等待，不是 CPA 的全程超时设置。成功后继续按[响应处理](#cpa-response)检查，不能直接把 `response.json` 当图片。

### <a id="cpa-edit-json"></a>JSON 参考图编辑

先读取获准使用的图片字节并做 base64 编码，把实际 MIME 和编码内容放入 data URL；不要只改文件扩展名，也不要将占位符原样发送。将请求保存为 `edit.json`：

```json
{
  "model": "gpt-image-2",
  "prompt": "将茶壶改为橙色，保留背景、构图和其他可见元素。",
  "images": [
    {"image_url": "data:image/png;base64,<BASE64_IMAGE_BYTES>"}
  ],
  "n": 1,
  "size": "auto",
  "quality": "low"
}
```

发送一次编辑请求：

```bash
printf 'Authorization: Bearer %s\n' "$CPA_LOCAL_KEY" |
  curl --silent --show-error --fail-with-body --max-time 180 \
    -H @- -H 'Content-Type: application/json' \
    "$CPA_BASE_URL/v1/images/edits" \
    --data-binary @edit.json --output response.json
```

这是一条带原图的生成式编辑请求。提示词中的“保留”需要检查结果，不等于像素不变保证。多图、遮罩和 file ID 应在基础编辑通过后分别验收。

### <a id="cpa-edit-multipart"></a>multipart 文件编辑

文件式调用无需调用方先把图片编码为 JSON 文本。下面示例只上传一张参考图，CPA 再负责转换：

```bash
printf 'Authorization: Bearer %s\n' "$CPA_LOCAL_KEY" |
  curl --silent --show-error --fail-with-body --max-time 180 \
    -H @- "$CPA_BASE_URL/v1/images/edits" \
    -F 'model=gpt-image-2' \
    -F 'prompt=将茶壶改为橙色，保留背景和构图。' \
    -F 'image[]=@<REFERENCE_FILE>' \
    -F 'n=1' -F 'size=auto' -F 'quality=low' \
    --output response.json
```

不要为这个请求再手工设置 `Content-Type: application/json`。多个文件使用重复的同名字段，并确认该版本的选择规则；避免同时混用 `image` 和 `image[]` 后误以为两组都会被采用。

如果需要遮罩，先核对 [mask 的入口差异](#edit-masks)。CPA 能把上传的 mask 文件转为下游引用，不代表它已验证遮罩尺寸、透明通道或编辑精度。

### <a id="cpa-sdk"></a>官方客户端调用

官方 Python 客户端可以把 `base_url` 指向 CPA；此时 `api_key` 参数填写的是 CPA 本机 key。`images.generate()` 对应生成，`images.edit(image=文件)` 对应文件式编辑；不要因为使用官方 SDK 就默认请求已经改走公共 API 计费。

以下示例需要已安装 `openai` 和 Pillow，只执行一次编辑。环境和依赖的安装按 `software` skill 处理，不向系统 Python 写入依赖。

```python
import base64
import os
import warnings
from io import BytesIO
from pathlib import Path
from openai import OpenAI
from PIL import Image

client = OpenAI(
    base_url=os.environ["CPA_BASE_URL"].rstrip("/") + "/v1",
    api_key=os.environ["CPA_LOCAL_KEY"],
    max_retries=0,
    timeout=180.0,
)
with open("<REFERENCE_FILE>", "rb") as source:
    result = client.images.edit(
        model="gpt-image-2", image=source,
        prompt="将主体改为橙色，保留背景和构图。",
        n=1, size="auto", quality="low",
    )

if not result.data or not result.data[0].b64_json:
    raise ValueError("响应没有可处理的 b64_json 图片")
encoded = result.data[0].b64_json
limit = 32 * 1024 * 1024  # 示例的本地处理预算，不是后端能力上限
if len(encoded) > 4 * ((limit + 2) // 3):
    raise ValueError("编码图片超过本地处理预算")
raw = base64.b64decode(encoded, validate=True)
if not raw or len(raw) > limit:
    raise ValueError("图片为空或超过本地处理预算")
Image.MAX_IMAGE_PIXELS = 32_000_000  # 示例的本地像素预算
warnings.simplefilter("error", Image.DecompressionBombWarning)
with Image.open(BytesIO(raw)) as image:
    image.verify()
with Image.open(BytesIO(raw)) as image:
    image.load()
    print(image.format, image.size, image.mode)
with Path("<OUTPUT_FILE>").open("xb") as destination:
    destination.write(raw)
```

根据打印出的实际格式选择交付文件扩展名。`xb` 防止覆盖已有文件；校验通过后仍需查看视觉结果。这个示例的大小检查发生在 SDK 取得响应之后，不能当作网络接收阶段的硬上限或 CPA 服务端保护。

### <a id="cpa-response"></a>图片响应的处理

先检查 HTTP 状态和业务错误，再处理图片条目。所核原生非流式路径直接返回上游成功响应体，不重新构造一份保证所有字段存在的标准结果。

| 响应内容 | 处理方法 |
|---|---|
| `data[].b64_json` | 检查长度、严格解码，再检查实际图片 |
| `data[].url` | 先区分 data URI 与 HTTPS URL；按实际认证、有效期和读取权限处理 |
| `size`、`quality`、`background` | 作为可选的服务端报告值保留，不替代文件检查 |
| usage | 按该接口的报告语义保存；不能单凭它推算订阅实际扣减规则 |
| 无有效图片条目 | 视为交付失败或不完整结果，不只报告“HTTP 200” |

不要拿 Responses 分支的 URL 转换 helper 推断原生响应里的 URL 一定是 data URI。返回多条数据时也要核对实际数量，而不是仅凭请求的 `n` 宣布生成了相应张数。

> 原生响应读取和返回见 [执行器](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L360-L376)。CPA 转发成功不代表已经替调用方完成图片内容、像素和视觉校验。

### <a id="cpa-errors"></a>错误响应的诊断

同一个 HTTP 状态可能来自不同层。排障时先确认拒绝发生在调用方、CPA 准入、认证加载还是上游图片请求。

| 现象 | 优先核对 | 不应直接采取的动作 |
|---|---|---|
| 缺 key 或错误 key | CPA 本机认证，是否误用了上游凭据 | 重复生图或把真实凭据贴到日志 |
| 上游 401／403 | 所选身份、令牌时效、权限及实际端点 | 自动切换到其他计费身份 |
| 400 或参数错误 | 内容类型、字段、模型路由、本地校验和后端错误 | 把所有代理错误都当作模型能力不足 |
| 429 | 哪一层限流、图片额度、可用的重试提示 | 通过多账户盲目重投以规避限制 |
| 超时、断流、5xx | 安全关联标识、调用阶段、结果是否可能已经生成 | 假定前次一定未执行并立即重发 |
| 200 但没有有效图像 | 响应格式、有效 data、解码及交付路径 | 只返回“生成成功” |

客户端关闭重试不能禁止 CPA 内部的所有重发。所核 Go HTTP client 未设置专门的 CheckRedirect，配合可重放 POST 请求体时，307／308 仍可能触发重新提交；普通前置反向代理不能替这个上游 HTTP client 决定是否跟随重定向。需要严格限制时，应核对实际传输实现或明确接受其边界，而不是再添加一个不相关的 retry 开关。

> HTTP client 见 [代理客户端构造](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/helps/proxy_helpers.go#L28-L61)，POST 构造见 [请求准备](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_executor_request.go#L136-L149)，401 更新后重发见 [执行分支](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/sdk/cliproxy/auth/conductor_execution.go#L576-L584)。这些结论来自所引用版本的源码，不代表 401 更新后重发、重定向或断流等场景已经过真实错误注入验证。

### <a id="cpa-observations"></a>实测记录

2026-09-09 的历史验收使用官方 v7.2.155 发行包，记录了下载包校验及构建提交对应关系。实例使用独立配置和凭据目录，仅提供访问令牌和账户 ID，未配置 refresh token 或其他刷新来源；原登录文件在验收前后哈希相同。

| 操作 | 请求条件 | 历史观察 |
|---|---|---|
| JSON 生成 | `gpt-image-2`、`n=1`、`size=auto`、`quality=low` | HTTP 200；取得真实 PNG 并检查视觉内容 |
| JSON 编辑 | 相同模型和输出选项，单张参考图 | HTTP 200；语义修改达到测试要求 |
| multipart 编辑 | 相同模型和输出选项，单张上传文件 | HTTP 200；语义修改达到测试要求 |
| 准入检查 | 未提供本机 key；管理入口已按测试条件禁用 | 受保护模型路由返回 401；管理路由返回 404 |

当时还限制了账户候选和额外重试条件，采用非流式调用。临时实例及测试材料已清理；这里保留脱敏条件和结果，不依赖那些临时文件。

> 2026-09-09 的记录仅覆盖 `gpt-image-2`、`n=1`、`size=auto`、`quality=low` 下的非流式生成、单参考图 JSON 编辑、单参考图 multipart 编辑和上述准入检查。多参考图组合、`n>1`、mask、file ID、1.5、2.5、其他尺寸或质量、流式及长期续期未验证；未进行同条件性能比较，也未验证编辑区域之外逐像素不变。对应实现见[该版本原生执行器](https://github.com/router-for-me/CLIProxyAPI/blob/7fac6b15bcfe5ea55c18c9eaec8e5b7e6457d974/internal/runtime/executor/codex_openai_images.go#L318-L376)。

历史成功证明这些有限条件下的调用链可用。后续升级、改变认证来源或增加图片能力时，仍应按[验收检查表](#verification-checklist)重新验证受影响的部分。
