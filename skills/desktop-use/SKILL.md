---
name: desktop-use
description: Windows / macOS 桌面系统操作。用户遇到桌面端的软件使用、系统配置、网络连接、远程桌面、文件格式转换等问题时触发。
---

# 桌面系统操作

## 快速命令参考

### 关闭 Clash

```powershell
Get-Process | Where-Object { $_.Name -like "Clash*" } | Stop-Process -Force
```

## 网络与远程连接

RDP、向日葵、WSL Mirror 模式网络（含 Clash Party 代理对 WSL 路由的影响）、会话管理（tsdiscon/logoff）、MTU 排障 → [references/network.md](references/network.md)

## Windows 系统与 Office

镜像下载与激活指南 → [references/activation.md](references/activation.md)

## Windows 服务器配置

EasyTier 组网（安装、TOML 配置模板、Peer 配置、与 VPS 差异）、Windows 防火墙 → [references/server.md](references/server.md)

## Hermes

Gateway / Dashboard systemd 服务、profile 与 `HERMES_HOME`、开机自启、反代暴露、npm/bun 构建限制 → [references/hermes.md](references/hermes.md)

## macOS

推荐应用（VMware Fusion、Mounty + macFUSE NTFS 读写）、应用无法打开的权限修复、外置存储隐藏文件（DS_Store/Spotlight/Trashes）阻止与清理 → [references/macos.md](references/macos.md)

## 格式转换

pandoc 文档转换（LaTeX→Word、Markdown→PDF）、PDF→图片 → [references/format-conversion.md](references/format-conversion.md)

## MineRU PDF→Markdown 云端转换

MineRU（mineru.net）提供 VLM 模型将 PDF 转为 Markdown/JSON，支持公式和表格识别。

### 认证

Bearer token 认证。token 存放在环境变量 `MINERU_TOKEN` 中，使用前先确认已设置。

### 提交任务（URL 方式，推荐）

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

### `is_ocr` 选什么

**优先 `is_ocr=false`**，前提是 PDF **带嵌入文本层**——即：

- 原生文本 PDF（Word/LaTeX 导出、可复制文字）
- 扫描版但做过 OCR 的双层 PDF（Anna's Archive / duxiu / Acrobat OCR 后保存的 PDF 都属此类）

判断：在 PDF 上 Ctrl+A 能选中连续可复制文字 → 带文本层，`is_ocr=false` 即可。若无文本层（纯扫描未 OCR），必须 `is_ocr=true`。

**两阶段模型**：MineRU 先做 layout（图像识别区域类型），再填充文本。两模式 layout 一致，差异只在文本填充。

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

### 轮询结果

```bash
curl -s "https://mineru.net/api/v4/extract/task/<task_id>" \
  -H "Authorization: Bearer $MINERU_TOKEN"
```

`state` 为 `done` 时，`full_zip_url` 即结果下载地址（含 full.md、JSON、images/）。

### 超过 600 页的文件

API 限制单次最多 600 页。用 `page_ranges` 参数拆分提交同一个 URL：

```bash
# 第一部分
-d '{"url": "...", "page_ranges": "1-500", ...}'
# 第二部分
-d '{"url": "...", "page_ranges": "501-697", ...}'
```

转换完成后将两部分的 `full.md` 拼接即可。注意：`page_ranges` 仅在 URL 提交方式（`/api/v4/extract/task`）下生效，batch 上传方式不支持。

### 超过 200MB 的文件（需物理拆分）

`page_ranges` 只解决页数上限，**大小限制 200MB 必须物理拆分 PDF**。用 [scripts/mineru_large_pdf.py](scripts/mineru_large_pdf.py)：

```bash
export MINERU_TOKEN=...
uv run ~/.claude/skills/desktop-use/scripts/mineru_large_pdf.py \
    --input 'https://example.com/big.pdf' \
    --out-dir ./mineru_output/big \
    --pages-per-part 500 --overlap 5
```

**拆分策略**：每卷主体 `pages-per-part` 页 + 末尾 `overlap` 页过渡（默认 5 页），用于覆盖跨页表格/公式。相邻卷 overlap 区内容会重复，合并 md 时用 `<!-- === part NN (pages S-E) === -->` 标记分卷，人工审阅去重。

**自适应**：若某卷物理大小超 190MB，脚本自动减小 `pages-per-part` 后整体重拆。断点续跑：`--skip-split` 复用已拆分卷，`--resume-batch <id>` 复用已提交的 batch。

**⚠ 串行提交分卷**：多卷通过 **URL 方式**提交 MineRU 时，**不要一次性批量提交**。MineRU 会并行拉所有 URL，把源服务器（家庭 VPS、EasyTier 隧道等低带宽链路）带宽打满 → 导致后几个任务 `failed to read file, please check if the file is corrupted`。正确做法：
- **逐个提交**，每个提交后等前一个进入 `running`（已下载完）再提下一个；或
- **间隔 60–120 秒**提一个，让源带宽有喘息；或
- 实在要批量提，就走 OSS 上传（慢但稳）。

若出现 `failed to read file`，先本地验证 PDF 完整（`pdfinfo` / pypdf 能读），再间隔重试即可恢复。

### 本地上传方式（备用）

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

### HTTPS 与自签名证书

MineRU 服务器支持 HTTPS 直链，但**不接受自签名证书**（如 IP + tls internal 的 Caddy）。解决方案：在 Caddy 中为同一后端额外开一个 HTTP 端口供 MineRU 拉取。

### 性能对比（实测，697 页 165MB 扫描版 PDF）

| 方案 | 拉取 | 转换 | 总计 |
|---|---|---|---|
| 本地上传 OSS（WSL→阿里云 OSS） | 420s | ~165s | **~585s（约 10 分钟）** |
| Caddy 文件服务 HTTP 直链 | ~30s | ~120s | **153s（约 2.5 分钟）** |

推荐将 PDF 放到 VPS 的 `share/MinerU-upload/` 目录，通过 HTTP 直链提交。相同文件重复提交会命中缓存直接返回结果。
