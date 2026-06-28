# Copilot CLI MCP configuration

MCP configuration discovery, workspace `.mcp.json` behavior, environment interpolation pitfalls, and per-run MCP profile injection. Use this for agent-harness designs that spawn Copilot sessions with isolated tool profiles.

## Per-run MCP profile injection

Verified on Copilot CLI `1.0.66-1` with `copilot --help`:

```text
--additional-mcp-config <json>
  Additional MCP servers configuration as JSON string or file path (prefix with @)
  (can be used multiple times; augments config from ~/.copilot/mcp-config.json for this session)
```

Practical meaning:

- `--additional-mcp-config '{"mcpServers": {...}}'` passes inline JSON for one run.
- `--additional-mcp-config @/abs/path/profile.json` loads JSON from a file. The `@` prefix is Copilot CLI's file-reference syntax.
- A daemon or orchestrator should prefer per-run/per-agent MCP profile injection over mutating a shared workspace `.mcp.json`. Treat `.mcp.json` as the developer's interactive workspace config unless the user explicitly wants the workspace profile changed.

## MCP 配置

### 三种 MCP 配置文件的区别

Copilot 生态里有**三个不同位置**的 MCP 配置文件（其实是四种实例，但只有三种 schema），名字都带 "mcp" 容易搞混，尤其是 `.mcp.json` 和 `.vscode/mcp.json` 格式不兼容但长得像。

#### 对比表

| | `.mcp.json` | `.github/mcp.json` | `.vscode/mcp.json` | `~/.copilot/mcp-config.json` |
|---|---|---|---|---|
| **谁读它** | Copilot CLI / Claude Code / Cursor | Copilot CLI | VS Code（编辑器内 Copilot Chat）| Copilot CLI |
| **设计目的** | 项目级 MCP，跨编辑器通用标准 | 项目级 MCP，GitHub 风格路径 | VS Code workspace 级 MCP | 用户全局 MCP，跨所有项目 |
| **顶层 key** | `mcpServers` | `mcpServers` | `servers`（+可选 `inputs`）| `mcpServers` |
| **位置** | 项目根 / git root | 项目根下 `.github/` | `<workspace>/.vscode/` | `~/.copilot/`（固定）|
| **Walk-up（向上查找）** | ✅ 从 cwd 向上，**停在 git root** | ✅ 同 `.mcp.json`（共用 `bBt` 发现函数）| ❌ 只读当前 VS Code 打开的 workspace folder | ❌ 固定全局路径 |
| **Trust level** | Medium（需 review） | Medium（需 review） | VS Code 内独立管理 | User-defined |
| **变量展开 — `${VAR}` env** | `env` 字段支持；`headers` 字段**名义支持但实测不生效**（#1232）| 同 `.mcp.json` | 通过 `${env:VAR}` 支持 | 同 `.mcp.json` |
| **变量展开 — `${input:...}`** | ❌ 不支持 | ❌ 不支持 | ✅ 支持（弹窗输入，OS keychain 安全存储）| ❌ 不支持 |
| **变量展开 — `${workspaceFolder}`** | ❌ | ❌ | ✅ | ❌ |
| **`envFile`** | ❌ | ❌ | ✅（stdio 类型）| ❌ |
| **优先级** | 高于全局 `mcp-config.json`；低于 `--additional-mcp-config` | 同 `.mcp.json`（同名时与 `.mcp.json` 合并）| VS Code 内独立管理 | 最低（被同名 workspace 配置覆盖）|
| **同名冲突规则** | Copilot CLI: **last-wins**（workspace 覆盖全局）| 同 `.mcp.json` | VS Code 内独立 | 被 workspace 覆盖 |
| **是否入版本控制** | 可以（如不含 secrets）| 可以（`.github/` 本就版本控制友好）| 官方推荐入版本控制 | ❌ 用户私有 |

#### 源码证据

**Copilot CLI walk-up 逻辑**（`app.js` 中 `bBt` 函数，见下节详解）：

```js
function bBt(t, e, r, n) {
  // t = cwd, e = gitRoot (trust boundary)
  let s = normalize(e), a = normalize(t);
  for (;;) {
    // 在 a 找 .mcp.json ...
    if (a === s) break;       // 停在 git root
    let u = dirname(a);
    if (u === a) break;       // 到了根目录
    a = u;
  }
}
```

**VS Code 不做 walk-up**（`mcpWorkbenchService.ts`）：直接用 `workspaceFolder.uri` 拼 `.vscode/mcp.json`，没有任何目录遍历。

**VS Code 变量展开**（`mcpRegistry.ts`）：启动 MCP server 时调用 `_replaceVariablesInLaunch()` → `configurationResolverService.resolveWithInteraction()`，对 launch 对象（含 headers）做完整的变量替换。

#### 各自的设计目的

1. **`.mcp.json`**：Claude Code / Cursor / Copilot CLI 共用的"项目级 MCP 配置"事实标准。Copilot CLI 后来跟进支持这个格式（[#2938](https://github.com/github/copilot-cli/issues/2938)），以兼容 Claude Code 生态。
2. **`.github/mcp.json`**：Copilot CLI 专有的项目级 MCP 配置（Claude Code / VS Code 不读）。遵循 GitHub 的 `.github/` 约定（类似 `.github/copilot-instructions.md`、`.github/workflows/`），跟 `.mcp.json` 同格式同行为。选哪个看团队偏好——跨编辑器通用用 `.mcp.json`，符合 GitHub 目录惯例用 `.github/mcp.json`。
3. **`.vscode/mcp.json`**：VS Code 原生的 MCP 配置，遵循 VS Code 的 `settings.json` / `tasks.json` 等惯例。有完整的变量系统（`inputs` / `${env:}` / `${workspaceFolder}`）。Copilot CLI 曾短暂支持读取这个文件，后改为推荐迁移到 `.mcp.json`，社区有抱怨（[#3019](https://github.com/github/copilot-cli/issues/3019)、[#3059](https://github.com/github/copilot-cli/issues/3059)）。
4. **`~/.copilot/mcp-config.json`**：Copilot CLI 的用户级全局配置。适合放全局性的 MCP server（如 GitHub MCP），不跟随项目走。优先级最低，会被同名 workspace 配置覆盖（参考官方文档[add-mcp-servers](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers)、[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)：项目级 `.mcp.json` / `.github/mcp.json` 优先于用户级 `~/.copilot/mcp-config.json`）。

#### 实际使用建议

- **只用 Copilot CLI**：用 `.mcp.json`，secrets 硬编码（目前没有安全的替代方案，`headers` 里 `${VAR}` 展开不可靠，见下文）
- **只用 VS Code**：用 `.vscode/mcp.json` + `${input:...}` 或 `${env:VAR}`
- **两边都用**：维护两份配置，`.mcp.json`（CLI）+ `.vscode/mcp.json`（VS Code），用 direnv 同步环境变量

#### 相关 issue / 文档

- 参考官方文档[add-mcp-servers](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-mcp-servers)：Copilot CLI 加 MCP server、用户级 vs 项目级优先级
- 参考官方文档[cli-plugin-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference)：含加载优先级图
- [VS Code MCP 配置参考](https://code.visualstudio.com/docs/copilot/reference/mcp-configuration)
- [VS Code MCP 文档](https://code.visualstudio.com/docs/copilot/chat/mcp-servers)
- Copilot CLI 添加 `.mcp.json` 支持：[#2938](https://github.com/github/copilot-cli/issues/2938)
- 社区抱怨需要两份配置：[#3019](https://github.com/github/copilot-cli/issues/3019)
- VS Code 源码 `mcpWorkbenchService.ts`：workspace folder 直接拼 `.vscode/mcp.json`
- VS Code 源码 `mcpRegistry.ts`：`_replaceVariablesInLaunch()` → `configurationResolverService`
- VS Code 源码 `pluginParsers.ts`：`resolveMcpServersMap()` 兼容 `mcpServers` 和 `servers` 两种 key

---

### `.mcp.json` 上溯停在 git root（多 repo 工作区漏装）

#### 症状

两个反向场景都会出现"父目录 `.mcp.json` 看不到"：

1. **Parent 是 git repo、子项目也各自是独立 git repo**：父目录 `.mcp.json` 注册了 server，在父目录直接 `copilot mcp list` 能看到，但 `cd <subdir> && copilot mcp list` 显示 `No MCP servers configured`。
2. **Parent 不是 git repo、子项目是 git repo**：父目录 `.mcp.json` 含 server-a + server-b，子目录 `.mcp.json` 含 server-c。在子目录起 copilot 只看到 server-c，父目录那两个继承不到。

#### 结论（先说人话）

1. **会不会合并？会。** `bBt` 收集 cwd → git root 之间每一层的 `.mcp.json`，`bLa` 按 depth 倒序合并、cwd 覆盖祖先（last-wins，同名 server 以 cwd 为准）。
2. **触发上溯/合并的前提**（看 `sN` 三个分支）：
   - cwd 在某个 git repo 内 → 上溯到该 repo 的 root，沿途各层合并
   - cwd **不在**任何 git repo 内 → 走 `else` 分支，**只读 cwd 一份**，连 `bLa` 都不调
   - cwd 自己就是 git root → 第一轮 push 完 cwd 那份就 break，parent 一份都拿不到
3. **"没 git root 影响就会合并" 反着的**：git root 不是限制开关，反而是让跨目录合并能发生的**前提**。想让 `~/projects/{a,b,c}/` 都自动继承 `~/projects/.mcp.json` → 在 `~/projects/` `git init` 一下，且 `a/b/c` 自己**不是**独立 git repo（否则它们的 git root 钉在自己身上，看不到 parent）。

VS Code 的 "workspace folder" 概念跟它完全不同，所以从 VS Code 思维转过来反直觉。

#### 代码支撑

```js
async function bBt(t, e, r, n) {
  // t = cwd，e = boundary（git root），r = [{kind:"file", relativePaths:[".mcp.json"]}]，n = trust 检查 callback
  let o = [], s = Q3.normalize(e), a = Q3.normalize(t), l = 0;
  for (;;) {
    let c = l === 0 ? "project" : "inherited";   // 给每条命中打来源标签
    for (let d of r) for (let m of d.relativePaths) {
      let p = Q3.join(a, m);
      wqr(p) && o.push({path: p, directory: a, depth: l, source: c});
    }
    if (a === s) break;                          // ① 停在 git root
    let u = Q3.dirname(a);
    if (u === a || (n && !await n(u))) break;    // ② 或停在 fs 根 / 不可信目录
    a = u; l++;
  }
  return o;
}

async function bLa(t, e, r) {
  let o = await bBt(t, e, [{kind:"file", relativePaths:[".mcp.json"]}], /* trust cb */);
  if (o.length === 0) return {mcpServers:{}};
  let s = [...o].sort((l, c) => c.depth - l.depth);    // 祖先在前
  let a = {mcpServers:{}};
  for (let l of s) a = pre(a, zWo(l.directory));       // last-wins：cwd 覆盖 inherited
  return a;
}

// sN（顶层调度）：
if (!s) d = {...c};                              // 没启用 workspace 加载
else if (a) d = pre(c, await bLa(e, a, o));      // a = gitRoot 存在 → 上溯到 gitRoot
else { let p = zWo(e); d = pre(c, p); ... }      // 不在 git repo 里 → 只读 cwd 一份
```

对照前面三条结论：

- 结论 1 的"合并 + last-wins" → `bLa` 里 `sort((l,c)=>c.depth-l.depth)` + `for...pre(a, zWo(...))`
- 结论 2 的三个分支 → `sN` 里 `if(!s) / else if(a) / else` 三段
- 结论 2 第三种"cwd 自己就是 git root" → `bBt` **先 push 当前层、再判断 `a === s`**，所以 cwd 那份能拿到，但下一轮 `dirname` 之前就 break

#### 解决（多 repo 工作区共用同一份 `.mcp.json`）

复用 [Copilot discovery 里的 `link_into_subdirs` helper](copilot-discovery.md#通用-workarounddirenv-symlink)：

```bash
# .envrc
link_into_subdirs "$PWD/.mcp.json" '.mcp.json'
```

每个子项目都被自动塞一份 `.mcp.json` 软链 + 写进 `.git/info/exclude` 不污染 `git status`。子项目想覆盖 / 加自己的 server 时，可以单独把那一份从软链改成手写文件（合并不会发生，因为子项目的 git root 就是它自己——但反正配置直接照 cwd 那份用就够了）。

#### 教训

- "Workspace MCP" 的 "workspace" 是 **git repo 级**，不是用户主观的"工作区"，更不是 VS Code 概念里的 workspace folder。
- 实测才信结论；只看 `copilot mcp list` 输出容易得出错误判断。读 `app.js` 才能确认它**会**上溯但停在 git root；而"没 git root"反而连 parent 都不看。
- `copilot mcp list` 输出的 `Source:` 列：`Project (.mcp.json)` 是 cwd 那份，`Inherited (...)` 是上溯命中的祖先那份，可以用来快速验证 symlink / 合并实际生效到了哪。
- 同名 server 冲突时 last-wins，cwd 覆盖 inherited；想强制不被父目录覆盖，server 名字起独特一点。

---

### `.mcp.json` headers 里 `${VAR}` 展开不生效

#### 症状

`.mcp.json` 配置 HTTP MCP server 时，`headers` 里用 `${VAR}` 引用环境变量，Copilot CLI 不做展开，把字面量 `Bearer ${MY_GH_PAT}` 发给服务端，导致：

```
Streamable HTTP error: Error POSTing to endpoint: bad request:
Authorization header is badly formatted
```

硬编码 PAT 则正常。

#### 复现矩阵（都不生效）

1. `"Bearer ${VAR}"`（复合字符串） → 字面量发送
2. `"${VAR}"`（纯变量引用，env 值含 `Bearer ` 前缀） → 字面量发送
3. `"$VAR"`（无花括号） → 字面量发送
4. 配置文件放 `~/.copilot/mcp-config.json`（全局） → 同样失败
5. curl 直接用环境变量拼 header → 200（PAT 本身有效）
6. 硬编码到任何位置的配置文件 → 立刻成功

#### 已知 issue

- **[#1232](https://github.com/github/copilot-cli/issues/1232)**：用户 @stefanbosak 精确复现了 `"Authorization": "Basic ${TOKEN}"` 不展开。2026-04-07 官方关闭说已修复，但 @therealvio 在 v0.0.420 + **direnv** 环境下仍报告不工作，无人确认修复生效。
- **[#3100](https://github.com/github/copilot-cli/issues/3100)**：即使 `headers` 里有 `Authorization: Bearer <token>`，CLI 可能先触发 OAuth discovery 流程并失败，header 根本没机会发出去。
- **[#1841](https://github.com/github/copilot-cli/issues/1841)**：Feature request 要求支持 `${input:...}` 语法，仍然 open。
- **[#2960](https://github.com/github/copilot-cli/issues/2960)**：反向佐证——有用户用 `"Bearer ${GRAFANA_MCP_TOKEN}"` **成功展开**了（问题是 token 太长超限制），说明在某些环境下确实能用。

#### 根因推测

可能是以下因素叠加：

1. headers 里复合字符串 `"Bearer ${VAR}"` 的展开逻辑不完整（#1232 最初报的就是这个）
2. direnv 注入的环境变量可能走了不同的进程继承路径（@therealvio 也用 direnv）
3. 全局 vs workspace 配置可能走不同的解析管道
4. `Nhe` 黑名单的 `${VAR}` 展开拦截（见 `Das()`）会主动屏蔽敏感变量名，进一步劝退靠 env 注入 secret 的做法

#### 解决（当前 workaround）

headers 里硬编码 PAT。文件 `chmod 600` + 不入版本控制。

如果用 VS Code，可以走 `.vscode/mcp.json` + `${env:VAR}` 或 `${input:...}`，那套变量系统是 VS Code 原生的 `configurationResolverService`，完全独立于 Copilot CLI 的解析器。

#### 教训

- **官方文档说"supports variable expansion"不等于实际能用**——changelog 说修了、文档说支持，但没有受影响用户确认修复、也没有自动化测试保证回归。实测为准。
- **direnv 是额外变量**——它注入 env 的方式（hook `$PROMPT_COMMAND` / `precmd`）跟直接 `export` 在微妙场景下可能有差异。遇到 env 不生效先排除 direnv 因素。
- **VS Code 和 Copilot CLI 是两套独立的变量系统**——VS Code 的 `${env:VAR}` 走 `configurationResolverService`，经过完整的变量解析管道；Copilot CLI 的 `${VAR}` 走自己的简单字符串替换。不要混用语法。

---
