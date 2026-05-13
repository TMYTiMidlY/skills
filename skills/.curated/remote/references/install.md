# 安装 portal-mcp-server（项目级注册）

不需要 clone——`uvx` 会在 MCP client 启动时直接从 GitHub 拉。在项目根创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "portal": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/TMYTiMidlY/portal-mcp-server.git",
        "portal-mcp-server"
      ]
    }
  }
}
```

> 注意两件事：
> - `.mcp.json` 顶层 `mcpServers` 下的 key（这里是 `"portal"`）是这个 server 的本地标识。**Copilot CLI** 把它作为前缀拼到工具名前面（你看到的就是 `portal-portal_read` 等）；其他客户端（Claude Code / Codex / Cursor）格式不同——Codex 用 `mcp__portal__portal_read`，Claude Code 通常直接 `portal_read`——但都用这个 key 在配置层管理 server。改 key 会同步改 Copilot CLI 看到的工具前缀。
> - VS Code 的 `.vscode/mcp.json` 用 `servers` 而不是 `mcpServers`，每个 server 多写一行 `"type": "stdio"`，否则同格式

之后在该项目目录下启动 `copilot`，会自动加载。验证：

```bash
copilot mcp list                # → Workspace servers: portal (local)
copilot mcp get portal          # → Source: Workspace (.../.mcp.json)
```

> ⚠️ 别用 `copilot mcp add` 走交互——它默认写到 user-level `~/.copilot/mcp-config.json`，会污染所有项目。**直接编辑 `.mcp.json`** 才能保持项目级。

如果用户是 portal-mcp-server 开发者要本地改代码，可以把 `--from <git url>` 改成 `--from /abs/path/to/portal-mcp-server`，uvx 会从本地工作树 install。详见 [portal-mcp-server README](https://github.com/TMYTiMidlY/portal-mcp-server#%EF%B8%8F-我改了代码但-agent-调-mcp-时为什么还是旧行为)。
