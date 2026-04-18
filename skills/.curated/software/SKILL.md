---
name: software
description: 软件服务、CLI 工具、本地/自托管服务配置与排障；尤其是 SSH 使用、systemd/service 配置、格式转换、WebDAV 上传、自托管 Markdown 分享、MinerU PDF 转 Markdown、软件 API 或命令行测试时使用。
---

# Software

## SSH

SSH 密钥 passphrase、ssh-agent、RemoteForward 代理转发等通用 SSH 用法见 [references/ssh.md](references/ssh.md)。

## Service / systemd

多用户共享服务、systemd 模板单元与按 UID 分配端口见 [references/service.md](references/service.md)。

## 格式转换

pandoc 文档转换、Markdown→PDF、PDF→图片、feishu2md 飞书/Lark→Markdown 等见 [references/format-conversion.md](references/format-conversion.md)。

## 自托管 Markdown 文件分享（doc-share）

把本地 Markdown / 文件推到自托管 WebDAV、拿 capability URL 分享链接、以及给 Markdeep viewer 写作的惯例（`[#key]` 引用 vs `[^name]` 脚注可选、GFM 兼容场景反而要避开 `[#key]`、研报长文模板）见 [references/doc-share.md](references/doc-share.md)。上传凭据约定从 `~/.env` 读 `WEBDAV_URL / WEBDAV_USER / WEBDAV_PASS`。

服务端（Caddy site block、WebDAV handler、viewer 实现、目录权限）由 `vps-maintenance` skill 覆盖。如果源文件需要先做格式转换，看 [references/format-conversion.md](references/format-conversion.md)。

## MinerU PDF→Markdown 云端转换

MinerU（mineru.net）提供 VLM 模型将 PDF 转为 Markdown/JSON，支持公式和表格识别；详细流程见 [references/mineru.md](references/mineru.md)。
