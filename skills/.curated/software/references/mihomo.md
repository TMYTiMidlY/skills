# Mihomo / Clash 内核（Windows）

Mihomo 是 Clash Meta 的 Go 内核。Dashboard/API 只是控制面，代理监听、DNS、规则匹配、TUN、协议 outbound 等后端逻辑都在同一个 Go 可执行文件里。

## 默认配置位置

Mihomo 默认从用户配置目录读取 `config.yaml`。Windows 当前用户下常用路径：

- `%USERPROFILE%\.config\mihomo\config.yaml`：默认运行配置。这个目录在 mihomo 的安全路径内，REST API 可以用 `path` 方式热重载。
- `%USERPROFILE%\mihomo`：mihomo 源码仓库，当前可切到 release tag 构建；`mihomo.exe` 放在这里用于运行/验证。

检查版本：

```powershell
cd "$env:USERPROFILE\mihomo"
.\mihomo.exe -v
```

默认配置启动：

```powershell
cd "$env:USERPROFILE\mihomo"
.\mihomo.exe
```

显式指定配置目录：

```powershell
cd "$env:USERPROFILE\mihomo"
.\mihomo.exe -d "$env:USERPROFILE\.config\mihomo"
```

校验默认配置：

```powershell
cd "$env:USERPROFILE\mihomo"
.\mihomo.exe -t -d "$env:USERPROFILE\.config\mihomo"
```

## REST API 运行态排障

当前配置使用：

```yaml
external-controller: 127.0.0.1:9090
secret: ''
```

常用检查：

```powershell
curl.exe http://127.0.0.1:9090/configs
curl.exe http://127.0.0.1:9090/proxies
curl.exe http://127.0.0.1:9090/connections
curl.exe --max-time 3 "http://127.0.0.1:9090/logs?format=structured&level=info"
curl.exe --max-time 3 http://127.0.0.1:9090/traffic
```

`/configs` 只展示运行态通用配置，不展示当前配置文件路径。核对加载是否正确时，结合 `/configs` 的 TUN、端口、日志级别和 `/proxies` 的节点组、`testUrl`、当前选择一起看。

用安全路径内的默认配置热重载：

```powershell
$body = @{ path = "$env:USERPROFILE\.config\mihomo\config.yaml" } | ConvertTo-Json -Compress
Invoke-WebRequest -Uri 'http://127.0.0.1:9090/configs?force=true' -Method Put -ContentType 'application/json' -Body $body
```

如果配置不在安全路径内，`path` 方式会报 `path is not subpath of home directory or SAFE_PATHS`。这种情况下可以临时用 `payload` 方式提交完整 YAML；日常使用应直接维护默认位置的 `.config\mihomo\config.yaml`。

CLI 默认日志输出到 stdout，不默认写日志文件。适合 AI 监控的是内置 API：`/logs?format=structured` 看结构化日志，`/traffic` 看速率，`/connections` 看连接命中规则，`/proxies` 看节点健康和选择状态。

## 切换到 release tag

构建指定 release 前先切 tag：

```powershell
cd "$env:USERPROFILE\mihomo"
git checkout v1.19.24
git describe --tags --exact-match
```

如果工作区有本地配置文件、脚本或生成物，它们会显示为 untracked；不要因为切 tag 或构建而清理这些文件，除非用户明确要求。

## 官方 workflow 的 windows-amd64 构建

GitHub Actions 里无 `v1/v2/v3` 文件名后缀的 `mihomo-windows-amd64` 对应：

- `GOOS=windows`
- `GOARCH=amd64`
- `GOAMD64=v3`
- build tag：`with_gvisor`
- 输出中间文件：默认 `mihomo.exe`
- 后处理才复制为 `mihomo-windows-amd64.exe` 并打 zip

PowerShell 复现核心 `go build`：

```powershell
cd "$env:USERPROFILE\mihomo"
$env:GOOS = "windows"
$env:GOARCH = "amd64"
$env:GOAMD64 = "v3"

go build -v -tags "with_gvisor" -trimpath -ldflags "-X 'github.com/metacubex/mihomo/constant.Version=v1.19.24' -X 'github.com/metacubex/mihomo/constant.BuildTime=$(Get-Date -Format r)' -w -s -buildid="
```

这条命令不指定 `-o`，所以会在当前目录生成或覆盖 `mihomo.exe`。如果 `mihomo.exe` 正在运行，Windows 会因为文件占用导致构建失败，需要先停掉 mihomo。

## 不覆盖 release exe 的构建

需要保留现有 `mihomo.exe` 时，显式输出到其他文件：

```powershell
cd "$env:USERPROFILE\mihomo"
$env:GOOS = "windows"
$env:GOARCH = "amd64"
$env:GOAMD64 = "v3"

go build -v -tags "with_gvisor" -trimpath -ldflags "-X 'github.com/metacubex/mihomo/constant.Version=v1.19.24' -X 'github.com/metacubex/mihomo/constant.BuildTime=$(Get-Date -Format r)' -w -s -buildid=" -o mihomo-windows-amd64.exe .
```

## zip 不是 go build 默认产物

`go build` 只生成 exe。Release 包里的 `mihomo-windows-amd64-v1.19.24.zip` 是 workflow 在构建后额外压缩出来的，逻辑相当于：

```powershell
Copy-Item .\mihomo.exe .\mihomo-windows-amd64.exe -Force
Compress-Archive -LiteralPath .\mihomo-windows-amd64.exe -DestinationPath .\mihomo-windows-amd64-v1.19.24.zip -Force
```

## 验证

构建后用：

```powershell
.\mihomo.exe -v
```

期望包含：

```text
Mihomo Meta v1.19.24 windows amd64
Use tags: with_gvisor
```
