---
name: git
description: 用户要提交 / 回退 / 改写 git 历史、开隔离工作区做实验、克隆不下来仓库或 submodule、分不清 gh 登录与提交身份、用 jj 干活、配自动发版与发布 CI，或自建 Forgejo / Gitea 与 git-pages 静态站时使用。核心是先认清动的是哪棵树（HEAD / index / worktree）、发版先认清版本真相源是配置文件还是 Git 历史、以及临时绕行不落进仓库长期配置。
---

# Git

本 skill 索引 Git 与 jj 的日常操作、隔离工作区、受限网络下的仓库获取、发版 / 发布 CI，以及自建托管。

## 精准操作（有并发/无关改动时只提交、暂存、丢弃、amend 一处）

工作区同时躺着"你想动的改动"和"不该由你带走的改动"（并发脏文件、别人已 `git add` 的 rename、untracked）时，如何在**命令行非交互**只对一处做 commit / stage / discard / stash，以及提交被别人叠了新提交后怎么改它。按 surgery.md 的章节：**三棵树与 commit 的快照范围**（谁是底座 floor 决定动得了什么）、**速查**（场景→命令→章节）、**整文件级**（`git commit -- <path>` pathspec 隔离、新文件先 `add -N`、`restore` / `stash push --`、"加 -p 反破坏隔离"的坑）、**子文件 hunk/行级**（`filterdiff` + `apply --cached` 补丁手术、交互 `-p` 各命令基准对照）、**改一条不在 HEAD 的旧提交**（`rebase -i` reword、`--fixup` + autosquash、脏工作区拒绝启动时的兜底）、**commit-tree 手工建提交**（绕过 index/worktree 的 plumbing、陈旧 index 陷阱）、**reflog 归因**（认出谁移动了 ref）、**jj 无 index 的替代路**。见 [references/surgery.md](references/surgery.md)。

## 隔离工作区（实验性改动 / 并行分支）

给"可能出错或需要并行的改动"开隔离工作区，避免 stash / reset 频繁切换。两个判据互相独立：**有没有 submodule** 决定用哪套机制（无则 `git worktree`，有则共享 clone——因为 submodule 的定位字段 `core.worktree` 是单值、表达不了 N 个工作区），**要不要编译** 决定要不要把 submodule 拉下来（docs 类任务跳过 submodule 实测省 83 倍时间、122 倍空间）。建立 / 分支流转 / 拆除 / 占盘实测见 [references/isolated-workspace.md](references/isolated-workspace.md)。

`core.worktree` 劫持、`--force` 累积失效注册、`submodule foreach --recursive` 的遍历盲区、手删 `worktrees/` 连活注册一起删等五个坑，以及动手前的诊断与恢复流程见 [references/submodule-hazards.md](references/submodule-hazards.md)。

## 受限网络下的仓库获取

原站够不着时怎么把仓库和 submodule 弄到手：ghfast 代理 GitHub 的一次性 `url.insteadOf` 改写（不落进仓库配置）、ghfast 不代理 GitLab 因而要另找入口、按 submodule 定点覆盖非等价镜像、递归初始化与嵌套层级、完全离线时的 bare mirror 树与 bundle 传输、以及只缺目标提交时向已有 gitdir 补对象。见 [references/clone.md](references/clone.md)。

## jj（Jujutsu）：无暂存区模型、分支与 Git 互操作

jj 用 Git 仓库当后端、协作者可无感，但模型和 Git 不同——遇到 jj 的工作副本 / 分支（bookmark）/ 操作日志 / 冲突 / Git 互操作 / 文件持久性问题看这篇。按 jj.md 的章节：**概述**（Git 兼容、四个心智转变）、**核心术语速查**（change/commit、change-id/commit-id、bookmark、operation 等）、**工作副本 `@` 与暂存区**（无 index、命令懒快照 `@`）、**change 与 commit**（change-id 稳定、commit-id 随重写变、隐藏 commit 靠 change-id+偏移找回）、**分支操作：bookmark 与匿名分支**（bookmark≈git 分支但无"当前分支"、新建 commit 不推进、重写才跟随、abandon 即删；create/set/move/list 命令与 `jj b` 简写；匿名分支；`bookmark@remote` 与 tracked、push 安全检查、`main??` 冲突）、**两条历史：操作日志与提交图**（op log vs jj log、undo/op restore/--at-op、"命名=贴 op 标签 vs 建 commit"的两轴与提交边界、编辑→commit 循环能 diff/回退到哪）、**一等冲突**（rebase 不阻塞、冲突进 commit、按需再解、auto-rebase）、**冲突与 change-id 在 Git 层的表示**（`.jjconflict-*` / `jj:trees` / `refs/jj`、change-id header 泄进 git）、**本地 vs 随 push 传播的数据**（操作×是否进 git 表、push 拒推校验、clone vs 拷目录、远端只能 git）、**改动的持久性与恢复**（懒快照时机、`jj op abandon`+`jj util gc` 修剪、明文非备份边界）、**与纯 Git 工具混用的限制**（hooks / staging / detached HEAD）。实测 jj 0.43.0、引用锁 v0.43.0。见 [references/jj.md](references/jj.md)。

## gh 认证 vs git 提交身份（两套"身份"别混）

`gh auth login` 配的是 **GitHub 登录认证**（token / 凭据助手，用于 clone/pull/push 那一下），`git config user.name`/`user.email` 是 **每条 commit 的作者身份**——**两者互不相干，`gh` 不会把登录账户自动转成 Git 的提交姓名邮箱**；GitHub 官方也明确 "Git username ≠ GitHub username"、改提交身份要单独 `git config`。所以常见的坑是 `gh auth login` 走完、`gh auth status` 全绿，一提交却仍报 `Author identity unknown`。覆盖：`gh auth login` 两个易混提示（protocol HTTPS/SSH；"Authenticate Git with your GitHub credentials?" 里的 "credentials" 指凭据助手不是 user.name/email，选 Yes 只写一条 `credential.https://github.com.helper = !gh auth git-credential`，等价于 `gh auth setup-git`）、`gh api user` 能查账户但 email 常因隐私为 `null` 且不会喂给 commit；结论——不必 `--global`（可每仓库 `--local` 覆盖）、任何层级都没设则 `gh` 不补、git 仍 fatal `Author identity unknown` / `unable to auto-detect email address`、重新 `gh auth` 只修失效 token 不重生成提交身份、推荐全局姓名 + GitHub noreply 邮箱（`ID+username@users.noreply.github.com`）。见 [references/identity.md](references/identity.md)。

## 自建 forge（Forgejo / Gitea 双栈 + 公网 SSH relay + CI runner + MCP）

forge 指 Git 托管加一圈协作服务（issue、review、CI、包仓库）的平台，Forgejo 与 Gitea 都属此类。无独立公网 IP 的内网 WSL2 机上自建 Forgejo，借唯一公网落点 VPS 做入口。核心做法是 SSH passthrough（公网 sshd 按登录名 `git` vs 运维用户分流，不破坏运维 shell）+ 跨机 relay（key 查询/git 命令经一条 SSH 转发到内网 Forgejo 容器的 `forgejo keys`/`serv`）。覆盖整体三段链路架构、为什么网页端加 SSH key 入口机即认（`AuthorizedKeysCommand` 当场查 Forgejo 数据库、不拷文件）、内网机用 authorized_keys 内联 forced command 转发 keys/serv（不另放脚本）、ControlMaster 复用绕过坑、`serv` stdin 透传、入口机发行版差异（SSH service 名/SELinux/sshd_config.d 因发行版而异）、sshd 幂等 append + 安全兜底、Forgejo Actions runner（DinD 隔离、token 注册三步、job 容器回连 `http://forgejo:3000` 的网络设计）、web 经边缘 Caddy 反代（默认中文 header；WSL/Docker 网络细节转 `network` skill）、session COOKIE_NAME 改名治登录 500、数据卷 `/data` 挂载坑（非 rootless 镜像）、**把 forge 接到 AI agent 的 MCP 配置**（Gitea 有第一方官方 `gitea.com/gitea/gitea-mcp`、Forgejo 无官方 MCP 故用社区事实标准 `codeberg.org/goern/forgejo-mcp` 及为什么是它、两家 flag/env/优先级对照、Copilot CLI `mcp-config.json` 接入、token 走 env 不走 argv 的安全理由）见 [references/forge.md](references/forge.md)。

## git-pages 静态站托管（Git forge → 网站，GitHub Pages 替代）

[git-pages](https://codeberg.org/git-pages/git-pages) 把某个 Git 仓库某分支的内容直接 serve 成静态网站（文件按路径即 URL、图片等资源原样出，不用内联 data-URI），S3 或文件系统后端，配 Caddy on-demand TLS 全自动签证。是 `software` skill 里 docs-share「S3 presigned 直链」模型的**另一条路线**（docs-share 本身也已迁到这套）。核心要点见 [references/git-pages.md](references/git-pages.md)：**最关键的决策是公开库 vs 私有库走不同发布路径**——webhook（POST）让 git-pages 匿名 clone、**只对公开库有效**（私有库必 401）；私有库要走**归档 PUT + `Forge-Authorization` token**（内容在请求体、不 clone），典型是 Forgejo Action 打 tar + curl PUT。还覆盖：一个项目下用 `path` 发布多个子站 / 不可猜路径及首次初始化、matching / non-matching wildcard 的 token 边界、预装 MkDocs runner image 和 checkout/依赖加速、metadata 枚举封锁、S3 桶布局（`blob`/`.index`/`.exists` 语义，`.exists` 驱动 on-demand TLS 且故意不随删站清除）、wildcard 映射、`Dry-Run` 头验链路，以及 `git archive` pax header、runner 单并发堵塞等排障。另含 Codeberg Pages / v2 迁移、同类实现对比、自建整套与生命周期、鉴权源码导读。

## 自动发版与发布 CI

跨 Python 与 Node 的自动发版先选版本真相源：Commitizen 由配置文件和显式 `cz bump` 决定版本，
semantic-release 则在 CI 中分析 Git 历史。覆盖：QuantumAtlas 式 PEP 621 配置、PEP 440 的
a/b/rc/dev/post、CHANGELOG 增量更新与 prerelease / 正式段、`pre_bump_hooks` 失败后的半途状态，
以及 tag 或配置更新触发的 GitHub Release + PyPI OIDC；semantic-release 的提交分析、插件生命
周期、npm 首次 web auth 发布与版本基线、Trusted Publisher OIDC、GitHub `environment:`、
staged publishing、Bun 多平台二进制 + checksum 模板和端到端验证。见
[references/release-ci.md](references/release-ci.md)。

## 双向 SSH 镜像（不推荐，存档）

多设备协作且部分设备无法访问 GitHub 时，用一台公网 VPS 做双向 SSH git 镜像。**这条路线不作首选**——自建 forge 能力更完整、维护面更小；纯粹拉不下来的场景多数可以用受限网络获取那套绕过。保留仅作存档，架构、搭建步骤、hooks、Actions workflow、防回环、防 split-brain 见 [references/mirror.md](references/mirror.md)。
