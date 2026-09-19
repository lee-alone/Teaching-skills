# 渲染交付验收清单

> **「脚本没报错」不等于交付成功。** 本文记录的是真实翻过车的地方：
> 曾经 `render.py` 退出码 0、`qa_check.py` 零告警通过，成品却把教案的
> 「主线架构图」与「板书设计」整块丢掉、列表编号错乱、正文里留下 216 个星号。
> 所以下面每一项都要**实际执行并看到结果**，不能凭脚本退出码推断。

---

## 一、必做的四步核验

### 1. 带源质检（不可省略 `--source-md`）

```bash
"<python>" <skill>/scripts/qa_check.py 文档.docx --source-md doc.md
```

判读要点：

| 字段 | 合格值 | 说明 |
| --- | --- | --- |
| `ok` / 退出码 | `true` / `0` | 有 issue 就不合格 |
| `md_items_missing` | **0** | 非 0 就是整块内容丢了，`missing` 字段会列出具体是哪几块 |
| `residual_asterisk` | **0** | 非 0 说明 `**加粗**` 没被渲染成粗体 |
| `residual_backtick` | **0** | 非 0 说明 `` `等宽` `` 没被渲染 |
| `math_objects` | 与源文件公式数吻合 | 明显偏少说明有公式没转换 |
| `code_block_paragraphs` | 与源文件 ``` 块行数吻合 | 为 0 而源文件有代码块 = 整块丢失 |
| `warnings` / `notes` | 逐条读过 | 例如「代码块偏宽……只能压到 6.0pt」 |

### 2. 解包核验原生公式与图片

```bash
python - <<'EOF'
import zipfile, re
z = zipfile.ZipFile("文档.docx")
x = z.read("word/document.xml").decode("utf-8")
print("oMath:", x.count("<m:oMath"))          # 原生公式数
print("残留 $:", x.count("$"))                 # 必须为 0
print("残留 **:", x.count("**"))               # 必须为 0（**加粗** 标记必须全部被渲染）
print("反引号:", x.count("`"))                 # 排除代码块后应为 0
print("表格:", x.count("<w:tbl>"))
print("图片:", x.count("<w:drawing>"))
print("媒体:", [n for n in z.namelist() if "media" in n])
EOF
```

PPTX 同理，改读 `ppt/slides/slideN.xml`，图片关系数看 `ppt/media/` 与
各 `slideN.xml.rels`。

### 3. 用 Word 真实排版引擎核验「有没有折行、有没有越界」

解包只能看到 XML 里写了什么，**看不到 Word 实际排出来是什么样**。
方框图是否折行、正文栏是否溢出，只有排版引擎说了算。

```python
# 用 pywin32，不要用 PowerShell
import win32com.client as wc
app = wc.gencache.EnsureDispatch("Word.Application")
app.Visible = False
doc = app.Documents.Open(r"D:\path\文档.docx", False, True)

pw, ph = float(doc.PageSetup.PageWidth), float(doc.PageSetup.PageHeight)
col_r = pw - float(doc.PageSetup.RightMargin)
print(f"{pw:.1f}x{ph:.1f}pt  正文栏右界 {col_r:.1f}pt")
print("oMath:", doc.OMaths.Count, " 图片:", doc.InlineShapes.Count)

for p in doc.Paragraphs:
    t = p.Range.Text.lstrip()
    if not t or t[0] not in "─│┌┐└┘├┤┬┴┼":
        continue
    lines = p.Range.ComputeStatistics(1)          # wdStatisticLines
    x2 = float(doc.Range(p.Range.End - 1, p.Range.End - 1).Information(5))
    if lines > 1 or x2 > col_r + 0.5:
        print("有问题：", lines, x2, repr(t[:40]))

doc.Close(False); app.Quit()
```

### 4. 逐块清点（人工抽查）

打开成品，对照 Markdown 源**从头翻到尾**，确认：

- 每个二级标题都在，中间没有断层；
- 代码块（板书设计、问题链架构图）完整，没有少行、没有错位；
- 师生活动是**并列**关系，不是被并进同一串编号；
- 加粗的地方真的粗了，没有漏出星号。

---

## 二、环境与工具的坑

### 页面尺寸：python-docx 默认是 Letter，不是 A4

`Document()` 的默认模板是 **Letter（8.5×11in = 612×792pt）**。国内教学材料必须显式设成 A4：

```python
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
```

忘了设的后果：打印时与 A4 纸张不匹配；而且按 A4 算的栏宽估算会偏，代码块字号全错。

### Word 完全忽略负的段落缩进

实测（A4、左右边距 2.2cm、90 个字符的行）：

| 左缩进 | 右缩进 | 首字符位置 | 行末位置 |
| --- | --- | --- | --- |
| 0 | 0 | 62.5pt | 467.7pt |
| **-1.4cm** | 0 | 62.5pt | 467.3pt |
| 0 | **-1.4cm** | 62.5pt | 467.7pt |
| **-1.4cm** | **-1.4cm** | 62.5pt | 467.3pt |

`w:ind w:left="-794"` 写得再对也没用，**排版位置一动不动**。
所以不要指望用负缩进把内容撑进页边距——那是靠不住的。
需要更宽的版面，就老老实实改 Markdown 里的内容宽度，或改页面/页边距。

### PowerShell 的晚绑定 COM 不可靠

`$d.PageSetup.PageWidth` 返回的是 `__ComObject` 而不是数字：

- `$x -gt $d.PageSetup.PageWidth` → `无法将"78.35"与"System.__ComObject"进行比较`
- `$d.PageSetup.PageWidth - $d.PageSetup.RightMargin + 1` → `不包含名为"op_Addition"的方法`

`[double]` 强转也救不回来。**要驱动 Word/Excel COM，用 pywin32（Python）**，
或者干脆把值先转成字符串再在 Python 里算。

### PowerShell 工具的 stdout 不被捕获

必须把日志写进文件，再用 Read 读。另外 `$ErrorActionPreference = "Stop"` 要配合
`try/catch` 把异常也写进同一个日志文件，否则脚本静默失败、日志是空的。

### 本机导出 PDF 会被中止

`ExportAsFixedFormat` 与 `SaveAs2(pdf, 17)` 在本机沙箱内会杀掉 Word 进程。
**不要用导出 PDF 的方式核验排版**——用上面第 3 步的 `ComputeStatistics` +
`Information(5)` 组合，能拿到行数与实际坐标，比截图更精确。

---

## 三、常见缺陷对照表

| 现象 | 根因 | 处理 |
| --- | --- | --- |
| 正文里漏出 `**` / 反引号 | 渲染器没解析行内标记 | 修 `add_rich` / `fill_paragraph`，先配平行内标记再切公式 |
| 代码块整块消失 | 块渲染循环里没有 `t == "code"` 分支 | 补分支；等宽字体 + 浅底纹原样输出 |
| 列表编号变成 6./10./11. | 一整段列表行收成一个 block，`ordered` 只看首行，渲染时全局重编号 | 按「缩进 + 标记类型」分组，组内计数，缩进加深即重开 |
| 方框图折行，图废掉 | 字号超过正文栏宽能容纳的宽度 | 按最长行自适应字号；下限 6pt 兜底；过宽时提示去收窄源文件 |
| 公式没转换、漏出 `\frac` | 引擎不支持该宏包（如 `\ce{}`） | 按 `references/subjects.md` 改用 `\text{}` 写法 |
| 公式里中文变成方框 | OMML 的 run 没指定中文字体 | 走 `\text{}`，引擎会自动带 `w:eastAsia` |

---

## 四、验收记录模板

交付时把这几项写清楚，便于回溯：

```
文件：xxx.docx
源文件：xxx.md
质检：qa_check.py --source-md → ok=true, md_items_missing=0,
      residual_asterisk=0, residual_backtick=0, math_objects=121
解包：oMath=121, 残留 $=0, 表格=2, 图片=0
排版：Word 核验 A4 595.3x841.9pt，方框图段落 31 个，折行 0，越界 0
警告：代码块偏宽（74 字符当量 > 55），已压到 6.0pt
```
