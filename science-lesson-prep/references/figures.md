# 函数图象规格

图象写在 `plot` 围栏代码块里，内容是一段 JSON。`render.py` 会用 matplotlib 绘制，
输出 PNG 与 SVG，并插入到文档中。

## 最小示例

````markdown
```plot
{
  "title": "二次函数 y = x² - 2x - 3 的图象",
  "x": [-3, 5],
  "y": [-6, 8],
  "curves": [{"expr": "x**2 - 2*x - 3", "label": "y = x² - 2x - 3"}]
}
```
````

## 字段说明

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `title` | 字符串 | 图标题 |
| `x` | `[xmin, xmax]` | 横轴范围，必填 |
| `y` | `[ymin, ymax]` | 纵轴范围，省略则自动 |
| `size` | `[宽, 高]`（英寸） | 图幅，单图默认 `[7.2, 4.4]` |
| `grid` | 布尔 | 是否画网格，默认 `true` |
| `axis` | 布尔 | 是否画 x/y 轴，默认 `true` |
| `xlabel` / `ylabel` | 字符串 | 坐标轴名称，默认 `x` / `y` |
| `samples` | 整数 | 采样点数，默认 1200；图象有尖角时可调大 |
| `curves` | 数组 | 曲线列表 |
| `points` | 数组 | 标记点 |
| `vlines` / `hlines` | 数组 | 参考线（对称轴、渐近线、边界线） |
| `texts` | 数组 | 图上文字标注 |
| `layout` + `panels` | — | 并排多图 |

### curves 数组

| 字段 | 说明 |
| --- | --- |
| `expr` | **必填**，x 的表达式，NumPy 写法 |
| `label` | 图例文字 |
| `color` | 颜色，如 `"#D85A30"`；省略则按调色板自动分配 |
| `style` | 线型：`"-"` 实线、`"--"` 虚线、`":"` 点线 |
| `width` | 线宽，默认 2.0 |
| `xrange` | `[a, b]`，只画这一段定义域，用于分段函数 |

### points 数组

`{"x": 1, "y": -4, "label": "顶点 (1, -4)", "color": "#A32D2D", "size": 7, "annotate": true}`

### vlines / hlines 数组

`{"x": 1, "label": "对称轴 x = 1"}`、`{"y": 0, "label": "y = 0"}`
可加 `"style": "--"`、`"color": "#888780"`。

## 表达式写法

`expr` 是 x 的 NumPy 表达式，可用函数：

`sin cos tan arcsin arccos arctan sinh cosh tanh`、`exp log ln log10`、
`sqrt abs floor ceil sign power maximum minimum where`、
常量 `pi e inf`

示例：

| 函数 | expr |
| --- | --- |
| 二次函数 | `"x**2 - 2*x - 3"` |
| 绝对值 | `"np.abs(x - 1)"` |
| 分式 | `"1/(x-2)"` |
| 指数 | `"2**x"` 或 `"np.exp(x)"` |
| 对数 | `"np.log(x)"`（注意定义域 x>0） |
| 三角函数 | `"np.sin(x)"` |
| 分段（用 where） | `"np.where(x>=0, x**2, -x)"` |
| 分段（用 xrange） | 两条 curve，各自设 `xrange` |

## 分段函数的两种画法

**方法一：两条曲线各限定义域**（推荐，交接处不会连错）

```json
{
  "x": [-3, 3], "y": [-1, 9],
  "curves": [
    {"expr": "x**2", "xrange": [0, 3], "label": "y = x² (x ≥ 0)"},
    {"expr": "-x",   "xrange": [-3, 0], "label": "y = -x (x < 0)", "color": "#D85A30"}
  ]
}
```

**方法二：用 where 一次画出**

```json
{"curves": [{"expr": "np.where(x>=0, x**2, -x)", "label": "f(x)"}]}
```

## 并排多图

```json
{
  "size": [9.2, 3.9],
  "layout": [1, 2],
  "panels": [
    {"title": "y = x²", "x": [-3.5, 3.5], "y": [-1, 9],
     "curves": [{"expr": "x**2", "label": "y = x²"}]},
    {"title": "y = (x+1)²", "x": [-4.5, 2.5], "y": [-1, 9],
     "curves": [{"expr": "(x+1)**2", "label": "y = (x+1)²", "color": "#D85A30"}],
     "vlines": [{"x": -1, "label": "对称轴 x = -1"}]}
  ]
}
```

`layout` 为 `[行, 列]`。用 `panels` 时顶层不要再写 `curves`。

## 关于标签中的上下标

`label`、`title`、`points[].label` 里可以直接写 `x²`、`x₁` 这类 Unicode 上下标——
`figures.py` 会自动把它们转成 mathtext，交给数学字体渲染，不会出现方框。

也可以直接写 matplotlib 数学模式：`"label": "$y = x^2$"`，两种写法都支持。

## 版面行为

- **教案 DOCX**：图象居中，宽度 13cm，内部文字按打印尺寸渲染。
- **课件 PPTX**：图象内部文字自动放大 1.8 倍（投影可读）。
  - 宽高比 ≥ 1.6 的宽图 → 排在文字下方通栏；
  - 更接近方形的图 → 排在文字右侧。
  - 同一页有多张图时自动两列排布。

## 注意事项

- 图象数量不必多。一节课 2~4 张关键图象即可，重复的图形反而分散注意力。
- 画对数、分式等有间断点的函数时，务必给 `y` 设范围，
  否则竖直渐近线附近会画出误导性的连线。
- `expr` 中的乘方要写 `**`，不要写 `^`。
- `expr` 里不要写 `x²`，写 `x**2`。
