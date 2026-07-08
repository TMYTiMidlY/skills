# MinerU PDF→Markdown 转换

MinerU（mineru.net）提供 VLM 模型将 PDF 转为 Markdown/JSON，支持公式和表格识别。

## 默认策略与本地部署边界

默认优先使用 MinerU 云端 API、Open API SDK 或用户已经明确配置好的现有服务。**未经用户明确允许，不要在本机安装、部署或临时拉取 MinerU 运行环境**，包括但不限于：

- `uvx --from "mineru[all]" ...`
- `pip install "mineru[all]"`
- 启动本地 MinerU / VLM / pipeline 服务

原因：MinerU 本地部署依赖很重，可能拉取数 GB 的 Python、torch、CUDA、vLLM 等组件，耗时、占空间，也可能污染用户环境。若确实需要本地部署，先说明预计影响（下载量、磁盘、是否需要 GPU/CPU、输出目录、如何清理），并等待用户确认。

如果只需要快速预览，优先考虑 flash 模式；如果文件超出 flash 限制或需要完整图片/表格/公式资产，再走 token 认证的精度解析。

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

## 认证

Bearer token 认证。token 存放在环境变量 `MINERU_TOKEN` 中，使用前先确认已设置。

## 提交任务（URL 方式，推荐）

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

**额度**：

- 每日解析总上限 **10000 页**，其中前 **2000 页**高优先级，超出部分降级。
- 按**实际处理页数**扣，`is_ocr` 开不开不影响扣页数。
- 失败任务（`state=failed`）**不扣**额度，可放心重试。
- 相同 URL 重复提交走**缓存**直接返回已有结果，也不重复扣。

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

## 轮询结果

```bash
curl -s "https://mineru.net/api/v4/extract/task/<task_id>" \
  -H "Authorization: Bearer $MINERU_TOKEN"
```

`state` 为 `done` 时，`full_zip_url` 即结果下载地址（含 full.md、JSON、images/）。

## 超过 600 页的文件

API 限制单次最多 600 页。用 `page_ranges` 参数拆分提交同一个 URL：

```bash
# 第一部分
-d '{"url": "...", "page_ranges": "1-500", ...}'
# 第二部分
-d '{"url": "...", "page_ranges": "501-697", ...}'
```

转换完成后将两部分的 `full.md` 拼接即可。注意：`page_ranges` 仅在 URL 提交方式（`/api/v4/extract/task`）下生效，batch 上传方式不支持。

## batch 上传单文件 200 页限制

**batch 上传方式（`/api/v4/file-urls/batch`）的隐藏硬上限是单文件 200 页**，超过会返回 `state=failed` + `err_msg='number of pages exceeds limit (200 pages), please split the file and try again'`。MinerU 文档没明示这条，但实测确认。

实操要点：

- 走 batch 时，`mineru_large_pdf.py` 的 `--pages-per-part` 必须 ≤ `200 - overlap`（overlap 默认 2 → 用 198；`--pages-per-part` 默认 500 是按 URL 方式 600 页设的，走 batch 会全卷 fail）。
- 200 页限制只针对 **batch 上传**；URL 提交（`/api/v4/extract/task`）仍是 600 页/次，可继续用 `page_ranges` 拆 500/卷。
- 没有公网直链或不想折腾反代时，batch + ~198 页/卷（`--overlap 2`）是最省心的兜底方案，不依赖任何 EasyTier/Caddy 路径暴露。

## 本地输入文件正在传输的坑

走本地路径（而非 URL）喂脚本时，常见场景是：客户端（Mac/手机）正在往服务器 `/tmp/clipboard/` 上传 PDF，本地同时 `rsync` 拉下来准备处理。如果上传还没完就开拆，会拷到一个**字节数不完整的 PDF**——大小看起来对，但末尾 `%%EOF`/xref 还没写，pypdf 拆分时炸：

```
pypdf.errors.PdfStreamError: Stream has ended unexpectedly
```

`mineru_large_pdf.py` 的 `wait_until_stable()` 会在读本地文件前轮询 `stat().st_size`，连续 2 次间隔 1.5s 大小一致才动手。所以现在就算上传还没完就喂给脚本，它会等到稳定再开始拆，不会读到半截。

URL 输入走 `httpx.stream` 流式下载，本身就保证完整，不需要这套逻辑。

## 超过 200MB 的文件（需物理拆分）

`page_ranges` 只解决页数上限，**大小限制 200MB 必须物理拆分 PDF**。用同 skill 自带的 `scripts/mineru_large_pdf.py`：

```bash
export MINERU_TOKEN=...
uv run scripts/mineru_large_pdf.py \
    --input 'https://example.com/big.pdf' \
    --out-dir ./mineru_output/big \
    --pages-per-part 500 --overlap 2
```

**拆分策略**：每卷主体 `pages-per-part` 页 + 末尾 `overlap` 页过渡，用于覆盖跨页表格/公式。**推荐 `overlap=2`**：一个表/公式最多跨一个页边界，后卷开头多带 2 页就能让接缝页在两卷里都被完整识别；`mineru_large_pdf.py` 原默认 5 偏大（现已改默认 2），大 overlap 只是徒增后面要去重的重复量（而 `overlap=0` 会让跨页内容在接缝被切坏）。相邻卷 overlap 区内容会重复，合并时按下节规则**去重**（JSON 程序化去重、md 由 agent 复核去重）。

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
| `*_origin.pdf` | 原始输入副本（归档时通常可剔除） | — |

一个 PDF 因 >200MB / >600 页**物理拆成多卷分别转换**后，把各卷输出拼回一份，按**结构**（而非文件名）处理。拆分务必落在**整页边界**（别在页中切），每页完整属于某一卷。

**先处理 overlap**：用了 `overlap≥1`（推荐 2）时相邻卷共享 `overlap` 页、内容重复，合并前必须**丢弃后一卷开头的 `overlap` 页**（它们与前卷末尾是同一批页）。记各卷"保留页数" K₀,K₁,…（首卷 K₀=全部页，其余 Kᵢ = 该卷页数 − overlap），累计基址 baseᵢ = K₀+…+Kᵢ₋₁。`overlap=0` 时无需丢弃，baseᵢ 即之前各卷页数之和。

- **`images/`**：取并集；文件名是内容哈希，跨卷天然唯一、不冲突。
- **`content_list.json`（扁平块，带 `page_idx`）**：后卷丢弃 `page_idx < overlap` 的块，其余 `page_idx ← page_idx − overlap + baseᵢ`，顺序拼接。
- **`layout.json` 的 `pdf_info`（每页一项，带 `page_idx`）**：同上——丢前 `overlap` 项、`page_idx` 偏移、再拼接；顶层元数据（`_backend`/`_ocr_enable` 等）取任一卷。
- **`content_list_v2.json` / `model.json`（按页分组、靠位置，第 i 项 = 第 i 页）**：后卷切掉开头 `overlap` 项（`list[overlap:]`），首尾直接相接，内部不动。
- **`full.md`（无显式分页标记）**：`mineru_large_pdf.py` 只做「顺序拼接 + 卷间插 `<!-- === part NN (pages S-E) === -->` 标记」，**不合并 JSON**；随后由 **agent 复核去重**——移除全部标记，并删掉后卷开头 `overlap` 页的重复段。

**full.md 去重的定位技巧**（md 无分页标记，只能靠内容锚点切）：后卷要删开头 `overlap` 页 → 取该卷 `content_list.json` 里**第一个 `page_idx==overlap` 的文本块**的文本当锚点，在该卷 full.md 里定位它，从此处往后保留、之前丢弃。**坑**：锚点文本（如节标题）常在目录 + 正文各出现一次，单取「首个匹配」会误切；稳妥做法是**按 overlap 占比估预期字节位** `expected ≈ overlap ÷ 该卷页数 × len(md)`，在所有匹配里取**离 expected 最近**的那个。**验证**：去重后同一段 overlap 文本应从「出现 2 次」变「1 次」、图片引用仍全部命中、首页(标题)/尾页(索引)内容正确、`full.md` 与各 JSON 同为 N 页。（实测 Dalzell 416 页：拆 3 卷、两处接缝各删 5 页 overlap，md 与 JSON 均对齐到 416 页。）

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

## 性能参考（实测，697 页 165MB 扫描版 PDF）

NAS → Caddy :80 直链提供 URL：拉取 ~30s + 转换 ~120s = **~153s（约 2.5 分钟）**。

推荐将 PDF 放到 VPS 的 `share/MinerU-upload/` 目录，通过 HTTP 直链提交。相同文件重复提交会命中缓存直接返回结果。
