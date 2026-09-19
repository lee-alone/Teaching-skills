---
name: science-lesson-prep
description: 理科符号规范与文档排版助手——专门用于科学学科（数学、物理、化学、生物）的文件创建、符号与公式标准化书写，以及将包含理科公式的 Markdown 文档排版渲染为 Word (.docx) 与 PowerPoint (.pptx) 原生可编辑格式。当涉及理科符号/公式书写规范（LaTeX 语法、化学方程式与反应条件、物理矢量与正体单位、生物遗传符号）、函数与科学图象绘制（plot 语法）、公式在 docx/pptx 中乱码或方框排查，或需要将理科文档/试卷/讲义/学案排版渲染为原生 Office 文件时使用。注：教案与教学设计逻辑由 lesson-plan 技能负责，本技能专助理科符号规范与文档排版渲染。
agent_created: true
---

# 理科符号规范与文档排版助手

## 这个技能解决什么问题

科学学科（数学、物理、化学、生物）文件中的公式与特殊符号，在导出为 Word 与 PowerPoint 时经常显示错误：变成 `\frac{a}{b}` 源码、变成方块乱码、根号横线断裂、重音符号飘到字符外面、或者化学方程式与物理单位变成斜体变量。

根因是：
1. **符号规范不统一**：不慎使用了 Unicode 上下标（如 `x²`、`H₂O`）导致缺少字形变方框，或使用了 Office 无法解析的 LaTeX 宏包（如 `\ce{}`）。
2. **缺乏原生转换通道**：模型能写出正确的 LaTeX，但**没有能力手写 OOXML**。规范写得再详细也解决不了这个问题——必须有一条可执行的转换通道。

本技能提供全套解决方案：
- **符号规范化**：建立数学、物理、化学、生物各学科规范的符号与表达式写法。
- **原生排版通道**：模型只写标准 Markdown 与 `$...$`，脚本负责把公式转成 Office 原生数学对象（OMML）并绘制函数图象。

**核心原则：内容生成与文件排版分离。模型写 Markdown，脚本做排版，模型绝不碰 XML。**

## 两个技能的职责分工与协作

| 场景 | 负责技能 |
| --- | --- |
| 撰写教案、教学设计、设计教学主线、问题链、三维目标、环节四要素 | **`lesson-plan`**（教案编写助手） |
| 判断教案结构是否完整、教学逻辑是否闭环 | **`lesson-plan`**（运行 `check_plan.py`） |
| 理科符号与公式标准化书写（LaTeX、化学正体、物理单位正体、矢量等） | **本技能**（查阅 `references/math-syntax.md`、`subjects.md`） |
| 绘制函数图象与科学曲线 | **本技能**（使用 ````plot ... ```` 语法） |
| 将 Markdown 渲染为 Word（DOCX）或幻灯片（PPTX）原生可编辑文档 | **本技能**（运行 `render.py`） |
| 检查公式转换是否完整、是否有残留源码或 PPT 排版越界 | **本技能**（运行 `qa_check.py`） |

> **标准协作流程**：
> 若用户需要一份**包含理科公式的 Word/PowerPoint 教案**：
> 1. 先由 `lesson-plan` 技能完成教学设计，生成符合 12 大板块、四要素及对照表要求的 Markdown 内容（公式采用 LaTeX 书写）；
> 2. 由本技能按照理科符号规范对公式、图象及排版标记进行核验；
> 3. 调用本技能的 `render.py` 渲染为 `.docx` 或 `.pptx`；
> 4. 调用本技能的 `qa_check.py` 质检公式完整性并交付用户。

## 执行流程

### 第 1 步：环境自检（首次必做）

```bash
python <skill>/scripts/bootstrap.py
```

检查 Python 依赖、Node 依赖与中文字体，缺什么自动装什么。依赖装在隔离位置，不污染全局环境：

| 平台 | 默认位置 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\science-lesson-prep\` |
| Linux | `~/.cache/science-lesson-prep/` |
| macOS | `~/Library/Caches/science-lesson-prep/` |

最后一行输出 JSON，其中 `python` 字段是后续所有脚本应当使用的解释器路径。

> **第 3、4 步务必用 `python` 字段的值来调用脚本。**
> 直接用系统全局 Python 可能因缺少依赖而失败（典型症状：图象报
> `缺 matplotlib 无法生成函数图象`）。脚本已内置兜底——检测到关键依赖缺失时
> 会自动切换到隔离解释器重新执行。

### 第 2 步：按符号规范编写 Markdown

把理科内容写成 Markdown，公式用 `$...$`（行内）与 `$$...$$`（独立成行）：

- **数学公式书写规范**见 `references/math-syntax.md`——**必读**，列出了必须避免的写法（如 Unicode 上下标、斜杠分数等）。
- **物理 / 化学 / 生物分科符号规范**见 `references/subjects.md`——**必读**。
  - 化学方程式尤其要注意：`\ce{}` 不受支持，必须用 `\text{}` 正体 + `\xrightarrow{}` 条件写。
  - 物理单位必须用 `\text{}` 正体（如 `$9.8\ \text{m/s}^2$`），矢量用 `\vec{}`。
  - 生物分子式正体，遗传学下划线转义为 `\_`。
- **函数与科学图象规格**见 `references/figures.md`（使用 ````plot ... ```` 代码块）。

渲染器支持的 Markdown 子集（写超纲语法会被静默忽略，所以只写这些）：

| 语法 | 渲染结果 |
| --- | --- |
| `#` / `##` / `###` / `####` | 各级标题（黑体） |
| `**加粗**` | 真正的粗体。**必须用这个写法，不要靠引号或书名号代替** |
| `` `等宽` `` | 等宽行内文字（宋体，宽度与汉字对齐） |
| `$...$` / `$$...$$` | 行内公式 / 独立居中公式（Office 原生对象） |
| `-` 与 `1.` 列表 | 层级与组内编号按缩进还原；缩进加深即开新组并从 1 重新计数 |
| `> 引用` | 楷体提示栏 + 浅底纹 |
| `\| a \| b \|` 表格 | 带网格线与表头底纹的表格 |
| ```` ```plot ```` | 函数图象（JSON 规格） |
| ```` ```其他语言 ```` | **原样输出**（宋体等宽 + 浅底纹），用于板书设计、问题链架构图等 ASCII 图 |
| `::: blank N` / `::: pagebreak` / `---` | 留白 / 分页 / 分隔线 |

> **行内标记可以跨公式**：`**输入一个确定的 $x$ 就能唯一确定 $y$！**` 是正确的写法，
> 引擎会先配平 `**` 再切公式，加粗段落里夹公式不会被拆坏。

> **ASCII 图要控制在 55 字符当量以内**（一个汉字算 2）。
> 板书设计的方框图常被画到 70+ 字符宽，A4 正文栏放不下，渲染器只能压到 6pt 才不折行，
> 虽然不会折行但小到难认。超宽时 `render.py` 与 `qa_check.py` 都会给出提示。

可参考 `assets/example-xuean.md` 与 `assets/example-wuli-xuean.md`（理科 Markdown 格式与公式图象语法示范）。

### 第 3 步：渲染为 Office 文档

```bash
# 用第 1 步 JSON 里的 python 字段作为解释器
"<python>" <skill>/scripts/render.py --kind jiaoan --input doc.md --output 文档.docx
"<python>" <skill>/scripts/render.py --kind xuean  --input doc.md --output 文档.docx
"<python>" <skill>/scripts/render.py --kind kejian --input doc.md --output 课件.pptx
```

参数说明：
- `--kind`：`jiaoan`（文档排版，页边距 2.2cm）｜`xuean`（学习材料/题单排版）｜`kejian`（课件，16:9 幻灯片排版）
- `--math-mode`：
  - `native`（默认）——Office 原生公式，双击可编辑。
  - `image`——公式一律转为矢量图片。**仅 DOCX 支持**；PPTX 不支持此选项。
  - `auto`——优先使用原生公式，转换失败时自动退回矢量图片（DOCX）。
- `--work-dir`：图片与中间产物的输出目录，默认为输出文件同级的 `_assets/`

输出 JSON 含 `math`（公式数）、`figures`（图象数）、`warnings`。**`warnings` 必须逐条查看。**

### 第 4 步：公式与排版质检（必做）

```bash
# --source-md 指向渲染所用的那份 Markdown，启用逐块内容清点（强烈建议带上）
"<python>" <skill>/scripts/qa_check.py 文档.docx --source-md doc.md
"<python>" <skill>/scripts/qa_check.py 课件.pptx --kind kejian --source-md doc.md
```

质检脚本专职检查：
- **内容完整性（需 `--source-md`）**：Markdown 里每一块内容是否都在成品里——包括
  代码块（板书设计、架构图）是否整块丢失、列表编号是否与源文件一致；
- **行内标记残留**：正文里是否漏出 `**` 或反引号（说明行内标记没被渲染成格式）；
- 是否残留 `$` 定界符或裸露的 LaTeX 命令；
- 是否存在未修正的重音结构或空文本 run；
- 公式内中文是否缺失中文字体导致方框；
- PPT 文本框与形状是否越出画布边界。

退出码 0 才算通过。

> **只查 `$` 是不够的。** 曾经出现过 `qa_check.py` 零告警通过、成品却把教案的
> 「主线架构图」「板书设计」整块丢掉、列表编号错乱的情况——这些缺陷全都发生在 `$` 之外。
> 所以 `--source-md` 不是可选项，而是**交付前的必做动作**。

> **关于"未发现原生公式对象"**：该提示只在「既无原生公式对象、也无任何图片」时判为问题。
> 若本次使用 `--math-mode image`，公式本就以矢量图片呈现，脚本会输出一条**提示**而非错误，
> 退出码仍为 0。反之，纯文字材料若既无公式也无图片，则会正常报错。

> **`notes` 字段要读。** 例如「代码块偏宽：最宽约 74 字符当量……只能压到 6.0pt 显示」——
> 这不是错误（脚本已保证不折行），但说明 Markdown 里那张图该收窄了。

### 第 5 步：交付

将生成的文件给用户，并说明公式是 Word/PowerPoint 原生对象、双击可自由编辑。

> **交付前对照 `references/qa-checklist.md` 走一遍。** 那里记着「脚本没报错但成品是坏的」
> 这类翻车案例的核验方法：解包数原生公式、用 Word 排版引擎查折行与越界、
> 以及本机环境的几个坑（python-docx 默认 Letter 不是 A4、Word 忽略负缩进、
> PowerShell 的 COM 不可靠要改用 pywin32）。

## 脚本清单

| 脚本 | 作用 |
| --- | --- |
| `scripts/env.py` | 运行环境解析：解释器、Node/npm、依赖目录（唯一路径入口） |
| `scripts/bootstrap.py` | 环境自检与依赖自动安装 |
| `scripts/omml.py` | LaTeX → OMML 公式引擎（含 6 项缺陷修复） |
| `scripts/mathimg.py`、`scripts/mathjax_tex2svg.js` | 公式降级为 SVG/PNG |
| `scripts/figures.py` | 函数图象绘制（matplotlib） |
| `scripts/render.py` | Markdown → DOCX/PPTX 渲染器 |
| `scripts/qa_check.py` | 公式完整性与排版越界质检 |

## Markdown 支持的语法

````markdown
---
课题: 二次函数的图象与性质
学科: 数学
年级: 九年级
---

# 一级标题（文档标题 / 课件封面）
## 二级标题（大板块 / 课件每页标题）
### 三级标题

普通段落，行内公式写作 $x^2 + 2x + 1$，中文标点照常使用。

$$x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$$

- 无序列表
1. 有序列表

> 提示栏，渲染为楷体浅底

| 表头 | 表头 |
| --- | --- |
| 单元格支持 $|a|$ 这类含竖线的公式 | 内容 |

```plot
{
  "title": "二次函数图象",
  "x": [-3, 5], "y": [-6, 8],
  "curves": [{"expr": "x**2 - 2*x - 3", "label": "y = x² - 2x - 3"}],
  "points": [{"x": 1, "y": -4, "label": "顶点 (1, -4)"}],
  "vlines": [{"x": 1, "label": "对称轴 x = 1"}]
}
```

::: blank 4
::: pagebreak
````

## 必须遵守的硬性要求

1. **公式一律用 LaTeX 书写，绝不手写 OMML/XML。** 引擎已处理好命名空间、标签闭合、
   重音结构、双线数集、间距与中文字体；手工拼接只会引入难查的错误。
2. **不使用 Unicode 上下标表示数学结构。** 写 `$x^2$`、`$H_2O$`，不写 `x²`、`H₂O`。
   中文字体普遍缺少这些字形，会渲染成方框。（`plot` 的 label 里写了无妨，
   `figures.py` 会自动转成 mathtext。）
3. **表格单元格里的公式含竖线时照常写 `$|a|$`**，解析器会正确处理；
   不要为了避开竖线而改写公式。
4. **公式内的中文写在 `\text{}` 里**，例如 `$x \text{ 为有理数}$`，引擎会自动指定中文字体。
5. **化学方程式不使用 `\ce{}`**（mhchem 宏包，引擎不支持，会原样漏出源码）。
   用 `\text{}` 写化学式，用 `\xrightarrow{}` 写反应条件：
   `$2\text{KClO}_3 \xrightarrow[\text{MnO}_2]{\Delta} 2\text{KCl} + 3\text{O}_2\uparrow$`。
   物理单位同样要写成正体 `$9.8\ \text{m/s}^2$`。详见 `references/subjects.md`。
6. **每份材料生成后必须跑 `qa_check.py`，并且必须带 `--source-md`。**
   只跑不带源的版本等于只检查了公式，漏掉的正是「整块内容丢失」「编号错乱」
   「行内标记没渲染」这几类最致命的缺陷。
7. **验收不能只看「脚本没报错」。** 交付前还要确认：`md_items_missing` 为 0、
   `residual_asterisk` 与 `residual_backtick` 为 0、`warnings` 与 `notes` 逐条看过。
   渲染类交付的解包核验清单见 `references/qa-checklist.md`。

## 运行环境与可移植性

技能目录可以被复制到任何一台电脑上使用，**不依赖任何平台专有目录**。
所有路径按「环境变量 > 技能自带 > 通用缓存目录 > 平台目录兼容回退」的顺序探测，
找不到就自动创建，不会因为某个目录不存在而中断。

排查环境问题时可用以下环境变量重定向（正常使用不需要）：

| 变量 | 作用 |
| --- | --- |
| `SCIENCE_LESSON_PREP_HOME` | 缓存根目录（虚拟环境与 Node 包都放这里） |
| `SCIENCE_LESSON_PREP_PYTHON` | 直接指定解释器 |
| `SCIENCE_LESSON_PREP_VENV` | 指定虚拟环境目录 |
| `SCIENCE_LESSON_PREP_BASE_PYTHON` | 创建虚拟环境时使用的基础解释器 |
| `SCIENCE_LESSON_PREP_NODE` / `SCIENCE_LESSON_PREP_NPM` | 指定 node / npm |
| `SCIENCE_LESSON_PREP_NODE_MODULES` | 指定 node_modules 目录 |

`scripts/env.py` 是唯一的路径解析入口，其余脚本都从它取路径。
排查「找不到解释器 / 找不到依赖」时，先单独运行它查看解析结果。

## 已知边界

- **PPTX 公式兼容性**：`a14:m` 原生公式需要 PowerPoint 2010 及以上。
  课件**没有图片降级方案**——PowerPoint 的文本模型无法把图片作为行内对象插入段落
  （PowerPoint 里"文字中插图"实际是独立图形，不参与文字排版），
  强行实现需要放弃文本框改为手工排版，因此 `--math-mode image` 对 PPTX 会明确报错。
  若目标环境是老版本 PowerPoint 或部分 WPS：把公式较多的内容放进 DOCX 教案或导学案
  （那里支持 `--math-mode image`），或换用兼容的播放环境。
- **DOCX 公式可编辑性**：原生 OMML 在 Word 与 WPS 中均可双击编辑；
  用 `--math-mode image` 时公式是图片，不可编辑。
- **降级链路需要 Node**：`mathjax-full` 与 `@resvg/resvg-js` 由 `bootstrap.py` 自动安装。
  Node 优先从 `PATH` 探测（其次才是缓存目录与平台目录），`NODE_PATH` 会串联所有候选
  目录而不是锁定单一位置，因此全局安装的包同样能被找到。
  无 Node 时 `--math-mode image` 不可用，但原生公式不受影响。
- **课件文字量**：课件每页正文建议不超过 6 行。脚本不会自动缩排，文字过多会溢出幻灯片。
- **课件版式**：输出为 16:9（13.333 × 7.5 英寸）。`render.py` 会在保存后把
  `sldSz` 的版式标记改写为 `screen16x9`——python-pptx 默认模板会写死
  `screen4x3`，导致部分阅读器按 4:3 打开（右侧留白或被裁切）。

## 常见故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 文档里出现 `$` 或 `\frac` | 公式没被转换 | 检查是否漏写 `$`；跑 `qa_check.py` 定位 |
| 重音符号飘在字符外 | 走了未修复的转换路径 | 确认使用的是本技能的 `omml.py` |
| 公式内中文变方框 | 缺中文字体 | 跑 `bootstrap.py` 看 `fonts` 字段 |
| 图象里中文变方框 | matplotlib 未选到中文字体 | 确认系统装有黑体或微软雅黑 |
| 文件被占用无法覆盖 | 用户开着 Word/PPT | 脚本会自动改存带时间戳的副本，提示用户关闭后重跑 |
