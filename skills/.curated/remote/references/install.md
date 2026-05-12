# 安装 portal-mcp-server（项目级注册）

portal-mcp-server 项目根有 `mcp-config.example.json`。Copilot CLI **原生支持工作区级 `.mcp.json`**（与 Claude Code / Cursor 同格式）：

```bash
cp <portal-mcp-server>/mcp-config.example.json <project>/.mcp.json
# 编辑里面的绝对路径指向你 clone 的位置
```

之后在该项目目录下启动 `copilot`，会自动加载。验证：

```bash
copilot mcp list                # → Workspace servers: portal (local)
copilot mcp get portal          # → Source: Workspace (.../.mcp.json)
```

> ⚠️ 别用 `copilot mcp add` 走交互——它默认写到 user-level `~/.copilot/mcp-config.json`，会污染所有项目。**直接编辑 `.mcp.json`** 才能保持项目级。
