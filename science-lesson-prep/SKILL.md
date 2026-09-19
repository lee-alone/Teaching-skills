---
name: science-lesson-prep
description: 理科备课助手——生成理科（数学、物理、化学、生物）备课材料，包括教案、导学案、教学课件，并保证数学公式在 Word 与 PowerPoint 中正确显示。当用户需要写教案、备课、做导学案、做课件、准备一节课，或反馈"公式在 docx/pptx 里显示不对""公式变成乱码或源码""数学符号变成方框"时使用。也适用于需要绘制函数图象、设计板书、整理教学过程的场景。本技能通过脚本把 LaTeX 公式落地为 Office 原生数学对象，不依赖 LaTeX 发行版。
agent_created: true
---

# 理科备课助手

## 这个技能解决什么问题

教师备课材料里的数学公式，在 Word 与 PowerPoint 中经常显示错误：变成 `\frac{a}{b}` 源码、
变成方块乱码、根号横线断裂、重音符号飘到字符外面。

根因是：模型能写出正确的 LaTeX，但**没有能力手写 OOXML**。规范写得再详细也解决不了这个问题——
必须有一条可执行的转换通道。

本技能提供这条通道：模型只写 `$...$`，脚本负责把公式转成 Office 原生数学对象（OMML）。

**核心原则：内容生成与文件排版分离。模型写 Markdown，脚本做排版，模型绝不碰 XML。**

## 执行流程

### 第 1 步：环境自检（每次必做）

```bash
python <skill>/scripts/bootstrap.py
```

检查 Python 依赖、Node 依赖与中文字体，缺什么自动装什么。

依赖装在**可移植的隔离位置**，不污染全局环境，也不假设任何平台专有目录存在：

| 平台 | 默认位置 |
| --- | --- |
| Windows | `%LOCALAPPDATA%\science-lesson-prep\` |
| Linux | `~/.cache/science-lesson-prep/` |
| macOS | `~/Library/Caches/science-lesson-prep/` |

最后一行输出 JSON：

- `ok: true` 表示就绪；为 `false` 时先按 `messages` 处理再继续。
- **`python` 字段是后续所有脚本应当使用的解释器路径。**

> **第 3、4 步务必用 `python` 字段的值来调用脚本。**
> 直接用系统全局 Python 可能因缺少依赖而失败（典型症状：图象报
> `缺 matplotlib 无法生成函数图象`）。脚本已内置兜底——检测到关键依赖缺失时
> 会自动切换到隔离解释器重新执行，并在 stderr 打印一行 `[env] … 重新执行`。
> 但这只是兜底，正常流程仍应显式使用 `python` 字段。

### 第 2 步：编写 Markdown 中间表示

把教学内容写成 Markdown，公式用 `$...$`（行内）与 `$$...$$`（独立成行）。

- 公式书写规范见 `references/math-syntax.md`——**必读**，其中列了必须避免的写法。
- 教学设计的必备板块与写作要求见 `references/pedagogy.md`。
- 函数图象规格见 `references/figures.md`。
- **物理 / 化学 / 生物的写法见 `references/subjects.md`**——写非数学科目时**必读**。
  化学方程式尤其要注意：`\ce{}` 不受支持，必须用 `\text{}` + `\xrightarrow{}` 写。

同一节课若需同时产出教案与课件，先完成一份完整教学设计，再据此分别改写成
`jiaoan` 版与 `kejian` 版 Markdown（同源异构，见 `references/pedagogy.md`）。

可参考 `assets/example-xuean.md`（一份完整的数学导学案，覆盖了本技能支持的全部语法）。

### 第 3 步：渲染

```bash
# 用第 1 步 JSON 里的 python 字段作为解释器
"<python>" <skill>/scripts/render.py --kind jiaoan --input plan.md --output 教案.docx
"<python>" <skill>/scripts/render.py --kind xuean  --input plan.md --output 导学案.docx
"<python>" <skill>/scripts/render.py --kind kejian --input plan.md --output 课件.pptx
```

参数说明：

- `--kind`：`jiaoan`（教案）｜`xuean`（导学案）｜`kejian`（课件）
- `--math-mode`：
  - `native`（默认）——Office 原生公式，双击可编辑。
  - `image`——公式一律转为矢量图片。**仅 DOCX（教案、导学案）支持**；
    用于 PPTX 会直接报错（见下方"已知边界"）。
  - `auto`——先用原生，转换失败时自动退回矢量图片（DOCX）。
    PPTX 下等同 `native`：转换失败时按原文保留并给出警告。
- `--work-dir`：图片与中间产物的输出目录，默认为输出文件同级的 `_assets/`

输出 JSON 含 `math`（公式数）、`figures`（图象数）、`warnings`。**`warnings` 必须逐条查看。**

### 第 4 步：质检（必做）

```bash
"<python>" <skill>/scripts/qa_check.py 教案.docx --kind jiaoan
"<python>" <skill>/scripts/qa_check.py 课件.pptx --kind kejian
```

退出码 0 才算通过。**不要把"脚本没报错"当成"文件没问题"**——
`warnings` 与质检输出都要逐条确认，必要时打开文件核对。

### 第 5 步：交付

用 `present_files` 把生成的文件给用户，并说明公式是 Word/PowerPoint 原生对象、双击可编辑。

## 脚本清单

| 脚本 | 作用 |
| --- | --- |
| `scripts/env.py` | 运行环境解析：解释器、Node/npm、依赖目录（唯一路径入口） |
| `scripts/bootstrap.py` | 环境自检与依赖自动安装 |
| `scripts/omml.py` | LaTeX → OMML 公式引擎（含 6 项缺陷修复） |
| `scripts/mathimg.py`、`scripts/mathjax_tex2svg.js` | 公式降级为 SVG/PNG |
| `scripts/figures.py` | 函数图象绘制（matplotlib） |
| `scripts/render.py` | Markdown → DOCX/PPTX 渲染器 |
| `scripts/qa_check.py` | 生成后自动质检 |

## Markdown 支持的语法

````markdown
---
课题: 二次函数的图象与性质
学科: 数学
年级: 九年级
课时: 第 2 课时
---

# 一级标题（教案标题 / 课件封面）
## 二级标题（教案板块 / 课件每页标题）
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
6. **每份材料生成后必须跑 `qa_check.py`。**

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

## 常见故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| 文档里出现 `$` 或 `\frac` | 公式没被转换 | 检查是否漏写 `$`；跑 `qa_check.py` 定位 |
| 重音符号飘在字符外 | 走了未修复的转换路径 | 确认使用的是本技能的 `omml.py` |
| 公式内中文变方框 | 缺中文字体 | 跑 `bootstrap.py` 看 `fonts` 字段 |
| 图象里中文变方框 | matplotlib 未选到中文字体 | 确认系统装有黑体或微软雅黑 |
| 文件被占用无法覆盖 | 用户开着 Word/PPT | 脚本会自动改存带时间戳的副本，提示用户关闭后重跑 |
