---
name: software
description: 本地软件、CLI 工具与自托管服务的配置和排障知识库。用于 SSH/systemd、终端与包管理工具、语言工具链、PostgreSQL、S3 对象存储、Docker/PaaS、Overleaf/OpenList、文档处理与发布，以及 Windows/WSL/macOS 日常软件问题。
---

# Software

Git 与 jj 的日常操作、隔离工作区、受限网络获取、发版 / 发布 CI、自建 forge 与 git-pages 已迁往 `git` skill。

## PostgreSQL 读写性能

量化 PostgreSQL 读写性能受哪些因素影响，按三层拆开讲机理、测法与实测：**容器层**（数据卷不过 overlayfs 所以 I/O ≈ 原生，代价在 `/dev/shm` 默认 64MB、`stop_grace_period` 默认 10 秒等别处；SSD+HDD 混用时用 tablespace 做冷热分层的目标形态，以及原生安装 vs Docker 落地这套分层的成本对照——Docker 一次性配置略麻烦、但容器内路径是稳定抽象，换盘换机器不用碰库里的 tablespace 定义）、**介质层**（硬 RAID 卡后面 `ROTA` 不可信要用 `storcli` 问介质与缓存保护模块，BBU 坏会静默降级 WriteThrough；校验型 RAID 的写惩罚；写缓存打穿前后 fsync 差 64 倍并解释了 checkpoint 单文件 fsync 565 秒的事故——附「`Ds` 状态 + BlockIO 计数器不变无法区分卡死与巨慢、观察窗口要匹配单次操作量级」的诊断教训；SSD 镜像 / HDD 阵列 / 网络 LUN 横向实测，fsync 差到 1600 倍而顺序带宽反向）、**网络层**（千兆链路上限与延迟构成、经 Windows iSCSI Initiator + WSL2 的完整链路对读数归因的影响；**精简置备空洞读法**把网络与磁盘瓶颈分开，据此定出「顺序读卡网络、随机读卡磁盘、存储端 CPU 有 15 倍余量」；队列深度扫描，`dd`/`hdparm` 相当于 QD=1 会低估 36%）。另含共用的指标口径与 `fio` / `pgbench` 基线命令、PG 的数据布局与参数（`random_page_cost` 随介质设、`work_mem` 是每节点每并行进程一份）、以及迁移相关的 zstd vs gzip 实测与 `pg_restore` 出错仍返回 0 必须加 `--exit-on-error`，见 [references/postgresql.md](references/postgresql.md)。

## SSH

SSH 密钥 passphrase、ssh-agent、非交互环境（CI / `bash -c`）私钥带 passphrase 又无解锁 agent 导致 `Server accepts key` 却 `Permission denied` 的诊断与复用常驻 agent 解法、RemoteForward 代理转发、主机密钥校验（known_hosts、`CheckHostIP` 默认及 OpenSSH 与 asyncssh 等第三方库对 IP 的处理差异——同一主机换 IP 后 OpenSSH 沉默而第三方库报 `Host key is not trusted` 的根因与修复）、ControlMaster 连接复用、裸 ssh/scp 跑命令与交互式 sudo（`ssh -t`）及远端文件编辑等通用 SSH 用法见 [references/ssh.md](references/ssh.md)。

## 包管理器全景 / 分类对比（Nix vs apt、choco/winget/Scoop、npm/pnpm/bun、pip…）

"包管理器"是差异极大的一大类工具的统称，按**管谁的包**分五类——系统级（apt/dpkg、dnf/rpm、pacman、Homebrew、Windows 的 choco/winget/Scoop）、语言级（pip/PyPI、npm、cargo、go、gem、nuget、composer、maven、vcpkg/Conan）、跨发行版声明式（Nix/Guix）、应用沙箱分发（Flatpak/Snap/AppImage）、跨语言环境与版本管理器（conda/mamba/pixi/uv、asdf/mise）。覆盖：一套横向**对比维度**（管谁的包 / 全局共享单版本 vs 哈希隔离多版本 / 命令式 vs 声明式 / 中心 registry vs 去中心化 vs distro repo / 预编译 vs 源码构建 / 有无 lockfile）；**Nix vs apt** 深入对照（`/nix/store` 哈希隔离怎么白送多版本共存·原子回滚·可复现·免 root·精确 GC，代价是磁盘膨胀与非 FHS 二进制难跑）；**Windows choco / winget / Scoop 三家**（社区 NuGet+PowerShell 脚本 vs 微软官方 winget-pkgs manifest vs Scoop 便携解压到 `~/scoop/` 免管理员，前两者只是静默跑 installer 的自动化壳、不隔离，winget 另有 DSC 声明式 Configuration）；**npm / pip(PyPI)** 与 **npm/pnpm/yarn/bun 四家客户端对照**（同一 registry、差别在 `node_modules` 布局·lockfile·速度，corepack 按项目切版本；pnpm 的 `node_modules/.pnpm` 虚拟 store + 全局 CAS 硬链接怎么同时省盘与防幽灵依赖；**bun 两极分化**——install 快~25×·一体化工具链 vs Node 兼容坑·JSC≠V8·生产内存·历史 `bun.lockb` 二进制锁与 Windows 迟到，逐条标已修复/仍成立；npm 依赖树多版本嵌套共存 = 跟 apt 全局单版本的根本区别；pip 的 wheel vs sdist、venv 隔离、无原生 lock、PEP 668 externally-managed 与系统 Python 打架）；**conda/pixi/uv 环境管理器 + asdf/mise 版本管理器**与本仓 `Pixi > uv > pip` 优先级；**绕过包管理器的 `curl|sh` 与 PowerShell `irm|iex`**（= `Invoke-RestMethod|Invoke-Expression`，执行未审计远程代码的取舍与先落地再审阅）；**把 npm/包管理器借用作跨平台原生二进制"安装器"的壳包 + 平台专属 optionalDependencies（os/cpu/libc 门控、musl 分叉判据，及"静态链接可只发一个 musl 通吃、故没分叉≠非原生"的反向陷阱）模式**（esbuild/swc/biome/turbo 等泛例；三大 coding agent 的工具链/安装方案/软弃用/采用度普查已拆到 harness skill 的"coding agent 的安装与分发形态"章节）；**npm/pnpm/yarn/bun 四家客户端采用度快照**（周下载量 + 系统性偏差提醒 + HN 风向）；以及系统级/语言级两张"想干嘛×各家"命令速查与踩坑合集见 [references/package-managers.md](references/package-managers.md)。Go 模块生态"无中心仓库、import 路径即源码地址"的细节见 [references/go.md](references/go.md)。

## Go 工具链（去中心化模块 / `go install` / 解析与版本 / cgo 坑）

Go 的包生态是**去中心化**的：没有 PyPI/npm/crates.io 那样的中心注册仓库，import 路径**就是**源码地址（`github.com/…`、`gitea.com/…`、`codeberg.org/…/v2`），`go install pkg@version` 直接从对应 VCS host 拉源码编译成二进制丢进 `$GOBIN`；`proxy.golang.org` 只是惰性缓存镜像不是注册中心，"发版"= 推一个 git tag。覆盖：`go` 无中心仓库的事实与对 PyPI/npm 的对照、原生装法 `go install` / `go run pkg@version`（`@latest`/`@vX`/`@commit` 版本选择、`GOBIN`/`GOPATH`、`@ver` 时忽略当前 `go.mod` 不污染项目依赖、Go 1.16 起装工具专用它、`/vN` 主版本进路径）、**导入路径→仓库的解析机制**（已知托管站规则 / `.git` 后缀 / vanity 路径 `?go-get=1` + `<meta name="go-import">` 重定向 + Go 1.25 subdir + `mod` 代理变体）、**版本模型**（SemVer、`/vN` 共存、伪版本、MVS 最小版本选择）、`go.mod`/`go.sum`/模块缓存、GOPROXY/GOSUMDB/GOPRIVATE（默认 `proxy.golang.org` + `sum.golang.org`、`direct` 回落、私有模块绕过、墙内换 `goproxy.cn`）、`go install` 遇 `replace` 指令为何失败（replace 只对主模块生效）、从 module proxy 装 vs 本地 clone build 的 `vcs.*` 戳/`+dirty` 判别、以及 **`pixi global install go`（conda-forge 包）的 cgo 坑**（`DefaultCC=x86_64-conda-linux-gnu-cc` 被编译期烧进 go 二进制、缺配套编译器致 cgo 构建失败，判别四连 + 修法 `pixi global install --environment go c-compiler`）见 [references/go.md](references/go.md)。

## pixi（全局环境 / trampoline / 升级与临时环境）

pixi 自身的操作模型：`pixi global` 的真相源是清单 `~/.pixi/manifests/pixi-global.toml`（`[envs.X]` 的 `dependencies` / `exposed` / `channels` 各管什么、手改后 `pixi global sync` 对齐、子命令按"改清单哪一部分"分工）；一个包默认独占一个同名环境、`-e/--environment` 才是塞进同一环境的开关；`~/.pixi/bin/<命令>` **不是软链而是同一个 trampoline 二进制的硬链接**，真实目标与注入的 `CONDA_PREFIX`/`PATH` 写在 `trampoline_configuration/<命令>.json` 里（排障别用 `readlink`）；`pixi global upgrade` **已被移除**、改用 `pixi global update <环境名>`；`pixi search` 一次回答"能不能 pixi 装"和"版本落后多少"；`pixi exec -s <包> -- <命令>` 是不留常驻环境的临时跑法（`uv run --with` 的 conda 版）。见 [references/pixi.md](references/pixi.md)。conda-forge 版 go 的 cgo 坑仍在 [references/go.md](references/go.md#cgo-pitfall)。

## Zellij

Zellij Web client、HTTPS 证书要求、login token/session token、反代注入 Cookie、`default_shell`、Web/xterm 主题分层、给特定软件写 OSC 10/11 颜色 wrapper、Codex 输入框颜色、鼠标选区颜色、pane 大小相关操作（全屏 `Ctrl p`→`f`、resize 模式 `Ctrl n`、`stacked_resize` 只由无方向的 `+`/`=` 与 `-` 触发、边框/留白开关 `Ctrl p`→`z`（`TogglePaneFrames`，误触致内容贴边无留白、再按一次恢复））、pane 布局排列（swap layout 切换 `Alt [`/`Alt ]` 及随 pane 数自动跳档、新建普通 pane vs stacked pane `Ctrl p`→`s`、焦点在 stack 内新建即并入、`MovePane` 只对调不增长 stack）、keybinds 合并块 vs `clear-defaults` 全量（合并块只写增量、`unbind` 撤默认键，避免给动作加新键后两键都触发）、改 `web.kdl` 后哪些要重启 web service 哪些新开会话即生效、与 WSL systemd service 写法见 [references/zellij.md](references/zellij.md)。

## uv（Python 包 / 环境管理器）

[uv](https://github.com/astral-sh/uv)（Astral 的快速 Python 包 / venv 管理器）使用与排障。重点记一个**不是 uv 本身、而是 snap 版 uv** 的坑：`ExecStart=/snap/bin/uv run …` 的 systemd 服务，被 uv 拉起的应用日志**在 `journalctl -u <service>` 里完全看不到**——snapd 把进程重挪进 `snap.astral-uv.uv-<uuid>.scope` cgroup，journald 按 cgroup 归属日志，应用输出挂在 snap scope 名下而非服务单元名下（`classic` confinement 也一样）；绕过是按 `journalctl -t <SyslogIdentifier>` 查，治本是把 `ExecStart` 换成非 snap 的 uv。另附 `uv run` 下 Python 块缓冲需 `PYTHONUNBUFFERED=1` 的实测。见 [references/uv.md](references/uv.md)。

## Service / systemd

多用户共享服务、systemd 模板单元与按 UID 分配端口、systemd `LoadCredential` 注入密钥，**user 级服务（`systemctl --user`）与 `loginctl enable-linger` 常驻**（user manager 生命周期默认绑 login session、登出即被杀、开机不自启的坑），以及 **stdout 块缓冲导致 journal 看不到服务卡死前最后输出**（`StandardOutput=journal` 接的是管道不是 TTY；Python 要 `PYTHONUNBUFFERED=1`，`stdbuf` 对它无效）见 [references/service.md](references/service.md)。

## MkDocs

从 Markdown 源文件、`mkdocs.yml`、主题、插件和扩展的基本模型开始，逐步覆盖原生 `nav`、awesome-pages 的 `.pages`、front matter 权重、Material/PyMdown、KaTeX/MathJax、开发站与静态 Pages 的行为分离、浏览器整页/WYSIWYG/内容块编辑、Sveltia 等 Git-backed CMS、Git 修改时间与最近更新、strict/validation、常驻 user service、同域 HTTP+WSS 作者网关及分层排障，见 [references/mkdocs.md](references/mkdocs.md)。公网 TLS 与身份认证转用 `vps-maintenance` skill；EasyTier、端口转发与 WSL/宿主网络转用 `network` skill；Forgejo Actions 与 git-pages 发布协议转用 `git` skill。

## ChatGPT 网页端自动化

ChatGPT 网页端 Pro / Extended 自动化、`steipete/oracle` browser engine、Windows Chrome DevTools、WSL Mirror / NAT 差异、以及必须用 network payload 验证真实模型与 thinking effort 的经验见 [references/oracle-pro.md](references/oracle-pro.md)。

## 挂载与文件共享

WSL 挂载 Windows 盘、UNC/SMB 共享、`drvfs/9p` 小文件性能、CIFS 凭据与 `mount.cifs` 排障见 [references/mount.md](references/mount.md)。

## Windows / WSL2 的内存模型

全篇分概念、WSL 与 Windows 侧的配置、Slurm 侧的内存限额三部分。guest / host / 物理内存三者的语义差别（`memory=` 是上限不是预留；所有发行版共用同一台虚拟机，所以 Docker 引擎与 WSL integration 随虚拟机一起存亡）、页与缺页机制、NVMe / VHDX / 页面文件的术语（VHDX 动态扩展但不自动缩回，决定 swap 容量该怎么规划）、三条换页路径分别由谁决定以及 guest 能否看见（宿主换出虚拟机内存对 guest 完全隐形，只能靠"延迟中位数不变但出现秒级尖峰、多进程同时冻结、guest 内核零消息"这组形状反推，且它与 guest 侧颠簸对应的旋钮不可互换；三者物理终点是同一块盘，延迟差距来自层数与争用而非介质）、Windows 的提交量与提交上限记账（上限 = 物理内存 + 页面文件，所以"虚拟机上限 + 宿主需求 ≤ 物理内存"这个和无人把关）、宿主与 guest 两层同构的提交记账术语对照（system commit charge / commit limit ↔ `Committed_AS` / `CommitLimit`；页面文件与 swap 同层次但只有各自那一份进各自公式；宿主始终执行而 guest 侧仅 `vm.overcommit_memory=2` 时执行）、swap 能扩总容量却扩不了活跃工作集（冷页划算、热工作集颠簸）、`.wslconfig` 内存相关键的默认值（`swap` 缺省按内存 25% 折算、`autoMemoryReclaim` 缺省为 `dropCache` 而非关闭）、guest 侧 `vm.swappiness` 与 `vm.overcommit_memory` 的含义、OOM killer 以"回收有无进展"为判据导致大 swap 下的回收活锁与 PSI / 早期 OOM 守护进程的补位（这类守护进程只管得到 guest 内部，宿主换页时 PSI 读数正常、不会触发）、guest `free` 的 `used` 不含缓存所以两侧要用 `MemTotal−MemFree` 对比（附双侧同步采样的对应关系、固定虚拟机开销与宿主侧退还滞后），以及 Slurm 侧 `RealMemory` / `DefMemPerNode` / `MaxMemPerNode` 与 `task/cgroup` 的协同、限制挂在 job 层而叶子 task cgroup 显示 `max` 的层级落点、绕过调度器的裸 `mpiexec` 如何补上限额，以及一份把各层落成具体取值的配置示例（起因 → 该拧的旋钮 → 示例值），见 [references/memory.md](references/memory.md)。

## Linux 回收站（trash-cli / gio trash）

`trash-cli` 与 GLib `gio trash` 是两套实现但遵循同一 FreeDesktop Trash 规范（同一 `~/.local/share/Trash/`、`files/`+`info/*.trashinfo` 配对、`.Trash-$uid` 卷内逻辑），互通可混用。覆盖回收站两半结构（含 `Path=` 在卷内回收站是**卷内相对路径**、`trash-put` 同卷只是 rename **不释放空间**）、**回收站条目名不是原文件名**（重名追加 `_N` 且加在扩展名之后、超 100 次改随机数、超长会截断，所以按条目名扩展名筛选会大量漏项，必须读 `Path=`；同一原始路径可对应多个条目、`trash-rm` 会一并删光）、坏 `.trashinfo` 的影响范围（解析错误会跳过继续，但**删除失败会抛异常中止整批**、剩余项静默不处理）、`trash-rm` 匹配规则（`/` 开头按整路径否则按 basename，附 `filter.py` 源码与正确写法）、gio 无选择性永久删单项（附 `gio-tool-trash.c` 源码）、删挂载盘文件两者同规范的卷内落点、以及 **fstype 白名单导致的卷发现失败**（`trash-put` 走 `ismount` 上溯所以总对，`trash-list`/`trash-rm`/`trash-empty` 走白名单过滤；上游把 WSL 的 `9p` 写成 `'p9'`，2022 年引入至今未修，附 issue #242 里"作者无 Windows 机器代测、报告者只验证了 put"的存活原因，以及 #256/#412 表明同机制也坑 virtiofs 等其他文件系统；绕过用 `TRASH_VOLUMES`，它同时是约 94× 的提速开关）见 [references/trash.md](references/trash.md)。

## RustFS + MinIO mc 客户端

RustFS（Rust 实现的 S3 兼容对象存储，github.com/rustfs/rustfs）+ MinIO `mc` CLI 的对接经验：**mc（CLI 二进制）与 boto3（Python SDK）互为补集，建议混用 crosscheck**；versioning 是桶级开关、软删（`mc rm` 不带 `--versions` = 写 delete marker，可 `mc undo` 恢复）vs 硬删（`mc rm --versions --force` = 物理删，不可逆）的语义与恢复/GC 链路；**列举数可疑时用 boto3 + mc 交叉验证、`ListObjectVersions`（`mc ls --versions` / boto3 `list_object_versions()`）当兜底 oracle**（这套习惯曾帮忙定位一个上游已修复的服务端列举问题）；跨桶 server-side copy 在 HDD 后端高并发会撞 `Io error: timeout` 500（`--max-workers` 限并发 / 调 RustFS timeout env）；`mc rb --force` 在大 versioning 桶会 hang、改用 `x-minio-force-delete` header server 端清桶（脚本 `scripts/rustfs_force_delete_bucket.py`）；HDD 后端 wall-clock ∝ 对象数（打 zip 聚合 ~10× 加速）。见 [references/rustfs.md](references/rustfs.md)；大批量 op 可靠性模式（并发 list/delete/copy + 断点续传骨架）见 [references/rustfs-bulk-ops.md](references/rustfs-bulk-ops.md)。

**SeaweedFS 对照**（另一类 S3 兼容存储）：SeaweedFS 是 Haystack blob 存储 + Filer、不是 MinIO 克隆——与 RustFS 的关键区别（架构 / 纠删码 / 版本存储 / lifecycle / 服务端 copy / 删桶 / S3 保真度）及其多前端客户端（S3 网关、原生 REST、Filer HTTP、FUSE、WebDAV，运维用 `weed shell`；`mc` 仅通用 S3 模式可用、`mc admin` 不行）见 [references/seaweedfs.md](references/seaweedfs.md)。

## Windows / WSL 宿主侧速记

跑在 Windows 宿主上的小经验：PowerShell 5.1（Desktop）与 7（pwsh，Core）两套运行时的辨认（含 `v1.0` 目录名是历史遗留、`SysWOW64` 下另有 32 位副本）、**文本编码的三个独立开关**（`[Console]::OutputEncoding` 写 stdout 的字节两版相同都是系统 codepage、`$OutputEncoding` 管道送进原生程序时 5.1 用 `us-ascii` 会不可逆丢字、落盘 cmdlet 默认编码 5.1 是 UTF-16LE+BOM 而 7 是 UTF-8 无 BOM）与接收端按 UTF-8 严格解码时的对策排序（结果落盘 ＞ 设 `OutputEncoding` ＞ 管 `iconv`）见 [编码章节](references/windows.md#encoding)；原生程序参数数组、cmdlet splatting 与 `-LiteralPath`、落地成 `.ps1` 用 `-File` 跑（含 `-NonInteractive` 把挂死变失败、别习惯性加 `-ExecutionPolicy Bypass`）见 [命令与参数的传递](references/windows.md#invocation)；从 WSL 弹 UAC 拿管理员权限并靠文件标记跨上下文回传结果见 [提权章节](references/windows.md#elevation)。另有 cmd.exe 不接 UNC 当 CWD、跨用户判断软件最后使用时间（`%USERPROFILE%` 的 `LastWriteTime` 不可信）、Windows 回收站与 `trash-put` 的分工、**WSL `/tmp` 每次 `wsl --shutdown` 后被清空的真因（systemd-tmpfiles `D /tmp` 规则 + boot `--remove`，不是 tmpfs；`30d` age 只管周期清理不管 boot 全清；保命放 `$HOME`/`trash-put`）**、**WSL 的开机时刻判定（`uptime -s` 与 `btime` 记的可能是上次关机时刻、误差等于停机时长，一律以 `journalctl --list-boots` 为准）** 见 [references/windows.md](references/windows.md)。

## Windows / Office 激活

MAS（`irm https://get.activated.win | iex`；HWID / Ohook / TSforge / Online KMS 四种机制的产品支持、联网需求与持久性各不相同——HWID 不激活 Office，Ohook 不支持商店版 Office 而 TSforge 支持）、CMWTAT、macOS 的 VL Serializer 路线，以及正版与第三方介质来源、[国内直连的可达性](references/activation.md#cn-reachability)见 [references/activation.md](references/activation.md)。

## macOS 小问题集锦

推荐应用（VMware Fusion、Mounty + macFUSE NTFS 读写）、应用无法打开的权限修复、外置存储隐藏文件（`.DS_Store` / `.Spotlight-V100` / `.Trashes`）阻止与清理见 [references/macos.md](references/macos.md)。

## 飞书文档中的公式与矢量图

飞书原生公式块、Mermaid/SVG 画板，以及量子线路的两条制作路线——直接生成飞书兼容 SVG，或复用 TikZ/Quantikz 源并经过 PDF→SVG 与路径兼容化——见 [references/feishu.md](references/feishu.md)。其中包含 `<use>` 字形引用、`matrix(...)` 变换在浏览器正常但进入飞书后重叠的实测，以及必须以服务端画板预览验收的流程。

## 格式转换

pandoc 文档转换（LaTeX→Word）、PDF→图片、feishu2md 飞书/Lark→Markdown，以及 Markdown→PDF 的三档路线——最轻量的 Calibre `ebook-convert`、印刷级 CSS Paged Media 引擎（Prince / Vivliostyle / Paged.js / WeasyPrint 选型、Prince XML 无 sudo pixi 安装与 CJK 字体大坑、引用标签预处理 → pandoc → Prince 一键流水线、Vivliostyle 自定义 CSS）、中文友好的 Typst 路线——全部见 [references/format-conversion.md](references/format-conversion.md)。

## USTC Overleaf / olcli

USTC 自建 Overleaf 的 `olcli-ustc` 安装与一次性 token 无头鉴权、nvm-safe npm prefix、与上游 `@aloth/olcli` 的差异及上游连接 Overleaf 官方站的边界，以及内部 HTTP 项目创建、普通 OT 编辑、评论、Track Changes、Accept/Reject 和 `figures/` 上传实测见 [references/overleaf.md](references/overleaf.md)。同步根必须是编译根（否则产生影子副本）、服务端 latexmk 缓存卡死导致引用变 `?`、`download` 静默失败、把 `OverleafClient` 当库用直取 build 产物，以及本地与 Overleaf 的 TeX Live 版本错配（cleveref first aid），同见该文。

## 本地中文 ASR

FunASR、Fun-ASR-Nano、Paraformer + VAD + Punc + CAM++、SenseVoiceSmall、Whisper turbo 在 CPU 机器上处理中文长录音的实测经验、切块策略、speaker/timestamp 取舍见 [references/asr.md](references/asr.md)。

## 私有 docs-share 站点（Git 仓库 → S3 直链分享）

把要公网呈现的 md/html 放进一个私有 Git 仓库，每次 `git push` 或网页端上传/编辑即触发 CI（`rclone sync --checksum`）**增量同步**到一个 S3 兼容桶（桶结构 = 仓库树）；对外走 S3 **presigned 直链**（URL 自带签名 + 有效期）分享；`public/` 前缀通过 bucket policy 开放匿名读、无需签名——知道 URL 即可访问。`.md` 原样存（下载=raw），由 Caddy Accept rewrite + markdeep viewer 客户端渲染。完整内容见 [references/docs-share.md](references/docs-share.md)：密钥体系（root key 派生受限 CI key、凭据存储位置）、public 路径 vs 私有路径的 bucket policy 机制、presigned URL 生成（直贴/viewer 包装/脚本批量）、更新与撤销、markdeep 写作惯例（`[#key]` 引用 vs `[^name]` 脚注、GFM 不兼容点、研报模板）。服务端部署中的 Caddy 配置、CI key 与 bucket policy 由 `network` skill 覆盖；viewer 壳子资产由 `vps-maintenance` skill 提供。S3 兼容存储底层行为见 [references/rustfs.md](references/rustfs.md)。

## OpenList 网盘聚合面板

OpenList（AList 的活跃 fork）的 **REST API 编程接入**（两种 token——登录 JWT vs 固定 admin token——的对比与为什么 agent 该用后者、CLI `openlist admin token` 取值、OpenList-Desktop 桌面版的 session/盘符隔离坑、token 不落进对话/日志的 side-channel 取法、核心端点速查、跨存储 mv/cp 是异步任务且进度可经 `/api/admin/task/*` 轮询、HTTP 恒 200 真码在 `body.code`）、任何 backend 都成立的共性行为坑（C 系列：缩略图懒加载、DirectorySize 全 stat、搜索索引手动）见 [references/openlist.md](references/openlist.md)。

把 **iCloud Drive 接入 OpenList**（rclone 直连 vs 借道常开 Mac 用 SMB 中转的选型对比、R 系列 rclone 直连专属坑、M 系列 Mac SMB 中转专属坑、macOS SMB 部署步骤含 GUI 路径、嵌套挂载还原完整 iCloud 视图、`dd over ssh` 远程链路测速 + 体验对照、EasyTier 双向不对称排查）见 [references/openlist-icloud.md](references/openlist-icloud.md)——这篇大量是 macOS GUI / 桌面操作，给人照做的部署说明。

## MinerU PDF→Markdown 转换

MinerU（mineru.net）提供 VLM 模型将 PDF 转为 Markdown/JSON，支持公式和表格识别。默认使用云端 API / Open API；未经用户明确允许，不要在本机安装或部署 MinerU。详细流程见 [references/mineru.md](references/mineru.md)。

## OpenAlex 数据访问与全文下载

OpenAlex 官方 CLI 的 uv 全局安装、API key / 匿名预算与计费、DOI / filter 元数据下载、Content API 和 OA / 许可证边界，以及网站、OQL/OQO、Snapshot、Sync、R2 全文档案、Unpaywall、Agents 与社区 SDK 的分工见 [references/openalex.md](references/openalex.md)。其中记录了 `openalex-official 0.3.3` 把 Content API 的 `200 application/pdf` 误判为失败且仍计费的交叉实测、源码根因、上游 issue 状态和当前绕行方式。

## Docker（安装 + 多用户共用）

Ubuntu 上装 Docker Engine 的**官方推荐方式**（apt 仓库法，非 `get.docker.com` 便捷脚本）与让多个非 root 用户共用见 [references/docker.md](references/docker.md)：官方 apt 仓库法完整步骤（modern `signed-by` keyring、arch/codename 动态取、Engine+CLI+containerd+buildx+compose 五件套）、多用户共用（`usermod -aG docker` 把用户加进包安装时自动建好的 `docker` 组 = 免 sudo 读写 `/var/run/docker.sock`）、**组变更生效时机的坑**（`usermod -aG` 只改组数据库、已登录会话要**重登**才生效，`newgrp`/`sg docker -c` 可不重登临时激活并顺带验证，`id -nG <user>` 查库 vs 无参 `id -nG` 查当前会话的区别）、以及**安全取舍**（docker 组 ≈ 免密 root，`-v /:/host` 一行提权；可信开发机常规做法 / 给 sudoer 加风险不变 / 给非 sudoer 加 = 变相发 root，替代方案 rootless Docker、`sudo docker`、细粒度 sudoers）。含一次 HFNL（Ubuntu 24.04）实操记录。

## Coolify 与 Dokploy（自托管 PaaS）

[Coolify](https://coolify.io) 与 [Dokploy](https://dokploy.com) 的宿主约束、端口所有权、上游反代、控制面/工作负载边界、分层清理及产品专有架构统一见 [references/coolify-dokploy.md](references/coolify-dokploy.md)。其中 Coolify 部分按 v4.1.2 源码覆盖运行架构、实时路由、配置持久性和对外应用发布；Dokploy 部分区分 v0.29.8 锁定源码、滚动安装脚本、官方默认入口与非官方 socat workaround。WSL/mesh 入站 portproxy 相关见 `network` skill 的 WSL 章节；边缘 Caddy 服务端配置由 `network` skill 覆盖。
