# 包管理器全景：分类维度 + Nix / apt / choco / winget / npm / pip 横向对比

> "包管理器（package manager）"是一大类差异极大的工具的统称，各自解决不同问题：**系统级**（apt/dpkg、dnf/rpm、pacman、Homebrew、Windows 的 choco/winget）管整台机器的原生软件；**语言级**（pip、npm、cargo、go）管某门语言的库和工具；**跨发行版声明式**（Nix/Guix）用哈希隔离换可复现；**应用沙箱**（Flatpak/Snap/AppImage）把桌面应用连依赖打包隔离；**跨语言环境**（conda/mamba/pixi/uv）给项目搭独立工具链。
>
> 这篇先给一套**横向对比维度**，再把常见的摆进去，重点放大 **Nix vs apt** 与 **Windows 的 choco vs winget**，并覆盖用户常用的 **npm / pip(PyPI)**。Go 模块生态"没有中心仓库、import 路径即源码地址"的细节已在 [go.md](go.md)，此处不重复。

---

## 一、先分清"管谁的包"——五大类

理解包管理器全景的第一刀不是比命令，而是看它**管的是谁的包、装到哪一层**。同一台机器上这五类可以并存、各管各的：

1. **系统级 / OS package manager**：管整个操作系统的原生二进制与共享库，装进系统全局路径（`/usr`、`Program Files`）。
   - Linux：`apt`（底层 `dpkg`，`.deb`）、`dnf`/`yum`（`rpm`）、`pacman`（Arch，`.pkg.tar.zst`）、`apk`（Alpine）、`zypper`（openSUSE）。
   - 跨平台/用户级：**Homebrew**（macOS 原生，也能装 Linux，装进自己 prefix 不碰系统）。
   - Windows：**Chocolatey (choco)**、**winget**、**Scoop**（详见第四节）。
2. **语言级 / 生态级 package manager**：只管某门语言的库和 CLI，通常装到项目本地或语言专属目录。`pip`(Python)、`npm`(Node)、`cargo`(Rust)、`go`(Go)、`gem`(Ruby)、`nuget`(.NET)、`maven`/`gradle`(Java)、`composer`(PHP)。
3. **跨发行版声明式 / 函数式**：**Nix**、**Guix**。不依赖发行版，把每个包连同全部依赖装进带哈希的只读路径，换来多版本共存、原子回滚、可复现（详见第三节）。
4. **应用沙箱分发（sandboxed app）**：把桌面应用连运行时依赖一起打包并沙箱隔离。**Flatpak**（Flathub 源、用户级、portal 权限模型）、**Snap**（Canonical，含服务/CLI/GUI，商店后端专有，自动更新，squashfs 挂载）、**AppImage**（单文件、下载即跑、无中心仓库、无"安装"步骤）。
5. **跨语言环境管理（cross-language env）**：**conda / mamba / pixi**（不止 Python，带预编译二进制，conda-forge 生态）、**uv**（Python 专用、极快）。给每个项目搭独立、可复现的工具链（详见第六节）。

---

## 二、六个对比维度（这篇的灵魂）

抓住这六个轴，任何包管理器都能一眼归位；后面所有对比都是这张表的展开。

| 维度 | 一端 | 另一端 | 谁在两端 |
| --- | --- | --- | --- |
| **管谁的包** | 系统原生软件 | 某语言的库 | apt/choco/winget ↔ pip/npm/cargo |
| **安装布局** | 全局共享、**单版本** | 隔离、**多版本共存** | apt/dnf/choco/winget ↔ Nix、npm `node_modules`、python `venv` |
| **操作模型** | 命令式（改系统当前状态） | 声明式（描述目标状态、可复现） | apt/choco ↔ Nix flake、`requirements.txt`+lock、Brewfile、winget Configuration |
| **包从哪来** | 中心 registry（按名字下载） | 去中心化（源码地址即包） / distro repo | PyPI·npm·crates.io·choco社区源 ↔ Go modules·Nix ↔ apt/dnf 发行版仓库 |
| **产物形态** | 预编译二进制 | 从源码构建 | apt·winget·pip wheel ↔ Nix(可缓存)·cargo·`go install`·AUR |
| **可复现** | 有 lockfile / 内容寻址 | 无锁、随仓库漂移 | npm·cargo·Nix·pip(uv/poetry) ↔ 裸 apt、裸 `pip install` |

两条最容易误解、也最能拉开差距的轴：

- **"全局单版本 vs 隔离多版本"**。`apt` 把 `libfoo` 装到全局 `/usr/lib`，**一个库只能有一个版本**——A 要 `libfoo 1`、B 要 `libfoo 2` 就直接冲突（经典 dependency hell）。而 Nix 用哈希路径、npm 用嵌套 `node_modules`、Python 用 `venv`，都能让多版本**并存**，各链各的。
- **"命令式 vs 声明式"**。`apt install` 是一步步**修改**系统"当前长啥样"；声明式（Nix 表达式、lockfile、winget Configuration）是写一份"我要的**最终状态**"，同一份定义在别的机器上能重放出同样结果。

---

## 三、重点：Nix vs apt（几乎每个维度都相反）

用户熟 `apt`，理解 Nix 最快的路径就是拿它俩逐维对撞——这也是理解"声明式 + 内容寻址"包管理的最佳样本。

| | **apt (dpkg)** | **Nix** |
| --- | --- | --- |
| 操作模型 | 命令式：改系统全局当前状态 | 声明式：描述目标，同输入必同输出 |
| 安装路径 | 共享 `/usr/bin`、`/usr/lib` | `/nix/store/<hash>-name-ver/`，哈希=f(源码+全部依赖+编译选项+编译器) |
| 可变性 | 原地覆盖旧文件 | store 只读、装好永不改 |
| 多版本 | 全局单版本，冲突即失败 | 各占各的哈希路径，天然共存 |
| 依赖地狱 | 会（全局单版本所致） | 不会（隔离白送） |
| 升级/回滚 | 破坏性覆盖；回滚≈没有 | 原子换一组符号链接（一个"generation/代"）；`--rollback` 秒回上一代 |
| 可复现 | 依赖"本机当前状态"，做不到逐字节一致 | 哈希含全部输入，跨机重放出**相同**结果 |
| 需要 root | 是（动系统） | 单用户模式可无 root（包全在 `/nix`，不碰 apt） |
| 垃圾回收 | `apt autoremove`（启发式） | 精确：沙箱构建知道确切引用，`nix-collect-garbage` 只删没人引用的 |

**核心机制一句话**：apt 命令式地修改一份全局共享状态；Nix 把每个包连同全部依赖钉进一个**带哈希的只读路径**，你 `PATH` 里看到的只是指向它的符号链接。上表右列的多版本共存、原子回滚、可复现、免 root、精确 GC，**全是这一条机制白送的**。

代价（诚实说）：

- **磁盘换隔离**：同一库存多份副本、store 什么都留，`/nix/store` 容易膨胀到几十 GB，得定期 `nix-collect-garbage -d`。
- **非 FHS 二进制难跑**：Nix 不遵守 Filesystem Hierarchy Standard（没有标准 `/usr/lib`、`/lib64/ld-linux…`），自己下载的闭源预编译 ELF 找不到动态链接器会直接挂，要 `patchelf` 或 `steam-run`/`nix-ld` 包一层。
- **两套命令 + 学习曲线**：老的 `nix-env`/`nix-build` 与新的 flakes（`nix profile`/`nix shell`/`nix develop`）并存，文档新旧混杂；Nix 语言惰性求值、报错难读。

> Nix 大多数包**不用本地编译**——官方有二进制缓存 `cache.nixos.org`，直接下预编译产物；本地只在缓存未命中或改了构建输入时才编。参考 [nixos.org](https://nixos.org/)、[Nix manual](https://nixos.org/manual/nix/stable/)、apt 概念 [wiki.debian.org/Apt](https://wiki.debian.org/Apt)。

---

## 四、Windows 三家：Chocolatey (choco) / winget / Scoop

choco 和 winget 都是**"静默跑官方安装程序"的自动化壳**——本质是替你 `下载官方 installer → 静默安装`，装进系统标准位置（`Program Files` 等），**都不做 Nix 那种隔离**，装完就是普通的已安装程序。**Scoop 走的是另一条路**：把程序当**绿色便携版**解压到用户目录 `~/scoop/`、不进系统、不需管理员、卸载=删目录，更像"给 CLI 工具用的、免污染系统"的方案。区别在"谁维护、包长什么样、装到哪一层"。

| | **Chocolatey (choco)** | **winget** | **Scoop** |
| --- | --- | --- | --- |
| 出身 | 第三方社区（另有商业版） | **微软官方**，Win10 1709+/11 内置 | 第三方社区（[scoop.sh](https://scoop.sh/)） |
| 装到哪 | 系统全局（`Program Files`） | 系统全局 | **用户目录 `~/scoop/`**，便携解压 |
| 要管理员 | 多数包要 | 视包而定 | **默认不要**（装进自己家目录） |
| 包格式 | NuGet `.nupkg` 内含 **PowerShell 脚本**包装 installer/exe/zip | GitHub 上 **YAML manifest** 指向官方 installer URL+哈希 | **JSON manifest**（多指向便携 zip / 官方免安装包） |
| 源 | 社区源 `community.chocolatey.org` | 默认 `winget`([winget-pkgs](https://github.com/microsoft/winget-pkgs)) + `msstore` | **buckets**（`main`/`extras`/… 均为 git 仓库） |
| 装什么 | installer、绿色 zip、纯脚本动作都行 | 主要"拉官方 installer 静默装" | 偏 **CLI 工具 / 绿色软件**（GUI 大件较少） |
| 卸载/回滚 | 靠自身 DB | 靠自身 DB | 删目录即净卸；多版本可并存切换 |
| 声明式 | `packages.config` 批量装 | **Configuration**（DSC `*.dsc.yaml`，装软件+配系统合一，[docs](https://learn.microsoft.com/en-us/windows/package-manager/configuration/)） | `scoop export`/`import` 导出装机清单 |

官方定义（均官方原文核实）：

- **Chocolatey**：*"software management automation for Windows that wraps installers, executables, zips, and scripts into compiled packages"* —— 关键词 **wraps … into compiled packages**（PowerShell 驱动）。见 [docs.chocolatey.org](https://docs.chocolatey.org/en-us/)。
- **winget**：*"a comprehensive package manager solution that consists of a command line tool and set of services"*。见 [learn.microsoft.com/windows/package-manager](https://learn.microsoft.com/en-us/windows/package-manager/)。
- **Scoop**：把 Scoop 自己也用 `irm get.scoop.sh | iex` 一行装（PowerShell 版 `curl|sh`，见第七节）。

常用命令（三家横向对照）：

```powershell
# 搜索 / 安装 / 升级 / 卸载 / 列已装
choco search <pkg>    ;  winget search <pkg>   ;  scoop search <pkg>
choco install <pkg> -y   ;  winget install <pkg>  ;  scoop install <pkg>
choco upgrade <pkg> -y   ;  winget upgrade <pkg>  ;  scoop update <pkg>   # scoop update * = 全部
choco uninstall <pkg> -y ;  winget uninstall <pkg>;  scoop uninstall <pkg>
choco list --local-only  ;  winget list          ;  scoop list
```

**关键区别与坑**：

- **谁维护**：winget 微软官方、系统自带、manifest 直指官方下载；choco 覆盖面/历史最广、脚本最灵活但社区源信任要自己掂量；Scoop 便携、免管理员、对 CLI 工具最省心。
- **多套 DB 互不相认**：choco / winget / scoop 各记各的安装数据库，同一软件别跨家混装，卸载会对不上。
- **隔离程度**：choco/winget 装完是全局已安装程序、不能原子回滚；Scoop 装进 `~/scoop/`、删目录即净卸、能多版本并存——但仍不是 Nix 式内容寻址隔离。

---

## 五、语言级：npm / pip(PyPI)（+ cargo/gem/nuget 简表）

语言级包管理器**只管本语言的库**，且大多支持"项目本地隔离 + 多版本共存"——这是它们跟系统级 apt 最根本的差异。

### npm（Node.js）

- **中心 registry** `registry.npmjs.org`，按名字下载。
- **项目本地** `node_modules/` + 全局 `-g`；`package.json` 声明依赖、`package-lock.json` 锁定精确版本树（[docs](https://docs.npmjs.com/cli/v10/configuring-npm/package-lock-json)）。
- **允许依赖树里多版本共存**：A 依赖 `lodash@3`、B 依赖 `lodash@4`，npm 靠嵌套/去重让两份并存——这正是 apt 全局单版本**做不到**的事，是"语言级隔离"的典型。
- 变体：**pnpm**（全局 content-addressable store + 项目内 `node_modules/.pnpm` 虚拟 store，硬链接省磁盘、符号链接防幽灵依赖，详见表下说明）、**yarn**。
- 常用：`npm install` / `npm install -g <pkg>` / `npm update` / `npm uninstall` / `npx <pkg>`（临时跑不留全局）。

**npm / pnpm / yarn / bun 四家对照**（都读 `package.json`、都连 npm registry，差别在装法与速度）：

| | **npm** | **pnpm** | **yarn** | **bun** |
| --- | --- | --- | --- | --- |
| 出身 | Node 官方自带 | 第三方（[pnpm.io](https://pnpm.io/)） | Meta 起（Yarn Berry v2+） | Bun 运行时自带（[bun.sh](https://bun.sh/)） |
| `node_modules` 布局 | 扁平化提升、可能重复且有幽灵依赖 | **顶层全是符号链接 → `node_modules/.pnpm/` 虚拟 store**（内容再硬链到全局 CAS），无幽灵依赖 | Berry 默认 PnP（无 `node_modules`、`.pnp.cjs` 索引）；v1/可选是扁平 | 扁平、兼容 npm 布局 |
| lockfile | `package-lock.json` | `pnpm-lock.yaml` | `yarn.lock` | `bun.lock`(文本, 1.2+ 默认) / 旧 `bun.lockb`(二进制) |
| 速度 | 基准 | 快、省盘 | 快（PnP 更快） | **最快**（Zig 写，含自带 runtime/打包/测试） |
| 定位 | 稳、无脑兼容 | monorepo/省盘首选 | 大厂/PnP 生态 | 一体化工具链，追新 |

- **pnpm 的两层结构**（用户常问的"那个特殊目录"）：全局有一个 **content-addressable store**（CAS，默认 `~/.local/share/pnpm/store`），同一版本的文件全机器只存一份；项目里 `node_modules/.pnpm/` 是**虚拟 store**，每个依赖摊平放在 `.pnpm/<name>@<version>/node_modules/<name>`（文件从全局 CAS **硬链接**过来，不占额外空间）；项目顶层 `node_modules/` 里只有**符号链接**指向 `.pnpm/` 中对应目录——**只有 `package.json` 里声明过的依赖才在顶层可见**，所以能挡住"用了没声明的包"（幽灵依赖 / phantom dependency）。这正是 pnpm 既省盘（硬链）又严格（符号链接隔离）的来源，官方图解见 [pnpm.io/symlinked-node-modules-structure](https://pnpm.io/symlinked-node-modules-structure) 与 [pnpm.io/motivation](https://pnpm.io/motivation)。
- 四家的库都来自同一个 `registry.npmjs.org`，**换的是客户端不是源**；`package.json` 通用，切换成本主要在 lockfile 与 `node_modules` 策略。
- `corepack`（Node 自带）能按项目 `package.json` 的 `"packageManager"` 字段自动切到对应的 pnpm/yarn 版本，避免"本机装的版本和项目要求不一致"。

**bun 为何两极分化**（追新者力捧、生产派谨慎——快速迭代中，早期批评不少已过时，评价要看版本/日期）：

- **爱它的理由（真实优势）**：① `bun install` 官方基准比 npm 快 ~25–30×、比 yarn ~18×（[v1.0](https://bun.sh/blog/bun-v1.0)/[v1.1 博客](https://bun.sh/blog/bun-v1.1)，注：跑分带 `--ignore-scripts`、有缓存，冷装差距会缩小，但装包快这点外部验证较多）；② **一体化**——一个二进制顶替 node + npm/yarn/pnpm + esbuild/webpack + jest/vitest，原生跑 TS/JSX、ESM/CJS 混用、`.env` 开箱即用，省掉大半工具链配置；③ 启动比 Node 快 ~4×，脚本/测试循环体感好。
- **不信任它的理由（争议点，标注是否仍成立）**：
  - **Node 兼容性仍有坑**（🟡 **仍成立、持续改善**）：`async_hooks`/`cluster`/`worker_threads` 等部分实现；用 V8 C++ API 的原生扩展（node-canvas 等）不保证能跑；`node:v8` 序列化用 JSC wire format 而非 V8 格式（跨进程行为差异）。官方 [Node 兼容文档](https://bun.sh/docs/runtime/nodejs-compat)、[v1.2 博客](https://bun.sh/blog/bun-v1.2)。
  - **Windows 迟到 ~2.5 年**（✅ **已修复**）：2021-10 建 issue、直到 2024-04 的 [v1.1](https://bun.sh/blog/bun-v1.1) 才原生支持 Windows（此前只能 WSL）——是早期 Linux-first 的历史印记（[oven-sh/bun#43](https://github.com/oven-sh/bun/issues/43)）。
  - **生产内存/崩溃**（🟡 **部分仍成立**）：容器里从 Node 迁到 Bun 后内存飙到 OOM 的报告（[#17723](https://github.com/oven-sh/bun/issues/17723)，2025-02 至今仍开放）；根因之一是 JSC 的 GC 定时器没跟事件循环集成、Linux 上 GC 信号 `SIGUSR1` 撞用户程序，均在 [v1.2.2](https://bun.sh/blog/bun-v1.2.2) 修（空闲内存降 10–30%），但迁移前仍需实测。
  - **`bun.lockb` 二进制 lockfile**（✅ **已修复**）：早期用不可 diff/review 的二进制锁，PR 看不到依赖变更、Dependabot 两年不支持（[dependabot#6528](https://github.com/dependabot/dependabot-core/issues/6528)，577👍，2023-01→2025-02）；[v1.2](https://bun.sh/blog/bun-v1.2)（2025-01）起新项目默认改文本 `bun.lock`（旧项目要主动迁移）。
  - **JSC ≠ V8**（🟡 **根本性、长期存在**）：Bun 用 JavaScriptCore（Safari 引擎）、Node 用 V8（Chrome 引擎），GC 策略与值表示根本不同，V8 C++ API 要 Bun 自己仿一层"假 V8"，注定补不全。
  - **成熟度/社区**（🟡 **仍成立**）：v1.0 到 2023-09 才发布、团队约 14 人（[Roadmap#159](https://github.com/oven-sh/bun/issues/159)），生产验证时间远短于 Node 十余年积累；官方跑分多为自测、运行时数据独立复现有限。
  - **背景变化：2025-12-02 Anthropic 收购 Bun**（[官方公告](https://www.anthropic.com/news/anthropic-acquires-bun-as-claude-code-reaches-usd1b-milestone)，随 Claude Code 达 $1B 里程碑；HN 2192pt）——Bun 团队并入 Anthropic、作为 Claude Code 的打包/运行基座。此前"小团队、前途未卜"的顾虑因此缓解；但 JSC≠V8、Node 兼容等**技术性**差异不受收购影响、依旧成立。
- **中肯定位**：**开发环境**的极速 npm 替代 + TS 脚本 runner 已经很能打；**核心生产服务**建议先小规模灰度、盯版本，别仓促全量迁移。（时间线核对至 2026-07，bun 迭代快，用前请复核最新版本文档。）

### pip（Python / PyPI）

- **中心 registry** `pypi.org`；包两种形态：**wheel**（`.whl`，预编译二进制，装得快）vs **sdist**（源码 tar，装时可能要编译）。见 [pip.pypa.io](https://pip.pypa.io/en/stable/)。
- **隔离靠 venv**（虚拟环境），不是 pip 自带的多版本机制——同一 venv 内仍是每个包单版本。
- **无原生 lockfile**：`requirements.txt` 是清单不是锁（`pip freeze` 能钉死版本当近似锁）；真 lock 由现代工具给：**uv**、**poetry**、**pdm**、**pip-tools**。
- **PEP 668 坑（externally-managed-environment）**：Debian/Ubuntu 给系统 Python 打了 `EXTERNALLY-MANAGED` 标记，`pip install` 直接**拒绝**装进系统解释器（否则会和 apt 装的 python 包打架）。见 [PEP 668](https://peps.python.org/pep-0668/)。
  - 正解：用 `venv` / `uv venv` 起隔离环境，或 `uv run --with <pkg>`、`pipx` 装 CLI；**别** `--break-system-packages` 硬闯（会与系统包冲突）。本仓统一走 `uv`（见第六节与顶层 AGENTS 规则）。

### 其他语言级（一句话 + 命令）

| 生态 | registry | 清单 / lock | 装法 | 备注 |
| --- | --- | --- | --- | --- |
| Rust `cargo` | crates.io | `Cargo.toml` / `Cargo.lock` | `cargo install <bin>` / `cargo add` | 从源码编，[doc](https://doc.rust-lang.org/cargo/) |
| Go `go` | **无中心仓库** | `go.mod` / `go.sum` | `go install pkg@ver` | import 路径即源码地址，详见 [go.md](go.md) |
| Ruby `gem`/bundler | rubygems.org | `Gemfile` / `Gemfile.lock` | `gem install` / `bundle` | |
| .NET `nuget` | nuget.org | `.csproj` / `packages.lock.json` | `dotnet add package` | choco 底层复用其包格式 |
| C++ `vcpkg` | 无中心（端口树） | `vcpkg.json` manifest | `vcpkg install <x>` | 微软，多从源码编，[doc](https://learn.microsoft.com/en-us/vcpkg/) |
| C++ `Conan` | ConanCenter + 可自建 | `conanfile.txt/py` / `conan.lock` | `conan install .` | 去中心、可存**预编译二进制**，[conan.io](https://conan.io/) |
| PHP `composer` | packagist.org | `composer.json` / `composer.lock` | `composer require <x>` | |
| Java `maven`/`gradle` | Maven Central | `pom.xml` / `build.gradle` | `mvn`/`gradle` 声明依赖 | |

---

## 六、跨语言环境 & 版本管理器：conda / pixi / uv、asdf / mise

**（A）环境管理器**——介于"语言级"和"系统级"之间，给**项目**搭一整套隔离、可复现的工具链，且能带非 Python 的原生依赖（C 库、CUDA、甚至 `go`、`nodejs`）。

- **conda**：多语言、装的是**预编译二进制**，源是 channel（`conda-forge` / `defaults`）。经典痛点是 solver 慢 → 换 **libmamba** 求解器或直接用 **mamba**（C++ 重写、更快）。见 [docs.conda.io](https://docs.conda.io/)。
- **pixi**：conda-forge 生态的**现代前端**（Rust 写、快），`pixi.toml` + `pixi.lock`，项目级 + `pixi global`。见 [pixi.sh](https://pixi.sh/)。
- **uv**：Astral 出品，Python 专用、极快，一把管 venv / 依赖 / lock / Python 版本。见 [docs.astral.sh/uv](https://docs.astral.sh/uv/)。

> 本仓约定的 Python 环境优先级：**Pixi > uv > python/python3**（见顶层 AGENTS.md）。两条相关坑：① `conda base` 常年激活会污染 `PATH`、conda 与 pip 在同环境混装易冲突（先 conda 后 pip、别反复横跳）；② `pixi global install go` 装的 go 有 cgo 编译器坑（`DefaultCC` 被烧进二进制），判别与修法见 [go.md](go.md) 第三节。

**（B）版本管理器**——不装"库"，只管**同一门语言的多个版本**并按目录/项目切换：

- **单语言**：`nvm`(Node)、`pyenv`(Python)、`rbenv`(Ruby)、`fnm`(Node，Rust 写更快)——各管一门。
- **多语言合一**：**`asdf`**（插件式，一个工具管 node/python/ruby/… 多版本，`.tool-versions` 声明，[asdf-vm.com](https://asdf-vm.com/)）、**`mise`**（Rust 写、更快、兼容 asdf 插件，还能管**环境变量 + task runner**，`mise.toml`/`.tool-versions`，[mise.jdx.dev](https://mise.jdx.dev/)）。
- **和包管理器的关系**：版本管理器负责"用哪个版本的 node/python"，包管理器（pnpm/pip）负责"这个版本下装哪些库"——两层正交、常配合用（`mise use node@22` 定运行时 → `pnpm install` 装依赖）。conda/pixi/uv 有部分重叠（它们也能定 Python 版本），所以 Python 圈常直接用 uv/pixi 一把梭，不再单独上 pyenv。

---

## 七、绕过包管理器的安装：`curl | sh` 与 `irm | iex`

不是所有软件都进包管理器。很多工具的官方安装方式是**下载一段脚本直接执行**——这是一整类"装软件的方式"，跟包管理器并列：

```bash
# Linux / macOS：下载脚本管道给 shell 执行
curl -fsSL https://sh.rustup.rs | sh          # rustup
curl -LsSf https://astral.sh/uv/install.sh | sh   # uv
# 常见还有 Homebrew、nvm、ollama、starship… 都用这个模式
```

```powershell
# Windows PowerShell：等价物 —— irm 下载、iex 执行
irm get.scoop.sh | iex                        # 装 Scoop（第四节）
irm https://…/install.ps1 | iex
irm https://…/install.ps1 -OutFile a.ps1      # 或先落地再跑（能先审阅）
```

- **`irm` = `Invoke-RestMethod`**（发 HTTP 请求、把响应体拿回来）；**`iex` = `Invoke-Expression`**（把拿到的字符串当 PowerShell 代码执行）。`irm <url> | iex` 就是 **PowerShell 版的 `curl <url> | sh`**——语义完全对应：下载一段远程脚本，直接喂给解释器跑。
- **本质与风险**：这等于"**执行一段没审计过的远程代码**"。方便（一行装好、不依赖任何包管理器、跨发行版），代价是**信任完全押在那个 URL 和它的 TLS 上**——域名被劫持/中间人/脚本被改，就是在你机器上跑任意代码。对不熟的来源，稳妥做法是**先下载到文件、看一眼、再执行**（`-OutFile` / `curl -o`）。
- **和包管理器的取舍**：包管理器给你**版本记录、可升级、可卸载、可复现**；`curl|sh`/`irm|iex` 给你**当下最快**，但装完这东西不在任何包数据库里，升级/卸载得靠它自己的机制。工具能进 winget/scoop/brew/apt 就优先走包管理器，进不了或要最新版才用脚本直装。
- **easytier / mihomo** 等本仓工具的 Windows 安装就用 `irm … -OutFile`（见 `network` skill 相关 reference）。

---

## 八、把包管理器当"跨平台二进制安装器"：壳包 + 平台子包（三大 coding agent 实测）

前七节的"包"多是某语言的库。但有一类工具反过来——**它本体是预编译原生二进制（Rust/Zig/Go/Bun 编译产物），却借 npm（或 Homebrew/winget）当跨平台安装器**。此时 npm 不是"运行时依赖管理器"，而是被当成"最普及、且自带 os/cpu/libc 分发能力的下载器"。esbuild、swc、@biomejs/biome、turbo 都是这个模式；OpenAI Codex、Claude Code、GitHub Copilot CLI 三个 coding agent 也是——所以"npm 包只是个壳"这个直觉是对的。

### 机制：几 KB 的壳 + 一组平台专属 `optionalDependencies`

- 主包（`npm i -g` 装的那个）只是 **launcher 壳**，几 KB~百 KB，`dependencies` 基本为空。
- 它挂一组 **`optionalDependencies`**，每个子包用 `os`/`cpu`/`libc` 字段标平台；npm 安装时**只有匹配当前平台的那个子包会被下载**（不匹配的 optional 依赖装失败也不报错，这正是 optional 的用途），几百 MB 的原生二进制在子包里。壳的 `bin` 启动时把执行转交给本地那个平台二进制。

registry 实测（`npm view`，codex 0.142.4 / claude-code 2.1.195 / copilot 1.0.65）：

| | 壳包 `bin` | 壳包体积 | 平台二进制子包（linux-x64） | 子包分发形态 |
| --- | --- | --- | --- | --- |
| `@openai/codex` | `bin/codex.js` | **9.5 KB** | `@openai/codex@<ver>-linux-x64`，**279 MB** | 同名包的**版本变体**，`optionalDependencies` 里用 npm alias 引 |
| `@anthropic-ai/claude-code` | `bin/claude.exe` | 154 KB | `@anthropic-ai/claude-code-linux-x64`，**245 MB** | 独立命名子包 |
| `@github/copilot` | `npm-loader.js` | 12.7 KB | `@github/copilot-linux-x64`，**276 MB** | 独立命名子包（另依赖 `detect-libc`） |

- **最硬的证据是 `libc` 分叉**：三家都为 Linux 同时发 `glibc` 与 `musl` 两套子包（`…-linux-x64` vs `…-linux-x64-musl` / `…-linuxmusl-x64`，实测 `libc=["glibc"]` vs `libc=["musl"]`）。纯 JS 到处能跑、根本不必区分 C 运行时；**专门为 musl 单独发一份，只可能是嵌了原生运行时的二进制**。壳 ~10 KB vs 子包 ~250–280 MB 的体量差也印证这点。
- codex 核心是 **Rust**（Release 产物名 `codex-x86_64-unknown-linux-musl` 是 Rust target triple）。claude-code 的壳 `bin` 在所有平台都叫 `claude.exe`——这是 **Bun `--compile` 单文件可执行**的命名印记。（不确定项：copilot 具体用 Bun 还是 Node SEA 未逐一验证，但"壳 + 平台原生子包"结构一致。）

### 三大 coding agent 安装方案全景（官方 README 实测）

厂商现在**主推 curl 脚本 / Homebrew / winget 直接拉原生二进制**，npm 降为兜底：

| | curl 脚本（首推） | Homebrew | winget | npm（兜底） |
| --- | --- | --- | --- | --- |
| **Codex** | `curl -fsSL https://chatgpt.com/codex/install.sh \| sh`（Win：`irm https://chatgpt.com/codex/install.ps1\|iex`） | `brew install --cask codex` | — | `npm i -g @openai/codex` |
| **Claude Code** | `curl -fsSL https://claude.ai/install.sh \| bash`（Win：`irm https://claude.ai/install.ps1\|iex`） | `brew install --cask claude-code` | `winget install Anthropic.ClaudeCode` | `npm i -g @anthropic-ai/claude-code`（**README 标 deprecated**） |
| **Copilot CLI** | `curl -fsSL https://gh.io/copilot-install \| bash`（支持 `PREFIX`/`VERSION` 环境变量） | `brew install copilot-cli` | `winget install GitHub.Copilot` | `npm i -g @github/copilot` |

三家也都在 GitHub Releases 直挂各平台二进制供手动下载。

- **"软弃用（soft deprecation）"**：Claude Code 的 README 原文 *"Installation via npm is deprecated"*，但这是**文档层引导**——registry 上并**没有**打 deprecated 标记（实测 `npm view @anthropic-ai/claude-code deprecated` 为空），npm 包照常发布、`npm i -g` 照装照用、无警告。目的是引导迁移又不砸掉存量的海量教程/CI 脚本（它 npm 周下载量仍上千万）。
- **与第七节的关系**：第七节的一般建议是"能进包管理器就优先走包管理器、少用 `curl|sh`"。这里看似相反、其实是它的**边界情形**：当工具本身就是**自带更新机制的自包含原生二进制**时，厂商反而更推 curl 脚本/brew（一步到位、还不用先装 Node），npm 退化成"给 Node 用户的兼容入口"。
- **因果链（解一个常见困惑："既然 Bun 编译成单文件、为何又弃用 npm"）**：正因为用 Bun `--compile` 把它编成**不依赖 Node 的自包含单文件**，才**有底气**砍掉 Node 专属的 npm 渠道——单文件化是因、弱化 npm 渠道是果，二者顺承不矛盾。"Bun"在这里身兼两角：`bun build`（**打包器**：多文件 TS → 单个 JS）与 `bun build --compile`（**编译器**：把那段 JS 连同 Bun 运行时塞进一个原生可执行文件）；npm 自始至终只是"快递盒"、不是发动机。旁证：2026-03 Claude Code 源码"泄露"正是 npm 包误附了 source map、把内嵌 JS 还原出来（[复盘](https://alex000kim.com/posts/2026-03-31-claude-code-source-leak/)）——**外壳原生 + 芯子 JS** 本就并存，不矛盾。

### 采用度 / 社区风向（客观数据，2026-07）

npm registry 周下载量（`api.npmjs.org/downloads`，**带系统性偏差**，见下）：

| 客户端 | 周下载量 | | coding agent | 周下载量 |
| --- | --- | --- | --- | --- |
| **pnpm** | ~114 M | | `@openai/codex` | ~13.4 M |
| npm | ~14.9 M | | `@anthropic-ai/claude-code` | ~10.8 M |
| yarn | ~9.2 M | | `@github/copilot` | ~0.92 M |
| bun | ~2.7 M | | | |

- **偏差提醒（别直接拿绝对值比高低）**：`npm` 随 Node 自带、`bun` 主要靠官方脚本/brew 装 → 二者 registry 下载量**严重低估**真实使用；`pnpm/yarn` 更依赖从 registry 装（尤其 CI）→ 偏高。看**趋势**（pnpm 强势领先、yarn 明显掉队）可信，绝对值别当真。这条正好佐证第五节对 yarn"掉队"、bun"追新"的定性。
- Hacker News 风向：pnpm 口碑正面（`disk space efficient`、防供应链攻击的新设置）、bun 高热看好（v1.0、Zig runtime）、yarn 几无独立高热帖（话题多是"从 yarn 迁到 pnpm"）；另一类高赞是对 node/npm 依赖链复杂度的疲劳吐槽（`Why does every package+module system become a Rube Goldberg machine`）——这正是这些 agent 转原生二进制的动因之一。

---

## 九、"想干嘛 × 各家"命令速查

**系统级**（同一动作横向对照）：

| 动作 | apt | dnf | pacman | brew | choco | winget | nix profile (flakes) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 搜索 | `apt search` | `dnf search` | `pacman -Ss` | `brew search` | `choco search` | `winget search` | `nix search nixpkgs <x>` |
| 安装 | `apt install` | `dnf install` | `pacman -S` | `brew install` | `choco install -y` | `winget install` | `nix profile install nixpkgs#<x>` |
| 卸载 | `apt remove` | `dnf remove` | `pacman -R` | `brew uninstall` | `choco uninstall -y` | `winget uninstall` | `nix profile remove <x>` |
| 升级全部 | `apt upgrade` | `dnf upgrade` | `pacman -Syu` | `brew upgrade` | `choco upgrade all -y` | `winget upgrade --all` | `nix profile upgrade` |
| 列已装 | `apt list --installed` | `dnf list installed` | `pacman -Q` | `brew list` | `choco list` | `winget list` | `nix profile list` |
| 临时用一下 | —（得真装） | — | — | — | — | — | `nix shell nixpkgs#<x>` |
| 回滚 | ≈没有 | `dnf history undo` | 有限 | — | — | — | `nix profile rollback` |

**语言级**：

| 动作 | pip | npm | cargo | go |
| --- | --- | --- | --- | --- |
| 装依赖 | `pip install <x>` | `npm install <x>` | `cargo add <x>` | `go get <x>` |
| 装 CLI 工具 | `pipx install <x>` / `uv tool install` | `npm install -g <x>` | `cargo install <x>` | `go install <x>@latest` |
| 临时跑 | `uvx <x>` | `npx <x>` | — | `go run <x>@latest` |
| 锁定 | `uv lock` / `pip freeze` | 自动 `package-lock.json` | 自动 `Cargo.lock` | `go.sum`（MVS 天然确定） |

---

## 十、踩坑合集（紧贴主题）

- **PEP 668**：`pip install` 报 `externally-managed-environment` = 系统 Python 被 apt 保护，别硬装。用 `uv venv` / `venv` / `pipx`（详见第五节）。
- **npm 全局 vs 项目本地**：CLI 工具用 `-g` 或 `npx`；库依赖留在项目 `node_modules`。`node_modules` 体积大是常态，pnpm 用硬链接大幅省盘。
- **Nix 非 FHS 二进制**：自己下载的预编译 ELF 在 NixOS/纯 Nix 环境跑不起来（找不到 `ld-linux`），要 `patchelf`/`steam-run`/`nix-ld`。
- **choco 与 winget 混装**：两套安装数据库互不相认，同一软件别两家都装，卸载会对不上。choco 多数操作要管理员 shell。
- **conda + pip 混装**：同环境里 conda 装一部分、pip 装一部分容易依赖打架；能统一走一个就别混，或让 pip 只在 conda 环境末尾补装。
- **Homebrew on Linux**：装在 `/home/linuxbrew/.linuxbrew`（或 `~/.linuxbrew`），是**用户级、不需 root**的补充，别指望它替代 apt 管系统底层库。
- **"发布"动作因生态而异**：npm=`npm publish`、cargo=`cargo publish`、PyPI=`twine upload`、Go=推一个 git tag（不上传产物）。这些是对外发布，按 AGENTS 规则须用户单独确认，别顺手执行。
