# 飞书文档中的公式与量子线路图

飞书文档可以原生显示公式、Mermaid/PlantUML 图和 SVG 画板，但不会运行完整的 LaTeX 编译环境。因此，数学公式可以直接写成公式块，TikZ/Quantikz 线路则要么改写为飞书兼容的画板 SVG，要么先在本地编译成矢量图再导入。

> 以下流程实测于 `lark-cli 1.0.60`、`whiteboard-cli 0.2.13` 和 TeX Live 2025。实际插入或精修云文档内容使用 `lark-doc` skill；更新已有画板内容使用 `lark-whiteboard` skill。

## 原生公式与画板格式

飞书的 `<latex>` 块只解释数学公式：

```xml
<p align="center">
  <latex>
    (\langle0|^{\otimes a}\otimes I)U_A
    (|0\rangle^{\otimes a}\otimes I)=A/\alpha
  </latex>
</p>
```

它不会执行 `\usepackage`、`\begin{tikzpicture}` 或 `\begin{quantikz}`。图形需要写成画板块：

```xml
<whiteboard type="mermaid">
flowchart LR
  A[Input] --> B[Block encoding] --> C[QLSS]
</whiteboard>
```

```xml
<whiteboard type="svg">
  <svg viewBox="0 0 1200 700">...</svg>
</whiteboard>
```

新画板随文档内容一起插入；已有画板应按其 `whiteboard token` 原位更新，避免反复新建重复画板。

## 面向飞书画板的 SVG 线路图

这条路线直接生成适合飞书解析的 SVG。量子线路用水平 `<line>`、门框 `<rect>`、控制点 `<circle>`、控制线和 `<text>` 组成；输入态、输出态、门名和说明也直接写在 SVG 中。

基本流程：

1. 先确定寄存器、量子线和门的布局。
2. 只使用飞书画板容易解析的 SVG 元素。
3. 以 `<whiteboard type="svg">` 插入文档。
4. 从返回值取出 `block_token`，导出实际画板预览。
5. 发现重叠或截字时，原位更新同一画板。

飞书画板可稳定处理的结构包括：

- `rect`、`circle`、`ellipse`、`polygon`
- `line`、`polyline`、`path`
- `text`、`tspan`
- `g` 以及简单的 `translate`、`rotate`、`scale`

生成时应避免：

- `filter`、`mask`、`clipPath`、`pattern`
- `radialGradient` 等复杂装饰
- 远程图片、脚本和外部字体
- 未烘焙的 `matrix(...)`、`skewX(...)`、`skewY(...)`

CJK 文本用 `<text>`，并按中文约一字一 `em` 留足容器宽度。线路较复杂时，与其依赖 SVG 自动排版，不如直接计算每条线、门和控制点的坐标。

插入示意：

```bash
lark-cli docs +update \
  --doc "<doc-token>" \
  --as user \
  --command block_insert_after \
  --block-id "<anchor-block-id>" \
  --content - <<'EOF'
<whiteboard type="svg">
  <svg viewBox="0 0 1200 700">
    <!-- self-contained circuit SVG -->
  </svg>
</whiteboard>
EOF
```

上传成功只说明画板块已经创建，不代表飞书渲染正确。必须查询服务端实际结果：

```bash
lark-cli whiteboard +query \
  --whiteboard-token "<whiteboard-token>" \
  --output_as image \
  --output ./preview.png \
  --as user
```

这条路线的图形与飞书画板模型一致，基础节点通常可以继续编辑；代价是需要自行负责线路布局，和论文中的 TikZ 源不是同一份真相源。

## TikZ 与 Quantikz 的矢量图路线

需要复用论文图、保持 LaTeX 字体和公式排版时，可以让 Quantikz 负责线路布局，再将编译结果转成飞书兼容 SVG。

一个最小源文件：

```latex
\documentclass[border=8pt]{standalone}
\usepackage[UTF8]{ctex}
\usepackage{quantikz}

\begin{document}
\begin{quantikz}
\lstick{$|0\rangle$} & \gate{U_b} & \ctrl{1} & \qw \\
\lstick{$|0^a\rangle$} & \qw & \gate{U_A} & \qw
\end{quantikz}
\end{document}
```

先编译 PDF，再从 PDF 转 SVG：

```bash
latexmk -xelatex -interaction=nonstopmode -halt-on-error circuit.tex
pdftocairo -svg circuit.pdf circuit.svg
```

在一次包含 Quantikz、中文和 TikZ 分组框的实测中，PDF 本身显示正确；`dvisvgm` 从 XDV 导出时遗漏了部分 PDF special，线路和门框没有完整进入 SVG。`pdftocairo -svg` 保留了 PDF 中的矢量线路，因此这类图应先检查 PDF，再检查转换后的 SVG，不要只看 LaTeX 是否编译成功。

## SVG 兼容化

`pdftocairo` 生成的 SVG 在浏览器里可以完全正常，但飞书画板有自己的解析器。实测遇到两类差异：

- 字形保存在 `<defs>` 中，正文通过带 `x/y` 的 `<use>` 引用；飞书忽略这些位置后，文字会全部叠在一起。
- 部分图形使用 `matrix(...)` 变换；飞书会降级或错误放置。

导入前需要把 SVG 规范化：

1. 将每个 `<use x="..." y="..." href="#glyph">` 展开为对应的真实 `<g>` 或 `<path>`。
2. 把 `x/y` 转换为 `translate(x y)`，或直接烘焙进路径坐标。
3. 把 `matrix(...)` 变换烘焙进图形坐标。
4. 删除不再使用的 `<defs>`。
5. 去掉 `<?xml ...?>` 声明和生成器注释，只保留完整 `<svg>` 根节点。
6. 确认 SVG 不引用外部资源。

可以先做快速检查：

```bash
grep -o '<use\b' circuit.svg | wc -l
grep -o 'matrix(' circuit.svg | wc -l
grep -Eo '<(filter|mask|clipPath|pattern)\b' circuit.svg | sort -u
```

这里的目标不是追求最短 SVG，而是得到**自包含、坐标已经确定、飞书无需再次解释复杂引用和变换**的 SVG。

规范化后仍应走两次验证：

1. 用独立 SVG/PDF 渲染器确认矢量图与原始 PDF 一致。
2. 插入飞书后，通过 `whiteboard +query --output_as image` 检查服务端实际画板。

本地浏览器能显示，不代表飞书画板一定能显示。若首次导入已生成损坏画板，应更新原来的 token，而不是在文档里再追加一张。

## 两种路线的差别

| 维度 | 面向飞书的原生 SVG | TikZ/Quantikz → SVG |
|---|---|---|
| 布局来源 | 直接计算 SVG 坐标 | TikZ/Quantikz 排版 |
| 与论文源的一致性 | 需要单独维护 | LaTeX 源可以复用 |
| 飞书兼容性 | 使用基础元素时较直接 | 必须处理字体引用和变换 |
| 画板可编辑性 | 基础节点通常可编辑 | 文字转路径后编辑性较弱 |
| 数学排版 | 需要自行摆放文本或路径 | 由 LaTeX 负责 |
| 主要验证点 | CJK 宽度、连线和控制点 | PDF→SVG 保真、`use` 与 transform 展开 |

流程图、模块关系和简单线路可以直接生成飞书兼容 SVG；需要与论文共享同一份线路源、公式排版较重的图，可以保留 Quantikz 源并增加 SVG 兼容化步骤。两条路线最终都以飞书服务端导出的画板预览为验收依据。
