---
name: writing-humanizer
description: "面向技术文档、教程科普、行业评论与严肃学术论文的专业去 AI 味与结构去模板化工具。基于大语言模型结构偏见（RLHF 长度偏见、论证均质化、动词名物化）与计算文体学研究，消除元话语充水、假大空升华、翻案腔与机械对称。支持普通改稿、严格白名单清理、自动化特征扫描诊断及学术正向润色模式；死守信息守恒、受保护实体（代码/公式/数据/引文）绝对保真与严肃书面语体底线（去味绝不口语化），不虚构数据，明确不承诺、不以规避检测器分数为目的。"
compatibility: "纯文本及 Markdown 文件编辑；可选 Python 运行自动化扫描与门禁脚本。"
---

# Writing Humanizer (Professional & Academic Edition)

专注于**技术文章、教学指南、深度评论与严肃学术论文**的去 AI 味、结构去模板化与专业编辑工具。

本项目底层结合了两大理论支柱：
1. **大语言模型表述偏见实证研究**（RLHF 充水偏见、论证均质八股化、动词名物化与虚假深刻）；
2. **文本统计特征与计算文体学**（节奏工程与突发性 CV、语义连贯、受保护片段隔离与语体守门）。

**核心立场**：**高信噪比、机制透彻、动词强劲、结构随逻辑自然流动**。**去 AI 味 $\ne$ 口语化**。本工具旨在帮助作者产出严谨、清晰的人类专业文本，提升真实可读性与学术规范，**明确不以对抗或规避特定检测器为目的，不承诺任何检测器分数**。

---

## 一、 快速任务判定与模式路由

根据用户需求快速分流执行：

1. **普通改稿（默认）**：用户提出“去 AI 味”、“改得自然一点”、“润色优化”。
   - 重点打破八股循环、清除元话语、动词归位、消除空泛拔高。字数控制在原文有效字数的 90%–110%。
2. **学术论文正向润色**：用户提出“论文去 AI 味”、“学术润色”、“清除论文模板套话”。
   - 执行**三轮正向编辑协议**（隔离受保护片段 $\rightarrow$ 结构重组与确定性精简 $\rightarrow$ 注入学术审慎特征 $\rightarrow$ Anti-AI 审计与语体守门）。以消除模板化句式与改善论证质量为验收依据，**严肃学术书面语体为硬底线，严禁为了显得“像人写”而引入口语化**。参考 `references/academic-positive-style.md`。
3. **严格白名单清理**：用户提出“只按规则改”、“不要自由发挥”、“保底成稿清理”。
   - 严格按明确规则逐句改写（参考 `references/strict-whitelist-rules.md`）。**未命中规则的句子逐字保留**，排版与结构不变。
4. **检测/诊断模式**：用户提出“查哪里像 AI”、“运行扫描”、“只诊断不改”。
   - 调用 `python scripts/aigc_scan.py <file>` 扫描 10 核心维度特征，输出结构与表达层面的问题表格及最小修复建议。

---

## 二、 最高准则（不可逾越的红线）

1. **信息守恒（零幻觉、零虚构）**：
   - 严禁新增任何原文未包含的实体、参数、实验数据、年份、API、案例、结论或参考文献标号；
   - 严禁删减或篡改原文的适用范围、限制条件、否定判断与确定程度。
2. **专业实体与受保护片段绝对保真（参考 `references/protected-spans.md`）**：
   - 代码块、行内命令、配置参数、文件路径原样保留；
   - 数学公式、LaTeX、统计值（P值、误差范围）、图表编号、文献引用编号（`[20]`）原样保留；
   - 方法描述中规范合规的被动语态予以保留。
3. **语体规范优先于修改率（硬底线）**：
   - 严禁为了“制造人味”或“凑修改率”引入网络热词、俚语、大白话、轻浮短句或泛滥的破折号；
   - 宁可保留少许书面生硬，也绝不滑向口语化。**语体规范始终优先于字面修改率**。
4. **最小有效干预**：
   - 没有结构或表达病征的自然段落原样保留，严禁无病呻吟式重写。

---

## 三、 四层审查与优化流程

```text
通读预检 ──► 1. 篇章结构 ──► 2. 深度去味 ──► 3. 句法语义 ──► 4. 终审守门
(圈保护区)    (打破八股)      (消除充水)      (动词归位)     (语体防超标)
```

1. **篇章层：打破八股与对称（参考 `references/document-flow.md`）**
   - 打破段落对称与八股循环（消除通篇“观点 $\rightarrow$ 阐述 $\rightarrow$ 总结”）；
   - 调节节奏工程（长短句自然错落，目标突发性 CV 提升至 $\approx 0.45$）；
   - 彻底删除结尾处假大空的“全新范式”、“奠定基石”等虚无升华。
2. **深度层：深度 AI 痕迹脱水（参考 `references/deep-ai-patterns.md` & `meta-discourse.md`）**
   - 排查 10 种深度 AI 痕迹：重要性膨胀、系词回避、三板斧强迫症、公式化挑战段、悬浮式因果链等；
   - 剔除无靶自立的翻案腔（“不是……而是……”）与空转元话语（“需要明确的是”）。
3. **句法层：动词归位与确定性替换（参考 `references/sentence-clarity.md` & `replacement-tables.md`）**
   - 动词归位：还原弱化动词与名物化堆叠（将“实现……的优化”还原为实动词）；
   - 检索 72 个中文 AI 高频词与模板连接词，执行语境化的确定性替换。
4. **终审层：保真复核与语体守门（参考 `references/academic-positive-style.md` & `protected-spans.md`）**
   - 核对受保护片段与实词出处；
   - 运行口语化负面清单与破折号密度核验（每段破折号 $\le 1$ 个）。

---

## 四、 交付规范

- **普通改稿交付**：交付优化后的完整正文，附带简要《改动说明》（关键结构优化点、清除的高频充水套话，以及有效字数变化比）。
- **学术润色交付**：交付符合严肃学术语体的正文，附带受保护片段保真确认、破折号及语体守门合格确认。
- **严格白名单交付**：输出逐字清理文本，标明命中的具体规则编号。
- **诊断模式交付**：输出 10 核心维度扫描报告或问题诊断定位表格（片段位置、病征分析、阅读负担、最小修改建议）。

---

## 五、 模块化参考索引（低耦合设计）

- **理论基石**：
  - [references/theoretical-basis.md](references/theoretical-basis.md)：OpenAI RLHF 结构偏见与实证研究
  - [references/detection-principles.md](references/detection-principles.md)：知网/万方/PaperPass/GPTZero检测机制与攻防深度解析
- **篇章与表达规范**：
  - [references/document-flow.md](references/document-flow.md)：篇章流、打破八股、反流水账与节奏工程
  - [references/meta-discourse.md](references/meta-discourse.md)：元话语脱水、清除翻案腔与假大空升华
  - [references/deep-ai-patterns.md](references/deep-ai-patterns.md)：10 种深度 AI 痕迹识别模式
  - [references/sentence-clarity.md](references/sentence-clarity.md)：句法精炼、动词归位与去名物化
  - [references/replacement-tables.md](references/replacement-tables.md)：词级替换表、72个AI高频词与口语化负面清单
- **体裁与安全护栏**：
  - [references/genre-profiles.md](references/genre-profiles.md)：技术文档、教程科普、行业随笔、学术论文体裁侧重
  - [references/academic-positive-style.md](references/academic-positive-style.md)：学术论文正向标准与三级对照表（守语体底线）
  - [references/protected-spans.md](references/protected-spans.md)：受保护片段与语义守恒契约（代码/公式/数据/引文预检与保真核验）
  - [references/strict-whitelist-rules.md](references/strict-whitelist-rules.md)：严格白名单规则集（保底改稿专精）
  - [references/length-budget.md](references/length-budget.md)：篇幅预算与修改率核算标准
- **评测与自动化工具**：
  - [scripts/aigc_scan.py](scripts/aigc_scan.py)：Python 10 维度轻量 AIGC 与语篇规范扫描器
  - [evals/benchmark.md](evals/benchmark.md)：双向改稿 Benchmark（SF 该改 / SNF 严禁误伤）
