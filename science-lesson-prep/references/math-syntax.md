# 数学公式书写规范

本文件规定 Markdown 中间表示中公式的写法。**这些规则不是风格偏好，写错会导致渲染失败或显示错误。**

## 一、基本约定

| 场景 | 写法 | 说明 |
| --- | --- | --- |
| 行内公式 | `$x^2 + 2x + 1$` | 与中文同段，前后不加空格也可 |
| 独立公式 | `$$x = \frac{-b}{2a}$$` | 单独成行，渲染为居中 |
| 公式内中文 | `$x \text{ 为有理数}$` | 必须包在 `\text{}` 里 |

公式外与正文衔接处用全角中文标点：

```markdown
设函数 $f(x)$ 的定义域为 $A$，则 $f(0) = 1$。
```

## 二、必须避免的写法

### 1. 不使用 Unicode 上下标

中文字体（宋体、黑体）普遍缺少 `²`、`₃`、`ⁿ` 这类字形，直接写会渲染成方框。

| 错误 | 正确 |
| --- | --- |
| `x²` | `$x^2$` |
| `x₁` | `$x_1$` |
| `H₂O` | `$H_2O$` |
| `aⁿ` | `$a^n$` |

### 2. 分数用 `\frac`，不用斜线模拟

| 错误 | 正确 |
| --- | --- |
| `a/b`（表示分数时） | `$\frac{a}{b}$` |
| `(x+1)/(x-1)` | `$\frac{x+1}{x-1}$` |

日期、文件路径、编号、比例中的 `/` 不受此限制。

### 3. 箭头用 LaTeX 命令

数学公式内部：`$A \to B$`、`$A \Rightarrow B$`、`$A \Leftrightarrow B$`。
教学流程、普通文本中的箭头可用 Unicode `→`。

### 4. 表格单元格里含竖线的公式照常写

```markdown
| 参数 | 影响 |
| --- | --- |
| $|a|$ | 越大开口越小 |
| $P(A|B)$ | 条件概率 |
```

解析器会把 `$...$` 内部的 `|` 识别为公式内容而不是表格分隔符。
**不要为了绕开竖线而把公式改写成不含绝对值的形式。**

## 三、已验证可用的 LaTeX 命令

以下命令均经过实际转换与 Office 渲染验证，可放心使用。

**结构**：`\frac{}{}`、`\sqrt{}`、`\sqrt[3]{}`、`\begin{cases}...\end{cases}`、
`\begin{pmatrix}...\end{pmatrix}`、`\begin{vmatrix}...\end{vmatrix}`、`\left( \right)`、
`\left| \right|`、`\sum_{i=1}^{n}`、`\int_0^1`、`\lim_{x \to 0}`、`\binom{n}{m}`

**重音与装饰**：`\vec{}`、`\bar{}`、`\hat{}`、`\tilde{}`、`\dot{}`、`\overline{}`

**数集**：`\mathbb{R}`、`\mathbb{Z}`、`\mathbb{N}`、`\mathbb{Q}`、`\mathbb{C}`

**希腊字母**：`\alpha \beta \gamma \theta \mu \sigma \varphi \omega \Delta \Omega`

**关系与运算**：`\pm \mp \times \div \cdot \leq \geq \neq \approx \equiv \sim \propto`
`\in \notin \subseteq \subset \cup \cap \varnothing \infty`

**几何**：`\triangle \angle \parallel \perp \cong \sim`、`^\circ`

**逻辑**：`\because \therefore \Rightarrow \Leftrightarrow \to`

**函数名**：`\sin \cos \tan \arcsin \arccos \arctan \log \ln \exp`

**其他**：`\quad`、`\qquad`、`\,`、`\cdots`、`\dots`

## 四、排版细节

- **不要在一个段落里塞太多独立公式**，独立公式之间用空行分开。
- **公式内不加中文空格**，需要间隔用 `\quad` 或 `\ `。
- **分段函数的分支对齐用 `&`**：

```markdown
$$f(x) = \begin{cases}
  x^2, & x \geq 0 \\
  -x,  & x < 0
\end{cases}$$
```

- **方程组写法**：

```markdown
$$\begin{cases}
  2x + y = 5 \\
  x - y = 1
\end{cases}$$
```

## 五、公式显示异常时的排查顺序

1. 跑 `qa_check.py`，看报告里指出的具体位置与问题类型。
2. 若报告"残留 `$` 定界符"：多半是公式里漏了配对的 `$`，或表格单元格里公式含竖线但写法有误。
3. 若报告"残留 LaTeX 命令"：说明该公式没走转换，检查是否写在了 `$` 之外。
4. 若报告"未修正的重音结构"：说明用了 `omml.py` 之外的转换路径。
5. 若报告"公式内中文未指定字体"：把中文改写进 `\text{}`。
