# 模式 B：docx 小汇报 / 短文（doc-report）

单章交稿、课程报告、技术短文 —— **不走整书 pandoc 回填**，因为回填会丢图、丢元数据、丢用户手动改动。

> 共享能力（引用核查、配图与资产管理、GB/T 7714 文献规范、核查输出格式）见 `SKILL.md`，本文不重复。文中「run」「一手来源」「占位符工作流」等名词，定义见 `SKILL.md`《名词表》。

## 1. 工具选型

| 工具 | 用途 | 何时用 |
|------|------|------|
| **python-docx** | 原地修改现有 docx | **主推** — 改几段文字、改元数据、替换内嵌图 |
| **docxtpl / docx-mailmerge** | 模板填充（Jinja2 风格） | 从字段批量出 docx（合同、通知、批量邮件等模板场景） |
| **pandoc** | 整体重写 → md → 回填 | 大改写时；回填会丢图/元数据，需对此可接受 |
| **codex-image** | 重做配图 | 仅图层面，与 docx 工具配合用 |

**选型原则**：
- **保结构精确改少量字符** → **python-docx**
- **从模板生成新 docx** → docxtpl
- **整章大重写、且不在乎图/元数据保真** → pandoc
- **不要直接操作 docx 的 zip + XML**（`zipfile.write` 字符串替换 / lxml 改 `word/document.xml`）—— 这是 DIY 方案，长期不可维护、坑多（zip 目录条目、entry 顺序、命名空间 schema），让位给上面的库。

## 2. python-docx cookbook

本节给出本 skill 验证过可用的 5 个高频操作。

> **run**（贯穿本节的关键名词）：python-docx / Word 里**一段共享同一组字符格式的文本**（字体/字号/粗体/颜色等；对应 Word XML 的 `<w:r>` 节点）。WPS / Word 经常在格式切换处（上标、加粗、变色）把一句话拆成多个 run，所以"一句话跨多个 run"是常态，下面的替换策略都围绕它展开。

### 2.1 跨 run 字符串替换（WPS 拆分场景）

一句话被拆成多个 run 的典型结构（每段引用脚注上标都会切一次 run）：

```
paragraph.runs:
  [0]: '……前半句正文，陈述某个观点'
  [1]: '[7]'               ← 上标（vertAlign=superscript）
  [2]: '，后半句正文继续陈述，又接了一个需要引用的论断'
  [3]: '[8]'               ← 上标
  [4]: '。再接下来一句正文……'
```

**两种处理策略**：

**策略 A：定位到单 run 直接改**（推荐 — 不破坏上标格式）

```python
from docx import Document
doc = Document('input.docx')
TARGET = '原句中要替换的那段文字'
NEW = '替换后的新表述'
for p in doc.paragraphs:
    for r in p.runs:
        if TARGET in r.text:
            r.text = r.text.replace(TARGET, NEW)
doc.save('output.docx')
```

适用：要改的字符串恰好落在单个 run 内（最常见 — WPS 通常只在格式切换处才拆 run）。

**策略 B：合并 paragraph 文本判断 + 重建 runs**（兜底）

如果替换段跨多个 run，先用 `paragraph.text` 合并后判断，再清空所有 runs 重建：

```python
for p in doc.paragraphs:
    if '需要替换的关键短语' in p.text:
        new_text = p.text.replace('...', '...')
        for r in list(p.runs):
            r._element.getparent().remove(r._element)
        p.add_run(new_text)
```

⚠️ 策略 B **会丢掉跨 run 的格式**（上标 / 粗体 / 颜色）。如果原段有上标 `[N]`、粗体小标题等，需手动按字符位置映射回 run 重建 — 工作量大；除非必要不用。

### 2.2 删段

python-docx 没有 `paragraph.delete()` API，用私 API：

```python
def remove_paragraph(p):
    p._element.getparent().remove(p._element)
    p._p = p._element = None

# 删除某条尾注文献整段
for p in list(doc.paragraphs):
    if '[18] <作者>' in p.text:
        remove_paragraph(p)
        break
```

### 2.3 替换内嵌图

```python
img_part = None
for rel in doc.part.rels.values():
    if 'image2.png' in rel.target_ref:
        img_part = rel.target_part
        break

with open('images/<图名>-v2.png', 'rb') as f:
    img_part._blob = f.read()
```

**只要不动 rels、不动 partname**，文档结构不会破坏 —— 旧图位置上换成新图字节即可。配合 `SKILL.md`《项目资产管理》的 `images/` 单一源 + 刷新脚本使用最稳。

### 2.4 修改元数据

```python
doc.core_properties.author = '<作者名>'
doc.core_properties.last_modified_by = '<作者名>'
# title / subject / keywords / comments / category 同理
```

### 2.5 Application 字段的限制（python-docx 暴露 AI 痕迹）

`docProps/app.xml` 里的 `<Application>` 字段表征"用什么软件写的"，比如 `python-docx` / `WPS Office_…` / `Microsoft Office Word`。

**python-docx 生成/编辑后保存的 docx 会显示 `Application=python-docx`**，直接暴露"这是程序生成的" — 交给老师/审稿人很显眼。

**两种处理**：

| 方案 | 操作 | 适用 |
|------|------|------|
| **A. 交稿前 WPS / Word 另存一次** | 用户手动打开 → 文件 → 另存为 → 同名覆盖；`Application` 自动刷新成 WPS / Word | **推荐** — 简单可靠，刷新顺便让用户检查文档显示 |
| **B. lxml 直改 app.xml** | 找到 `docProps/app.xml` part，替换 `<Application>` 字符串 | 完全自动化场景；与"不直接操作 zip + XML"原则冲突，少用 |

**默认推方案 A**：自动化任务跑完后，**明确告知用户"交稿前请在 WPS / Word 中另存一次，刷新作者元数据"**。

## 3. 完工前二次核验流程

**LLM 写作 / 修订完成的 docx，必须独立做一遍"逐数据点回原文"核验**。不要相信 handoff / 上轮对话里勾选的"已核" —— LLM 容易把"近义概念"错配成"另一个具体数字"，这种错误**无法靠语义检查检出**，必须回到一手原文逐字对照。

### 典型幻觉模式（本 skill 实际遇到过）

| 文献原文 | LLM 写出 docx | 错在哪 |
|------|------|------|
| 某对象的**指标 A** 是参照物的**上千倍**；另一处提到它的**指标 B** 与参照物相近 | 某对象的**指标 C** 约为参照物的**两倍以上** | "指标 A 上千倍" 被错配成 "指标 C 两倍" —— 编了一个原文不存在的具体数字 |

LLM 看到原文有"上千倍"和某个参照物两个关键词，结合上下文自己生成了一个"两倍"的合理化叙述。**这是看似合理的近义改写，不是 thesis.md §4 讲的"无意义近义词替换"**，更隐蔽。

### 核验流程

1. **数据点穷举**：把 docx 正文里**每一处具体数字、机构名称、年份、公告号、政策名**拆出来列表（编号 D01..DNN）
2. **对照一手来源**：每个数据点查 `mineru/` / `sources/` 一手原文（PDF / HTML / 政府门户原文 / MinerU 转录稿），用 `grep` / `find` 在原文里搜关键字，逐字比对
3. **三档结论**：
   - ✅ **吻合**：与原文逐字一致 → 放过
   - ⚠️ **支撑偏弱**：文献存在但不直接支撑这个具体说法（如某文献 PDF 不直接支撑论文写的口径，只给了另一个范围/对象的数字）→ 问用户软化（加"据公开报道" / "据行业统计"）或换源
   - 🚨 **伪数据**：文献中根本不存在 → 必改 / 必删
4. **🚨 项必改**；⚠️ 项问用户态度；✅ 项放过
5. 输出按 `SKILL.md`《核查输出格式》规范，**核验台账落项目根 `reference.md`**（逐数据点 `D01..` 的 ✅/⚠️/🚨 结论 + 一手出处），别只留在对话里

**强约束**：每条 ⚠️/🚨 必须**贴出原文出处**（文件路径 + 关键句）作为依据，不能凭印象判定。

### 何时做二次核验

- 模式 A 论文：每章修订完做一次（章为单位）
- 模式 B docx 小汇报：交稿前**最后一次性核**整文（避免分批漏）
- **永远在 handoff 完成后再做一次** —— 即使 handoff 说"已核"

## 4. AI 写作场景下的常见坑

汇总本 skill 实战遇到的高频问题：

1. **伪数据**（§3 已讲）—— LLM 把概念错配成另一个具体数字
2. **引用条目编造** —— 期刊号 / 卷期 / 页码看似规范但实际查不到。处理：让用户从知网下原文 PDF 后人工补，AI 不要凭空补页码
3. **不存在的文献删除** —— 删时四件事都要做：
   - 删尾注条目
   - 删正文上标 `[N]`（按情况：删整句 / 去脚注 / 换源）
   - 后续条目重编号（`[N+1]` → `[N]`...）
   - **散落引用别漏**：小结/列举里可能有 `[3, 19]` 这种多文献引用，扫描 `\[\d+,\s*\d+\]` 模式
   - **根本解法**：用 `SKILL.md`《文献格式规范 GB/T 7714-2015》的占位符工作流，从源头消除"删一条要改 N 处"的工程负担
4. **AI 配图未标注** —— 看似中性的"作者自绘"实际是 AI 生成；按 `SKILL.md`《配图与 AI 标注》的措辞 gradient 加标
5. **数据年份口径混乱** —— 例：某指标 A（某年同比下降 X%）和某指标 B（另一年的绝对值 Y%）看似都来自同一份公告，但两者年份口径不同，docx 容易把两数挂在同一年份口径下。核验时一定看原文具体年份
6. **元数据暴露 AI 写作** —— python-docx 留 `Application=python-docx` 指纹，见 §2.5
