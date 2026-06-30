# 归档：旧 doc-share 方案（WebDAV + Markdeep viewer + copyparty）

这是已经退役的「自托管 Markdown 文件分享」方案的完整历史快照，仅作存档。
**现行方案已换成 S3 presigned 直链**：`software` skill 的 `references/docs-share.md`（客户端）
+ `vps-maintenance` skill 的 `references/caddy.md`「文档私链分享站（docs-share）」（服务端）。

## 出处
- 退役/拆分点：commit `5877d77`（`docs(docs-share): 拆分 software 客户端 / vps-maintenance 服务端，新增 Idiom B (Accept rewrite)`）。
- 下面两个文件均取自该 commit 的父提交 `5877d77^`（最后一个还在用 WebDAV 的状态），verbatim。

## 内容
- `doc-share.md` —— 客户端参考，取自 `5877d77^:skills/.curated/software/references/doc-share.md`。
  覆盖：WebDAV 上传/验证、capability URL 分享链接形态、Markdeep 写作惯例（引用 vs 脚注、与 GFM 的不兼容点、研报模板）、
  以及 **copyparty**（带 UI + `POST /?share` API 的全功能替代）的完整部署、官方 argon2 密码哈希流程、权限边界自检、踩坑。
- `caddy-webdav-server.md` —— 服务端配置段，取自 `5877d77^` 的 caddy.md「## 无额外认证的文档私链（WebDAV + Markdeep viewer）」。
  覆盖：`caddy-webdav` 扩展安装、viewer/token/密码/目录准备、最小可用 Caddyfile 模板。
  其中引用的 viewer 壳子 `md-viewer.html` 至今仍被现行 S3 方案复用，见 `vps-maintenance/assets/md-viewer.html`。
