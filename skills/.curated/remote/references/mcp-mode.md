# MCP 模式（默认）

## 关键不变量（理解后再用）

- **写之前必须先 read**：`remote_read` 返回 `file_hash` 和每段 `range_hash`；`remote_patch` 必须带回。中途别人改了文件，patch 会被服务端拒绝并返回当前 hash + 内容。
- **patch 是事务的**：一次 patches_json 内多段全成或全败；overlapping patches 直接拒。
- **bash session 粘性**：第一次 `remote_bash` 自动建一个 `bash -i`，cwd / export 跨调用保留；想清空 `remote_bash_close`。
- **文件 IO 与 bash 共用同一 SSH 连接**（连接池复用），不会因为多工具就开多条 TCP。

## 工具速查

| 工具 | 用途 | 必需参数 | 返回关键字段 |
|---|---|---|---|
| `remote_read` | 读文件或行范围 | `host, path, [start, end]` | `content, file_hash, range_hash, total_lines` |
| `remote_patch` | 改文件（hash 防冲突） | `host, path, file_hash, patches_json` | `result=ok\|error, file_hash`（成功）/ `current_file_hash`（hash mismatch） |
| `remote_grep` | 远端 rg / grep | `host, path, pattern, [glob, file_type, ignore_case, max_count]` | `engine, matches[{file,line,text}]` |
| `remote_glob` | 远端文件列表 | `host, pattern, [path]` | `engine, files[]` |
| `remote_bash` | 持久 shell | `host, command, [timeout]` | `host, session_id, output` |
| `remote_bash_close` | 关闭主机 session | `host` | 状态字符串 |
| `remote_bash_status` | 查看缓存的 session | — | host→session_id 映射 |

## 安全规则（强制）

1. **默认只可写远端 `/tmp/` 路径**。改用户家目录、项目代码目录、`/etc`、`/usr` 等任何非 `/tmp` 位置之前，**必须先问用户**并明确得到许可。
2. 真实项目目录上做实验，先建议复制到 `/tmp/<task-name>/` 沙箱，确认无误后让用户决定是否合并回真实路径。
3. patch 失败（hash mismatch）后**不要立刻覆盖式重试**——先 `remote_read` 看新 hash 和新内容，识别是不是别的 agent / 用户在并发改；是的话向用户汇报并等指示。
4. `remote_bash` cwd 是粘性的——执行任何命令前先 `pwd` 确认，不要假定还在上次目录（被 timeout 关 / 用户在另一会话里 close 都会重置）。
5. 不要直接调用 `ssh-shell-mcp` 上游的 `ssh_write` / `ssh_run` 等等价工具——它们没 hash 校验，会绕开本 skill 并发安全模型。优先用 `remote_*` 系列。

## 典型工作流

### A. 在远端项目里做小改动

```
1. remote_grep host=<H> path=<dir> pattern="<symbol>" glob="*.py"
   → 找到目标 file:line
2. remote_read  host=<H> path=<file> start=<n-5> end=<n+10>
   → 拿到 file_hash + range_hash
3. remote_patch host=<H> path=<file> file_hash=<...>
                patches_json='[{"start":<n>,"end":<n>,"contents":"<new>\n","range_hash":"<from 2>"}]'
4. 如 error 且 reason 含 "hash mismatch"：回到 step 2 重读，识别冲突再决定
```

### B. 在远端跑命令并保留上下文

```
1. remote_bash host=<H> command="cd /tmp/sandbox && python -m venv .venv && source .venv/bin/activate"
2. remote_bash host=<H> command="pip install ..."   # 仍在 /tmp/sandbox 且 venv 已激活
3. remote_bash host=<H> command="python script.py"
4. 完成后 remote_bash_close host=<H>
```

### C. 多 patch 一次性改完同一文件

把多段 patch 放在一个 `patches_json` 里——服务端从下到上应用避免行号漂移。重叠会被拒绝。改动跨度太大宁可拆成多个 read+patch 循环，也不要试图用一个超长 patch。
