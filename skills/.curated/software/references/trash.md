# Linux 回收站（trash-cli / gio trash）

`trash-cli`（`trash-put`/`trash-list`/`trash-rm`/`trash-empty`）和 GLib 的 `gio trash` 是两套独立实现，但**遵循同一套 FreeDesktop Trash 规范**：同一个回收站目录、同一种元数据格式、同一套挂载盘逻辑，因此**互通**——一个工具丢进去的，另一个能 `--list` / `trash-list` 看到、能 `--restore` / `trash-restore` 还原。

## 回收站是“两半”，info 维护不好会让 trash-rm 整体失效

每个被删项在 `~/.local/share/Trash/` 下**成对**存在，缺一不可：

- `files/NAME` —— 真实数据（或符号链接本体）
- `info/NAME.trashinfo` —— 元数据，纯文本，含 `Path=`（原始路径）、`DeletionDate=`

手动 `rm` 任意一半都会打破配对，产生**孤儿**（`trash-list` 显示幽灵条目、还原报错）。比“孤儿”更隐蔽的坑：

> **单个损坏/空的 `.trashinfo` 会让 `trash-rm` / `trash-empty` 对整个回收站罢工**：它们启动时遍历所有 `info/*.trashinfo`，撞到一个解析不了 `Path` 的就直接 `trash-rm: …/X.trashinfo: unable to parse 'Path'` 中止，**什么都不删**（退出码仍可能是 0，是假象）。把那个坏 info 删掉后立即恢复。`trash-list` 不受影响（它只列能解析的项），所以“list 正常但 rm/empty 不动”就该怀疑有坏 info。

诊断：`info` 与 `files` 应一一对应；逐项校验 `info/X.trashinfo` 有无对应 `files/X`（注意失效符号链接：`[ -e ]` 会跟随链接，对断链返回 false，要用 `[ -L ]` 兜底）。

## trash-rm 的匹配规则（关键，反直觉）

`trash-rm '<pattern>'` 的匹配只看一件事——**pattern 是否以 `/` 开头**（源码 `trashcli/rm/filter.py`，HEAD `6a0884e`）：

```python
def matches(self, original_location):
    basename = os.path.basename(original_location)
    subject = original_location if self.pattern[0] == '/' else basename
    return fnmatch.fnmatchcase(subject, self.pattern)
```

即：**`/` 开头 → 拿去匹配完整原始绝对路径；否则 → 只匹配 basename**，两者都走 `fnmatch.fnmatchcase`（`*` 可跨 `/`）。所以：

| pattern | 匹配对象 | `/a/b/_audit-clones` 是否命中 |
|---|---|---|
| `_audit-clones` | basename | ✅ |
| `*audit-clones*` | basename | ✅ |
| `*/_audit-clones` | basename（含 `/`，basename 永不含 `/`） | ❌ 永不命中 |
| `/a/b/_audit-clones` | 整路径 | ✅ |
| `/a/*/_audit-clones` | 整路径 | ✅ |

**正确写法**：纯 basename 通配（不带 `/`，如 `'_audit-clones'`、`'*audit-clones*'`），或以 `/` 开头的整路径通配（如 `'/home/<user>/proj/_audit-clones'`、`'/home/*/proj/_audit-clones'`）。最稳的是直接从 `trash-list` 复制整条原始路径当 pattern。官方亦注明 “trash-rm uses fnmatch.fnmatchcase”（`trashcli/rm/rm_cmd.py`）。源码：<https://github.com/andreafrancia/trash-cli/blob/master/trashcli/rm/filter.py>

## gio trash 没有“选择性永久删单项”

`gio trash` 只有四个开关（源码 `gio/gio-tool-trash.c`，glib HEAD `2156dbf`）：

```c
{ "force",   'f', …, &global_force, … },
{ "empty",   0,   …, &empty,   … },   // 清空整个回收站
{ "list",    0,   …, &list,    … },
{ "restore", 0,   …, &restore, … },
```

`--empty` 作用于 `trash:` 根、清掉全部，无法定点删某一项：

```c
else if (empty) {
    file = g_file_new_for_uri ("trash:");
    delete_trash_file (file, FALSE, TRUE, &error);   // 全清
}
```

**结论**：要“永久删除回收站里的某一项”只能用 trash-cli 的 `trash-rm`；gio 只能“丢进去 / 列出 / 还原 / 全清”。源码：<https://gitlab.gnome.org/GNOME/glib/-/blob/main/gio/gio-tool-trash.c>

## 删挂载盘上的文件：用 `trash-put`，落到卷内 `.Trash`

家目录里的文件进 `~/.local/share/Trash`。**别的挂载卷上的文件**，删除时**仍用 `trash-put` 而不是 `rm`**：两个工具都按 FreeDesktop 规范把回收站建在**该卷顶层目录**，文件留在同一 filesystem、可 `trash-restore` 恢复（而不是被搬到 `~/.local/share/Trash`、跨 filesystem 触发完整数据拷贝）。这条对 FUSE 和内核挂载（CIFS / NFS / NTFS 等）都成立。卷内回收站**不消耗本地盘**，但会占该卷 / 远端 share 的配额，按需 `trash-empty` 清理。

落点细节（两者同规范，都先试全局再回退每用户）：

- **候选顺序**：家卷文件 → `~/.local/share/Trash`；否则 → `$topdir/.Trash/$uid`（要求 `.Trash` 存在、是目录、带 sticky 位、非符号链接）→ 回退 `$topdir/.Trash-$uid`。多数挂载卷没有预建带 sticky 的全局 `.Trash`，所以实际看到的通常是每用户的 `.Trash-<UID>/`。
- gio：源码 `gio/glocalfile.c` `g_local_file_trash`（同上判定）。
- trash-cli：源码 `trashcli/put/trasher.py`（docstring 明示“每个卷有两个 trash 目录 `$volume/.Trash/$uid` 与 `$volume/.Trash-$uid`，先试前者再试后者”）、`trashcli/lib/trash_dirs.py`（三个目录的定义）；并由 `trash_dir_checker.py` 强制“trash 目录与待删文件必须同卷”（否则 `DifferentVolumes`）——这正是“留在同一 filesystem、不跨盘拷贝”的底层保证，`security_check.py` 另查 `.Trash` 父目录 sticky 位。

Windows/WSL 下 `/mnt/c` NTFS、以及与 Windows 资源管理器回收站互不可见的专属角度见 [windows.md](windows.md)。

## PATH 小坑：非登录 shell 找不到 trash-cli

若 trash-cli 用 `uv tool` 安装，可执行文件在 `~/.local/bin`，只在**登录 shell** 的 PATH 里。`ssh host '命令'`、CI、`portal_exec` 等默认是**非登录非交互** shell，PATH 最小、找不到 `trash-put`。解法：包一层 `bash -lc '…'`，或用绝对路径 `~/.local/bin/trash-put`。（`gio` 在 `/usr/bin`，不受影响。）
