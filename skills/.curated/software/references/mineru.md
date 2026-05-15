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

- 走 batch 时，`mineru_large_pdf.py` 的 `--pages-per-part` 必须 ≤ `200 - overlap`（默认 overlap=5 → 用 195）。脚本默认值 500 是按 URL 方式 600 页设的，走 batch 会全卷 fail。
- 200 页限制只针对 **batch 上传**；URL 提交（`/api/v4/extract/task`）仍是 600 页/次，可继续用 `page_ranges` 拆 500/卷。
- 没有公网直链或不想折腾反代时，batch + 195 页/卷是最省心的兜底方案，不依赖任何 EasyTier/Caddy 路径暴露。

## 超过 200MB 的文件（需物理拆分）

`page_ranges` 只解决页数上限，**大小限制 200MB 必须物理拆分 PDF**。用同 skill 自带的 `scripts/mineru_large_pdf.py`：

```bash
export MINERU_TOKEN=...
uv run scripts/mineru_large_pdf.py \
    --input 'https://example.com/big.pdf' \
    --out-dir ./mineru_output/big \
    --pages-per-part 500 --overlap 5
```

**拆分策略**：每卷主体 `pages-per-part` 页 + 末尾 `overlap` 页过渡（默认 5 页），用于覆盖跨页表格/公式。相邻卷 overlap 区内容会重复，合并 md 时用 `<!-- === part NN (pages S-E) === -->` 标记分卷，人工审阅去重。

**自适应**：若某卷物理大小超 190MB，脚本自动减小 `pages-per-part` 后整体重拆。断点续跑：`--skip-split` 复用已拆分卷，`--resume-batch <id>` 复用已提交的 batch。

**串行提交分卷**：多卷通过 **URL 方式**提交 MinerU 时，**不要一次性批量提交**。MinerU 会并行拉所有 URL，把源服务器（家庭 VPS、EasyTier 隧道等低带宽链路）带宽打满，导致后几个任务 `failed to read file, please check if the file is corrupted`。正确做法：

- **逐个提交**，每个提交后等前一个进入 `running`（已下载完）再提下一个；或
- **间隔 60-120 秒**提一个，让源带宽有喘息；或
- 实在要批量提，就走 OSS 上传（慢但稳）。

若出现 `failed to read file`，先本地验证 PDF 完整（`pdfinfo` / pypdf 能读），再间隔重试即可恢复。

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
