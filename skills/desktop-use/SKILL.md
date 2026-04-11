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
    "is_ocr": true
  }'
```

返回 `task_id`，用于轮询结果。

**关于直链：** URL 必须是可直接下载 PDF 文件的链接（Content-Type 为 `application/pdf`），不能是网盘的预览页面。当前使用 Caddy 文件服务，`/share/` 路径直接返回文件。

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
