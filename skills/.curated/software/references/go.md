# Go 工具链：模块、`go install`、依赖解析

面向"用过 pip / npm、第一次认真看 Go 怎么装工具、怎么拉依赖"的人。核心反直觉点：**Go 没有 PyPI / npm 那样的中央包索引**——包的"名字"本身就是"去哪找它"的地址。下面的说法据 Go 官方 [模块参考 `go.dev/ref/mod`](https://go.dev/ref/mod) 与本机 `go help <topic>`（`go1.26.3`）。

## 心智模型：导入路径 = 仓库地址（去中心化）

- **模块（module）** 是一起发布、版本化、分发的一组包；根目录有个 `go.mod` 声明**模块路径**（module path）。**包路径** = 模块路径 + 模块内子目录。例：模块 `golang.org/x/net`，其 `html/` 子目录的包路径是 `golang.org/x/net/html`（[ref/mod](https://go.dev/ref/mod)）。
- **模块路径既描述"是什么"又描述"在哪找"**：通常 = 仓库根路径（+ 可选子目录 + major ≥ 2 的版本后缀）。所以 `github.com/user/proj` 这个名字**直接告诉工具链去 `github.com/user/proj` 这个仓库拉**——没有中间的"拿包名去中央索引查位置"这一步。
- 对照 **PyPI**：中央 index，`pip install requests` 按**名字**查索引再下预编译 wheel/sdist，发布要 `twine upload` 传产物（名字 ≠ 位置）。Go 里 **push 一个 git tag 就等于发布**，从不"上传"到某个索引。

## `go install`：装一个命令行工具

`go install <包路径>@<版本>` 编译并把可执行文件装到 **`GOBIN`**（默认 `$GOPATH/bin`，`GOPATH` 默认 `~/go`）（`go help install`）：

```bash
go install codeberg.org/git-pages/git-pages@latest   # 装最新
go install example.com/cmd/tool@v1.4.0               # 装指定版本
```

带 `@version` 后缀时的关键语义（`go help install`）：

- **忽略当前目录及任何父目录的 `go.mod`**，在 module-aware 模式下独立解析——所以**装工具不会污染你当前项目的依赖**。
- 参数必须指向 **main 包**（能产出可执行文件），且同一次调用里所有参数同模块、同版本。
- 不使用 vendor 目录。

无 `@version`（如 `go install ./...`）时才在"当前主模块"上下文里跑。**Go 1.16 起**约定变了：`go get` 不再负责装二进制、也不再默认改依赖；**装工具统一用 `go install pkg@version`**，`go get` 现在只管 `go.mod` 里的依赖增删。

## 从导入路径怎么找到仓库（解析机制）

工具链拿到一个非标准库导入路径后，按下面顺序定位源码（`go help importpath`）：

1. **已知代码托管站**有内建规则，直接推导仓库：`github.com/…`、`bitbucket.org/…`、`hub.jazz.net/git/…`、`launchpad.net/…` 等。
2. **显式带 VCS 后缀**：`example.org/repo.git/foo/bar` 明确表示"`example.org/repo` 这个 Git 仓库的 `foo/bar` 目录"（支持 `.git` / `.hg` / `.bzr` / `.svn` / `.fossil`）。
3. **自定义域名（vanity import path）**：既不是已知站、又没 VCS 后缀时，工具链对 `https://<路径>?go-get=1` 发一个 HTTP GET，在返回 HTML 的 `<head>` 里找一个 `<meta>` 标签：

   ```html
   <meta name="go-import" content="import-prefix vcs repo-root">
   ```

   例：拉 `example.org/pkg/foo` → 请求 `https://example.org/pkg/foo?go-get=1` → 若含 `<meta name="go-import" content="example.org git https://code.org/r/p/exproj">`，工具链会**再验证** `https://example.org/?go-get=1`（prefix）也有同样 tag，然后从 Git 仓库 `https://code.org/r/p/exproj` 拉代码。这就是 `golang.org/x/...` 这类"体面导入路径"能重定向到实际托管地的原理。
   - **Go 1.25+** 认第 4 段 `subdir`（`content="prefix vcs repo-root subdir"`），允许模块根在仓库的子目录里；此时 VCS tag 要带 `subdir/` 前缀（如 `subdir/v1.2.3`）。
   - `vcs` 取 `mod`（`content="example.org mod https://code.org/moduleproxy"`）表示"这些路径走这个**模块代理**取"，优先于 VCS 方式。
4. **import path checking**：源码里 `package foo // import "canonical/path"` 这种 import comment 会强制只能用规范路径引用；模块模式下它已被 `go.mod` 的 `module` 声明取代、不再检查。

> 一句话回答"go install 是读特定文件还是有中央平台"：**都不是**——它把**导入路径当成 URL**去 VCS（或经代理）取源码，`proxy.golang.org` 只是挡在前面的缓存/校验层，不是你发布的目标索引。

## 版本：语义化 + 最小版本选择

- 版本形如 `v1.12.3`，遵循 [SemVer 2.0](https://semver.org/spec/v2.0.0.html)：major 破坏兼容、minor 加功能、patch 修 bug；可带预发布后缀 `-rc.1` 或构建元数据 `+meta`（[ref/mod](https://go.dev/ref/mod)）。
- **major ≥ 2 必须在模块路径尾部带 `/vN` 后缀**（`example.com/mod/v2`）——同一仓库的不同大版本被当**不同模块**、可在一次构建里共存。这是 Go 特有的 "semantic import versioning"。
- **伪版本（pseudo-version）**：给没打 tag 的具体 commit 用，形如 `v0.0.0-20260627181231-7d0c66d223ab`（`vX.Y.Z-<UTC时间戳>-<12位commit>`；前缀依"最近的 tag"分三种变体）。
- **MVS（最小版本选择，Minimal Version Selection）**：构建时 Go 选"能同时满足所有 `require` 的**最低**版本"，而不是自动取最新——依赖因此可复现、可预测（和 npm/pip 倾向解析到最新兼容版不同）（[ref/mod](https://go.dev/ref/mod#minimal-version-selection)）。

## `go.mod` / `go.sum` / 模块缓存

- **`go.mod`**：`module` 声明本模块路径、`go` 指定语言版本、`require` / `replace` / `exclude` 管依赖。
- **`go.sum`**：记录每个依赖版本的**加密校验和**（模块内容、`go.mod` 各一条），拉取时逐条比对防被偷换。它不是 lockfile（版本锁在 `require` + MVS 里），而是完整性清单。
- 下载的模块解包进**模块缓存** `$GOPATH/pkg/mod`（只读、跨项目共享）。

## 代理与校验数据库：GOPROXY / GOSUMDB / GOPRIVATE

本机默认（`go env`）：`GOPROXY=https://proxy.golang.org,direct`、`GOSUMDB=sum.golang.org`。

- **GOPROXY**：模块代理就是"任何能响应特定 GET 请求的 web 服务"，连 `file:///` 都行（`go help goproxy`）。默认先走公共镜像 `proxy.golang.org`，取不到再 `direct`（回落到直接 VCS clone）；设 `off` 则禁止联网取模块。国内常改 `https://goproxy.cn,direct` 之类加速。
- **GOSUMDB**：公共校验和数据库 `sum.golang.org`，第一次见到某模块版本时用它交叉核验校验和（防上游事后篡改 tag 内容）。
- **私有模块**（`go help private`）：`GOPRIVATE=*.corp.example.com,rsc.io/private`（`path.Match` glob 前缀列表）把匹配的模块标记为私有——**不走公共代理、不查公共 sumdb**（直接 VCS 拉、只信本地 `go.sum`）。更细粒度用 `GONOPROXY` / `GONOSUMDB` 分别覆盖"是否走代理""是否查 sumdb"。

## 一句话对照

| | Go modules | PyPI (pip) | npm |
|---|---|---|---|
| 包索引 | **无中央索引**，导入路径即仓库地址 | 中央 index（名字 ≠ 位置）| 中央 registry |
| 发布 | push git tag | `twine upload` 传产物 | `npm publish` |
| 装工具 | `go install pkg@ver` | `pipx install` | `npm i -g` |
| 版本选择 | MVS（取最低可行）| 解析器（倾向最新兼容）| 语义范围 + lockfile |
| 完整性 | `go.sum` + `sum.golang.org` | hash（可选）| `package-lock` + registry |
| 大版本共存 | `/vN` 路径后缀，可共存 | 不可 | 不可 |
