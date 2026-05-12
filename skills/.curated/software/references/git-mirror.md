# Git 镜像仓库方案

## 场景

多台开发设备协作同一个 GitHub 仓库，但部分设备（如 HPC 集群）无法直连 GitHub。需要一个中间节点做双向镜像，让所有设备体验统一。

## 架构

```
        GitHub (origin)  ← 中心仓库，所有权威数据在此
          ↑↓ push/fetch                ↑↓ GitHub Actions (自动)
    ┌─────┴──────┐              ┌───────┴──────────┐
    │ 联网设备    │              │ 镜像服务器        │
    │ origin=GitHub│             │ /srv/git/*.git    │
    └────────────┘              │ pre-receive hook  │
                                │ post-receive hook │
                                └────────┬─────────┘
                                         │ ssh
                                   ┌─────┴────┐
                                   │ 离线设备  │
                                   │ origin=镜像│
                                   └──────────┘
```

- **联网设备**：`origin` 直指 GitHub，正常 push/fetch
- **镜像服务器**：有公网 IP、24/7 在线、能访问 GitHub 的 VPS 或服务器
- **离线设备**：`origin` 指向镜像服务器，通过 SSH（可经 HTTP 代理穿透）推拉

## 搭建步骤

### 1. 镜像服务器上创建 bare 仓

```bash
sudo mkdir -p /srv/git && sudo chown <user>:<user> /srv/git
git clone --mirror git@github.com:<owner>/<repo>.git /srv/git/<repo>.git
```

`/srv/git/` 是 [Pro Git](https://git-scm.com/book/en/v2/Git-on-the-Server-Setting-Up-the-Server) 推荐的自托管 git 路径（FHS `/srv` = site-specific served data）。

### 2. 修正 mirror refspec

`git clone --mirror` 默认拉全量 refs 包括 `refs/pull/*`，但 GitHub 不允许客户端写这些 refs。改成只同步 branches + tags：

```bash
cd /srv/git/<repo>.git
git config --unset remote.origin.mirror
git config --unset-all remote.origin.fetch
git config --add remote.origin.fetch '+refs/heads/*:refs/heads/*'
git config --add remote.origin.fetch '+refs/tags/*:refs/tags/*'
git config --add remote.origin.push '+refs/heads/*:refs/heads/*'
git config --add remote.origin.push '+refs/tags/*:refs/tags/*'
# 清理已拉下来的 pull refs
git for-each-ref --format='delete %(refname)' refs/pull | git update-ref --stdin
```

### 3. 两把 SSH key

| Key | 用途 | 私钥位置 | 公钥位置 |
|-----|------|---------|---------|
| **A: 镜像→GitHub** | hook 推回 GitHub | 镜像服务器 `~/.ssh/` | GitHub repo Deploy Keys (write) |
| **B: Actions→镜像** | workflow 推到镜像 | GitHub Secrets (base64) | 镜像服务器 `~/.ssh/authorized_keys` |

Key-A 建议用 repo 级 Deploy Key（无 passphrase），而非账号全局 key，权限最小化。

Key-B 在 `authorized_keys` 中限制只能执行 `git-receive-pack`：

```
command="export SU2QM_PUSH_SOURCE=actions && cd /srv/git/<repo>.git && exec git-receive-pack /srv/git/<repo>.git",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty ssh-ed25519 AAAA... <comment>
```

`SU2QM_PUSH_SOURCE=actions` 环境变量是留给 hook 识别"谁在推"的标记（名字可自定义）。

### 4. pre-receive hook（分支保护）

离线设备只允许推 feature 分支，防止 split-brain：

```bash
#!/usr/bin/env bash
# /srv/git/<repo>.git/hooks/pre-receive
if [[ "$<PUSH_SOURCE_VAR>" == "actions" ]]; then exit 0; fi

PROTECTED="^refs/heads/(main|develop)$"
REJECT=0
while read oldrev newrev refname; do
  if [[ "$refname" =~ $PROTECTED ]]; then
    echo "*** REJECTED: push to $refname not allowed from this source."
    REJECT=1
  fi
done
exit $REJECT
```

### 5. post-receive hook（自动推回 GitHub）

```bash
#!/usr/bin/env bash
# /srv/git/<repo>.git/hooks/post-receive
unset GIT_DIR GIT_WORK_TREE
cd /srv/git/<repo>.git || exit 1

LOG=/srv/git/<repo>.git/hooks/post-receive.log
exec >> "$LOG" 2>&1

echo "[$(date -Iseconds)] post-receive triggered (source=${<PUSH_SOURCE_VAR>:-external})"
while read oldrev newrev refname; do
  echo "  ref=$refname  ${oldrev:0:8} -> ${newrev:0:8}"
done

# Actions 推入的不用再推回 GitHub
if [[ "$<PUSH_SOURCE_VAR>" == "actions" ]]; then
  echo "  source=actions, skip push (no bounce)"
  exit 0
fi

echo "  pushing to GitHub..."
git push origin --prune 2>&1
```

### 6. GitHub Actions workflow（GitHub → 镜像）

```yaml
name: Mirror to server
on:
  push:
    branches: ['**']
    tags: ['**']
  delete:
  workflow_dispatch:

concurrency:
  group: mirror
  cancel-in-progress: false

jobs:
  mirror:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - run: |
          git fetch --prune origin '+refs/heads/*:refs/remotes/origin/*'
          git fetch --tags --prune origin
      - name: Install SSH key
        env:
          KEY_B64: ${{ secrets.<SECRET_NAME> }}
        run: |
          mkdir -p ~/.ssh && chmod 700 ~/.ssh
          printf '%s' "$KEY_B64" | base64 -d > ~/.ssh/id_mirror
          chmod 600 ~/.ssh/id_mirror
          ssh-keyscan -H <mirror-host> >> ~/.ssh/known_hosts 2>/dev/null
      - name: Push
        run: |
          git remote add mirror ssh://<user>@<mirror-host>/srv/git/<repo>.git
          for ref in $(git for-each-ref --format='%(refname)' refs/remotes/origin/ | grep -v '/HEAD$'); do
            branch="${ref#refs/remotes/origin/}"
            GIT_SSH_COMMAND='ssh -i ~/.ssh/id_mirror -o IdentitiesOnly=yes' \
              git push mirror "+${ref}:refs/heads/${branch}" || true
          done
          GIT_SSH_COMMAND='ssh -i ~/.ssh/id_mirror -o IdentitiesOnly=yes' \
            git push mirror --tags || true
```

Secret 用 base64 单行编码（`base64 -w0 < key > key.b64`）避免 GitHub Secrets 粘贴时换行/字符损坏。

### 7. 离线设备配置

如果离线设备需要通过 HTTP 代理访问镜像服务器：

```
# ~/.ssh/config
Host mirror-alias
    HostName <mirror-host>
    User <user>
    ProxyCommand ncat --proxy <proxy-ip>:<port> --proxy-type http %h %p
```

然后 `git remote add origin ssh://mirror-alias/srv/git/<repo>.git`。

## 防回环机制

关键设计：`authorized_keys` 里的 `command=` 给 Actions key 注入环境变量 → hook 检测该变量 → Actions 来源不触发 push 回 GitHub。

```
Actions push → Alibaba → post-receive → 检测 source=actions → 跳过 → 链止 ✅
HPC push → Alibaba → post-receive → 检测 source=hpc → push GitHub → Actions 触发 →
  → push Alibaba（no-op，refs 没变）→ post-receive → source=actions → 跳过 → 链止 ✅
```

## 注意事项

- **不要双向同时推同一分支**：这是 bidirectional mirror 的经典 split-brain 坑。用 `pre-receive` hook 限定离线设备只推 feature 分支，保护分支由联网设备统一管理
- **hooks 不在 git 版本控制中**：`hooks/` 是 bare 仓本地目录，clone/push/pull 不会携带。建议在项目 AGENTS.md 或 README 中记录 hook 逻辑
- **Actions 配额**：公开仓免费，私有仓有月度分钟限制。每次 push 触发一次 workflow，通常 20-60 秒
- **mirror clone 的 /srv/git 路径**：FHS 标准，也是 Pro Git 官方教程用的路径。单用户场景 `~/git/` 也行
- **Key-B 用 base64 传**：GitHub Secrets 粘贴 OpenSSH PEM 格式经常丢换行导致 `error in libcrypto`，base64 单行编码彻底规避
