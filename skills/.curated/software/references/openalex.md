# OpenAlex 数据访问、CLI 与全文下载

OpenAlex 把学术元数据、开放获取状态与缓存全文放在不同的服务面上；排障时先分清要的是元数据、OA 位置，还是 OpenAlex 已缓存的 PDF / TEI XML。本文覆盖官方 CLI 的安装和边界、当前全文下载兼容性、API 与批量数据入口，以及不同规模任务的选择依据。

> 本文按 2026-08-22 的实测与当时已部署的官方文档整理；官方认证页更新至 2026-08-19，Snapshot / Sync 页更新至 2026-08-17，CLI / Fulltext 页更新至 2026-08-11。动态数量和价格应回看对应 manifest 与[官方费用表](https://help.openalex.org/access/example-costs/)，不要由网页更新时间推断数据发布日期。

## <a id="data-surfaces"></a>数据对象与访问入口

OpenAlex 的入口共享同一知识图谱，但数据范围、时效和传输方式不同。官方的[访问方式总览](https://help.openalex.org/access/overview/)把它们分成网站、Agents、API、CLI、Snapshot、Sync、Fulltext 与 Unpaywall：

| 入口 | 数据范围 | 时效 | 典型用途 |
| --- | --- | --- | --- |
| 网站 Basic / Advanced / OQL | 在线查询结果 | 实时服务面 | 浏览、聚合、导出不超过 100,000 条 works |
| REST API | 全实体元数据与查询 | 实时服务面 | 脚本、应用、按 DOI / ID 查询与筛选 |
| `openalex-official` CLI | works 元数据与缓存全文 | 跟随 API | 终端批量下载、并发、检查点与 S3 输出 |
| 公共 Snapshot | 完整元数据图谱 | 免费季度发布 | 离线仓库、全量连接与重复分析 |
| 付费 Sync | 每日完整快照或持续更新筛选 | 每日 / 连续 | 生产镜像与持续更新的子集 |
| Content API / R2 archive | OpenAlex 已缓存的 PDF 与 TEI XML | 持续变化 | 单文件、小语料或完整全文归档 |
| Unpaywall | Crossref DOI 的 OA 状态与位置 | 在线 / 付费每日 feed | 旧格式兼容、图书馆 link resolver、纯 DOI OA 查询 |

元数据与全文的授权也不同：OpenAlex 元数据按 CC0 发布；PDF 保留原始版权，OpenAlex 不额外授予复制或再分发权。`is_oa=true` 表示存在免费可读位置，`has_content.pdf=true` 表示 OpenAlex 已缓存 PDF，这两个集合不能互换；再利用前还要核对 `best_oa_location.license` 或文献自身版权声明。[Fulltext 文档](https://help.openalex.org/access/fulltext/)明确区分了缓存覆盖、传输服务与原文版权。

OQL 是面向人的查询语言，OQO 是同一查询的 JSON 表达；两者运行在网站或 API 上，不是新的数据传输协议。OQL 可以表达跨字段 OR、嵌套布尔条件、精确 / 词干 / 邻近 / 语义搜索、引用关系、分组和抽样，详见 [OQL](https://help.openalex.org/access/oql/) 与 [OQO schema](https://help.openalex.org/access/oqo-schema/)。排序、字段投影和分页仍是查询之外的展示 / API 参数。

## <a id="cli-installation"></a>CLI 安装与认证

官方 Python 包是 `openalex-official`，全局工具用 uv 安装：

```bash
uv tool install openalex-official
openalex --help
```

升级与卸载分别使用：

```bash
uv tool upgrade openalex-official
uv tool uninstall openalex-official
```

`download` 和 `status` 都把 `--api-key` 声明为必填，但会读取 `OPENALEX_API_KEY`（分别见 [download 选项](https://github.com/ourresearch/openalex-official/blob/v0.3.3/src/openalex_cli/cli.py#L108-L114)与 [status 选项](https://github.com/ourresearch/openalex-official/blob/v0.3.3/src/openalex_cli/cli.py#L360-L366)）。长期或自动化使用时把 key 放进环境变量或带外 secret 注入，不要写进脚本、共享日志、命令历史或 URL：

```bash
export OPENALEX_API_KEY='<API key>'
openalex status
```

OpenAlex 把 API key 同时当作账户身份和额度归属；泄漏时应在设置页轮换。认证的两种 HTTP 形式是 `?api_key=...` 与 `Authorization: Bearer ...`，二者语义相同，见[认证文档](https://help.openalex.org/api/authentication/)。

### <a id="keyless-access"></a>无 key 与免费 key

原始 API 允许无 key 基础访问，CLI 本身却在参数解析阶段拒绝无 key 的 `download` / `status`。因此“API 可匿名调用”不等于“CLI 可匿名下载”：

- 单实体按 ID / DOI 查询免费且不消耗预算；
- 无 key 有约 `$0.10/天` 的匿名预算；
- 免费账户 key 有 `$1/天`，每日 UTC 00:00 重置；
- 匿名预算按未认证请求归集，NAT / 共享出口环境更容易提前耗尽。

按[官方示例费用](https://help.openalex.org/access/example-costs/)换算：

| 操作 | 单价 | 无 key 每日预算约可完成 | 免费 key 每日预算约可完成 |
| --- | --- | ---: | ---: |
| 单实体查询 | 免费 | 不限 | 不限 |
| list / filter | `$0.10 / 1,000 calls` | 1,000 calls | 10,000 calls |
| 关键词 / 语义搜索 | `$1 / 1,000 calls` | 100 calls | 1,000 calls |
| PDF 或 TEI XML | `$10 / 1,000 files` | 10 files | 100 files |

这些操作共用同一日预算，不是各自独立配额；页面大小尽量用 API 当前允许的上限。CLI 没有独立 `search` 参数，搜索行只适用于网站 / API。

## <a id="cli-scope"></a>CLI 的数据范围与输出

`openalex download` 默认只保存完整 Work JSON，可用三种输入方式：

```bash
openalex download --ids 'W3038568908,10.1585/pfr.15.2402039' -o ./results
openalex download --filter 'publication_year:2024,type:article' -o ./results
printf '%s\n' W3038568908 | openalex download --stdin -o ./results
```

它还支持 `--sample` / `--seed`、本地或 S3 存储、1–200 workers、嵌套目录、日志、检查点与 resume。JSON 元数据总会尝试保存；`--content pdf`、`--content xml` 或 `--content pdf,xml` 再请求缓存全文。按 DOI 输入时，CLI 先用 filter API 批量解析成 Work ID，再以 DOI 生成文件名。

当前 CLI 是 Beta / work in progress，只处理 works，不提供通用实体导出、CSV 或关键词 `search`。筛选模式先用 list API 找 work，再以免费 singleton 查询补全每条记录；后一步并非完全多余，因为 list 响应会截断超长 `authorships`，singleton 可保留完整作者列表，[issue #5 的复核](https://github.com/ourresearch/openalex-official/issues/5#issuecomment-4730975345)记录了这个差异。

## <a id="content-http-200"></a>v0.3.3 的全文 HTTP 200 兼容性

截至 2026-08-22，`openalex-official 0.3.3` 的元数据路径正常，但 PDF 内容路径把成功的 HTTP 200 响应误判为失败。问题来自客户端仍假设 Content API 首跳必定返回重定向：

1. 以 `allow_redirects=False` 请求 `content.openalex.org/works/{id}.pdf`；
2. 只接受 301 / 302 / 307 / 308；
3. 读取 `Location` 后再下载签名对象；
4. 任何其他状态，包括 `200 application/pdf`，都返回 `Unexpected status: 200`。

这段逻辑可在 [v0.3.3 `api_client.py`](https://github.com/ourresearch/openalex-official/blob/v0.3.3/src/openalex_cli/api_client.py#L290-L371) 直接核对，从[初始实现 `a53f3f7`](https://github.com/ourresearch/openalex-official/commit/a53f3f75c23024561ca87309120ab943b8d86848)起一直保留。当前官方 [Fulltext](https://help.openalex.org/access/fulltext/) 则直接给出 `curl https://content.openalex.org/works/{id}.pdf?api_key=...`，没有要求调用者只接受重定向。

### <a id="content-reproduction"></a>交叉实测

使用有效免费 key，对两篇 `has_content.pdf=true` 的公开文献交叉测试：

| Work | CLI | 直接 Content API |
| --- | --- | --- |
| `W3038568908` | 保存 JSON，PDF 报 `Unexpected status: 200` | `200 application/pdf`，5,018,540 bytes，有效 PDF 1.4、7 页 |
| `W1775749144` | 保存 JSON，PDF同样失败 | `200 application/pdf`，823,098 bytes，有效 PDF 1.7、11 页 |

第二篇同时用 Bearer header 和官方 `?api_key=` 形式请求，并禁止自动重定向；两者均返回 200、正文以 `%PDF` 开头、没有 `Location`。响应头包含：

```text
content-type: application/pdf
x-ratelimit-cost-usd: 0.01
x-ratelimit-credits-used: 100
```

直接访问第二篇的出版社 PDF URL 则得到 Cloudflare 403 HTML，而 OpenAlex 缓存副本正常。这说明自动化全文获取应优先使用 Work 的 `content_urls.pdf`，而不是把 `best_oa_location.pdf_url` 当成稳定归档地址。

### <a id="content-impact"></a>失败边界

这个兼容性问题有三个容易误判的结果：

- Content API 已经返回并计费 `$0.01`，CLI 只是丢弃正文；反复 `--fresh` 重试会继续消耗预算。
- JSON 元数据已经写入，但 checkpoint 把 work 标为失败，汇总显示 `Downloaded: 0 files`。
- 一般内容失败不会让 CLI 返回非零退出码；`cli.py` 只在 credits exhausted 时显式 `sys.exit(1)`（[v0.3.3 `cli.py`](https://github.com/ourresearch/openalex-official/blob/v0.3.3/src/openalex_cli/cli.py#L348-L357)）。自动化不能只看进程退出码，还要检查日志、checkpoint 与实际文件。

PDF 与 XML 共用 `download_content()`，所以直返 200 时都会经过同一错误分支。XML 还有格式命名的不确定性：已合入的提交修正了 `.grobid-xml` 请求 URL，但未合并的 [PR #1](https://github.com/ourresearch/openalex-official/pull/1) 还主张按 gzip 内容保存为 `.xml.gz`；当前代码仍写 `.tei.xml` / `application/xml`。使用 XML 前应实测 `Content-Type`、`Content-Encoding` 与 magic bytes，不能仅信扩展名。

### <a id="content-upstream"></a>上游状态

官方仓库是 [ourresearch/openalex-official](https://github.com/ourresearch/openalex-official)，PyPI 与唯一 GitHub release 均为 [v0.3.3（2026-03-18）](https://github.com/ourresearch/openalex-official/releases/tag/v0.3.3)。截至 2026-08-22，主分支在该日期后没有新提交；完整枚举 issue、PR、评论、review、timeline、主分支与 PR commits 后，没有发现 `Unexpected status: 200`、上述 Work ID 或等价修复。

最接近的是：

- [issue #9](https://github.com/ourresearch/openalex-official/issues/9)：旧重定向流程把出版社 Cloudflare HTML 静默保存成 PDF，暴露出内容类型 / magic 未校验；
- [issue #10](https://github.com/ourresearch/openalex-official/issues/10)：429 恢复不足；
- [issue #15](https://github.com/ourresearch/openalex-official/issues/15)：CLI 缺少搜索参数；
- [PR #14](https://github.com/ourresearch/openalex-official/pull/14)：未合并的重试、检查点与进度修复，仍保留 redirect-only 内容逻辑。

社区 PyAlex 的 [issue #100](https://github.com/J535D165/pyalex/issues/100) 在 2026-03 仍观察到 302 + 签名 CDN 的两段流程；当前实测已变成直接 200。公开证据足以确认客户端 / 服务端契约不匹配，但不足以给服务端切换方式定出准确日期。

发布元数据也有一处小错位：`pyproject.toml` 声明 `0.3.3`（[源码](https://github.com/ourresearch/openalex-official/blob/v0.3.3/pyproject.toml#L1-L10)），运行时 `__version__` 仍是 `0.3.2`（[源码](https://github.com/ourresearch/openalex-official/blob/v0.3.3/src/openalex_cli/__init__.py#L1-L3)），所以 `openalex --version` 会少报一个 patch 版本。

### <a id="content-workaround"></a>当前绕行与修复形态

在 CLI 合入兼容修复前，元数据仍可用 CLI；PDF / XML 改为直接调用 `content_urls`。自动化下载至少检查：

1. HTTP 状态为 200；若要兼容旧服务，也支持 3xx 后再取签名 URL；
2. PDF 的 `Content-Type` 与前四字节 `%PDF`；
3. XML 的实际编码、压缩格式和根元素；
4. 不合理的小文件、HTML challenge、登录页与 paywall；
5. `X-RateLimit-*` 费用 / 剩余额度；
6. 文件大小、哈希、重试次数与 checkpoint。

CLI 侧的最小兼容修复应让 `download_content()` 同时处理 200 与 3xx，在保存前验证内容，并让存在失败文件的整批任务返回非零退出码。当前响应头使用 `X-RateLimit-Cost-USD` / `X-RateLimit-Credits-Used`；代码读取旧的 `X-Credits-Cost` 并默认 100，也应一并兼容。

## <a id="doi-workflow"></a>DOI 到元数据和全文

按 DOI 构建可复核下载流程时，把“解析文献”“判断缓存与授权”“下载内容”分开：

1. 用 singleton DOI 查询或批量 DOI filter 得到 Work；singleton 免费，批量 filter 有极低调用成本。
2. 保存完整 Work JSON，记录 OpenAlex ID、DOI、`open_access`、`best_oa_location`、`has_content` 与 `content_urls`。
3. `has_content.pdf=true` 时才请求 `content_urls.pdf`；需要结构化文本则检查 `has_content.grobid_xml`。
4. 下载后按上一节校验内容，不把 HTTP 200 单独当成成功证据。
5. 另行判断许可证；`license=null` 只表示 OpenAlex 未识别许可证，不能据此推断可任意再分发。

一次性手工调用可以使用：

```bash
curl --fail --show-error --location \
  -H "Authorization: Bearer $OPENALEX_API_KEY" \
  --output '<work-id>.pdf' \
  'https://content.openalex.org/works/<work-id>.pdf'
```

Shell 展开 header 后，key 可能短暂出现在同用户可见的进程参数中；对凭据隔离要求高的自动化，应让 HTTP 客户端在进程内从环境变量读取 key，或使用运行环境的带外 secret 注入，不把值拼进 argv。下载完成后至少检查 `%PDF`、大小与哈希。

## <a id="metadata-bulk"></a>元数据的批量入口

### <a id="website-export"></a>网站与导出

[Basic](https://help.openalex.org/access/website-basic/)适合常规搜索、筛选、facet 与排序；Advanced Builder 允许可视化 AND / OR / 分组，并同步显示 OQL（[文档](https://help.openalex.org/access/website-advanced/)）。网站可把 works 结果导出为 CSV、RIS 或类似 Web of Science / Dimensions 的 TXT，最多 100,000 works；CSV 是扁平化结果，Excel 兼容截断会损失长字段，见[集成文档](https://help.openalex.org/how-to/integrations/#how-do-i-export-results-from-the-openalex-website)。

### <a id="public-snapshot"></a>公共 Snapshot

公共 Snapshot 是完整元数据图谱，原生托管在 AWS S3，可匿名读取，无需 AWS 账户；JSONL gzip 与 Parquet Snappy 是两份完整副本，不应无目的地同时下载。按 2026-08-22 读取的 live manifest：

| 格式 | 发布日期 | 记录数 | 压缩字节数 |
| --- | --- | ---: | ---: |
| [JSONL manifest](https://openalex.s3.amazonaws.com/data/jsonl/manifest.json) | 2026-06 | 649,096,577 | 745,496,091,411 |
| [Parquet manifest](https://openalex.s3.amazonaws.com/data/parquet/manifest.json) | 2026-06 | 649,096,577 | 783,555,949,110 |

works 共 510,372,821 条。两种格式合计约 1.529 TB；文档中的概算可能滞后，容量规划和同步都以 manifest 的 `content_length`、文件清单与日期为准。[Snapshot 文档](https://help.openalex.org/access/snapshot/)描述了实体目录、分区与下载认证。

免费公共快照按季度原地替换，只保留当前发布；需要时间点复现时自行归档。记录按 `updated_date` 分区，更新后的记录会从旧分区移动到新分区；直接镜像文件时缺少 `--delete` 会留下重复。2026-08-22 实测公共 works 路径尚无 `deleted_ids.csv`，官方 [Sync 文档](https://help.openalex.org/access/sync/)称付费每日快照从 2026-08-15 起已有，下一次季度公开发布才会带入。合并实体到底 404 还是重定向，官方页面口径不完全一致，生产 ETL 应按实体类型实测并定期全量对账。

### <a id="paid-sync"></a>每日 Snapshot 与增量筛选

Member+ / Partner 提供每日完整 JSONL / Parquet 快照与 premium sync filters；每日快照适合整库镜像，`from_created_date` / `from_updated_date` 适合持续更新某机构、主题等子集。增量筛选不返回删除事件，仍需定期与快照对账。付费快照的历史保留期未公开，不应假设 dated folders 永久存在；访问服务持续提供时，单次临时凭据仍可能轮换。

## <a id="fulltext-archive"></a>全文档案与 R2 同步

OpenAlex Fulltext 是独立于元数据 Snapshot 的缓存档案：50M+ PDF（约 250 TB）与约 43M TEI XML（约 20 TB）。单文件 Content API 适合样本和小语料，每个 PDF 或 XML `$0.01`；完整档案通过 annual plan 的 PDF sync add-on 提供 Cloudflare R2 只读访问，R2 兼容 S3 协议但不是 AWS S3。对象使用 UUID，daily Parquet manifest 把 OpenAlex ID 映射到 PDF / XML 对象。

付费同步是持续服务，但具体 R2 credential 可能有有效期或被轮换，不能把某一组 token 理解成永久凭据。首次同步约 270 TB，官方估计常见网络需要 1–2 周；接收端仍应校验 PDF magic、大小、版权和 GROBID 解析质量。TEI 不做 OCR，扫描件、畸形 PDF、元数据 / 参考文献错配都可能传递到解析结果。

## <a id="unpaywall"></a>Unpaywall 的兼容面

Walden 重写后，Unpaywall 不再是独立数据库，而是同一 OpenAlex 数据管线上的旧格式 OA discovery surface，详见[当前说明](https://help.openalex.org/access/unpaywall/)。它只覆盖 Crossref 签发的 DOI；DataCite DOI 不在 Unpaywall 中，但 OpenAlex 原生 works 可以收录。

- [API v2](https://unpaywall.org/products/api) 免费，以真实 `?email=` 标识调用者，不使用 secret key，官方上限为每日 100,000 calls；
- Simple Query Tool 可无代码提交最多 1,000 DOI；
- 浏览器扩展和 link resolver 面向逐篇 OA 发现；
- Data Feed 为付费的每日旧格式变更，价格未公开；
- 旧的独立 Unpaywall Snapshot 已停用，新批量项目使用 OpenAlex Snapshot。

Unpaywall 的 OA 状态表示免费可读位置，不替代许可证检查。其 schema 允许新增字段，客户端应忽略未知字段；`roadoi` 等包装器也是第三方实现，不是官方 SDK。

## <a id="agents-libraries"></a>Agents、MCP 与社区客户端

官方 [Agents 指南](https://help.openalex.org/access/agents/)描述的是让通用聊天 / coding agent 调 API、CLI 或 Snapshot，不是一个新的托管 Agent API。OQO schema 与 [LLM quick reference](https://help.openalex.org/api/llm-quick-reference/)是官方提供给工具的机器可读接口；截至 2026-08-22，官方访问总览、机器索引和 OurResearch GitHub 组织中都没有官方 OpenAlex MCP Server。

官方当前也没有维护中的语言 SDK；[PyAlex](https://github.com/J535D165/pyalex)与 [openalexR](https://github.com/ropensci/openalexR)是社区客户端。它们继承 API 的数据、额度和时效，但可能落后于认证、价格或接口变化。PyAlex 当前的内容下载实现还有 [issue #100](https://github.com/J535D165/pyalex/issues/100)所列的 extensionless URL、重定向与费用头问题，因此元数据便利封装与全文传输应分别评估。

## <a id="route-selection"></a>按任务选择入口

| 任务 | 对应入口 | 主要边界 |
| --- | --- | --- |
| 浏览、计数、facet | 网站 Basic | 查询形状是友好子集 |
| 复杂无代码检索策略 | Advanced → OQL | OQL 不是批量传输层 |
| DOI / ID 元数据、应用集成 | REST API | 处理分页、重试和额度 |
| 终端元数据批量 | CLI metadata-only | works-only；筛选会再取 singleton |
| 少量 PDF / XML | Content API | `$0.01/文件`，校验格式与版权 |
| CLI PDF / XML | v0.3.3 暂停 | 当前把 HTTP 200 误判失败且仍计费 |
| 完整离线元数据图谱 | 公共 Parquet / JSONL Snapshot | 数百 GB、季度发布、需 ETL |
| 持续更新的元数据子集 | premium sync filters | 付费且不提供删除事件 |
| 每日完整元数据镜像 | 付费 daily Snapshot | 存储和重建成本高 |
| 完整全文语料 | R2 PDF sync add-on | 约 270 TB、报价制、版权与质量治理 |
| Crossref DOI 的 OA 兼容查询 | Unpaywall | 不含 DataCite，旧格式面向既有集成 |
| Agent 生成查询 | OQO / OQL + API | 没有官方 MCP；保存并核查实际请求 |

对“DOI → 完整元数据 → 可用 OA PDF”这类流水线，REST singleton / filter 与 Content API 提供最直接、可观测的分层；CLI 的并发和 checkpoint 设计仍有价值，但 `--content` 需要先兼容 200、验证正文并修正失败退出码。
