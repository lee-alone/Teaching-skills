# 科学学科符号与表达式规范（物理 / 化学 / 生物）

本文件规定科学学科（物理、化学、生物）中特有的符号、公式、方程式与单位的标准书写规范，确保导出至 Office 时符号正斜体正确、结构不乱码。

## 一、先看能力边界：只有一条硬约束

公式引擎对物理、化学、生物的常见写法**都支持**，唯一不支持的是 `\ce{}`（mhchem 宏包）。

```markdown
$$\ce{2H2 + O2 -> 2H2O}$$        ← 错误写法
```

它会原样漏出成 `\ce2H2+O2−>2H2O`——`\ce` 留在正文里，`->` 还被拆成减号加大于号。

**化学方程式一律用 `\text{}` + `\xrightarrow{}` 写**，见下一节。
除此之外无需回避任何常用写法。

## 二、化学：方程式写法

化学式里的元素符号必须用 `\text{}` 包成**正体**（化学式不排斜体）。

| 元素 | 写法 | 效果 |
| --- | --- | --- |
| 下标 | `\text{H}_2\text{O}` | H₂O |
| 离子电荷 | `\text{CO}_3^{2-}`、`\text{H}^+`、`\text{Fe}^{3+}` | CO₃²⁻、H⁺、Fe³⁺ |
| 反应条件 | `\xrightarrow{\text{点燃}}` | 条件排在箭头上方 |
| 加热 | `\xrightarrow{\Delta}` | Δ 排在箭头上方 |
| 催化剂 | `\xrightarrow[\text{MnO}_2]{\Delta}` | Δ 在上、MnO₂ 在下 |
| 气体 | `\uparrow` | ↑ |
| 沉淀 | `\downarrow` | ↓ |
| 可逆反应 | `\rightleftharpoons` | ⇌ |
| 结晶水 | `\text{CuSO}_4 \cdot 5\text{H}_2\text{O}` | CuSO₄·5H₂O |

完整示例：

```markdown
$$2\text{H}_2 + \text{O}_2 \xrightarrow{\text{点燃}} 2\text{H}_2\text{O}$$

$$2\text{KClO}_3 \xrightarrow[\text{MnO}_2]{\Delta} 2\text{KCl} + 3\text{O}_2\uparrow$$

$$\text{Fe}^{3+} + 3\text{OH}^- \to \text{Fe(OH)}_3\downarrow$$

$$\text{N}_2 + 3\text{H}_2 \rightleftharpoons 2\text{NH}_3$$
```

对照着看两种错法：

```markdown
$$\ce{2KClO3 ->[\text{MnO2}][\Delta] 2KCl + 3O2}$$   ← \ce 不支持
$$2KClO_3 \to 2KCl + 3O_2$$                          ← 元素符号被排成斜体
```

## 三、物理

矢量用 `\vec{}`，希腊字母直接写：

```markdown
$$\vec{F} = m\vec{a}$$
$$a = \frac{\Delta v}{\Delta t}$$
$$\varepsilon = -N\frac{\Delta\Phi}{\Delta t}$$
$$\rho = \frac{m}{V}$$
```

**单位必须写成正体**，否则会被当成变量排成斜体（m/s 会变成斜体 m 除以斜体 s）：

```markdown
$$9.8\ \text{m/s}^2$$      ← 对
$$9.8 m/s^2$$              ← 错，m 与 s 会变成斜体
```

变化量用 `\Delta`，如 `\frac{\Delta v}{\Delta t}`。

v-t 图、F-x 图、U-I 图用 `plot` 代码块画，横纵轴含义写进 `title` 或 `texts`
（见 `figures.md`）。

## 四、生物

分子式与化学同法：`\text{C}_6\text{H}_{12}\text{O}_6`、`\text{CO}_2`、`\text{H}_2\text{O}`。

```markdown
$$6\text{CO}_2 + 6\text{H}_2\text{O} \xrightarrow{\text{光照}} \text{C}_6\text{H}_{12}\text{O}_6 + 6\text{O}_2$$
```

遗传学：

```markdown
$$Aa \times Aa \to 3:1$$
$$P(A) = \frac{1}{2}$$
$$\frac{9}{16}A\_B\_$$
```

注意基因型里的下划线要转义成 `\_`，否则会被当成下标。

生物材料公式少、图示多，重点在过程图、实验设计与图表分析，公式按需写即可。
