# MCP 模式（默认）

## 关键不变量（理解后再用）

- **写之前必须先 read**：`portal_read` 返回 `file_hash` 和每段 `range_hash`；`portal_patch` 必须带回。中途别人改了文件，patch 会被服务端拒绝并返回当前 hash + 内容。
- **patch 是事务的**：一次 patches_json 内多段全成或全败；overlapping patches 直接拒。
- **bash session 粘性**：第一次 `portal_bash` 自动建一个 `bash -i`，cwd / export 跨调用保留；想清空 `portal_bash_close`。
- **文件 IO 与 bash 共用同一 SSH 连接**（连接池复用），不会因为多工具就开多条 TCP。

## 工具速查（18 个 portal_*）

### 8 个 core（首选）

| 工具 | 用途 | 必需参数 | 返回关键字段 |
|---|---|---|---|
| `portal_read` | 读文件或行范围 | `host, path, [start, end]` | `content, file_hash, range_hash, total_lines` |
| `portal_patch` | 改文件（hash 防冲突） | `host, path, file_hash, patches_json` | `result=ok\|error, file_hash`（成功）/ `current_file_hash`（hash mismatch） |
| `portal_grep` | 远端 rg / grep | `host, path, pattern, [glob, file_type, ignore_case, max_count]` | `engine, matches[{file,line,text}]` |
| `portal_glob` | 远端文件列表 | `host, pattern, [path]` | `engine, files[]` |
| `portal_bash` | 持久 shell（cwd/env 跨调用保留） | `host, command, [timeout]` | `host, session_id, output, exit_code` |
| `portal_bash_close` | 关闭主机 session | `host` | 状态字符串 |
| `portal_bash_status` | 查看缓存的 session | — | host→session_id 映射 |
| `portal_cleanup_tmps` | 清孤儿 patch tmp | `host, directory, [max_age_s]` | `scanned, removed, skipped` |

### 10 个高层（mode 切换）

| 工具 | 关键参数 | 用途 |
|---|---|---|
| `portal_host` | `action=list\|register\|remove` | 主机注册（仅当需要 tag 分组时；`~/.ssh/config` 别名自动解析） |
| `portal_transfer` | `direction=upload\|download\|sync` | SFTP 文件传输（二进制安全） |
| `portal_tunnel_open` | `mode=local\|reverse\|socks` | 开 SSH 隧道，返回 `tunnel_id` |
| `portal_tunnel_close` | `tunnel_id` | 关隧道 |
| `portal_tunnel_list` | — | 列所有活跃隧道 |
| `portal_multi_exec` | `mode=parallel\|rolling\|broadcast`，`hosts_json\|group_tag` | 多机命令编排（单机用 portal_bash） |
| `portal_playbook` | `host\|group_tag`，`playbook_json` | 多步骤剧本 |
| `portal_ping` | optional `hosts_json` | 健康检查 |
| `portal_audit` | `view=snapshot\|history\|stats\|policy` | 服务器内部状态 + 审计日志 |
| `portal_check` | `host`, optional `command` | policy dry-run（不执行） |

> Mode 切换工具的详细参数和示例在 server 端 docstring 里——agent 看到的工具描述包含完整例子。

## 安全规则（强制）

1. **默认只可写远端 `/tmp/` 路径**。改用户家目录、项目代码目录、`/etc`、`/usr` 等任何非 `/tmp` 位置之前，**必须先问用户**并明确得到许可。
2. 真实项目目录上做实验，先建议复制到 `/tmp/<task-name>/` 沙箱，确认无误后让用户决定是否合并回真实路径。
3. patch 失败（hash mismatch）后**不要立刻覆盖式重试**——先 `portal_read` 看新 hash 和新内容，识别是不是别的 agent / 用户在并发改；是的话向用户汇报并等指示。
4. `portal_bash` cwd 是粘性的——执行任何命令前先 `pwd` 确认，不要假定还在上次目录（被 timeout 关 / 用户在另一会话里 close 都会重置）。
5. **改文件优先用 `portal_patch`**（带 hash 校验）；只在 portal_patch 不适用时（二进制、整目录、非文本）才用 `portal_transfer`。**绝对不要在 `portal_bash` 里用 `cat > file` / `sed -i` / `tee` 等命令直接覆盖远端文件**——这绕开了并发安全模型，多 agent 场景下会丢改动。

## 典型工作流

### A. 在远端项目里做小改动

```
1. portal_grep host=<H> path=<dir> pattern="<symbol>" glob="*.py"
   → 找到目标 file:line
2. portal_read  host=<H> path=<file> start=<n-5> end=<n+10>
   → 拿到 file_hash + range_hash
3. portal_patch host=<H> path=<file> file_hash=<...>
                patches_json='[{"start":<n>,"end":<n>,"contents":"<new>\n","range_hash":"<from 2>"}]'
4. 如 error 且 reason 含 "hash mismatch"：回到 step 2 重读，识别冲突再决定
```

### B. 在远端跑命令并保留上下文

```
1. portal_bash host=<H> command="cd /tmp/sandbox && python -m venv .venv && source .venv/bin/activate"
2. portal_bash host=<H> command="pip install ..."   # 仍在 /tmp/sandbox 且 venv 已激活
3. portal_bash host=<H> command="python script.py"
4. 完成后 portal_bash_close host=<H>
```

### C. 多 patch 一次性改完同一文件

把多段 patch 放在一个 `patches_json` 里——服务端从下到上应用避免行号漂移。重叠会被拒绝。改动跨度太大宁可拆成多个 read+patch 循环，也不要试图用一个超长 patch。
