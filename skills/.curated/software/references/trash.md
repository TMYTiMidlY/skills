# Linux 回收站（trash-cli / gio trash）

`trash-cli`（`trash-put`/`trash-list`/`trash-rm`/`trash-empty`）和 GLib 的 `gio trash` 是两套独立实现，但**遵循同一套 FreeDesktop Trash 规范**：同一组回收站目录、同一种 `.trashinfo` 元数据格式、同一套挂载盘候选逻辑，因此**互通**——一个工具丢进去的，另一个能 `--list` / `trash-list` 看到、能 `--restore` / `trash-restore` 还原。

源码对照（两边落到同一组路径与同一种格式）：

- 目录：trash-cli `trashcli/lib/trash_dirs.py`（`home_trash_dir_path_from_env` → `$XDG_DATA_HOME/Trash` 或 `~/.local/share/Trash`；`volume_trash_dir1`/`volume_trash_dir2` → `$volume/.Trash/$uid`、`$volume/.Trash-$uid`）对应 gio `gio/glocalfile.c` 的 `g_local_file_trash`（home → `g_get_user_data_dir()/Trash`；卷 → `$topdir/.Trash/$uid` 回退 `$topdir/.Trash-$uid`）。
- 元数据：trash-cli `trashcli/put/format_trash_info.py` 的 `format_trashinfo()` 写 `[Trash Info]` / `Path=…` / `DeletionDate=…`；gio `g_local_file_trash` 同样写 `<name>.trashinfo`。

## 回收站是“两半”，破坏配对会产生孤儿/幽灵

每个被删项在回收站目录下**成对**存在，缺一不可（源码：写入 `trashcli/put/format_trash_info.py`，读取与配对 `trashcli/lib/trash_dir_reader.py`）：

- `files/NAME` —— 真实数据（或符号链接本体）
- `info/NAME.trashinfo` —— 纯文本元数据，`format_trashinfo()` 写成三行：`[Trash Info]`、`Path=<url_quote 的原始绝对路径>`、`DeletionDate=<ISO8601>`

手动 `rm` 任意一半都会打破配对，但**两个方向的后果不同**，别混为一谈：

- **删了 `info/`、留下 `files/`**：源码称之为 *orphan*（`trash_dir_reader.py` 的 `list_orphans`：遍历 `files/`，对应的 `info/NAME.trashinfo` 不存在即为孤儿）。`trash-list` 只扫 `info/`（`list_trashinfo` 只列 `*.trashinfo`），所以**根本列不出**它——成了占着卷空间却看不见的隐形垃圾；只有 `trash-empty` 会顺带清掉它（`trashcli/empty/emptier.py` 的 `files_to_delete` 末尾 `yield orphan`）。
- **删了 `files/`、留下 `info/`**：`trash-list` 仍会列出这条（它只看 `info/`），但 `trash-restore` 执行 `move(files/NAME → 原位)` 时源数据已不在、必然失败（源码 `trashcli/restore/restorer.py` 的 `restore_trashed_file`）——这才是“幽灵条目 + 还原报错”。

诊断：`info/` 与 `files/` 应一一对应；逐项校验 `info/NAME.trashinfo` 有无对应 `files/NAME`（注意失效符号链接：`[ -e ]` 会跟随链接、对断链返回 false，要用 `[ -L ]` 兜底）。

## 坏/空 `.trashinfo`：不会让 trash-rm/empty 罢工，但坏项删不掉、得手动修

> **纠正一个常见误解**：单个损坏/空的 `.trashinfo`（文件能读、但没有 `Path=` 行）**不会**让 `trash-rm` / `trash-empty` 对整个回收站罢工、什么都不删。源码 + 实测（trash-cli HEAD `6a0884e`）的真实行为是：

- **`trash-rm <pattern>`**：逐项处理，遇到 parse 不出 `Path=` 的项，只往 stderr 打印一行 `trash-rm: …/X.trashinfo: unable to parse 'Path'`，然后**跳过它、继续删其余匹配项**，退出码仍 `0`。源码：`trashcli/rm/rm_cmd.py` 的 `RmCmd.run`（消费 generator，遇 `unable_to_parse_path` 只 `report_error`、不中止循环）+ `trashcli/rm/list_trashinfo.py` 的 `list_from_volume_trashdir`（逐项 `yield`）+ `trashcli/parse_trashinfo/parse_path.py`（无 `Path=` 行就 `raise ParseError`）。
- **裸 `trash-empty`**：`trashcli/empty/delete_according_date.py` 的 `ok_to_delete` 在 `parsed_days is None` 时直接 `return True`，**根本不读、不解析 `.trashinfo` 内容**，坏/空项照样被清、不报 parse 错误（`trashcli/empty/emptier.py`）。只有带天数的 `trash-empty N` 才解析，且解析的是 `DeletionDate` 而非 `Path`（`trashcli/parse_trashinfo/parse_deletion_date.py`）。
- `trash-list` 对坏项也只打印一行 `Parse Error: …: Unable to parse Path.` 并继续列出其余（`trashcli/list/list_trash_action.py` 的 `_print_trashinfo`）。

**真正的坑**（实测验证）：那个坏 `.trashinfo` 对应的项，**自己用 `trash-rm <pattern>` 删不掉**——因为 `trash-rm` 按“原始路径”匹配（见下一节），而它恰恰解析不出原始路径，于是永远被当成 `unable_to_parse` 跳过；而且每跑一次 `trash-rm` 都会刷一行该错误。

**正确处置**：不要为了清掉一个坏项就 `trash-empty`——`trash-empty` 清的是**整个**回收站，会连带删掉其它你还想恢复的项，很危险。应当**手动修复那条 `.trashinfo`**：照同目录其它 `.trashinfo` 的格式，给它补回合法的 `Path=<原始绝对路径>` 行；修好后它就能被 `trash-list` / `trash-rm` / `trash-restore` 正常识别。实测：给无 `Path=` 行的 `bad.trashinfo` 补上 `Path=/tmp/bad` 后，`trash-rm '*bad*'` 即正常删除。

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

## 删挂载盘上的文件：两者同规范，落到卷内 `.Trash-<UID>`

删挂载卷上文件的操作规则（用 `trash-put` 而非 `rm -rf`、落到卷顶层 `.Trash-<UID>/`、留在同卷可 `trash-restore` 恢复、不占本地盘）见 [mount.md](mount.md)。这里只补 trash-cli 与 gio “同规范” 的源码证据：

- **候选顺序**（两者一致）：家卷文件 → `~/.local/share/Trash`；否则 → `$topdir/.Trash/$uid`（要求 `.Trash` 存在、是目录、带 sticky 位、非符号链接）→ 回退 `$topdir/.Trash-$uid`。多数挂载卷没预建带 sticky 的全局 `.Trash`，所以实际看到的通常是 `.Trash-<UID>/`。
- gio：源码 `gio/glocalfile.c` `g_local_file_trash`。
- trash-cli：源码 `trashcli/put/trasher.py`（docstring 明示两个卷内 trash 目录先试 `$volume/.Trash/$uid` 再试 `$volume/.Trash-$uid`）、`trashcli/lib/trash_dirs.py`；`trash_dir_checker.py` 强制 trash 目录与待删文件同卷（否则 `DifferentVolumes`），`security_check.py` 查 `.Trash` 父目录 sticky 位。

Windows/WSL 下 `/mnt/c` NTFS、与 Windows 资源管理器回收站互不可见的专属角度见 [windows.md](windows.md)。
