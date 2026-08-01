> 本文是 `reference/shell-integration.md` 的中文翻译副本，随上游同步需重译；行为以英文原文为准。

# Shell 集成参考

Worktrunk shell 集成的工作方式，以及如何调试问题。

## 为何需要 shell 集成

子进程无法更改父 shell 的当前目录。当
`wt switch feature` 运行时，`wt` 二进制文件作为子进程运行，无法让终端
执行 `cd`。

Worktrunk 通过**分离式指令文件传递**解决此问题：shell 包装器
创建两个临时文件，`wt` 向其中一个写入原始路径（cd），向另一个写入 shell 命令
（`--execute` 载荷），然后包装器在 `wt`
退出后应用两者。分离式设计消除了 cd 指令造成的 shell 注入——CD
文件保存的是从不作为 shell 解析的原始路径。包装器的步骤和
简化实现参见：[Shell 包装器的工作方式](#how-the-shell-wrapper-works)。

## 安装

```bash
# Auto-install for all shells (bash, zsh, fish, nushell (experimental), PowerShell)
wt config shell install

# Or manual installation - add to the shell config:
# bash (~/.bashrc):
eval "$(wt config shell init bash)"

# zsh (~/.zshrc):
eval "$(wt config shell init zsh)"

# fish (~/.config/fish/config.fish):
wt config shell init fish | source

# nushell (experimental) — save to vendor autoload directory:
wt config shell init nu | save -f ($nu.vendor-autoload-dirs | last | path join wt.nu)

# PowerShell ($PROFILE):
Invoke-Expression (& wt config shell init powershell | Out-String)
```

## 检查状态

```bash
# Show shell integration status
wt config show
```

RUNTIME 一节会显示当前会话中的 shell 集成是否处于活动
状态。

## 警告消息

当 shell 集成未工作时，`wt switch` 会显示警告并说明原因。

### "shell wrapper is out of date"

**含义**：当前 shell 仍加载着采用分离式设计之前的旧包装器。当前
版本不再把 shell 命令写入该 wrapper 的单个指令
文件，因为这会把可信的目录路径与任意 shell 内容混合。

**修复**：运行 `wt config shell install`，然后重启 shell（或重新加载其
配置），以启用当前的分离式文件包装器。

### "shell integration not installed"

**含义**：当前 shell 的配置文件中没有
`eval "$(wt config shell init ...)"` 这一行。当前 shell 根据
进程树检测（并以 `$SHELL` 兜底），因此这里指的是实际调用 wt
的 shell，不一定是登录 shell。

**修复**：运行 `wt config shell install`，或手动添加该行。

### "shell integration installed but not active"

**含义**：当前 shell 已配置 shell 集成，但 shell
函数尚未加载到本会话中——通常是因为会话在安装前就已
启动。

**修复**：打开新终端，或运行 `source ~/.bashrc`（或等效命令）。如果
重启后消息仍然存在，`wt config show` 会报告检测到的
shell、`$SHELL` 和每种 shell 的集成状态。

### "ran ./path/to/wt; shell integration wraps wt"

**含义**：调用二进制文件时使用了显式路径（例如 `./target/debug/wt`
或 `/usr/local/bin/wt`），而不是只使用 `wt`。shell 包装器只会拦截
裸命令 `wt`。

**修复**：使用不带路径的 `wt`。若要测试开发构建，请设置 `WORKTRUNK_BIN`：
```bash
export WORKTRUNK_BIN=./target/debug/wt
wt switch feature  # Now uses the dev build with shell integration
```

### "ran git wt; running through git prevents cd"

**含义**：使用了 `git wt`（git 别名）而不是 `wt`。Git 会把 Worktrunk 作为
子进程运行，绕过 shell 包装器。

**修复**：需要切换目录时，请直接使用 `wt`，不要使用 `git wt`。

### "Alias bypasses shell integration"

**含义**：`alias gwt="/usr/bin/wt"` 或 `alias gwt="wt.exe"`
这类别名直接指向二进制文件，而不是 shell 函数。

安装 shell 集成后，它会创建一个名为 `wt`（或
`git-wt`）的 shell 函数。如果别名指向二进制文件路径，就会绕过该函数，
导致 shell 集成无法工作。

**会绕过的示例**（不会自动 cd）：
```bash
alias gwt="/usr/bin/wt"
alias gwt="wt.exe"
alias wt="/path/to/wt"
```

**修复**：更改别名，使其指向函数名而不是二进制文件：
```bash
alias gwt="wt"       # Good - uses the shell function
alias gwt="git-wt"   # Good - uses the shell function
```

`wt config show` 会检测这些有问题的别名，并显示包含
建议修复方式的警告。

## <a id="how-the-shell-wrapper-works"></a>Shell 包装器的工作方式

shell 包装器（由 `wt config shell install` 安装）会定义一个 shell
函数，它会：

1. 创建两个临时文件（cd 和 exec）
2. 设置 `WORKTRUNK_DIRECTIVE_CD_FILE` 和 `WORKTRUNK_DIRECTIVE_EXEC_FILE`
3. 运行真正的 `wt` 二进制文件
4. 使用 `cd -- "$(< file)"` 读取 CD 文件（原始路径，不进行 shell 解析）
5. 如果 EXEC 文件非空，则加载该文件（用于 `--execute` 载荷）
6. 清理两个临时文件

简化示例（实际包装器还会处理补全和边界情况）：

```bash
wt() {
    local cd_file exec_file exit_code=0
    cd_file="$(mktemp)"
    exec_file="$(mktemp)"

    WORKTRUNK_DIRECTIVE_CD_FILE="$cd_file" WORKTRUNK_DIRECTIVE_EXEC_FILE="$exec_file" \
        command wt "$@" || exit_code=$?

    if [[ -s "$cd_file" ]]; then
        cd -- "$(<"$cd_file")"
    fi
    if [[ -s "$exec_file" ]]; then
        source "$exec_file"
    fi

    rm -f "$cd_file" "$exec_file"
    return "$exit_code"
}
```

### 指令信任边界

CD 文件只包含原始路径，因此 Worktrunk 可以把它传给
别名和 hook 子进程。EXEC 文件包含会由父
包装器加载的 shell 代码，因此 Worktrunk 会将其从项目定义的别名和
hook 中移除。用户配置别名是有意设置的例外：由于其中的
命令由用户编写，它们会保留 EXEC 文件，并能运行嵌套的
`wt switch --execute`。

## 调试检查清单

### 1. 检查是否安装包装器

```bash
# Should show shell function, not binary path
type wt

# Expected output (bash/zsh):
# wt is a function
# wt () { ... }

# If it shows a path like /usr/local/bin/wt, wrapper isn't loaded
```

### 1b. 检查是否安装包装器（PowerShell）

```powershell
# PowerShell: should show Function, not just Application
Get-Command wt -All

# Expected output when wrapper is loaded:
# CommandType  Name  Source
# -----------  ----  ------
# Function     wt
# Application  wt    C:\Users\...\wt.exe

# If only Application appears, wrapper isn't loaded (restart shell)
# If Function appears but integration is still "not active", check the body:
(Get-Command wt -CommandType Function).ScriptBlock | Select-String WORKTRUNK
```

### 2. 检查 shell 配置文件

```bash
# bash
grep -n "wt config shell init" ~/.bashrc

# zsh
grep -n "wt config shell init" ~/.zshrc

# fish
grep -n "wt config shell init" ~/.config/fish/config.fish
```

应当显示带行号的 `eval` 行。

### 3. 检查是否设置了指令文件

```bash
# After running any wt command, these should be unset (temp files deleted)
echo $WORKTRUNK_DIRECTIVE_CD_FILE
echo $WORKTRUNK_DIRECTIVE_EXEC_FILE

# During wt execution, these would be set to temp file paths
```

### 4. 手动测试指令文件

```bash
# Create temp files and test
export WORKTRUNK_DIRECTIVE_CD_FILE=$(mktemp)
export WORKTRUNK_DIRECTIVE_EXEC_FILE=$(mktemp)
command wt switch feature
cat $WORKTRUNK_DIRECTIVE_CD_FILE     # Should contain: /path/to/worktree (raw path)
cd -- "$(<$WORKTRUNK_DIRECTIVE_CD_FILE)"  # Should cd you there
rm -f $WORKTRUNK_DIRECTIVE_CD_FILE $WORKTRUNK_DIRECTIVE_EXEC_FILE
```

## 常见问题

### Shell 集成在终端中工作，但在 IDE 终端中不工作

IDE 终端可能使用不同的 shell 配置。请检查：
- VS Code：Settings → Terminal → Integrated → Shell Args
- IDE 终端可能会加载另一个 profile

### 补全不工作

补全会随 shell 集成一起安装。如果缺失：

```bash
# Reinstall (forces regeneration)
wt config shell install

# For zsh, you may need compinit before the wt line:
autoload -Uz compinit && compinit
eval "$(wt config shell init zsh)"
```

### Windows Git Bash 问题

Git Bash 使用 MSYS2，它会自动转换环境
变量中的 POSIX 路径。指令文件路径无需手动转换即可得到正确处理。

如果遇到路径问题，请确保使用较新的 Git for Windows 版本。

## 环境变量

| 变量 | 用途 |
|----------|---------|
| `WORKTRUNK_DIRECTIVE_CD_FILE` | 由 shell 包装器设置；wt 写入原始路径，包装器对其执行 `cd` |
| `WORKTRUNK_DIRECTIVE_EXEC_FILE` | 由 shell 包装器设置；wt 写入 shell 命令，包装器加载该文件 |
| `WORKTRUNK_BIN` | 覆盖二进制文件路径（用于测试开发构建） |
| `WORKTRUNK_SHELL` | 由 PowerShell（`powershell`）和 fish（`fish`）包装器设置；选择 wt 如何为该 shell 转义 EXEC 指令载荷 |

## 另请参阅

- `wt config shell --help`——shell 集成命令
- `wt config show`——查看当前配置和状态
