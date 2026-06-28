# Copilot CLI 配置发现：指令、Hooks、MCP、Skills

Copilot CLI 怎么发现项目级 / 用户级上下文：walk-up（向上查找）行为、Custom Instructions（指令文件）、Hooks 配置、MCP 配置、Skills 目录。排查"某个项目级指令 / hook / MCP server / skill 为什么没加载"时看这里。证据锚点用 `app.js` 里稳定的字面量；混淆符号名与字节偏移随版本变化，升级后需重新核对。

## Walk-Up（向上查找）机制总览

Copilot CLI 的多种项目级配置与指令文件共用一套 **walk-up**（从 cwd 向上遍历到 boundary）发现策略。本节是机制层面的统一说明，后面的 Custom Instructions / MCP / Skills / Hooks 各章节落具体规则与排障。

### 核心 walk-up 函数 `bBt`

MCP、Skills 的项目级发现都经过同一个 `bBt` 函数。它从 `startPath`（通常是 cwd）向上走，每层检查目标文件/目录是否存在，**撞到 boundary（通常是 git root）就停**。

```js
// app.js — bBt（简化）
async function bBt(t, e, r, n) {
  // t = startPath (cwd), e = boundary (git root), r = [{kind, relativePaths}], n = trust callback
  let o = [], s = normalize(e), a = normalize(t), l = 0;
  for (;;) {
    let c = l === 0 ? "project" : "inherited";
    for (let d of r) for (let m of d.relativePaths) {
      let p = join(a, m);
      existsSync(p) && o.push({path: p, directory: a, depth: l, source: c});
    }
    if (a === s) break;                          // ★ 撞 boundary 就停
    let u = dirname(a);
    if (u === a || (n && !await n(u))) break;    // 到 fs 根 / 不可信目录
    a = u; l++;
  }
  return o;
}
```

**关键行为**：

- 先 push 当前层，再判断 `a === s`，所以 **boundary 本身那层的文件能被收录**
- `source` 标签：depth 0 = `"project"`，>0 = `"inherited"`
- boundary 不存在（非 git repo）时各子系统行为不同：Skills 回退到 `$HOME`，MCP 只读 cwd 一份

**Custom Instructions 不走 `bBt`**——它有自己一套专用函数（`aKr`/`oKr`/`iKr`/`sKr` 单点查 + `vfi` 扫中间层），效果**等同**于 walk-up 但实现方式不同；见下面 Custom Instructions 章节。**Hooks 完全不 walk-up**，只看固定两处路径。

### 每种配置/指令文件到底会不会 walk-up 到 git root？

逐一回答"如果我在 `<gitRoot>/packages/billing/` 工作，`<gitRoot>/` 下的文件能不能被找到"：

| 文件 | 会 walk-up 到 git root 吗？ | 机制 |
|------|---------------------------|------|
| **AGENTS.md** | ✅ 会 | `oKr(gitRoot)` 直接查 git root；`vfi` 扫中间层；`oKr(cwd)` 查 cwd。三层都找到则**全部注入** |
| **CLAUDE.md** | ✅ 会 | 同 AGENTS.md（`iKr` 替代 `oKr`，额外查 `.claude/CLAUDE.md`） |
| **GEMINI.md** | ✅ 会 | 同 AGENTS.md（`sKr` 替代 `oKr`） |
| **.github/copilot-instructions.md** | ✅ 会 | `aKr(gitRoot)` 直接查 git root；`vfi` 扫中间层；`aKr(cwd)` 查 cwd |
| **.github/instructions/\*.instructions.md** | ✅ 会 | `Rfi` 在 git root 和 cwd 下分别 glob 扫描 |
| **嵌套子目录 AGENTS.md** | ✅ 向**下**扫 | `xfi` 扫子目录（不是向上），生成表格提示让 agent 按需 `view` |
| **.mcp.json** | ✅ 会 | `bBt` 从 cwd 向上逐层扫到 git root，沿途合并（last-wins） |
| **.github/mcp.json** | ✅ 会 | 同 `.mcp.json`，共用 `bBt` |
| **.agents/skills/** | ✅ 会 | `yQe`→`bBt` 从 cwd 向上逐层扫到 git root（无 git 时回退 `$HOME`） |
| **.github/skills/** | ✅ 会 | 同 `.agents/skills/`，共用 `j7e`→`yQe` |
| **.claude/skills/** | ✅ 会 | 同上 |
| **.github/hooks/** | ❌ 不会 | 只查 git root 一层，不做任何 walk-up |

**关键区别**：

- **Instructions（AGENTS.md 等）**：不走统一的 `bBt`，而是 `oKr(gitRoot)` + `vfi(中间层)` + `oKr(cwd)` 三段拼接，**效果等同于** cwd→git root 的完整 walk-up，但实现方式不同
- **MCP / Skills**：走统一的 `bBt` walk-up，一个循环搞定
- **Hooks**：完全不 walk-up

**所有 walk-up 的 boundary 都是 git root**——如果 cwd 在一个独立的子 git repo 里，上溯到子 repo 的 root 就停，看不到父目录。

### 子系统总对比表

| 子系统 | Walk-up | Boundary | 不在 git repo 时 | 用户级路径 | Env 覆盖 |
|--------|---------|----------|------------------|-----------|----------|
| **Custom Instructions**<br>(AGENTS.md 等) | `vfi`：cwd→git root **中间层**<br>（两端分别单独查） | git root | 只读 cwd | `~/.copilot/copilot-instructions.md`<br>`~/.copilot/instructions/` | `COPILOT_CUSTOM_INSTRUCTIONS_DIRS` |
| **MCP** (`.mcp.json`) | `bBt`：cwd→git root 沿途合并 | git root | 只读 cwd 一份，不上溯 | `~/.copilot/mcp-config.json` | — |
| **Skills** (`.agents/skills`) | `bBt`→`yQe`：cwd→git root 沿途收录 | git root；无 git 时回退 `$HOME` | 一路扫到 `$HOME` | `~/.copilot/skills`<br>`~/.agents/skills` | `COPILOT_SKILLS_DIRS` |
| **Hooks** (`.github/hooks`) | ❌ 不上溯，只看 git root 一层 | git root | cwd | `~/.copilot/hooks/`（文件）<br>+ `config.json` 内联 `hooks` 键 | — |

**共同特征**：

- Boundary 都是 git root——子项目如果是独立 git repo，上溯立刻停在子项目根，看不到父目录
- 用户级路径都不受 walk-up boundary 限制

### 通用 workaround：direnv symlink

所有 walk-up 子系统在"父目录套独立子 git repo"场景下都有同样的问题：看不到父目录的配置。通用解法是 direnv 自动维护 symlink：

```bash
# .envrc
link_into_subdirs() {
  local src="$1" rel="$2" sub target excl
  [[ -f "$src" || -d "$src" ]] || return 0
  for sub in "$PWD"/*/; do
    sub="${sub%/}"
    target="$sub/$rel"
    if [[ ! -e "$target" && ! -L "$target" ]]; then
      mkdir -p "$(dirname "$target")"
      ln -s "$src" "$target"
    fi
    excl="$sub/.git/info/exclude"
    if [[ -f "$excl" ]] && ! grep -qxF "/$rel" "$excl"; then
      printf '/%s\n' "$rel" >> "$excl"
    fi
  done
}

# 按需调用
link_into_subdirs "$PWD/.github/hooks/safety-net.json" '.github/hooks/safety-net.json'
link_into_subdirs "$PWD/.mcp.json"                     '.mcp.json'
link_into_subdirs "$PWD/.agents/skills"                '.agents/skills'
link_into_subdirs "$PWD/AGENTS.md"                     'AGENTS.md'
```

direnv 本身改不了 copilot 找配置的路径（copilot 是独立进程读文件系统），它只是帮你**自动维护 symlink 实体**；改 `.envrc` 后要 `direnv allow` 重新授权（基于文件 hash）。或者把配置搬到 user-level 路径（`~/.copilot/`（各子目录如 `~/.copilot/hooks/`、`~/.copilot/skills/`）或 `~/.agents/skills/`），绕过 walk-up boundary 限制。

后面 MCP / Skills / Hooks 章节的"多 repo 工作区漏装"排障节都复用这个 helper，不再重复定义。

---
## Custom Instructions（指令文件）

Custom Instructions 是 Copilot CLI 往 system prompt 里注入的用户/项目自定义指令。**它们不走 `bBt`**，而是用自己的一组专用函数分别处理 git root、cwd、中间层三个位置。

### 指令文件清单与搜索路径

指令文件的 convention 定义（`cKr` 数组）：

```js
// app.js — cKr
cKr = [
  {kind: "copilot", convention: ".github",      filename: "copilot-instructions.md"},
  {kind: "agents",  convention: ".",             filename: "AGENTS.md"},
  {kind: "claude",  convention: ".",             filename: "CLAUDE.md"},
  {kind: "claude",  convention: ".claude",       filename: "CLAUDE.md"},
  {kind: "gemini",  convention: ".",             filename: "GEMINI.md"},
];
```

即 Copilot CLI 能识别以下指令文件（在每个搜索位置）：

| 文件 | 搜索子路径 | 类型标签 |
|------|-----------|---------|
| `copilot-instructions.md` | `.github/` | `copilot` / `repo` |
| `AGENTS.md` | `.`（当前目录根） | `agents` / `model` |
| `CLAUDE.md` | `.` 和 `.claude/` | `claude` / `model` |
| `GEMINI.md` | `.`（当前目录根） | `gemini` / `model` |

这份单文件清单（源码 `cKr` 数组）与 CLI 启动时打印的 "Copilot respects instructions from these locations" 同源；后者还并列了 `.github/instructions/**/*.instructions.md` glob、用户级 `$HOME/.copilot/copilot-instructions.md` / `$HOME/.copilot/instructions/**/*.instructions.md` 和 env `COPILOT_CUSTOM_INSTRUCTIONS_DIRS`（各自见下文小节）。项目级指令文件的写法参考官方文档[add-repository-instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions)。

**多种文件全部合并注入，不互斥**：Copilot CLI 主动兼容其他 AI 编码工具的指令文件格式。如果仓库里同时存在 AGENTS.md、CLAUDE.md、GEMINI.md、copilot-instructions.md，**四种全部读取**，各自包裹在 `<custom_instruction>` 标签里按顺序拼接注入 system prompt。不做选择、不做冲突检测，只在 realPath 或 content 完全相同时去重（`rKr`）。

**大小写不敏感**（macOS/Linux 文件名匹配走 `Yq` 函数，先尝试精确匹配，失败后用 `readdir` + `toLowerCase()` 做 case-insensitive fallback）：

```js
// app.js — Yq
function Yq(t, e) {
  let r = join(t, e);
  if (existsSync(r)) return r;         // 精确匹配
  try {
    let n = readdirSync(t), o = e.toLowerCase(),
        s = n.find(a => a.toLowerCase() === o);
    if (s) { let a = join(t, s); if (existsSync(a)) return a; }
  } catch {}
}
```

### git root 级指令：直接查找

每种指令文件各有一个单点查找函数，直接在 git root（`t`）下查文件：

```js
// app.js — 直接查找函数
function aKr(t) {                                      // .github/copilot-instructions.md
  let e = join(t, ".github"),
      r = Yq(e, "copilot-instructions.md");
  return r ? {exists: true, path: r} : $M;             // $M = {exists: false, path: undefined}
}
function oKr(t) { return Yq(t, "AGENTS.md") ... }     // AGENTS.md
function iKr(t) { return Yq(t, "CLAUDE.md") ... }     // CLAUDE.md
function sKr(t) { return Yq(t, "GEMINI.md") ... }     // GEMINI.md
```

在主函数 `Efi` 中，**git root 和 cwd 各调一次**：

```js
// app.js — Efi（简化）
async function Efi(t, e, r, n, o) {
  // t = git root (location), e = enabled, r = cwd, n = settings
  let h = aKr(t),       // git root 下 .github/copilot-instructions.md
      g = oKr(t),       // git root 下 AGENTS.md
      f = iKr(t),       // git root 下 CLAUDE.md
      I = sKr(t);       // git root 下 GEMINI.md

  let y = r && !NR(r, t);     // cwd ≠ git root?
  let C = y ? aKr(r) : $M,    // cwd 下 .github/copilot-instructions.md
      E = y ? oKr(r) : $M,    // cwd 下 AGENTS.md
      S = y ? iKr(r) : $M,    // cwd 下 CLAUDE.md
      _ = y ? sKr(r) : $M;    // cwd 下 GEMINI.md
  // ...
}
```

### cwd 级指令：当 cwd ≠ git root 时额外查找

当 `cwd ≠ git root` 时，每种指令文件会在 cwd 额外查一次。两份都找到时**都注入**，不互相覆盖：

```js
// git root 级 → location: "repository"
Y && oe.push({id: "repo-copilot", label: ".github/copilot-instructions.md",
              sourcePath: ".github/copilot-instructions.md", content: Y,
              type: "repo", location: "repository"});

// cwd 级 → location: "working-directory"
B && C.exists && oe.push({id: "cwd-copilot", label: ".github/copilot-instructions.md",
                          sourcePath: relative(t, C.path), content: B,
                          type: "repo", location: "working-directory"});
```

AGENTS.md / CLAUDE.md / GEMINI.md 同理，git root 的 location 标记 `"repository"`，cwd 的标记 `"working-directory"`。

### 中间层指令：`vfi` walk-up

`vfi` 负责发现 **cwd 与 git root 之间**（不含两端）的指令文件。它从 cwd 的**父目录**开始向上走，到 git root **之前**停止：

```js
// app.js — vfi
function vfi(t, e) {
  // t = cwd, e = git root
  if (!t || NR(t, e)) return [];      // cwd == git root → 没有中间层
  let r = [], n = normalize(e), o = normalize(t),
      s = dirname(o);                  // ★ 从 cwd 的父目录开始
  for (; s !== n && s !== dirname(s); ) {   // ★ 到 git root 之前停
    for (let a of cKr) {               // 遍历 5 种 convention
      let l = a.convention === "." ? s : join(s, a.convention),
          c = Yq(l, a.filename);
      c && r.push({filePath: c, relativePath: relative(e, c),
                   directory: s, kind: a.kind});
    }
    s = dirname(s);
  }
  return r;
}
```

这些中间层文件被读取后，注入 prompt 时标记 `id: "inherited-*"`：

```js
// app.js — 中间层指令注入
let R = vfi(r, t);   // r = cwd, t = git root
// ...读取文件内容后...
for (let it of Le) {
  let Ke = St.kind === "copilot" ? "repo" : "model",
      Re = St.relativePath.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  oe.push({id: `inherited-${Re}`, label: basename(St.filePath),
           sourcePath: St.relativePath, content: bt,
           type: Ke, location: "repository"});
}
```

**注意**：`vfi` 用的是 `cKr`（5 种 convention），所以中间层也能发现 copilot-instructions.md、AGENTS.md、CLAUDE.md、GEMINI.md。

### 子目录嵌套 AGENTS.md：`xfi` BFS

除了向上找，Copilot CLI 还会向**下**扫描子目录中的 `AGENTS.md`（nested instructions）：

```js
// app.js — xfi
async function xfi(t, e = []) {
  // t = git root, e = additional dirs (COPILOT_CUSTOM_INSTRUCTIONS_DIRS)
  let r = [t]; r.push(...e);
  let n = hKr(r);              // 去重
  let s = (await Promise.all(n.map(async l => {
    let c = join(l, "AGENTS.md");
    if (existsSync(c)) try {
      if (!(await stat(c)).isFile()) return null;
      let d = await readFile(c, "utf-8"),
          m = relative(t, c);
      return m === "AGENTS.md" ? null   // ★ 跳过根目录那份（已由 oKr 处理）
             : {path: m, content: truncate(d)};
    } catch { return null; }
    return null;
  }))).filter(l => l !== null);
  return s.length === 0 ? void 0
       : {content: Dfi(s), source: "agents", sourcePath: "AGENTS.md (nested)"};
}
```

但注意 `xfi` **不做递归子目录遍历**——它只在传入的根目录列表的直接子目录（准确说是同级）查 `AGENTS.md`。真正的递归子目录扫描由 `LMr`（child instructions）负责。

嵌套 AGENTS.md 注入 prompt 时**不直接展开内容**，而是生成一个表格提示 agent "需要时用 `view` 工具读取"：

```js
// app.js — Dfi 生成提示表格
function Dfi(t) {
  let e = [];
  for (let r of t) {
    let o = dirname(r.path), s = x3(`${o}/`), a = x3(r.path);
    e.push(`| ${s} | '${a}' | Agent instructions for ${o}/**/* |`);
  }
  return [
    "Here is a list of nested AGENTS.md files ...",
    "Please make sure to follow the rules specified in these files ...",
    "If you have not already read the file, use the `view` tool to acquire it.",
    "| Directory | File Path | Description |",
    "| --------- | --------- | ----------- |",
    ...e
  ].join("\n");
}
```

### 子目录嵌套 .github/instructions：`Rfi` glob

`.github/instructions/**/*.instructions.md` 支持 glob 递归：

```js
// app.js — Rfi + gKr
async function Rfi(t, e, r = []) {
  // t = git root, e = cwd, r = additional dirs
  let n = [t];
  e && !NR(e, t) && n.push(e);    // cwd ≠ git root 时也扫 cwd
  n.push(...r);
  let o = hKr(n);                  // 去重
  return (await Promise.all(o.map(async a => {
    let l = join(a, ".github", "instructions");
    if (!existsSync(l)) return [];
    let c = await gKr(l);         // glob *.instructions.md
    return (await Promise.all(c.map(d => fKr(d, a))))
           .filter(d => d !== null).map(Lfi);
  }))).flat();
}

async function gKr(t) {
  let e = globPattern(join(t, "**", "*.instructions.md"));
  return glob(e, {nocase: true});
}
```

这些文件支持 **frontmatter**，包括 `applyTo`（glob pattern 限定适用范围）、`excludeAgent`（排除特定 agent 类型）、`description`（描述）：

```js
// app.js — bKr (frontmatter 解析)
function bKr(t) {
  let e = parse(t, {schema: Qfi, onUnsupportedFields: "ignore"});
  return e.kind !== "success" ? {excludeAgent: []}
       : {applyTo: e.value.frontmatter.applyTo,
          excludeAgent: e.value.frontmatter.excludeAgent,
          description: e.value.frontmatter.description?.trim() || void 0};
}
```

### 用户级指令

两个固定路径，不做 walk-up（参考官方文档[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference) 的 `copilot-instructions.md`、`instructions/` 条目；`~/.copilot` 是默认 configDir，可被 `COPILOT_HOME` 整体改写）：

| 路径 | 函数 | 注入 id | location |
|------|------|---------|----------|
| `~/.copilot/copilot-instructions.md` | `Nfi(n)` | `home-copilot` | `user` |
| `~/.copilot/instructions/**/*.instructions.md` | `kfi(n)` | `user-copilot-instructions` | `user` |

```js
// app.js — Nfi
function Nfi(t) {
  let e = ma(t, "config"),                       // = ~/.copilot（configDir）
      r = Yq(e, "copilot-instructions.md");
  return r ? {exists: true, path: r} : $M;
}

// app.js — kfi
async function kfi(t) {
  let e = ma(t, "config"),
      r = join(e, "instructions");
  if (existsSync(r)) {
    let n = globPattern(join(r, "**", "*.instructions.md")),
        o = await glob(n, {nocase: true});
    // ...读取、解析 frontmatter、过滤 excludeAgent...
  }
}
```

### Env 覆盖 `COPILOT_CUSTOM_INSTRUCTIONS_DIRS`

```js
// app.js — Efi 开头
let s = process.env.COPILOT_CUSTOM_INSTRUCTIONS_DIRS
          ?.split(",").map(it => it.trim()).filter(it => it.length > 0) ?? [];
```

逗号分隔的绝对路径列表，作为额外的搜索根，传给 `xfi`（嵌套 AGENTS.md）和 `Rfi`（.github/instructions glob）。

### 指令注入顺序与合并策略

主函数 `Efi` 将所有指令源 push 到 `oe` 数组中，**顺序决定在 prompt 中的出现位置**：

```
1. home-copilot          — ~/.copilot/copilot-instructions.md
2. user-copilot-instructions — ~/.copilot/instructions/**/*.instructions.md
3. repo-copilot          — <git-root>/.github/copilot-instructions.md
4. cwd-copilot           — <cwd>/.github/copilot-instructions.md（仅 cwd ≠ git root）
5. model-agents-md       — <git-root>/AGENTS.md
6. model-claude-md       — <git-root>/CLAUDE.md  /  <git-root>/.claude/CLAUDE.md
7. model-gemini-md       — <git-root>/GEMINI.md
8. cwd-model-*           — <cwd>/AGENTS.md, CLAUDE.md, GEMINI.md（仅 cwd ≠ git root）
9. inherited-*           — 中间层（vfi walk-up 结果）
10. .github/instructions  — glob 匹配的 *.instructions.md
11. nested-agents         — 子目录嵌套 AGENTS.md（表格提示）
12. child-instructions    — LMr 递归发现的子目录指令文件
```

最终由 `lKr` 组装成 prompt 文本：

- 前 9 类（非 vscode/nested/child）包裹在 `<custom_instruction>...</custom_instruction>` 标签中
- 后 3 类（vscode/nested/child）作为 `additionalInstructions` 附加

**去重规则**（`rKr`）：同 `realPath`（symlink 解析后）或同 `content` 的文件只保留一份，sourcePath 用 `+` 连接。

### `--no-custom-instructions` 开关

```
copilot --no-custom-instructions
```

跳过整个 `eB()` 调用，不加载任何 custom instructions：

```js
// app.js — kHe
let z = l ? Promise.resolve(void 0) : eB(t, true, r, u, {...});
// l = skipCustomInstructions（来自 --no-custom-instructions）
```

#### 相关 issue / 文档

- 参考官方文档[add-repository-instructions](https://docs.github.com/en/copilot/how-tos/configure-custom-instructions/add-repository-instructions)：`.github/copilot-instructions.md`、`.github/instructions/**/*.instructions.md` 的写法与作用域
- 参考官方文档[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)：用户级 `~/.copilot/copilot-instructions.md`、`~/.copilot/instructions/`

---
## Hooks（preToolUse / Safety Net）

### Hooks 发现机制（不做 walk-up）

与 MCP / Skills 不同，Hooks **完全不做 walk-up**，只看两个固定位置（参考官方文档[use-hooks](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks)、[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)）：

1. **项目级**：`<git-root>/.github/hooks/`（在 git repo 内用当前 git root，不在 git repo 则用 cwd）
2. **用户级**：两个来源都读——`~/.copilot/hooks/`（文件 `hooks.json` / `hooks/hooks.json`）+ `config.json`（全局配置）里的内联 `hooks` 键（同 `.github/hooks/*.json` schema）。源码 `loadAllHooks`：用户级 = `<configDir>/hooks` 目录的文件配置，外加 `config.hooks` 内联配置，两者合并。

不向上遍历父目录。这直接导致下文「项目级 hook 路径解析停在 git root」与「`cc-safety-net` 自定义规则 scope」两个排障场景。需要跨子项目共用 hook 时，只能用 user-level 或 symlink。

### marketplace 分发的 Safety Net plugin 装了不触发：双 bug

#### 症状

按官方说明 `/plugin install kenryu42/copilot-safety-net` 装好 Safety Net，重启后仍能成功执行 `rm -rf <cwd 内目录>` 和 `git reset --hard HEAD~1`，没有 BLOCKED 提示。`COPILOT_ALLOW_ALL=1` 也开着。

#### 排查 → 根因

`~/.copilot/logs/process-*.log` 只有 `Loaded 1 hook(s) from 1 plugin(s)`，但整个 session **没有任何一次 hook 实际被调用**。两个 bug 叠加：

**1. plugin 自带的 `hooks/hooks.json` schema 是 Claude Code 的格式，不是 Copilot CLI 的**

错的（plugin 现状）：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{"type":"command","command":"npx cc-safety-net --copilot-cli"}]
      }
    ]
  }
}
```

对的（Copilot 官方文档）：

```json
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "type": "command",
        "bash": "npx -y cc-safety-net --copilot-cli",
        "timeoutSec": 15
      }
    ]
  }
}
```

区别：Copilot 要求 `version: 1`、camelCase `preToolUse`、没有 `matcher`、命令字段叫 `bash` 且在顶层。

作者的另一个仓库 `kenryu42/claude-code-safety-net/.github/hooks/safety-net.json` 才是正确格式，但那是项目级示例，没打进 plugin。

**2. [copilot-cli#2540](https://github.com/github/copilot-cli/issues/2540) 未修 bug**

从 marketplace / git 装的 plugin 里 `hooks/*.json` 完全不会被 Copilot 加载执行。issue 评论确认：**手动**把 hook 文件复制到项目 `.github/hooks/` 才会触发。

#### 解决

不靠 plugin，自己在项目里写正确格式的 hook：

```json
// <project-root>/.github/hooks/safety-net.json
{
  "version": 1,
  "hooks": {
    "preToolUse": [
      {
        "type": "command",
        "bash": "npx -y cc-safety-net --copilot-cli",
        "cwd": ".",
        "timeoutSec": 15
      }
    ]
  }
}
```

然后 `copilot plugin uninstall copilot-safety-net`（避免误以为 plugin 在保护）。重启 Copilot 后即生效。

实测 `--allow-all-tools`（含 `COPILOT_ALLOW_ALL=1`）下 Safety Net 仍然能拦 `git reset --hard`。Copilot 的 `preToolUse` hook 在 permission system 之前跑，不会被 allow-all 跳过。

也可以走全局：把同一段 `hooks` 对象写到 `~/.copilot/settings.json` 的 `hooks` 键（参考官方文档[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference) 明确："define hooks inline in your user configuration file (`~/.copilot/settings.json`) using the `hooks` key"；旧版曾放 `config.json` 顶层，启动时自动迁移到 `settings.json`。Copilot CLI v0.0.422+ 支持 user-level hooks）。

#### 教训

- **"支持 Copilot CLI"≠"装上就有用"**：作者的主仓库 `claude-code-safety-net` 是对的，分发的 `copilot-safety-net` plugin 是错的；分清楚两个仓库。
- **`COPILOT_ALLOW_ALL` 不背锅**：它只是关掉 confirm 弹窗，不影响 hook 触发。看到 hook 不跑先去 `~/.copilot/logs/process-*.log` 查有没有 hook 调用记录，再看是 schema 错还是 plugin 加载 bug。
- **验证 cc-safety-net 工具本身是否正常**：直接喂 stdin 测：
  ```bash
  echo '{"toolName":"bash","toolArgs":"{\"command\":\"git reset --hard\"}"}' \
    | npx -y cc-safety-net --copilot-cli
  ```
  正常会输出 `{"permissionDecision":"deny",...}`。注意输入字段是 `toolName` / `toolArgs`（驼峰），且 `toolArgs` 是**字符串化**的 JSON 不是对象。

#### 相关 issue / 文档

- 参考官方文档[use-hooks](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/use-hooks)：Copilot CLI 的 hooks（仓库级 `.github/hooks/`、用户级 `~/.copilot/hooks/`、`settings.json` 的 `hooks` 键）
- 参考官方文档[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)：用户级 `~/.copilot/hooks/` 与内联 `hooks` 键
- [coding agent hooks 规范](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-hooks)：hook 配置 schema（cloud agent 侧）
- safety-net 主仓库 issue：[#24](https://github.com/kenryu42/claude-code-safety-net/issues/24)
- Copilot CLI plugin hook 不加载：[#2540](https://github.com/github/copilot-cli/issues/2540)

---

### 项目级 hook 路径解析停在 git root（多 repo 工作区漏装）

#### 症状

工作区是"父目录套多个独立 git 仓库"结构（如 `~/projects/{repo-a,repo-b,...}`，每个子目录是独立 repo，父目录本身不是 git）。父目录 `.github/hooks/safety-net.json` 配好后，cd 进父目录启动 copilot 正常；但 cd 进任何子项目启动 copilot，hook 完全不触发。

#### 根因

Copilot CLI `getHooksDir` 的查找逻辑：在 git repo 内用 **当前 git root**，否则用 cwd，**不会向上查父目录**。子项目自己是独立 git repo，git root 就是子项目自己，看不到父目录的 hook。env vars 改不了这个路径。

#### 解决：父目录 `.envrc` 自动 symlink

cd 进父目录时，让 direnv 把父目录 hook 软链到所有子目录的 `.github/hooks/`，并把 symlink 写入子项目的 `.git/info/exclude`（不污染 `.gitignore`，不进版本控制）。新增子项目 cd 一次父目录就自动同步。

复用[Walk-Up 总览里定义的 `link_into_subdirs` helper](#通用-workarounddirenv-symlink)：

```bash
# .envrc（link_into_subdirs 定义见 Walk-Up 总览节）
link_into_subdirs "$PWD/.github/hooks/safety-net.json" '.github/hooks/safety-net.json'
```

direnv 本身不能改 copilot 找 hook 的路径（copilot 是独立进程读文件系统），它只是帮你**自动维护 symlink 实体**。如果不想限定子项目而是想全局生效，把 hook 搬到 `~/.copilot/hooks/safety-net.json` 即可。

#### 教训

- "项目级 hook" = **当前 git root 级**，不是当前工作区根级。多 repo 工作区要么走 user-level hook（`~/.copilot/hooks/`），要么自己分发文件。
- 改 hook 文件 / 加新 symlink 后，**当前 copilot session 不会受影响**（hook 启动时一次性加载），下次启动 copilot 才生效。
- `direnv allow` **基于 `.envrc` 内容 hash 授权**：改一次 `.envrc` 就要重新 allow 一次，hash 不变之后 cd 进出都自动加载，不需要每次 allow。

---

### `cc-safety-net` 自定义规则：user scope vs project scope

#### 场景

父目录 `.safety-net.json` 写了自定义规则（例如禁止所有 `gh` 子命令、要求用 GitHub MCP server 代替）。但子目录是独立 git repo，Copilot 的 cwd 在子仓库里时 safety-net 只从 **cwd** 读 `.safety-net.json`，不向上遍历——规则不生效。

#### 根因

`cc-safety-net` 加载自定义规则的搜索路径只有两个，**不做父目录遍历**：

1. **User scope**：`~/.cc-safety-net/config.json`（始终加载）
2. **Project scope**：`$CWD/.safety-net.json`（仅当前目录）

同名 rule project scope 优先覆盖 user scope，其余合并。

#### 解决

跨项目通用的规则放 user scope：

```bash
mkdir -p ~/.cc-safety-net
# 把规则写入 ~/.cc-safety-net/config.json
```

实际生效范围 = "user scope 规则在全局可见" × "hook 只在装了 `.github/hooks/safety-net.json` 的项目里激活"。所以规则虽然全局定义，但**只在装了 hook 的项目及其子目录内拦截**。

#### 验证

```bash
cd <project-with-hook>
npx -y cc-safety-net --verify-config       # 应显示 user config 里的规则
npx -y cc-safety-net explain "gh repo view"  # 应显示 BLOCKED
```

#### 教训

- **想跨子仓库生效的规则放 user scope**，不要靠 symlink `.safety-net.json`——那是 project scope，只作用于 cwd。
- **hook 文件仍然需要 symlink**（`.github/hooks/safety-net.json`），因为 Copilot 只从 git root 的 `.github/hooks/` 读 hook。见上一节。
- 区分"规则定义在哪"和"hook 在哪激活"：前者决定规则内容，后者决定拦截是否发生。

---
## MCP 配置

> MCP（Model Context Protocol，模型上下文协议）：agent 借它挂载外部工具 / 数据源。Copilot CLI 有多处 MCP 配置文件，发现逻辑复用本章前面的 walk-up（向上查找）机制。

### 单次运行注入 MCP profile（`--additional-mcp-config`）

在 Copilot CLI `1.0.66-1` 上用 `copilot --help` 核对：

```text
--additional-mcp-config <json>
  Additional MCP servers configuration as JSON string or file path (prefix with @)
  (can be used multiple times; augments config from ~/.copilot/mcp-config.json for this session)
```

实际含义：

- `--additional-mcp-config '{"mcpServers": {...}}'`：单次运行内联一段 JSON。
- `--additional-mcp-config @/abs/path/profile.json`：从文件读 JSON；`@` 前缀是 Copilot CLI 自己的"引用文件"语法。
- daemon / orchestrator（编排器）想给每个 agent 配不同工具时，优先用这种 per-run / per-agent 注入，而不是去改共享的 workspace `.mcp.json`。除非用户明确要改 workspace 配置，否则把 `.mcp.json` 当成开发者交互会话自己的配置，不要动它。

---

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

复用 [Walk-Up 总览里的 `link_into_subdirs` helper](#通用-workarounddirenv-symlink)：

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

## Skills 发现

Copilot CLI 的 skill 来自三类位置，CLI 内置 `/skills` 帮助与官方文档一致（参考官方文档[add-skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills)、[about-agent-skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills)、[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)）：

- **项目级**（随 cwd→git root walk-up 收录，boundary = git root，无 git 回退 `$HOME`；source `project` / `inherited`）：`.github/skills/`、`.agents/skills/`、`.claude/skills/`
- **个人级**（固定路径；source `personal-copilot` / `personal-agents`）：`~/.copilot/skills/`、`~/.agents/skills/`
- **自定义 / 内置**：`/skills add <dir>` 或 env `COPILOT_SKILLS_DIRS`（逗号分隔绝对路径，source `custom`）；CLI 安装目录的 `builtin-skills/`（source `builtin`）

CLI 内置 `/skills` 帮助原文（`app.js` 字面量）就是这份清单：

```text
Skills are loaded from:
• Project: .github/skills/, .agents/skills/, or .claude/skills/
• Personal: ~/.copilot/skills/ or ~/.agents/skills/
• Custom: Directories added via /skills add
```

个人级 `~/.copilot/skills` 的解析见源码（`COPILOT_HOME` 可整体改写 configDir）：

```js
// app.js — mtt：个人级 skill 根 = configDir/skills
function mtt(t) {
  let e = t?.configDir ?? process.env.COPILOT_HOME ?? join(homedir(), ".copilot");
  return join(e, "skills");        // = ~/.copilot/skills
}
```

**同名时项目级覆盖个人级**（参考官方文档[add-skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills)、[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)）。Custom agents 同理：个人级 `~/.copilot/agents/`、项目级 `.github/agents/`，同名项目级优先（参考官方文档[create-custom-agents-for-cli](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli)）。

⚠️ **`<project>/.copilot/skills` 不是任何一种约定，Copilot CLI 不读它。** 项目级只有 `.github/skills`、`.agents/skills`、`.claude/skills` 三种；`.copilot/skills` 仅在 home（`~/`）下作为**个人级**（`~/.copilot/skills`）才有效。别把个人级路径照搬成项目里的 `<project>/.copilot/skills` 软链——那条不会被发现。

### 项目级 `.agents/skills` 上溯停在 git root（与 hooks/mcp 同款）

#### 症状

工作区是"父目录套子项目"结构，父目录 `.agents/skills/<skill-name>/SKILL.md` 写好了。在父目录起 copilot 能看到 skill；`cd <subdir>` 启动 copilot，`/skills` 里看不到那些 skill，agent 提示词里 `<available_skills>` 也没有。`~/.agents/skills/` 下的 user-level skill 始终能看到，因此现象是"项目级 skill 漏掉、user 级 skill 正常"。

#### 根因

Skill 发现走的是和 `.mcp.json`、`.github/hooks/` 完全相同的 `bBt` walk-up 函数，**boundary 同样是 git root**（即 `projectRoot`），所以子项目自己是 git repo 时上溯立刻停在子项目根，看不到父目录的 `.agents/skills`。

扫的就是本节开头那三类项目级 convention（`.github/skills` / `.agents/skills` / `.claude/skills`，每个独立调一次 `bBt`）；个人级 `~/.copilot/skills`（`personal-copilot`）、`~/.agents/skills`（`personal-agents`）、`builtin-skills/` 与 env `COPILOT_SKILLS_DIRS`（最高优先）走固定路径、不受 walk-up boundary 限制。

#### 代码支撑（`app.js:~676` 附近）

```js
// 项目级三套 convention 的入口
async function j7e(t, e, r, n) {
  // t=".agents" / ".github" / ".claude", e="skills", r=projectRoot, n=cwd
  if (n) {
    let o = r ?? wBt.homedir();          // ★ boundary：projectRoot 否则回退 HOME
    return yQe(t, e, { startPath: n, boundary: o })
  }
  return r ? yQe(t, e, { root: r }) : []
}

async function LIi(t, e=[], r, n=[], o, s={}) {
  // t=projectRoot, o=cwd
  let l = a ? [
    ...await j7e(".github", "skills", t, o),
    ...await j7e(".agents",  "skills", t, o),
    ...await j7e(".claude",  "skills", t, o),
  ] : [];
  let c = a ? [
    { path: GR.join(ma(r,"config"), "skills"),       source: "personal-copilot" },  // 1.0.66 实为 mtt(): join(configDir, "skills") = ~/.copilot/skills
    { path: GR.join(homedir(), ".agents", "skills"), source: "personal-agents"  },
  ] : [];
  let d = [
    ...process.env[Tqr]?.split(",").filter(Boolean) ?? [],   // COPILOT_SKILLS_DIRS
    ...e,                                                     // 调用方传入的 customDirs
  ].map(p => ({path: p.trim(), source: "custom"}));
  return [...l, ...c, ...n, ...d].filter(p => EQe(p.path));
}
```

`yQe` 在 `convention="directory"` 模式下转调 `bBt`（与 [本章 MCP 配置里的 `.mcp.json` walk-up](#mcpjson-上溯停在-git-root多-repo-工作区漏装) 是同一类机制）：

```js
// 简化复述：从 startPath 向上走，每层检查 `${a}/.agents/skills` 存在则收录
let s = normalize(boundary), a = normalize(startPath), l = 0;
for (;;) {
  if (existsSync(join(a, ".agents", "skills"))) o.push({path: ..., source: l===0?"project":"inherited"});
  if (a === s) break;                          // ★ 撞 boundary 就停
  let u = dirname(a);
  if (u === a) break;
  a = u; l++;
}
```

#### 与 hooks/mcp 的差异

| 项                | hooks (`.github/hooks/`)         | mcp (`.mcp.json`)                | skills (`.agents/skills/` 等)                          |
| ----------------- | -------------------------------- | -------------------------------- | ------------------------------------------------------ |
| Walk-up           | 否（只看 git root 一层）         | 是（cwd→git root，沿途合并）     | 是（cwd→git root，沿途收录）                           |
| Boundary          | git root                         | git root                         | git root；**没 git repo 时回退 `$HOME`**               |
| User scope 路径   | `~/.copilot/hooks/`              | `~/.copilot/mcp-config.json`     | `~/.copilot/skills` + **`~/.agents/skills`**           |
| Source 标签       | -                                | `Project` / `Inherited`          | `project` / `inherited` / `personal-agents` / `builtin`|
| Env 覆盖          | -                                | -                                | `COPILOT_SKILLS_DIRS`（逗号分隔，绝对路径）            |

注意 skills 比 hooks/mcp 多了一条 user-level 路径 **`~/.agents/skills`**：它是跨工具共享个人 skill 的中立目录，独立于项目级 `.agents/skills`（后者才走 walk-up、boundary=git root）。

另一个重要细节：**boundary 的 fallback 是 `$HOME` 而不是 `/`**。所以在"父目录不是 git repo、子项目也不是 git repo"（即 cwd 完全不在任何 git repo 内）时，会一路扫到家目录，反而能拿到祖先 `.agents/skills`。一旦 cwd 进入任何 git repo，boundary 就钉到那个 git root 上了。

#### 解决

复用[Walk-Up 总览里的 `link_into_subdirs` helper](#通用-workarounddirenv-symlink)：

```bash
# .envrc（父目录）
link_into_subdirs "$PWD/.agents/skills" '.agents/skills'
```

或者按 skill 粒度软链单个 skill 进子项目：

```bash
mkdir -p <subdir>/.agents/skills
ln -s ../../../.agents/skills/<skill-name> <subdir>/.agents/skills/<skill-name>
```

如果想全局生效（任意 cwd 都能看到），把 skill 软链到 user-level：

```bash
ln -s /path/to/<skill-name> ~/.agents/skills/<skill-name>
```

临时一次性测试可以用 env：

```bash
COPILOT_SKILLS_DIRS=/abs/path/to/.agents/skills copilot
```

#### 验证

```bash
# 启动后在 copilot 里
/skills           # 列表会显示来源标签 (project/inherited/personal-agents/builtin)
/env              # 看 skills 节，确认实际加载的路径
```

或在 prompt 里直接问 agent：列出可用 skills（agent 拿到的 `<available_skills>` 就是 `LIi` 的过滤结果）。

#### 教训

- "项目级 skill" 跟 hook/mcp 一样 = **当前 git root 级**，不是用户主观的工作区根。多 repo 套娃要么 symlink 进每个子 repo，要么挪到 `~/.agents/skills/`。
- **`.agents/skills` 和 `~/.agents/skills` 是两条独立路径**：前者走 walk-up + git root boundary，后者走固定 user-level。这也是为什么 `~/.agents/skills/<x>` 永远在、但项目里 `.agents/skills/<x>` 时有时无。
- 想验证是路径问题还是 SKILL.md 解析问题：先把目标 skill 临时软链到 `~/.agents/skills/`，能出现就是路径问题；仍然不出现就检查 `SKILL.md` frontmatter（`name` 必须匹配 `^[a-zA-Z0-9][a-zA-Z0-9._\- ]*$` 且 ≤64 字符；`description` ≤1024 字符；`user-invocable: false` 会从用户列表里隐藏；`disable-model-invocation: true` 会从模型列表里隐藏）。
- skill 改了之后**当前 session 不会重载**，下次启动 copilot 才生效（`Y3` 内部还有按 `JSON.stringify(args)` 的缓存 `rbe`）。

#### 相关 issue / 文档

- 参考官方文档[add-skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills)：项目级/个人级 skill 目录、`SKILL.md` frontmatter、`allowed-tools` 预批
- 参考官方文档[about-agent-skills](https://docs.github.com/en/copilot/concepts/agents/about-agent-skills)：skill 概念与跨产品（CLI / IDE / cloud agent）支持
- 参考官方文档[config-dir-reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference)：`~/.copilot/` 目录布局（含 `skills/`、`agents/`）
- 参考官方文档[create-custom-agents-for-cli](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/create-custom-agents-for-cli)：custom agents 的个人级/项目级目录与优先级

---
