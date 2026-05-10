---
name: mess
description: 记录排查过的疑难杂症和踩坑经历。当用户遇到类似问题、提到相关关键词、或想回顾之前解决过的问题时触发。
---

# Mess — 疑难杂症档案

记录排查过程中走过的弯路、最终定位的根因、以及解决方案。每个案例都是一次完整的排查故事，重点不是答案本身，而是**怎么找到答案的**。

遇到用户报告的问题与已有案例相似时，先回顾对应 reference，避免重复走弯路。

## 案例索引

- **VS Code Web 中文语言包 NLS 覆盖 bug** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`code serve-web`、`NLS MISSING`、`nls.messages.js`、`127.0.0.1 能用但另一个 IP 不行`（或反过来）、`workbench.js 报错`、`页面空白`、`语言包`、`Accept-Language`
- **VS Code 1.119 CLI launcher 拒绝 WebSocket upgrade（hyper 0.14→1.x 漏改 `with_upgrades`，`localhost` 直连也炸）** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`code serve-web`、`Time limit reached`、`The workbench failed to connect to the server`、`upgrade expected but low level API in use`、`websocket upgrade failed`、`hyper`、`hyper-util`、`serve_connection_with_upgrades`、`localhost 也不行`、`reverse proxy ws 卡死`、`reconnectionToken 死循环`、`1.119 vs 1.115`、`commit 8b640eef`、`commit 41dd792b`、`code-tunnel`、`pin 旧版 cli`、`Microsoft VS Code Issue #315448`、`#315003`
- **PDF.js v5.5+ 在 Chrome < 140 上崩溃 (`Uint8Array.toHex` polyfill 缺失)** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`hashOriginal.toHex is not a function`、`Uint8Array.toHex`、`pdfjs-dist`、`PDF.js v5.6.205`、`htbrowser`、`Chrome 132`、`viewer.mjs:24251`、`pdf.mjs:428`、`patchViewerUI`、`viewsManagerToggleButton`、`sidebarToggleButton`、`LaTeX-Workshop PDF 预览全白`、`merge upstream 后浏览器打不开 PDF`
- **Windows 端口绑定异常但 Win/WSL 都查不到占用，`wsl --shutdown` 后恢复** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`os error 10048`、`端口占用但 netstat 查不到`、`Get-NetTCPConnection 查不到`、`ss 查不到`、`excludedportrange 没有`、`wsl --shutdown`
- **Windows 普通 PowerShell 创建文件 symlink 失败，给用户授予 `SeCreateSymbolicLinkPrivilege` 后恢复** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`Administrator privilege required`、`mklink`、`You do not have sufficient privilege`、`SeCreateSymbolicLinkPrivilege`、`Create symbolic links`、`secedit 扩展错误`、`*SID`、`Developer Mode`、`AGENTS.md`、`CLAUDE.md`
- **公网 VPS 做 UDP 端口段转发到内网地址时，启用 `nftables.service` 影响 Caddy HTTPS/TCP 服务** → [references/bug-fix.md](references/bug-fix.md)
  - 关键词：`UDP 转发`、`端口段转发`、`DNAT`、`masquerade`、`nftables.service`、`nft flush ruleset`、`Caddy HTTPS 断了`、`gost udp://`、`11000-11009`

## Copilot CLI

- **`BASH_ENV` 注入只对非交互 bash 生效（agent 直跑命令拿不到 `GH_TOKEN`）** → [references/copilot.md](references/copilot.md)
  - 关键词：`BASH_ENV`、`.copilot.env`、`gh api user`、`错的账号`、`Copilot CLI bash 工具`、`非交互 bash`、`source .copilot.env`、`bash -c`
- **Safety Net plugin 安装后从不触发（plugin schema 是 Claude Code 格式 + marketplace plugin hook 不加载）** → [references/copilot.md](references/copilot.md)
  - 关键词：`Safety Net`、`copilot-safety-net`、`cc-safety-net`、`hooks.json`、`PreToolUse`、`preToolUse`、`matcher Bash`、`COPILOT_ALLOW_ALL`、`--allow-all-tools`、`rm -rf 没拦`、`git reset --hard 没拦`、`Loaded 1 hook(s)`、`copilot-cli#2540`、`.github/hooks/safety-net.json`
- **项目级 hook 不会向上查父目录，多 git repo 工作区里子项目漏装 Safety Net** → [references/copilot.md](references/copilot.md)
  - 关键词：`getHooksDir`、`gitRoot`、`hook 不触发`、`子项目 hook 没加载`、`monorepo`、`.github/hooks 向上查找`、`user-level hook`、`~/.copilot/config/hooks`、`direnv symlink`、`ensure_safety_net_symlinks`、`.git/info/exclude`、`direnv allow`
- **`.mcp.json` 上溯停在 git root，多 git repo 工作区里子项目看不到 workspace MCP** → [references/copilot.md](references/copilot.md)
  - 关键词：`.mcp.json`、`workspace MCP`、`copilot mcp list`、`No MCP servers configured`、`bBt`、`app.js`、`a===s`、`gitRoot`、`Source: Workspace`、`ensure_mcp_symlinks`、`.git/info/exclude`、`monorepo`、`direnv symlink`
- **`gh repo fork` 跨账号后 `git push` 用错 SSH 身份（Permission denied）** → [references/copilot.md](references/copilot.md)
  - 关键词：`gh repo fork`、`Permission to ... denied`、`错的账号 push`、`Agony5757 vs TMYTiMidlY`、`ssh-keygen -lf`、`ssh -T git@github.com`、`Hi <wrong-account>`、`IdentityFile`、`Host *`、`gh config set git_protocol https`、`git remote set-url --push`、`x-access-token`、`GH_TOKEN`、`AGENTS.md` 跨账号
- **用 `GIT_CONFIG_COUNT` env 把 gh 临时挂成 git credential helper（不污染 `~/.gitconfig`）** → [references/copilot.md](references/copilot.md)
  - 关键词：`GIT_CONFIG_COUNT`、`GIT_CONFIG_KEY_N`、`GIT_CONFIG_VALUE_N`、`scope=command`、`credential.helper`、`!gh auth git-credential`、`gh auth setup-git 不要用`、`Username for 'https://github.com'`、`空 helper 清空继承`、`累加 KEY_0`、`safe.bareRepository`、`direnv envrc`、`per-workspace credential`
- **`/rewind` 在非 git 仓库的 cwd 里直接拒绝（硬编码 `no-git-repo` 检查，与文件备份机制本身无关）** → [references/copilot.md](references/copilot.md)
  - 关键词：`/rewind`、`/undo`、`rewind 用不了`、`没 git 不能 rewind`、`只想回退会话`、`RewindManager`、`A6e`、`no-git-repo`、`rewind-snapshots/backups`、`index.json`、`gitCommit`、`gitBranch`、`gitStatus`、`hs(process.cwd())`、`Not a git repository`、`session-state`、`空 .git 绕过`
- **三种 MCP 配置文件的区别（`.mcp.json` vs `.vscode/mcp.json` vs `~/.copilot/mcp-config.json`）** → [references/copilot.md](references/copilot.md)
  - 关键词：`mcpServers`、`servers`、`inputs`、`${input:}`、`${env:}`、`mcp-config.json`、`.vscode/mcp.json`、`.mcp.json`、`.github/mcp.json`、`variable expansion`、`headers`、`configurationResolverService`、`walk-up`、`workspace MCP`、`全局 MCP`、`trust level`
- **Copilot CLI `.mcp.json` 的 headers 里 `${VAR}` 环境变量展开不生效** → [references/copilot.md](references/copilot.md)
  - 关键词：`Authorization header is badly formatted`、`Bearer ${VAR}`、`headers 环境变量`、`compound string`、`复合字符串`、`copilot-cli#1232`、`copilot-cli#3100`、`direnv`、`硬编码 PAT`
- **`trustedFolders` 与会话级 allowed-dir 是两套机制（在子目录启动后访问父目录文件被拦）** → [references/copilot.md](references/copilot.md)
  - 关键词：`Allow directory access`、`outside your allowed directory list`、`trustedFolders`、`/add-dir`、`/list-dirs`、`/allow-all`、`/cwd`、`config.json`、`permissions-config.json`、`tool_approvals`、`launch cwd`、`session sandbox`、`从子目录启动 copilot`、`父目录被拦`、`trust this folder`
- **`COPILOT_ALLOW_ALL` env var 只对应 `--allow-all-tools`，且 5 处直读 env 走严格 `=== "true"`（全是 isFolderTrusted 短路）；`--allow-all` ≡ `--yolo`，env 救不了 path/url 维度，alias 又不能写进 `.envrc`** → [references/copilot.md](references/copilot.md)
  - 关键词：`COPILOT_ALLOW_ALL`、`COPILOT_ALLOW_ALL=1`、`COPILOT_ALLOW_ALL=true`、`--allow-all`、`--yolo`、`--allow-all-tools`、`--allow-all-paths`、`--allow-all-urls`、`isFolderTrusted`、`wZ.isFolderTrusted`、`includeWorkspaceSources`、`commander .env()`、`布尔 flag 宽松解析`、`严格字符串比较`、`workspace MCP 不加载`、`trust folder 弹窗`、`bLa`、`txr`、`Aa`、`isAllowAllActive`、`目录审批绕不过`、`yolo 等于 allow-all`、`三合一展开`、`alias 不能写进 .envrc`、`direnv alias 失效`、`PATH_add`、`PATH-shim`、`.bin/copilot wrapper`、`exec copilot --yolo`
