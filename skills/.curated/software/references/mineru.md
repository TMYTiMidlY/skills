# MinerU PDF→Markdown 转换

MinerU（mineru.net）提供 VLM 模型将 PDF 转为 Markdown/JSON，支持公式和表格识别。

## 默认策略与本地部署边界

默认优先使用 MinerU 云端 API、Open API SDK 或用户已经明确配置好的现有服务。**未经用户明确允许，不要在本机安装、部署或临时拉取 MinerU 运行环境**，包括但不限于：

- `uvx --from "mineru[all]" ...`
- `pip install "mineru[all]"`
- 启动本地 MinerU / VLM / pipeline 服务

原因：MinerU 本地部署依赖很重，可能拉取数 GB 的 Python、torch、CUDA、vLLM 等组件，耗时、占空间，也可能污染用户环境。若确实需要本地部署，先说明预计影响（下载量、磁盘、是否需要 GPU/CPU、输出目录、如何清理），并等待用户确认。

如果只需要快速预览，优先考虑 flash 模式；如果文件超出 flash 限制或需要完整图片/表格/公式资产，再走 token 认证的精度解析。`mineru-open-sdk` 和 `mineru-open-mcp` 都只是连接云端 API 的轻量客户端，不等于安装本地 MinerU 模型。

## 接入方式选择：REST API、Python SDK、MCP

三者最终都调用 MinerU 云端服务，**解析模型和结果质量不会因为套了 MCP 而提高**；区别在调用契约、暴露能力和运维成本。当前 `software` skill 的默认顺序是：

1. **普通脚本与一次性转换：优先 Python SDK。** 它代办本地文件上传、轮询和结果 ZIP 解析，又保留图片、JSON、额外格式与任务状态。
2. **需要 callback、`no_cache`、自定义调度或精确观察 HTTP 响应：直接 REST API。**
3. **只有目标客户端按 MCP 协议接工具，且主要需求是“文件/URL 转 Markdown”时才选 MCP。** MCP 是 SDK 上的一层 Agent 适配，不是 API 的全功能替代品。

| 能力 | REST API | Python SDK `mineru-open-sdk` | MCP `mineru-open-mcp` |
|---|---|---|---|
| 本质 | 最底层 HTTP 接口 | REST API 的 Python 封装 | 基于 Python SDK 的 MCP Server |
| 安装/进程 | 无 SDK 依赖；自行发 HTTP 请求 | 安装 Python 包；无需常驻服务 | 安装或 `uvx` 临时运行；需要 stdio/HTTP MCP 进程 |
| URL 输入 | 直接提交 | 自动提交 | 支持 |
| 本地文件 | 先申请签名 URL，再 `PUT` | 自动申请并上传 | 自动上传，但 MCP 进程必须能看见该路径 |
| Flash / 精准解析 | 都支持 | 都支持 | 无 MCP token 时自动 Flash，有 token 时精准解析 |
| 参数覆盖 | 最完整，包括 callback、`no_cache`、`page_ranges`、额外格式等 | 模型、OCR、公式、表格、语言、页码、额外格式、超时；当前未直接暴露 callback / `no_cache` | 当前工具主要暴露文件、页码、OCR、语言、模型和输出目录 |
| 异步控制 | 手动提交、轮询或 callback | 阻塞式 `extract*`，也有 `submit*` / `get_*` | 一次工具调用内等待；通常不暴露任务控制原语 |
| 结果 | 原始 JSON、task/batch ID、完整 ZIP | `ExtractResult`、Markdown、`content_list`、图片、DOCX/HTML/LaTeX、`save_all()` | 当前公开工具以 Markdown 为主；见下节的源码边界 |
| 最适合 | 生产编排、回调、特殊参数、排障 | 本 skill 的默认自动化路径 | Claude Desktop、Cursor、Windsurf 等 MCP 客户端的轻量接入 |

### Python SDK

官方仓库：[MinerU-Ecosystem / sdk/python](https://github.com/opendatalab/MinerU-Ecosystem/tree/5733c03b3d53cb01c0361bb6acecda3f554c8c12/sdk/python)。安装：

```bash
# 项目内二选一
uv add mineru-open-sdk
# 或在已激活的 Python 环境中
pip install mineru-open-sdk
```

认证变量用 `MINERU_TOKEN`，值只放 token 本体，不包含 `Bearer `：

```bash
export MINERU_TOKEN="<token>"
```

精准解析示例：

```python
from mineru import MinerU

with MinerU() as client:  # 自动读取 MINERU_TOKEN
    result = client.extract(
        "https://example.com/file.pdf",  # 也可传本地路径
        model="vlm",
        ocr=False,
        formula=True,
        table=True,
        language="ch",
    )
    result.save_all("./mineru_output/file")
```

`extract()` / `extract_batch()` 会阻塞并轮询到结束；长流程可改用 `submit()` / `submit_batch()` 后配合 `get_batch()`。没有 `MINERU_TOKEN` 时 client 仍可调用 `flash_extract()`，但其他需要认证的方法会报 `NoAuthClientError`。

## MinerU Open MCP：简介与安装

官方项目：[MinerU-Ecosystem / mcp](https://github.com/opendatalab/MinerU-Ecosystem/tree/5733c03b3d53cb01c0361bb6acecda3f554c8c12/mcp)，PyPI 包名为 [`mineru-open-mcp`](https://pypi.org/project/mineru-open-mcp/)。它把 MinerU 云端解析包装成两个 MCP 工具：`parse_documents`（文件/URL 转 Markdown）与 `get_ocr_languages`（列 OCR 语言）。它适合 MCP 客户端开箱即用，但不是本地解析服务；文档仍会上传至 `mineru.net`。

### stdio：客户端自动启动

有 `uv` 时无需预装，在 MCP 客户端配置中使用 `uvx`：

```json
{
  "mcpServers": {
    "mineru": {
      "command": "uvx",
      "args": ["mineru-open-mcp"],
      "env": {
        "MINERU_API_TOKEN": "<token>",
        "OUTPUT_DIR": "/absolute/path/to/mineru-downloads"
      }
    }
  }
}
```

也可先固定安装再让客户端执行二进制：

```bash
uv tool install mineru-open-mcp
```

不设置 `MINERU_API_TOKEN` 时 MCP 自动使用 Flash 模式。token 不要提交进 Git；客户端支持 secret/env 注入时优先走注入。带沙箱的客户端必须把 MCP 进程可见的**绝对文件路径**传给工具，否则它找不到拖入聊天框后被隔离的临时文件。

### Streamable HTTP：手动启动

只在确实需要多个 Web/MCP 客户端共享时使用，并默认只监听回环地址：

```bash
MINERU_API_TOKEN="<token>" \
uvx mineru-open-mcp --transport streamable-http --host 127.0.0.1 --port 8001
```

客户端连接 `http://127.0.0.1:8001/mcp`。若要跨主机暴露，另行配置 TLS、认证和网络边界，不要直接把默认无保护端口暴露到公网。

> **环境**：以下边界核对自本地完整 clone `MinerU-Ecosystem` 的 commit [`5733c03b3d53cb01c0361bb6acecda3f554c8c12`](https://github.com/opendatalab/MinerU-Ecosystem/commit/5733c03b3d53cb01c0361bb6acecda3f554c8c12)，是该版本的实现行为，不是 MinerU API 的永久契约。
>
> - MCP 的 [`pyproject.toml`](https://github.com/opendatalab/MinerU-Ecosystem/blob/5733c03b3d53cb01c0361bb6acecda3f554c8c12/mcp/pyproject.toml#L15-L23) 直接依赖 `mineru-open-sdk`，所以它与 SDK/API 使用同一云端后端。
> - 有 token 时 `parse_documents` 调用 SDK 的 [`extract_batch()`](https://github.com/opendatalab/MinerU-Ecosystem/blob/5733c03b3d53cb01c0361bb6acecda3f554c8c12/mcp/src/mineru_open_mcp/tools/extract.py#L158-L220)；公开参数没有覆盖 SDK 的公式、表格、额外格式、callback、`no_cache` 和轮询控制。
> - [`tools.py`](https://github.com/opendatalab/MinerU-Ecosystem/blob/5733c03b3d53cb01c0361bb6acecda3f554c8c12/mcp/src/mineru_open_mcp/tools/tools.py#L47-L139) 将单文件 Markdown 内联限制为 20,000 字符、总内联限制为 60,000 字符；超出部分写到 `OUTPUT_DIR`。多文件调用直接把 Markdown 写到输出目录。
> - 当前实现先取得 `result.zip_url`，但最终响应会[主动移除 `zip_url`](https://github.com/opendatalab/MinerU-Ecosystem/blob/5733c03b3d53cb01c0361bb6acecda3f554c8c12/mcp/src/mineru_open_mcp/tools/tools.py#L127-L160)；`task_id` 也只在 debug 日志级别下附带。因此 README 中“返回 ZIP 链接/更多输出格式”的表述不能当作当前工具契约。需要完整 ZIP、图片、JSON 或额外格式时用 Python SDK / REST API。

## Flash 模式（无需 token，适合快速预览）

MinerU Open API SDK 提供 `flash_extract()`，不需要 `MINERU_TOKEN`。适合小文件快速转 Markdown：

```python
from mineru import MinerU

client = MinerU()
result = client.flash_extract("https://example.com/file.pdf")
print(result.markdown)
```

边界：

- 不需要 token；如果没有 `MINERU_TOKEN`，客户端只能使用 flash 类能力。
- 单文件限制约为 **10MB / 20 页**。
- 默认中文语言，公式和表格识别默认开启，OCR 默认关闭。
- 只适合快速预览 Markdown；需要完整 assets、JSON、DOCX/HTML/LaTeX 等，使用精度解析。

## REST API 认证

REST API 使用 Bearer token。本文的 curl/脚本把 token 存放在 `MINERU_TOKEN` 中，再发送 `Authorization: Bearer $MINERU_TOKEN`；环境变量里只放 token 本体。官方 Python SDK 也读取 `MINERU_TOKEN`，而官方 MCP 另用 `MINERU_API_TOKEN`。

## REST API：URL 提交示例

```bash
curl -s -X POST "https://mineru.net/api/v4/extract/task" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $MINERU_TOKEN" \
  -d '{
    "url": "<PDF 直链>",
    "model_version": "vlm",
    "language": "ch",
    "enable_formula": true,
    "enable_table": true,
    "is_ocr": false
  }'
```

返回 `task_id`，用于轮询结果。

**关于直链：** URL 必须是可直接下载 PDF 文件的链接（Content-Type 为 `application/pdf`），不能是网盘的预览页面。当前使用 Caddy 文件服务，`/share/` 路径直接返回文件。

## `is_ocr` 选什么

**优先 `is_ocr=false`**，前提是 PDF **带嵌入文本层**，即：

- 原生文本 PDF（Word/LaTeX 导出、可复制文字）
- 扫描版但做过 OCR 的双层 PDF（Anna's Archive / duxiu / Acrobat OCR 后保存的 PDF 都属此类）

判断：在 PDF 上 Ctrl+A 能选中连续可复制文字 → 带文本层，`is_ocr=false` 即可。若无文本层（纯扫描未 OCR），必须 `is_ocr=true`。

**两阶段模型**：MinerU 先做 layout（图像识别区域类型），再填充文本。两模式 layout 一致，差异只在文本填充。

| MD 元素 | 谁更好 | 原因 |
|---|---|---|
| `#` 标题层级（几级） | no-OCR | 标题分级靠字号；OCR 丢字号只能粗估；no-OCR 从 PDF 读到字号/粗体，分级精细 |
| `$公式$` 内容 | no-OCR 略好 | PDF 嵌入层含 `×÷≤` 时 no-OCR 直读；OCR 可能把 `×` 误识为 `x` |
| 全/半角标点 | 看原文 | OCR 训练偏全角输出；no-OCR 照搬 PDF 原字符 |
| 表格结构、图片位置 | 一致 | 由 layout 决定 |
| 字符准确率 | 互有胜负 | OCR 错字偏形近（催/摧、赛/寨）；no-OCR 错字偏 PDF 嵌入层原错 |

**策略**：

- 原生文本 PDF：`is_ocr=false`（速度+版式双优）。
- 扫描+已 OCR 双层 PDF：两版都跑做对比；OCR 版为底、no-OCR 补字号/公式。
- 纯扫描未 OCR：只能 `is_ocr=true`。

**额度（过去与现在）**：

- **过去**本地实测记录曾写成“每日总上限 10000 页、前 2000 页高优先级”。**现在**[官方 API 文档](https://mineru.net/apiManage/docs) 写的是：每个账号每天享有 **1000 页最高优先级解析额度**，超过 1000 页的部分降低优先级；当前文档没有继续承诺“每日总上限 10000 页”，不要再依赖旧数字。
- 页数按实际处理范围理解；`is_ocr` 只改变解析方式，不应用来规避页数额度。
- **过去**实测中，失败任务和命中相同 URL 缓存的重复任务没有重复扣额。**现在**公开文档提供 `no_cache` 开关，但没有把失败/缓存的计费行为写成稳定契约；批量生产前应以 API 管理页的当日额度显示和一次小样验证为准。

## 加密 PDF（owner-password 限制型）

z-library / Anna's Archive / 一些扫描书常见 owner-password 加密：限制打印/复制，但内容明文，空密码即可打开。

**MinerU 服务端能直接吃这种 PDF**——URL 提交、batch 上传都不受影响，不需要先解密。

**坑只在本地预处理阶段**：

- 用 `pypdf` 拆分（如 `mineru_large_pdf.py` 处理超 200 页 PDF 走 batch）时，pypdf 解 AES 加密流需要 `cryptography>=3.1`，否则报：
  ```
  pypdf.errors.DependencyError: cryptography>=3.1 is required for AES algorithm
  ```
  连 `len(reader.pages)` 都拿不到，拆分整个失败。本 skill 的 `mineru_large_pdf.py` 已在 PEP 723 inline deps 里声明 `cryptography`，`uv run` 会自动带上；如果用别的运行方式，记得装这个包。
- `PdfWriter` 默认不加密，所以拆出来的 part PDF 是明文的，传给 MinerU 也没限制问题。

**判断是否加密**：用空密码 `pypdf.PdfReader(p).is_encrypted` 即可。整本 PDF 不需要拆（≤200 页且能直接走 batch / URL 方式）的场景，根本不用碰 pypdf，直接丢给 MinerU 最省事。

**主动去限制（可选）**：若需要一份干净无限制的完整 PDF（比如不走拆分、要归档原件），最省事一行：

```bash
qpdf --decrypt in.pdf out.pdf          # 无 qpdf 时用下面的 pypdf 等价写法
```

```python
from pypdf import PdfReader, PdfWriter
r = PdfReader("in.pdf"); r.decrypt("")   # 空密码解开
w = PdfWriter(); w.append(r); w.write("out.pdf")   # 写出的 out.pdf 默认不加密、无限制
```

**能否无痛剥离的判据**：`PdfReader(p).decrypt("")` 的返回值——`1`（pypdf 的 `PasswordType.USER_PASSWORD`，空字符串即开卷密码）说明这是"仅 owner 限制"型，限制可一键剥掉；`2`（`OWNER_PASSWORD`）同样可开；只有 `0`（`NOT_DECRYPTED`）才是真需要开卷密码的加密，空密码打不开、也别指望本地处理。实测 z-library / 扫描书几乎都是 `1`。

## 轮询结果

```bash
curl -s "https://mineru.net/api/v4/extract/task/<task_id>" \
  -H "Authorization: Bearer $MINERU_TOKEN"
```

`state` 为 `done` 时，`full_zip_url` 即结果下载地址（含 full.md、JSON、images/）。

## 超过 200 页的文件：限制已经变化

- **过去**精准解析的实测规则是：URL 单任务（`/api/v4/extract/task`）可到 600 页，而 batch 上传单文件只有 200 页；旧脚本因此按 500 页主体 + overlap 拆卷。
- **现在**[官方 API 文档](https://mineru.net/apiManage/docs)和 [`MinerU-Ecosystem`](https://github.com/opendatalab/MinerU-Ecosystem/blob/5733c03b3d53cb01c0361bb6acecda3f554c8c12/README.zh-CN.md#L52-L64) 都把精准解析上限统一写为 **单文件 200MB / 200 页**，Flash 为 **10MB / 20 页**。URL 方式不再按“600 页特例”设计；旧的 500/600 页参数已经过时。

当前实操规则：

- 大于 200 页的 PDF 先做**物理分卷**，每卷总页数必须 ≤200。推荐主体 `198` 页 + `overlap=2`，即每卷最多正好 200 页。
- `page_ranges` 用来选择当前任务要解析的页，支持如 `"2,4-6"` 的范围；它不是绕过单文件页数/大小限制的可靠手段。对源文件本身已经超过 200 页的情况，默认仍按物理分卷处理，除非用小样重新验证服务端允许只读取指定范围。
- URL 提交和 batch 上传都能处理已经拆好的分卷。没有公网直链时，batch + 198 页主体 + 2 页 overlap 最省心，也不依赖 EasyTier/Caddy 暴露路径。
- 当前 `mineru_large_pdf.py` 已同步改为 200 页总上限和 `--pages-per-part 198` 默认值；旧命令里的 `500` 不再使用。

## 本地输入文件正在传输的坑

走本地路径（而非 URL）喂脚本时，常见场景是：客户端（Mac/手机）正在往服务器 `/tmp/clipboard/` 上传 PDF，本地同时 `rsync` 拉下来准备处理。如果上传还没完就开拆，会拷到一个**字节数不完整的 PDF**——大小看起来对，但末尾 `%%EOF`/xref 还没写，pypdf 拆分时炸：

```
pypdf.errors.PdfStreamError: Stream has ended unexpectedly
```

`mineru_large_pdf.py` 的 `wait_until_stable()` 会在读本地文件前轮询 `stat().st_size`，连续 2 次间隔 1.5s 大小一致才动手。所以现在就算上传还没完就喂给脚本，它会等到稳定再开始拆，不会读到半截。

URL 输入走 `httpx.stream` 流式下载，本身就保证完整，不需要这套逻辑。

## 超过 200MB 的文件（需物理拆分）

`page_ranges` 只能选择解析范围，不会缩小源文件本身；**超过 200MB 必须物理拆分 PDF**，而当前规则下超过 200 页也默认物理拆分。用同 skill 自带的 `scripts/mineru_large_pdf.py`：

```bash
export MINERU_TOKEN=...
uv run scripts/mineru_large_pdf.py \
    --input 'https://example.com/big.pdf' \
    --work-dir ./mineru_work/big \
    --pages-per-part 198 --overlap 2
```

**拆分策略**：每卷主体 `pages-per-part` 页 + 末尾 `overlap` 页过渡，用于给接缝两侧提供重复上下文。**推荐 `overlap=2` 只是常见场景的折中，不是完整性保证**：普通跨页段落、公式或短表通常只跨一个页边界；长表、附录和连续图版可能跨更多页，需增大 overlap 或由 agent 逐接缝回查原 PDF。`overlap=0` 容易让接缝对象被切坏，过大则增加重复解析和后处理量。JSON 只能先按页做确定性的基线合并，Markdown 和跨页结构仍必须由 agent 复核。

**自适应**：若某卷物理大小超 190MB，脚本自动减小 `pages-per-part` 后整体重拆。断点续跑：`--skip-split` 复用已拆分卷，`--resume-batch <id>` 复用已提交的 batch。

**串行提交分卷**：多卷通过 **URL 方式**提交 MinerU 时，**不要一次性批量提交**。MinerU 会并行拉所有 URL，把源服务器（家庭 VPS、EasyTier 隧道等低带宽链路）带宽打满，导致后几个任务 `failed to read file, please check if the file is corrupted`。正确做法：

- **逐个提交**，每个提交后等前一个进入 `running`（已下载完）再提下一个；或
- **间隔 60-120 秒**提一个，让源带宽有喘息；或
- 实在要批量提，就走 OSS 上传（慢但稳）。

若出现 `failed to read file`，先本地验证 PDF 完整（`pdfinfo` / pypdf 能读），再间隔重试即可恢复。

## 结果 zip 的输出结构与分卷合并

`full_zip_url` 解压后的主要产物（vlm + OCR 实测）：

| 文件 | 结构 | 页的标识 |
|---|---|---|
| `full.md` | 全文 Markdown（公式→LaTeX，图/表/公式图抽到 `images/`） | 无显式分页标记 |
| `images/` | 抽出的图片，**文件名为内容哈希** | — |
| `*_content_list.json` | **扁平**块列表，块为 `{type,text,text_level,bbox,page_idx}` | **块内显式 `page_idx`** |
| `*_content_list_v2.json` | **按页分组**：外层每元素 = 该页块列表 | **位置**（外层下标 = 页） |
| `*_model.json` | 按页分组：每元素 = 该页检测框列表 | **位置** |
| `layout.json` | dict `{pdf_info:[每页一项], _backend, _ocr_enable, …}`，每页项含 `page_idx` | **每页项显式 `page_idx`** |
| `*_origin.pdf` | MinerU 返回的输入副本；实测可能经 PDFium 重新封装，不保证与上传 PDF 字节级一致 | — |

### `*_origin.pdf` 的“原始”语义与任务元数据边界

`*_origin.pdf` 应理解为 **MinerU 随结果返回的输入文档副本/规范化副本**，不能直接当作上传文件的 byte-for-byte 归档原件。实测一份 163 页、960×540 pt 的 LibreOffice PDF：

- 上传文件：Creator=`Impress`、Producer=`LibreOffice 24.2`、Tagged=`yes`，保留标题和作者，7,795,965 bytes；
- 返回的 `*_origin.pdf`：Creator/Producer 均为 `PDFium`、Tagged=`no`，标题和作者被移除，7,431,988 bytes；
- 两者 SHA-256 不同，但字体集合、1,014 个嵌入图像对象和页数一致；`pdftotext` 普通/`-layout` 输出逐字节一致；以 36 dpi 渲染全部 163 页后像素完全一致。

结论：服务端可能经 PDFium 重写对象、压缩并剥离 metadata/tagging；**视觉和文本等价不代表文件字节相同**。需要保存原始证据链时，另留用户上传的 PDF；确认内容一致后，`*_origin.pdf` 可作为冗余副本剔除。

还要区分 **官方 zip 产物** 与 **本地编排元数据**：

- 官方 zip 的主要内容就是上表所列的 `full.md`、`images/`、`*_content_list*.json`、`*_model.json`、`layout.json`、`*_origin.pdf`；
- `batch_id.txt`、辅助脚本写出的 `results.json`，以及 agent 自行保存的 `_result.json`，都不是官方 zip 文件；前导下划线也没有 MinerU 官方语义；
- **辅助状态不得默认落进正式产物目录。** `mineru_large_pdf.py` 默认写到 `work-dir` 同级的隐藏目录 `.<work-dir-name>.mineru-state/`，也可用 `--state-dir` 显式指定；
- 只有项目明确要把运行证据随产物归档时，才由用户选择放入产物内的 `_meta/` 并注明生成方。否则任务成功并核验后，应保留在外部状态目录或移入回收站。

> `mineru_large_pdf.py` 的 `--work-dir`（旧名 `--out-dir`，仍作为兼容别名）是**任务工作目录**，不是最终产物目录。当前脚本只负责拆分、上传、下载各卷原始 zip，并写出带分卷标记的 `full.concat.md`；它**尚未合并 JSON / images，也没有删除 overlap，更没有完成 agent 接缝复核**。凡仍含 `partNN/`、`parts/` 或 `<!-- === part ... === -->` 的目录都只是中间态，不能交付。

### 分卷结果必须经过三阶段合并

推荐把流程状态显式记为 `raw_parts_only → structured_merged → agent_verified`；只有 `agent_verified` 才能进入最终 canonical 目录。

#### 阶段 A：保留各卷原始结果（脚本）

工作目录保留不可变的分卷底稿，方便后续交叉核验：

```text
<work-dir>/
├── parts/                 # 物理拆分 PDF
├── parts_manifest.json    # 全局页范围、overlap 与基线保留范围
├── part01/                # 第 1 卷官方 zip 原样解压
├── part02/                # 第 2 卷官方 zip 原样解压
└── full.concat.md         # 机械拼接 + part 标记；不是最终 full.md
```

拆分清单必须记录每卷的原 PDF 全局页范围 `start..end`、本卷页数和 overlap。原始 `partNN/` 在 agent 完成复核前不能修改；失败续跑、接缝对照和回查都以它们为准。

#### 阶段 B：结构化基线合并（脚本先做）

脚本应先把 JSON 和图片合并成 `merged-staging/`。这是**确定性的页级基线**，仍不是最终交付。各卷的 UUID 前缀不同，且旧版本可能直接叫 `content_list_v2.json`；merger 必须按“后缀 + JSON 结构”识别文件，并要求每卷每类恰好一份，不能靠固定 UUID 或完整文件名：

1. **页归属基线**：第一卷保留全部页；后续每卷先丢弃本地 `page_idx < overlap` 的重复页。对保留页，最不易出错的换算是：

   ```text
   global_page_idx = part.start - 1 + local_page_idx   # part.start 为 1-based；local/global page_idx 为 0-based
   ```

   例如 `part02` 覆盖原 PDF 第 199–398 页、`overlap=2`，则丢本地页 0–1，保留本地页 2–199，并映射为全局 `page_idx=200..397`（原 PDF 第 201–398 页）。

2. **`*_content_list.json`**：过滤被丢弃页的块，重写每个块的 `page_idx`，按全局页码和原块顺序拼接。
3. **`*_content_list_v2.json` / `*_model.json`**：二者靠外层列表位置表示页；后卷先切掉 `list[:overlap]`，再顺序拼接。若内部未来出现显式 `page_idx`，也必须同步改写，不能只假设格式永远不变。
4. **`layout.json`**：对 `pdf_info` 做同样的删页和全局 `page_idx` 改写；`_backend`、`_ocr_enable`、`_version_name` 等顶层元数据必须逐卷一致，不一致时停止合并而不是静默取第一卷。
5. **`images/`**：按文件名合并，但同名文件仍要校验字节/哈希一致；冲突即报错。不能只依据 `full.md` 清理图片，因为部分图片只被 JSON 引用。最终引用集合要扫描合并后的 Markdown **和全部 JSON**。
6. **`*_origin.pdf`**：各卷返回的是分卷副本，不进入最终目录；最终只保留用户的完整原始 PDF。
7. **机器校验**：`content_list_v2`、`model`、`layout.pdf_info` 的最终页数都必须等于原 PDF 的 N 页；全局页码必须恰好覆盖 `0..N-1`，不得重复或跳号；所有图片引用必须存在。

基线合并应生成明确标注为**合成文件**的名字（如 `merged_content_list.json`、`merged_content_list_v2.json`、`merged_model.json`），不要沿用某一卷的 UUID 冒充官方单卷原件。

> **当前实现缺口**：现有 `mineru_large_pdf.py` 尚未实现本阶段，只生成原始 `partNN/`、`parts_manifest.json` 和 `full.concat.md`。因此旧文档里“JSON 程序化去重”容易让人误以为脚本已经完成，实际并没有；在结构化 merger 实现并通过测试前，大文件流程只能视为 staging。

#### 阶段 C：接缝语义复核（agent）

页级固定丢弃只是基线，不足以保证跨页对象正确。比如表格跨原 PDF 第 200–201 页时，前卷可能缺第 201 页上下文，而后卷虽然完整看到了两页，其第 200 页又处在待丢弃 overlap 中。agent 必须逐接缝同时查看：前卷末尾、后卷开头、两卷 JSON/图片，以及原 PDF 接缝前后页面；必要时用后卷的块替换基线中前卷对应块，并同步修正结构化 JSON。

`full.concat.md` 没有可靠分页标记，不能简单按比例截断，也不能只取一个文本锚点——目录、页眉和重复节标题很容易误命中。定位时至少组合使用：

- `content_list.json` 中第一保留页的连续 2–3 个文本块；
- 该页附近的图片/表格引用；
- overlap 占本卷页数的比例，只作为预期位置；
- 原 PDF 接缝页的可视回查。

若第一保留页没有文本，改用图片、表格或下一页的多块序列定位。agent 的最终职责是：删掉重复前缀和所有 part 标记，确认接缝无重复、无缺段、跨页表格/公式完整，并在有替换时同步复核 JSON，而不是只修 Markdown 表面。

### 最终 canonical 产物

只有完成阶段 B 与 C 并通过核验后，才把干净结果写入项目目录：

```text
<project>/mineru/<文献名>/
├── <原始完整文件>.pdf
├── full.md
├── merged_content_list.json
├── merged_content_list_v2.json
├── merged_model.json
├── layout.json
└── images/
```

最终目录不应含 `parts/`、`partNN/`、分卷 `*_origin.pdf`、`full.concat.md`、part 标记、batch 状态或临时 merge manifest；这些只留在独立工作目录，确认无需回滚后再移入回收站。验收至少包括：N 页结构一致、页码连续、接缝抽查、首尾内容正确、Markdown/JSON 图片引用全命中，以及无未解释的孤儿图片。

## 本地上传方式（备用）

当没有可用直链时，用 batch 上传：

```bash
# 1. 获取上传地址
curl -s -X POST "https://mineru.net/api/v4/file-urls/batch" \
  -H "Authorization: Bearer $MINERU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"files": [{"name": "file.pdf"}], "model_version": "vlm", "language": "ch"}'

# 2. PUT 上传（注意清空 Content-Type）
curl -H "Content-Type:" -T file.pdf "<返回的 file_url>"

# 3. 上传完成后自动触发转换，轮询结果
curl -s "https://mineru.net/api/v4/extract-results/batch/<batch_id>" \
  -H "Authorization: Bearer $MINERU_TOKEN"
```

## HTTPS 与自签名证书

MinerU 服务器支持 HTTPS 直链，但**不接受自签名证书**（如 IP + tls internal 的 Caddy）。解决方案：在 Caddy 中为同一后端额外开一个 HTTP 端口供 MinerU 拉取。

## 历史性能参考（697 页、165MB 扫描版 PDF）

**过去**在 URL 单任务允许更大页数时，NAS → Caddy `:80` 直链实测拉取约 30s、转换约 120s，总计 **约 153s（2.5 分钟）**。**现在**需要按 200 页上限拆成更多任务，这个总耗时只能当历史量级，不能直接外推。

仍可把 PDF 分卷放到 VPS 的 `share/MinerU-upload/` 目录，通过 HTTP 直链逐卷提交。服务默认可能命中缓存，REST API 也提供 `no_cache`；缓存时延和额度效果应按当前账号与小样实测，不作为稳定保证。
