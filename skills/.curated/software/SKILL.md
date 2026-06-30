---
name: software
description: 本地软件、CLI 工具与自托管服务的客户端配置与排障笔记集，遇到下列方面的问题可先来这里查。涵盖 SSH 与 systemd 服务、Zellij 终端复用、WSL 与 Windows 宿主互操作（PowerShell/UAC/cmd）、挂载与 SMB/CIFS 文件共享、Git 镜像与自建 Forgejo、RustFS / SeaweedFS 与 MinIO mc 对象存储客户端、文档格式转换（pandoc/feishu2md/MinerU）与 Markdown→PDF 导出、自托管文档分享（S3 直链）、本地中文 ASR、OpenList 网盘聚合、Hermes agent、Windows/Office 激活与 macOS 杂项等。Agent harness、Copilot CLI/SDK/MCP 与会话导出等内部架构问题转用 `harness` skill。
---

# Software

## 写 / 改 reference 文件的规则

reference 文件的目标：让**任意** agent 或用户照着就能在**自己的**设备上搭起来。改某类问题的 reference 时遵循：

1. **概念优先、说人话**：先讲清“是什么、为什么这么做、解决什么问题”，再给细节；代码黑话/术语只在影响理解时才解释，不重要的略过。
2. **可复现、不绑定本机**：隐去具体主机名 / IP / 用户名 / 私有路径，用占位符（如 `<入口VPS>`、`<user>`）。路径、目录名这类“换台机器就不同”的东西讲清作用即可，别当硬性要求。
3. **命令 / 示例文件优先**：能贴一段可直接套用的 compose / 配置 / 脚本 / 命令就贴出来（敏感值留占位符），胜过大段散文。
4. **每条说法要有据**：自己实测的直接陈述（不用写“实测”二字）；来自官方/外部的**挂可点开的官方文档链接**；拿不准的标注不确定，别凭记忆编。多给客观证据（版本号、命令输出、API 返回等）。
5. **踩坑 / 排障紧贴主题**：记录真实踩过的坑和诊断/恢复办法，但只留与本主题强相关、对复现有用的；琐碎、一次性、跑题的不写。
6. **少写“给 agent 自动执行的操作流程”**：用什么 CLI 工具、要不要 sudo、怎么备份回滚、删文件用什么——这些是操作者临场决定的事，不进 reference，reference 只描述**目标产物长什么样**。
   - **例外：面向人的操作可以写详细。** GUI 点选路径、必须物理接触设备 / 进某台机器桌面才能做的步骤，是**只能由人来做、agent 读了也不会自动执行**的部署说明——这类写具体反而有用（人照着点）。判断标准：这段是给 agent 读了去跑命令的，还是给人读了自己动手的？后者放开写。
7. **不过度限制、少堆告诫**：陈述事实与权衡（必要时给出被否决的备选及代价），让读者自己判断，少用“绝不能 / 务必”这类防御句；复杂链路优先用 GitHub 能渲染的图（mermaid / 表格 / blockquote）。

## SSH

SSH 密钥 passphrase、ssh-agent、非交互环境（CI / `bash -c`）私钥带 passphrase 又无解锁 agent 导致 `Server accepts key` 却 `Permission denied` 的诊断与复用常驻 agent 解法、RemoteForward 代理转发、主机密钥校验（known_hosts、`CheckHostIP` 默认及 OpenSSH 与 asyncssh 等第三方库对 IP 的处理差异——同一主机换 IP 后 OpenSSH 沉默而第三方库报 `Host key is not trusted` 的根因与修复）、ControlMaster 连接复用、裸 ssh/scp 跑命令与交互式 sudo（`ssh -t`）及远端文件编辑等通用 SSH 用法见 [references/ssh.md](references/ssh.md)。

## Git 镜像仓库

多设备协作且部分设备无法访问 GitHub 时，用一台公网 VPS 做双向 SSH git 镜像。架构、搭建步骤、hooks、Actions workflow、防回环、防 split-brain 的完整方案见 [references/git-mirror.md](references/git-mirror.md)。

## 自建 Forgejo（公网 22 SSH relay + CI runner）

无独立公网 IP 的内网 WSL2 机上自建 Forgejo，借唯一公网落点 VPS 做入口。核心做法是 SSH passthrough（公网 sshd 按登录名 `git` vs 运维用户分流，不破坏运维 shell）+ 跨机 relay（key 查询/git 命令经一条 SSH 转发到内网 Forgejo 容器的 `forgejo keys`/`serv`）。覆盖整体三段链路架构、为什么网页端加 SSH key 入口机即认（`AuthorizedKeysCommand` 当场查 Forgejo 数据库、不拷文件）、内网机用 authorized_keys 内联 forced command 转发 keys/serv（不另放脚本）、ControlMaster 复用绕过坑、`serv` stdin 透传、入口机发行版差异（SSH service 名/SELinux/sshd_config.d 因发行版而异）、sshd 幂等 append + 安全兜底、Forgejo Actions runner（DinD 隔离、token 注册三步、job 容器回连 `http://forgejo:3000` 的网络设计）、web 经边缘 Caddy 反代（默认中文 header；WSL/Docker 网络细节转 `network` skill）、session COOKIE_NAME 改名治登录 500、数据卷 `/data` 挂载坑（非 rootless 镜像）见 [references/git-server.md](references/git-server.md)。

## Zellij

Zellij Web client、HTTPS 证书要求、login token/session token、反代注入 Cookie、`default_shell`、Web/xterm 主题分层、给特定软件写 OSC 10/11 颜色 wrapper、Codex 输入框颜色、鼠标选区颜色与 WSL systemd service 写法见 [references/zellij.md](references/zellij.md)。

## Service / systemd

多用户共享服务、systemd 模板单元与按 UID 分配端口见 [references/service.md](references/service.md)。

## Agent harness / Copilot CLI

GitHub Copilot CLI / SDK / MCP / session export 与跨 Claude Code、Codex 等 coding agent 的 runtime / harness 架构笔记已拆到 `harness` skill。`software` 只保留相邻的软件运维主题，例如 Zellij、SSH、Git、systemd、Windows/WSL 与对象存储客户端。

## ChatGPT 网页端自动化

ChatGPT 网页端 Pro / Extended 自动化、`steipete/oracle` browser engine、Windows Chrome DevTools、WSL Mirror / NAT 差异、以及必须用 network payload 验证真实模型与 thinking effort 的经验见 [references/oracle-pro.md](references/oracle-pro.md)。

## 挂载与文件共享

WSL 挂载 Windows 盘、UNC/SMB 共享、`drvfs/9p` 小文件性能、CIFS 凭据与 `mount.cifs` 排障见 [references/mount.md](references/mount.md)。

## Linux 回收站（trash-cli / gio trash）

`trash-cli` 与 GLib `gio trash` 是两套实现但遵循同一 FreeDesktop Trash 规范（同一 `~/.local/share/Trash/`、`files/`+`info/*.trashinfo` 配对、`.Trash-$uid` 卷内逻辑），互通可混用。覆盖回收站两半结构、坏 `.trashinfo` 的真实影响与正确处置（不会让 `trash-rm`/`trash-empty` 整库罢工，但坏项删不掉、需手动补回 `Path=`）、`trash-rm` 匹配规则（`/` 开头按整路径否则按 basename，附 `filter.py` 源码与正确写法）、gio 无选择性永久删单项（附 `gio-tool-trash.c` 源码）、删挂载盘文件两者同规范的卷内落点见 [references/trash.md](references/trash.md)。

## RustFS + MinIO mc 客户端

RustFS（Rust 实现的 S3 兼容对象存储，github.com/rustfs/rustfs）+ MinIO `mc` CLI 的对接经验：**mc（CLI 二进制）与 boto3（Python SDK）互为补集，建议混用 crosscheck**；versioning 是桶级开关、软删（`mc rm` 不带 `--versions` = 写 delete marker，可 `mc undo` 恢复）vs 硬删（`mc rm --versions --force` = 物理删，不可逆）的语义与恢复/GC 链路；**列举数可疑时用 boto3 + mc 交叉验证、`ListObjectVersions`（`mc ls --versions` / boto3 `list_object_versions()`）当兜底 oracle**（这套习惯曾帮忙定位一个上游已修复的服务端列举问题）；跨桶 server-side copy 在 HDD 后端高并发会撞 `Io error: timeout` 500（`--max-workers` 限并发 / 调 RustFS timeout env）；`mc rb --force` 在大 versioning 桶会 hang、改用 `x-minio-force-delete` header server 端清桶（脚本 `scripts/rustfs_force_delete_bucket.py`）；HDD 后端 wall-clock ∝ 对象数（打 zip 聚合 ~10× 加速）。见 [references/rustfs.md](references/rustfs.md)；大批量 op 可靠性模式（并发 list/delete/copy + 断点续传骨架）见 [references/rustfs-bulk-ops.md](references/rustfs-bulk-ops.md)。

**SeaweedFS 对照**（另一类 S3 兼容存储）：SeaweedFS 是 Haystack blob 存储 + Filer、不是 MinIO 克隆——与 RustFS 的关键区别（架构 / 纠删码 / 版本存储 / lifecycle / 服务端 copy / 删桶 / S3 保真度）及其多前端客户端（S3 网关、原生 REST、Filer HTTP、FUSE、WebDAV，运维用 `weed shell`；`mc` 仅通用 S3 模式可用、`mc admin` 不行）见 [references/seaweedfs.md](references/seaweedfs.md)。

## Windows / WSL 宿主侧速记

跑在 Windows 宿主上的小经验：PowerShell 5.1 vs 7（pwsh）的运行时与默认 encoding 差异、为什么从 WSL/agent shell 调 PowerShell 优先用 pwsh 7 避开中文 GBK decode 炸 channel、从 WSL 弹 UAC 拿管理员权限（`Start-Process -Verb RunAs` + 文件标记跨上下文传结果）、cmd.exe 不接 UNC 当 CWD、Windows 回收站与 `trash-put` 的关系见 [references/windows.md](references/windows.md)。

## Windows / Office 激活

镜像下载（山己几子木）与激活工具（MAS、CMWTAT、Microsoft Office For MacOS）见 [references/activation.md](references/activation.md)。

## macOS 小问题集锦

推荐应用（VMware Fusion、Mounty + macFUSE NTFS 读写）、应用无法打开的权限修复、外置存储隐藏文件（`.DS_Store` / `.Spotlight-V100` / `.Trashes`）阻止与清理见 [references/macos.md](references/macos.md)。

## 格式转换

pandoc 文档转换、Markdown→PDF、PDF→图片、feishu2md 飞书/Lark→Markdown 等见 [references/format-conversion.md](references/format-conversion.md)。

## 本地中文 ASR

FunASR、Fun-ASR-Nano、Paraformer + VAD + Punc + CAM++、SenseVoiceSmall、Whisper turbo 在 CPU 机器上处理中文长录音的实测经验、切块策略、speaker/timestamp 取舍见 [references/asr.md](references/asr.md)。

## 私有 docs-share 站点（Git 仓库 → S3 直链分享）

把要公网呈现的 md/html 放进一个私有 Git 仓库，每次 `git push` 或网页端上传/编辑即触发 CI（`rclone sync --checksum`）**增量同步**到一个 S3 兼容桶（桶结构 = 仓库树）；对外走 S3 **presigned 直链**（URL 自带签名 + 有效期）分享；`public/` 前缀通过 bucket policy 开放匿名读、无需签名——知道 URL 即可访问。`.md` 原样存（下载=raw），由 Caddy Accept rewrite + markdeep viewer 客户端渲染。完整内容见 [references/docs-share.md](references/docs-share.md)：密钥体系（root key 派生受限 CI key、凭据存储位置）、public 路径 vs 私有路径的 bucket policy 机制、presigned URL 生成（直贴/viewer 包装/脚本批量）、更新与撤销、markdeep 写作惯例（`[#key]` 引用 vs `[^name]` 脚注、GFM 不兼容点、研报模板）。服务端部署（Caddy 配置 / viewer 壳子 / CI key 创建 / bucket policy 设置命令）由 `vps-maintenance` skill 的 caddy.md 覆盖。S3 兼容存储底层行为见 [references/rustfs.md](references/rustfs.md)。

## Markdown → PDF 导出

CSS Paged Media 路线的工具生态定位（Prince / Vivliostyle / Paged.js / WeasyPrint / Typst 选型）、Prince XML 无 sudo pixi 安装与 CJK 字体大坑（Variable Font 静默失败、fontconfig 隔离）、Paged.js Chromium 依赖的 pixi 补齐、以及引用标签预处理 → pandoc → Prince 的一键 PDF 流水线见 [references/pdf-export.md](references/pdf-export.md)。

## OpenList 网盘聚合面板

OpenList（AList 的活跃 fork）的 **REST API 编程接入**（两种 token——登录 JWT vs 固定 admin token——的对比与为什么 agent 该用后者、CLI `openlist admin token` 取值、OpenList-Desktop 桌面版的 session/盘符隔离坑、token 不落进对话/日志的 side-channel 取法、核心端点速查、跨存储 mv/cp 是异步任务且进度可经 `/api/admin/task/*` 轮询、HTTP 恒 200 真码在 `body.code`）、任何 backend 都成立的共性行为坑（C 系列：缩略图懒加载、DirectorySize 全 stat、搜索索引手动）见 [references/openlist.md](references/openlist.md)。

把 **iCloud Drive 接入 OpenList**（rclone 直连 vs 借道常开 Mac 用 SMB 中转的选型对比、R 系列 rclone 直连专属坑、M 系列 Mac SMB 中转专属坑、macOS SMB 部署步骤含 GUI 路径、嵌套挂载还原完整 iCloud 视图、`dd over ssh` 远程链路测速 + 体验对照、EasyTier 双向不对称排查）见 [references/openlist-icloud.md](references/openlist-icloud.md)——这篇大量是 macOS GUI / 桌面操作，给人照做的部署说明。

## MinerU PDF→Markdown 转换

MinerU（mineru.net）提供 VLM 模型将 PDF 转为 Markdown/JSON，支持公式和表格识别。默认使用云端 API / Open API；未经用户明确允许，不要在本机安装或部署 MinerU。详细流程见 [references/mineru.md](references/mineru.md)。

## Hermes

[NousResearch/hermes-agent](https://github.com/nousresearch/hermes-agent)：Python CLI agent 框架。systemd 常驻服务（gateway / dashboard）配置、`HERMES_HOME` 与身份管理、terminal backend（local / ssh / docker / modal / daytona / singularity）切换、provider 兼容性踩坑、skill 体系（builtin / hub / local 三种来源、install/uninstall、`external_dirs` 挂载外部目录、按项目激活 skill 的缺失与近似解、跨 backend 的 symlink 差异、`--skills` 预加载）见 [references/hermes.md](references/hermes.md)。
