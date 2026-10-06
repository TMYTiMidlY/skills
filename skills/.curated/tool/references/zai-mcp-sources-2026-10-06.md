# Z.ai MCP 来源摘录（2026-10-06）

本文件保存核验日从官方文档读取的关键原文与配置值，作为 [Z.ai MCP](zai-mcp.md) 的日期快照；不是官网全文镜像，也不承诺之后的服务行为。此次读取的官网页面没有页面版本号，因此保留可点击的阅读入口，并将用于判断的摘录固定在本仓。省略号表示省略不影响对应断言的文字。

Vision 的实现依据另固定到 npm 发布版本 `@z_ai/mcp-server@0.1.5`，读取的是发布包中的编译 JavaScript；未安装、执行该包，未核验其上游 TypeScript 仓库或云端实现。

## <a id="service-types"></a>服务形态与工具

| 官方页面 | 原文摘录 |
|---|---|
| [Vision](https://docs.z.ai/devpack/mcp/vision-mcp-server.md) | “The Visual Understanding MCP Server is an exclusive Local MCP Server developed by Z.AI for GLM Coding Plan users.” |
| [Web Search](https://docs.z.ai/devpack/mcp/search-mcp-server.md) | “The Web Search MCP Server is an exclusive Remote MCP Server developed by Z.AI for GLM Coding Plan users.”；“HTTP protocol-based remote MCP service, no local installation required” |
| [Web Reader](https://docs.z.ai/devpack/mcp/reader-mcp-server.md) | “The Web Reader MCP Server is an exclusive Remote MCP Server developed by Z.AI for GLM Coding Plan users.”；“HTTP-based remote MCP service, no local installation required” |
| [Zread](https://docs.z.ai/devpack/mcp/zread-mcp-server.md) | “Built on the Model Context Protocol (MCP) and powered by zread.ai, it provides access to open-source repository documentation, code structures, and file contents” |

Web Search 工具条目：

> **`webSearchPrime`** - Search web information, returning results including page titles, URLs, summaries, site names, site icons, and more.

Web Reader 工具条目：

> **`webReader`** — Fetch webpage content for a specified URL. Returns the page title, main content, metadata, list of links, and more.

Zread 工具清单的名称为 `search_doc`、`get_repo_structure`、`read_file`。Vision 网页清单为 `ui_to_artifact`、`extract_text_from_screenshot`、`diagnose_error_screenshot`、`understand_technical_diagram`、`analyze_data_visualization`、`ui_diff_check`、`image_analysis`、`video_analysis`；发布包 0.1.5 的后两项实际注册名是 `analyze_image`、`analyze_video`，见 [图片工具](https://unpkg.com/@z_ai/mcp-server@0.1.5/build/tools/general-image.js) 与 [视频工具](https://unpkg.com/@z_ai/mcp-server@0.1.5/build/tools/video-analysis.js)。

### <a id="vision-media"></a>Vision 官方媒体描述

[英文 Vision 文档](https://docs.z.ai/devpack/mcp/vision-mcp-server.md)的 `video_analysis` 条目：

> Inspect videos (local/remote ≤8 MB; MP4/MOV/M4V) to describe scenes, moments, and entities.

[中文 Vision 文档](https://docs.bigmodel.cn/cn/coding-plan/mcp/vision-mcp-server.md)的 `video_analysis` 条目：

> 支持 MP4/MOV/M4V(限制本地最大8M) 等格式的视频场景解析，抓取关键帧、事件与要点

这两段是官网支持说明；[0.1.5 文件处理代码](https://unpkg.com/@z_ai/mcp-server@0.1.5/build/core/file-service.js)的本地校验和 HTTP(S) URL 提前返回行为另见 [发布包摘录](#vision-release)。

## <a id="connection"></a>接入配置值

以下值取自上列官方 MCP 页的客户端配置示例；国内入口同时核对了智谱的 [Search](https://docs.bigmodel.cn/cn/coding-plan/mcp/search-mcp-server.md)、[Reader](https://docs.bigmodel.cn/cn/coding-plan/mcp/reader-mcp-server.md)、[Zread](https://docs.bigmodel.cn/cn/coding-plan/mcp/zread-mcp-server.md) 页面。

| 服务 | Z.ai 示例 URL | 智谱国内示例 URL |
|---|---|---|
| Web Search | `https://api.z.ai/api/mcp/web_search_prime/mcp` | `https://open.bigmodel.cn/api/mcp/web_search_prime/mcp` |
| Web Reader | `https://api.z.ai/api/mcp/web_reader/mcp` | `https://open.bigmodel.cn/api/mcp/web_reader/mcp` |
| Zread | `https://api.z.ai/api/mcp/zread/mcp` | `https://open.bigmodel.cn/api/mcp/zread/mcp` |

认证示例均为 `Authorization: Bearer <API_KEY>`。旧版 Cline 示例另给各服务对应的 `/sse?Authorization=<API_KEY>`。

[Zread 站点 MCP 说明](https://zread.ai/mcp)的 SSE 小节写 “Recommended for priority use.”；Z.ai 文档则将 SSE 放在旧 Cline 不支持 Streamable HTTP 的分支。两者给出了两种接入方式，但推荐顺序的文案不一致。

[英文 Vision 文档](https://docs.z.ai/devpack/mcp/vision-mcp-server.md)写 “Node.js >= v22.0.0”、`Z_AI_MODE=ZAI`；[中文 Vision 文档](https://docs.bigmodel.cn/cn/coding-plan/mcp/vision-mcp-server.md)写 “Node.js 18 或更新版本”，模式默认 `ZHIPU`，可选 `ZHIPU` 或 `ZAI`。

## <a id="vision-release"></a>Vision 发布包

[标准 npm registry 的 0.1.5 元数据](https://registry.npmjs.org/@z_ai%2Fmcp-server/0.1.5)摘录：

```json
{
  "name": "@z_ai/mcp-server",
  "version": "0.1.5",
  "bin": { "zai-mcp-server": "build/index.js" },
  "engines": { "node": ">=18.0.0" },
  "gitHead": "fb0a079999af4fc8c89cfc573e5c9723950d7f09",
  "dist": {
    "tarball": "https://registry.npmjs.org/@z_ai/mcp-server/-/mcp-server-0.1.5.tgz",
    "shasum": "92c88e768233c0b888fd621cadde10a406dbbb25",
    "integrity": "sha512-zbZaVIUtsGjlc9oI/E+/gLfhylcZLGUfS356Zte9hdufSqmnIXw9lzhH07fIiHr4t+S3VDnV0A1v0XeRuhuiNA=="
  }
}
```

发布元数据没有 `repository` 字段；`gitHead` 本身不足以定位可引用的公开 Git 仓库。[版本化发布文件清单](https://unpkg.com/@z_ai/mcp-server@0.1.5/?meta)可用来核对编译文件。

[环境配置代码](https://unpkg.com/@z_ai/mcp-server@0.1.5/build/core/environment.js)摘录：

```javascript
// Priority: PLATFORM_MODE > Z_AI_MODE > default(ZHIPU)
const platformMode = envConfig.PLATFORM_MODE || envConfig.Z_AI_MODE;
// getVisionConfig() 中：
model: config.Z_AI_VISION_MODEL || 'glm-5.3-flash',
timeout: parseInt(config.Z_AI_TIMEOUT || '300000'),
url: config.Z_AI_BASE_URL + 'chat/completions',
```

代码将 ZAI 模式指向 `https://api.z.ai/api/paas/v4/`，将 ZHIPU 模式指向 `https://open.bigmodel.cn/api/paas/v4/`。识别出的平台模式会覆盖 `Z_AI_BASE_URL`。`Z_AI_API_KEY` 缺失时先用 `ZAI_API_KEY` 回填；之后若 Key 仍为空，或转小写后包含 `api` 或 `key`，则尝试使用存在且转小写后不含 `api` 的 `ANTHROPIC_AUTH_TOKEN`，否则报错。这是代码的占位值判定启发式，不是对实际 Key 有效性的认证；显式提供的 Key 也可能因此被覆盖。

[文件处理代码](https://unpkg.com/@z_ai/mcp-server@0.1.5/build/core/file-service.js)的 `validateImageSource` 默认限制 `5 * 1024 * 1024` 字节、扩展名 `.jpg/.jpeg/.png`；`validateVideoSource` 默认限制 `8 * 1024 * 1024` 字节，未执行视频扩展名校验。两种校验遇到 HTTP(S) URL 均提前返回。`encodeImageToBase64`、`encodeVideoToBase64` 对本地文件读取完整字节并生成 data URL，对 HTTP(S) 输入直接返回 URL。

[云端请求代码](https://unpkg.com/@z_ai/mcp-server@0.1.5/build/core/chat-service.js)的 `chatCompletions` 使用 `fetch` 发起 JSON POST，并添加 Bearer 认证；`visionCompletions` 从 `choices[0].message.content` 提取结果。

[响应与重试代码](https://unpkg.com/@z_ai/mcp-server@0.1.5/build/core/api-common.js)将成功结果包装为 MCP `content` 文本，失败结果附 `isError: true`。上述图片、视频工具注册时使用 `withRetry(..., 2, 1000)`，即初次尝试后最多两次重试，分别等待 1 秒、2 秒；包装器没有按 HTTP 状态筛选临时错误。这里是 0.1.5 客户端行为，不是远程 MCP 的重试或扣费保证。

[日志代码](https://unpkg.com/@z_ai/mcp-server@0.1.5/build/utils/logger.js)将日志写入 stderr 和文件；默认位置 `~/.zai/zai-mcp-YYYY-MM-DD.log`，允许 `ZAI_MCP_LOG_PATH` 改路径。[图片工具](https://unpkg.com/@z_ai/mcp-server@0.1.5/build/tools/general-image.js)和[视频工具](https://unpkg.com/@z_ai/mcp-server@0.1.5/build/tools/video-analysis.js)的日志调用会传入输入路径或 URL、prompt，失败分支还会传入 `params`。

## <a id="reader-api"></a>Reader API

[Web Reader API](https://docs.z.ai/api-reference/tools/web-reader.md)公布 `POST https://api.z.ai/api/paas/v4/reader`。以下为 `ReaderRequest` 属性与默认值的摘录，不是远程 MCP 的独立版本保证：

| 属性 | 文档中的类型或默认值 |
|---|---|
| `url` | string，唯一 required 属性 |
| `timeout` | integer，20 秒 |
| `no_cache` | boolean，false |
| `return_format` | string，markdown；说明举例 markdown、text |
| `retain_images` | boolean，true |
| `no_gfm` | boolean，false |
| `keep_img_data_url` | boolean，false |
| `with_images_summary` | boolean，false |
| `with_links_summary` | boolean，false |

结果的 `reader_result` 包含 `content`、`description`、`title`、`url`、`external`、`metadata`。MCP 页描述抓取和提取能力，未公布浏览器内核、抓取供应商、代理池、固定出口 IP、cookie 透传或 JavaScript 渲染保证。

[Search API](https://docs.z.ai/api-reference/tools/web-search.md)另公布 `POST /paas/v4/web_search`；引擎枚举只有 `search-prime`，但 `count`、域名和时间过滤的属性说明仍写 “Supported search engines: search_pro_jina”。该 API 页面存在命名不一致，不能据此补造 `webSearchPrime` 的 MCP 参数或证明 Reader 使用 Jina。

## <a id="repository-scope"></a>Zread 仓库范围

[Z.ai Zread MCP 的 Repository access failed 小节](https://docs.z.ai/devpack/mcp/zread-mcp-server.md)：

> Confirm the repository exists and is open source (public)
>
> Check if the repository name is spelled correctly (owner/repo)
>
> Visit zread.ai to search if this open source repository is supported

[中文对应页面](https://docs.bigmodel.cn/cn/coding-plan/mcp/zread-mcp-server.md)：

> 确认仓库是否存在且为开源（公开）仓库
>
> 访问 zread.ai 搜索此开源仓库是否被收纳支持

[Zread MCP 站点说明](https://zread.ai/mcp)：

> Currently, Zread MCP is only open to users who have purchased the GLM Coding Plan.
>
> It is currently provided via the GLM public cloud; separate enterprise versions or private deployments are not currently offered.

这里描述的是 Coding Plan 云 MCP。Zread 网站的私库导航是另一产品入口，不能用其存在替代该 MCP 的仓库授权说明。[Zread CLI 页面](https://zread.ai/cli)另有以下原文：

> Zread CLI is built for local repository workflows and helps developers generate project docs directly from a local directory.

本地仓库 CLI 的工作流也不能代替云 MCP 的私库授权契约。

## <a id="plan-credits"></a>套餐与 credits

[Z.ai Overview](https://docs.z.ai/devpack/overview.md)：

> All plans support Vision Understanding, Web Search MCP， Web Reader MCP and Zread MCP ...
>
> Each plan is subject to both a 5-hour usage limit and a weekly usage limit.
>
> MCP tool credit usage = Number of calls × Output multiplier

核验日计费表中 Web Search、Web Reader、Zread 的 Output Multiplier 均为 `1.2`；Vision 被列在 “GLM-5.3-Flash (Including MCP for visual understanding)” 模型行，以输入、缓存输入和输出 token 计算。

[智谱中文 FAQ](https://docs.bigmodel.cn/cn/coding-plan/faq.md)的 MCP 问答：

> 模型与 MCP 共享套餐调用额度，详情请查看用量说明。
>
> 除了套餐包，我们暂未提供其他调用这些 MCP 工具的接入方案。

[2026-07-30 套餐更新公告](https://docs.z.ai/devpack/notice/usage-revision.md)：

> Your current price, benefits, usage limits, and calculation method stay unchanged until the end of the current billing cycle.
>
> Plans are not switched automatically. You must subscribe or switch manually.

前一引句分别出现在 Legacy V1、Legacy V2、旧 Team 的说明中。新 credits 规则不能直接代入全部存量订阅。

[Team Plan](https://docs.z.ai/devpack/teamplan.md)：

> The Team Plan Key is independent from other platform API Keys. To use your Team Plan quota, make sure to use the Team Plan Key in the relevant scenarios.
>
> The team administrator can enable on-demand usage overage in advance.

Team 的超额说明主要针对模型，未逐工具给出 MCP 超额细节。[Usage Policy](https://docs.z.ai/devpack/usage-policy.md)还规定套餐仅用于官方支持的工具，速率和并发限制随套餐、资源动态调整；文档未给出固定 MCP QPS。

## <a id="errors"></a>错误码

[Z.ai 通用 API 错误表](https://docs.z.ai/api-reference/api-code.md)：

> the outer layer is the HTTP status code, and the inner layer is the business error code defined by Z.AI in the response body

| HTTP 状态 | 业务码 | 官方描述的含义 |
|---|---|---|
| 401 | 1000 / 1001 / 1003 | 认证失败 / Header 缺认证参数 / Token 过期 |
| 403 | 1220 | 无 API 访问权限 |
| 429 | 1113 | 余额不足或没有资源包 |
| 429 | 1302 / 1305 | 请求限频 / 临时过载 |
| 429 | 1308 / 1310 | 时间窗口额度 / 周或月额度耗尽，描述含 `next_flush_time` |
| 429 | 1309 / 1313 | 套餐过期 / 公平使用风控 |

这是通用 API 表，未实测远程 MCP 是否原样保留其 JSON 结构与业务码。[智谱速率限制页面](https://docs.bigmodel.cn/cn/api/rate-limit.md)针对 1302、1305 分别给出以下建议：

> 降低并发请求数量
>
> 增加请求队列或排队机制

> 稍后重试请求
>
> 增加重试间隔，避免立即高频重试

它描述通用 API 与 Coding Plan 的动态并发策略，没有给出独立 MCP 的固定 QPS。

## <a id="reader-observations"></a>Reader 会话实测

以下是 2026-10 会话观察，独立于官网声明；不保存机器地址或具体出口 IP。

- `webReader` 读取普通 Google 搜索 URL 时，曾返回结果标题、摘要和显示网址。
- 2026-10-06 补测：带 `site:` 过滤的搜索 URL 返回 MCP `-400: Please Enter the Correct URL Format！`；另一查询只返回 Google 的访问故障提示。没有证据将失败唯一归因于某个参数、编码方式或反爬策略。
- 用 `no_cache=true` 让 Reader 读取 `https://api.ipify.org?format=json`，与本机独立访问同一检测服务对比，两次观察的公网出口不同。这只能识别各自访问检测服务时的出口，不能确定同一服务访问 Google 时的出口、机房、固定地区或固定代理供应商。
- 本机的 HTTP 请求也可能经过 TUN、VPN 或代理；比较的是当时的出口，而非未经代理的物理主机公网地址。
