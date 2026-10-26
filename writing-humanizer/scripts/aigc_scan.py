#!/usr/bin/env python3
"""
AIGC 特征与语篇规范扫描器 — 专用于非虚构、技术文章与学术论文

基于计算文体学与知网/万方/PaperPass/GPTZero检测机理，扫描 10 个核心维度：
  1. 模板句式与翻案腔密度
  2. 被动语态比例（低权重参考项，尊重合规实验方法论）
  3. 句子长度均匀度（突发性 CV 变异系数，样本 >= 5 句有效）
  4. 段落长度对称性（反八股对称）
  5. 嵌套编号堆叠（排除公式、运算符、年份与文献引用）
  6. 冒号并列结构（支持分号与连续逗号列举）
  7. 标点符号规律性
  8. 口语化/网络用语预警（严肃语体守门）
  9. 破折号密度（全角/双破折号超标检测，每段 ≤1 处）
  10. 模型退化与元信息泄漏（死循环复读、大模型自指、拒答词、上下文占位符）

核心特性：
  - 自动隔离受保护片段（代码块、行内代码、LaTeX 公式、URL、HTML、Markdown 引用块及成对直接引语）；
  - 修复元信息正则，杜绝“策略模型/误差略有差异”等日常词汇误报；
  - 综合风险评分严格归一化为 0.0 ~ 1.0；
  - 支持 --threshold 阈值门禁控制与 CI/CD 自动化退出码（score >= threshold 时 exit 1）。

用法: python aigc_scan.py <file.txt/md> [--json] [--threshold 0.5]
"""

import re
import sys
import json
import argparse
from collections import Counter
from pathlib import Path

# Windows 终端 UTF-8 兼容性保障
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass


# ─── 1. 受保护片段隔离遮罩 ───
PROTECTED_PATTERNS = [
    # 多行代码块 (```...``` 及 ~~~...~~~)
    re.compile(r'```[\s\S]*?```'),
    re.compile(r'~~~[\s\S]*?~~~'),
    # 行内代码 (`...`)
    re.compile(r'`[^`\n]+`'),
    # 块级 LaTeX 公式 ($$...$$ 及 \[...\])
    re.compile(r'\$\$[\s\S]*?\$\$'),
    re.compile(r'\\\[[\s\S]*?\\\]'),
    # 行内/跨行 LaTeX 公式 ($...$ 及 \(...\))
    re.compile(r'(?<!\$)\$[^$\n]+\$(?!\$)'),
    re.compile(r'\\\([\s\S]*?\\\)'),
    # URL 链接 (http:// 或 https://)
    re.compile(r'https?://[^\s)）]+'),
    # HTML 注释与标签 (<!--...-->)
    re.compile(r'<!--[\s\S]*?-->'),
    # Markdown 引用块 (> ...)
    re.compile(r'^\s*>[^\n]*', re.MULTILINE),
    # 中文双引号直接引语（支持跨行，段落内封闭，不越过空行）
    re.compile(r'“[^”\r\n]*(?:\r?\n(?!\r?\n)[^”\r\n]*)*”'),
    # 中文单引号直接引语（支持跨行，段落内封闭，不越过空行）
    re.compile(r'‘[^’\r\n]*(?:\r?\n(?!\r?\n)[^’\r\n]*)*’'),
    # 中文直角引号直接引语 (「...」 / 『...』，支持跨行，段落内封闭)
    re.compile(r'「[^」\r\n]*(?:\r?\n(?!\r?\n)[^」\r\n]*)*」'),
    re.compile(r'『[^』\r\n]*(?:\r?\n(?!\r?\n)[^』\r\n]*)*』'),
    # 英文双引号直接引语（支持跨行，段落内封闭，不越过空行）
    re.compile(r'"[^"\r\n]*(?:\r?\n(?!\r?\n)[^"\r\n]*)*"'),
]


def mask_protected_spans(text: str) -> str:
    """用空格遮罩受保护片段，保留字符长度与行结构，避免引语与代码被误判"""
    def replacer(match):
        span_text = match.group(0)
        return ''.join('\n' if c == '\n' else ' ' for c in span_text)

    masked = text
    for pattern in PROTECTED_PATTERNS:
        masked = pattern.sub(replacer, masked)
    return masked


# ─── 2. 模板句式库（使用非捕获组确保完整匹配） ───
TEMPLATE_PATTERNS = [
    # 段落开头模板
    r'^(?:综上所述[，,])',
    r'^(?:基于.{2,10}(?:分析|研究|探讨))',
    r'^(?:通过.{2,15}(?:验证|实验|研究|测定))',
    r'^(?:随着.{2,20}(?:发展|进步|深入))',
    r'^(?:近年来[，,])',
    r'^(?:在.{2,20}(?:背景下|条件下|过程中))',
    r'^(?:本研究[旨在对通过])',
    r'^(?:目前[，,])',
    r'^(?:当前[，,])',
    r'^(?:因此[，,])',
    r'^(?:由此可见[，,])',
    r'^(?:总而言之[，,])',
    # 过渡词冗余
    r'(?:此外[，,])',
    r'(?:另外[，,])',
    r'(?:与此同时[，,])',
    r'(?:值得注意的是[，,])',
    r'(?:需要指出的是[，,])',
    # 模糊表述与空洞拔高
    r'(?:据统计[，,])',
    r'(?:相关研究表明[，,])',
    r'(?:一般认为[，,])',
    r'(?:具有重要的.{2,10}(?:意义|价值|作用))',
    r'(?:具有广阔的应用前景)',
    r'(?:为.{2,20}(?:提供了|奠定了).{2,10}(?:基础|依据|参考))',
    # 成对转折或否定收束（翻案腔）
    r'(?:不是[^\n。！？!?.]{1,40}而是)',
    r'(?:但至少)',
    r'(?:不代表)',
    r'(?:不等于)',
    r'(?:不一定[^\n。！？!?.]{1,40}(?:但是|但|却))',
    r'(?:即使[^\n。！？!?.]{1,40}也)',
]

# ─── 3. 被动语态标记 ───
PASSIVE_MARKERS = [
    r'被.{1,15}(?:测定|检测|验证|确认|证明|发现|计算)',
    r'由.{1,15}(?:进行|完成|测定|检测|计算)',
    r'经.{1,15}(?:测定|检测|计算|分析)',
    r'通过.{1,15}(?:测定|检测|验证|实验|计算)',
    r'采用.{1,15}(?:进行|测定|检测)',
]

# ─── 4. 嵌套编号条目候选（识别冒号/分号/段首引导的列表分项条目） ───
# 要求编号位于段首、行首、冒号或分号后，且后跟正文条目内容，排除行内算式 (1)+(2) 与文献引用
NESTED_NUM_CANDIDATE = re.compile(
    r'(?:^|[\n：:；;])\s*[（(](\d{1,2})[）)]\s*([^（()\n；;。！？]{2,})'
)

# ─── 5. 冒号并列结构 ───
COLON_LIST_PATTERNS = [
    # 冒号 + 至少两个分号分隔项
    re.compile(r'[：:]\s*[^。！？\n]+?[；;]\s*[^。！？\n]+?[；;]'),
    # 冒号 + 连续 3 个及以上逗号分隔项
    re.compile(r'[：:]\s*[^。！？\n]+?[，,]\s*[^。！？\n]+?[，,]\s*[^。！？\n]+?[，,。！？\n]'),
]

# ─── 6. 全角标点 ───
FULLWIDTH_PUNCT = set('，。！？；：、""''（）【】《》')

# ─── 7. 口语化 / 网络用语词库（严肃语体守门） ───
COLLOQUIAL_TERMS = [
    # 网络用语
    'yyds', '绝绝子', '破防', 'emo', '拿捏', '整活', '有梗', '无语',
    '离谱', '逆天', '炸裂', '社死', '摆烂', '搞定', '踩坑', '翻车',
    '封神', '硬核', '谁懂啊', '手感',
    # 情绪词
    '气死', '乐死', '笑死', '烦躁', '郁闷',
    # 口语化固定搭配
    '说实话', '坦白讲', '老实说', '不瞒你说', '说白了', '讲真', '反正',
    '大概齐', '差不多就是', '这事的难度', '这事儿', '不得不考虑的一环',
    '一点一点磨出来', '撑起来', '比表面看起来大得多', '说到底', '归根结底就是',
    '真的强', '真的行', '拉满', '没跑偏',
]

# ─── 8. 破折号模式（支持双全角、单全角及 ASCII 破折号） ───
DASH_PATTERN = re.compile(r'(?:——|—|(?<=\s)--(?=\s)|(?<=\s)---(?=\s))')

# ─── 9. 模型退化、拒答与元信息泄漏（严格限定占位语境，杜绝误报日常词汇） ───
META_LEAK_PATTERNS = [
    # AI 自指
    re.compile(r'作为(?:一个)?(?:AI|人工智能|大?语言模型|智能助手|聊天助手)', re.IGNORECASE),
    # 英文常见拒答/自指开场
    re.compile(r'(?:Sure|Certainly|Here\'?s|As an AI|I (?:cannot|can\'t|am unable|apologize))', re.IGNORECASE),
    # 中文拒答
    re.compile(r'我(?:无法|不能)(?:继续(?:写|生成|下去)|生成|完成(?:这个|本|该)?(?:请求|任务))'),
    # 明确括号内的占位符：如 (此处省略...) / （以下略）
    re.compile(r'[（(](?:此处|以下|这里)?\s*(?:省略|略去|略过)(?:[0-9一二三四五六七八九十百千万]+字)?[^）)]*?[）)]'),
    # 明确词组占位：此处省略 / 这里略去 / 以下省略若干字
    re.compile(r'(?:此处|这里|以下)\s*(?:省略|略去|略过)(?:[0-9一二三四五六七八九十百千万]+字)?'),
    re.compile(r'(?:省略|略去)\s*(?:[0-9一二三四五六七八九十百千万]+字|[0-9]+\s*words)'),
    # 常见占位符与截断
    re.compile(r'(?:未完待续|TODO|占位符|placeholder)', re.IGNORECASE),
    re.compile(r'\ufffd'),
]

# ─── 10. 核心维度权重配置（精确归一化，总和严格等于 1.00） ───
# 核心语体与退化门禁 (0.25 + 0.25) = 0.50
# 结构模板与节奏特征 (0.15 + 0.10 + 0.09) = 0.34
# 次要结构特征 (0.03 * 4 + 0.04) = 0.16
# 总计 = 0.50 + 0.34 + 0.16 = 1.00
DIMENSION_WEIGHTS = {
    'colloquial': 0.25,
    'degeneration': 0.25,
    'template_phrases': 0.15,
    'burstiness': 0.10,
    'dash_density': 0.09,
    'passive_voice': 0.03,
    'para_symmetry': 0.03,
    'nested_numbers': 0.03,
    'colon_lists': 0.03,
    'punctuation': 0.04,
}


def load_text(filepath: str) -> str:
    """读取文本文件"""
    path = Path(filepath)
    if not path.exists():
        print(f"错误: 文件不存在 — {filepath}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding='utf-8')


def split_paragraphs(text: str) -> list[str]:
    """按段落拆分，过滤纯空白行"""
    paras = re.split(r'\n\s*\n', text.strip())
    return [p.strip() for p in paras if p.strip()]


def split_sentences(text: str) -> list[str]:
    """
    智能句子切分：
    - 识别中文句末标点（。！？）与全角断句
    - 识别英文句号（排除浮点数 3.14、常见学术缩写 et al. / e.g. / Fig. 等）
    - 保留有效独立短句（>= 2 字），确保统计无偏移
    """
    cleaned = text
    abbrevs = ['et al.', 'e.g.', 'i.e.', 'Fig.', 'Tab.', 'vs.', 'etc.']
    for abbr in abbrevs:
        cleaned = cleaned.replace(abbr, abbr.replace('.', '__DOT__'))

    pattern = r'[。！？!?\n]|(?<!\d)\.(?!\d)'
    raw_sentences = re.split(pattern, cleaned)

    sentences = []
    for s in raw_sentences:
        restored = s.replace('__DOT__', '.').strip()
        if len(restored) >= 2:
            sentences.append(restored)
    return sentences


def count_template_matches(masked_text: str) -> dict:
    """统计模板句式命中（基于遮罩后文本）"""
    hits = []
    for pattern_str in TEMPLATE_PATTERNS:
        matches = re.finditer(pattern_str, masked_text, re.MULTILINE)
        for m in matches:
            hits.append(m.group(0))
    return {
        'count': len(hits),
        'density_per_1000': round(len(hits) / max(len(masked_text), 1) * 1000, 2),
        'matches': hits[:20]
    }


def count_passive_markers(masked_text: str, sentence_count: int) -> dict:
    """统计被动语态标记"""
    total = 0
    for pattern in PASSIVE_MARKERS:
        total += len(re.findall(pattern, masked_text))
    s_count = max(sentence_count, 1)
    return {
        'count': total,
        'per_sentence': round(total / s_count, 3)
    }


def analyze_burstiness(paragraphs: list[str]) -> dict:
    """分析突发性（句子长度变异系数 CV = std / mean）"""
    all_sent_lengths = []
    for para in paragraphs:
        sents = split_sentences(para)
        for s in sents:
            all_sent_lengths.append(len(s))

    if len(all_sent_lengths) < 5:
        avg_len = sum(all_sent_lengths) / len(all_sent_lengths) if all_sent_lengths else 0
        return {'avg_len': round(avg_len, 1), 'std_len': 0, 'cv': 0, 'risk': '句子样本少于5句，不判定CV风险'}

    avg_len = sum(all_sent_lengths) / len(all_sent_lengths)
    variance = sum((l - avg_len) ** 2 for l in all_sent_lengths) / len(all_sent_lengths)
    std_len = variance ** 0.5
    cv = std_len / max(avg_len, 1)

    if cv < 0.25:
        risk = '高风险 — 句子长度过于均匀，典型 AI 均质特征'
    elif cv < 0.35:
        risk = '中风险 — 句子变化度偏低'
    elif cv < 0.5:
        risk = '正常 — 具有自然长短句交错'
    else:
        risk = '正常 — 句子长度变化丰富'

    return {
        'avg_len': round(avg_len, 1),
        'std_len': round(std_len, 1),
        'cv': round(cv, 3),
        'risk': risk
    }


def analyze_para_symmetry(paragraphs: list[str]) -> dict:
    """分析段落长度对称性（检测连续 3 段以上字数偏差 < 20% 的刻板对称）"""
    para_lens = [len(p) for p in paragraphs]
    if len(para_lens) < 3:
        return {
            'para_count': len(para_lens),
            'avg_para_len': round(sum(para_lens) / len(para_lens), 1) if para_lens else 0,
            'symmetrical_runs': [],
            'risk': '段落数不足',
        }

    symmetrical_runs = []
    current_run = 0
    for i in range(1, len(para_lens)):
        deviation = abs(para_lens[i] - para_lens[i-1]) / max(para_lens[i-1], 1)
        if deviation < 0.2:
            current_run += 1
        else:
            if current_run >= 2:
                symmetrical_runs.append(current_run + 1)
            current_run = 0
    if current_run >= 2:
        symmetrical_runs.append(current_run + 1)

    return {
        'para_count': len(para_lens),
        'avg_para_len': round(sum(para_lens) / len(para_lens), 1),
        'symmetrical_runs': symmetrical_runs,
        'risk': f'发现 {len(symmetrical_runs)} 处对称段落组' if symmetrical_runs else '未发现明显刻板对称'
    }


def count_nested_numbers(paragraphs: list[str]) -> dict:
    """
    检测条目式嵌套编号：
    - 排除数学运算式中的 (1)+(2)
    - 排除式编号、图表编号与文献引用
    - 仅当同段存在递增的列表条目序号时计入
    """
    total_hits = 0
    valid_sequences = 0

    for para in paragraphs:
        # 查找符合列表条目模式的小标号（元组第 0 项为数字，第 1 项为条目内容）
        matches = [int(m[0]) for m in NESTED_NUM_CANDIDATE.findall(para)]
        if len(matches) >= 2:
            # 严格检查是否存在递增序列（如 1 后跟 2）
            has_seq = any(matches[i] + 1 == matches[i+1] for i in range(len(matches)-1))
            if has_seq:
                total_hits += len(matches)
                valid_sequences += 1

    return {
        'count': total_hits,
        'sequences': valid_sequences,
        'risk': f'检测到 {valid_sequences} 处嵌套编号序列' if valid_sequences > 1 else '正常'
    }


def count_colon_lists(paragraphs: list[str]) -> dict:
    """检测冒号后列举并列结构（支持分号与连续逗号列举）"""
    total = 0
    for para in paragraphs:
        for p in COLON_LIST_PATTERNS:
            total += len(p.findall(para))
    return {
        'count': total,
        'risk': f'检测到 {total} 处冒号列举并列结构' if total > 1 else '正常'
    }


def analyze_punctuation(masked_text: str, sentence_count: int) -> dict:
    """分析标点规律性"""
    fullwidth_count = sum(1 for c in masked_text if c in FULLWIDTH_PUNCT)
    total_chars = max(len(masked_text.strip()), 1)

    comma_count = masked_text.count('，') + masked_text.count(',')
    commas_per_sentence = round(comma_count / max(sentence_count, 1), 2)

    return {
        'fullwidth_punct_ratio': round(fullwidth_count / total_chars * 100, 2),
        'commas_per_sentence': commas_per_sentence,
        'risk': '逗号过密' if commas_per_sentence > 2.5 else '正常'
    }


def count_colloquial_terms(masked_text: str) -> dict:
    """检测口语化/网络用语（基于遮罩文本，防止代码块与引语误判）"""
    hits = []
    for term in COLLOQUIAL_TERMS:
        c = masked_text.count(term)
        if c:
            hits.extend([term] * c)
    return {
        'count': len(hits),
        'terms': sorted(set(hits)),
        'risk': f'⚠️ 检测到 {len(hits)} 处口语化/网络热词，破坏严肃专业语体' if hits else '正常'
    }


def analyze_dash_density(paragraphs: list[str]) -> dict:
    """检测破折号密度（支持 ——、—、--，每段最多 1 处）"""
    over_limit_paras = 0
    total_dashes = 0
    for para in paragraphs:
        matches = DASH_PATTERN.findall(para)
        n = len(matches)
        total_dashes += n
        if n >= 2:
            over_limit_paras += 1
    return {
        'total_dashes': total_dashes,
        'over_limit_paras': over_limit_paras,
        'risk': f'⚠️ {over_limit_paras} 段破折号超标（每段建议 ≤1 处）' if over_limit_paras else '正常'
    }


def analyze_degeneration_and_leakage(masked_text: str, sentences: list[str]) -> dict:
    """检测模型退化循环与元信息泄漏（完整提取匹配文本，杜绝日常用词误报）"""
    leak_hits = []
    for pattern in META_LEAK_PATTERNS:
        for match in pattern.finditer(masked_text):
            leak_hits.append(match.group(0))

    # 检查长句死循环重复（长度 >= 12 且重复出现 >= 3 次）
    long_sentences = [s for s in sentences if len(s) >= 12]
    sent_counts = Counter(long_sentences)
    repeated_loops = [sent for sent, count in sent_counts.items() if count >= 3]

    has_issue = bool(leak_hits or repeated_loops)
    risk_desc = []
    if leak_hits:
        risk_desc.append(f"发现 {len(leak_hits)} 处大模型自指/拒答/占位符泄漏: {leak_hits[:3]}")
    if repeated_loops:
        risk_desc.append(f"发现 {len(repeated_loops)} 组句子陷入死循环复读")

    return {
        'leak_hits': leak_hits,
        'repeated_loops': repeated_loops,
        'has_issue': has_issue,
        'risk': " ；".join(risk_desc) if has_issue else "正常（无自指与死循环）"
    }


def scan(text: str) -> dict:
    """
    完整扫描：
    1. 提取/遮罩受保护片段（代码、公式、URL、引用、直接引语）
    2. 计算 10 核心维度指标
    3. 计算综合风险得分 (composite_score)，权重精确归一化为 1.00
    """
    masked_text = mask_protected_spans(text)
    paragraphs = split_paragraphs(masked_text)
    raw_paragraphs = split_paragraphs(text)
    sentences = split_sentences(masked_text)

    tp = count_template_matches(masked_text)
    pv = count_passive_markers(masked_text, len(sentences))
    b = analyze_burstiness(paragraphs)
    ps = analyze_para_symmetry(paragraphs)
    nn = count_nested_numbers(paragraphs)
    cl = count_colon_lists(paragraphs)
    pu = analyze_punctuation(masked_text, len(sentences))
    co = count_colloquial_terms(masked_text)
    dd = analyze_dash_density(paragraphs)
    dg = analyze_degeneration_and_leakage(masked_text, sentences)

    # ─── 10 核心维度风险判定 ───
    risks = {
        'template_phrases': tp['count'] > 3,
        'passive_voice': pv['per_sentence'] > 0.4 and len(sentences) >= 5,
        'burstiness': b['cv'] < 0.35 and len(sentences) >= 5,
        'para_symmetry': len(ps['symmetrical_runs']) > 0,
        'nested_numbers': nn['sequences'] > 1,
        'colon_lists': cl['count'] > 1,
        'punctuation': pu['commas_per_sentence'] > 2.5,
        'colloquial': co['count'] > 0,
        'dash_density': dd['over_limit_paras'] > 0,
        'degeneration': dg['has_issue'],
    }

    triggered_count = sum(1 for val in risks.values() if val)

    # ─── 综合加权计算（基于模块级 DIMENSION_WEIGHTS 配置） ───
    raw_score = sum(DIMENSION_WEIGHTS[dim] for dim, triggered in risks.items() if triggered)
    # 严格保证输出在 [0.0, 1.0] 闭区间内
    composite_score = round(min(1.0, max(0.0, raw_score)), 2)

    return {
        'summary': {
            'total_chars': len(text),
            'total_paragraphs': len(raw_paragraphs),
            'total_sentences': len(sentences),
            'triggered_dimensions': triggered_count,
            'total_dimensions': 10,
            'composite_score': composite_score,
        },
        'dimension_risks': risks,
        'template_phrases': tp,
        'passive_voice': pv,
        'burstiness': b,
        'para_symmetry': ps,
        'nested_numbers': nn,
        'colon_lists': cl,
        'punctuation': pu,
        'colloquial': co,
        'dash_density': dd,
        'degeneration': dg,
    }


def print_report(result: dict, threshold: float = 0.5):
    """打印人类可读报告"""
    s = result['summary']
    tp = result['template_phrases']
    pv = result['passive_voice']
    b = result['burstiness']
    ps = result['para_symmetry']
    nn = result['nested_numbers']
    cl = result['colon_lists']
    pu = result['punctuation']
    co = result['colloquial']
    dd = result['dash_density']
    dg = result['degeneration']

    print("=" * 60)
    print("  Writing-Humanizer / 10 核心维度语篇规范扫描报告")
    print("=" * 60)
    print(f"\n文本概况: {s['total_chars']} 字符, {s['total_paragraphs']} 段, {s['total_sentences']} 句 (已隔离受保护片段与引语)")
    print(f"\n{'─' * 40}")
    print("  [1] 模板句式与翻案腔")
    print(f"      命中: {tp['count']} 处 (密度: {tp['density_per_1000']:.2f}/千字)")
    if tp['matches']:
        print(f"      示例: {tp['matches'][:5]}")
    print(f"      风险: {'⚠️ 偏高' if tp['count'] > 3 else '✅ 正常'}")

    print(f"\n{'─' * 40}")
    print("  [2] 被动语态（参考项）")
    print(f"      标记: {pv['count']} 处 (句均: {pv['per_sentence']})")
    print(f"      风险: {'⚠️ 偏高（实验方法论合规被动属正常规范，无需强行改主动）' if pv['per_sentence'] > 0.4 else '✅ 正常'}")

    print(f"\n{'─' * 40}")
    print("  [3] 句子长度变化（突发性 CV 变异系数）")
    print(f"      平均句长: {b['avg_len']} 字, 标准差: {b['std_len']}, CV: {b['cv']}")
    print(f"      风险: {b['risk']}")

    print(f"\n{'─' * 40}")
    print("  [4] 段落对称性")
    print(f"      平均段长: {ps['avg_para_len']} 字")
    print(f"      风险: {ps['risk']}")

    print(f"\n{'─' * 40}")
    print("  [5] 嵌套编号堆叠")
    print(f"      递进序号: {nn['sequences']} 处 (共 {nn['count']} 个标号)")
    print(f"      风险: {nn['risk']}")

    print(f"\n{'─' * 40}")
    print("  [6] 冒号并列结构")
    print(f"      列举并列: {cl['count']} 处")
    print(f"      风险: {cl['risk']}")

    print(f"\n{'─' * 40}")
    print("  [7] 标点规律性")
    print(f"      全角占比: {pu['fullwidth_punct_ratio']}%, 句均逗号: {pu['commas_per_sentence']}")
    print(f"      风险: {pu['risk']}")

    print(f"\n{'─' * 40}")
    print("  [8] 口语化/网络用语（严肃语体守门）")
    print(f"      命中: {co['count']} 处")
    if co['terms']:
        print(f"      词汇: {co['terms']}")
    print(f"      风险: {co['risk']}")

    print(f"\n{'─' * 40}")
    print("  [9] 破折号密度（每段 ≤1 处）")
    print(f"      总数: {dd['total_dashes']}, 超标段落: {dd['over_limit_paras']}")
    print(f"      风险: {dd['risk']}")

    print(f"\n{'─' * 40}")
    print("  [10] 模型退化与元信息泄漏")
    print(f"      状态: {'⚠️ ' + dg['risk'] if dg['has_issue'] else '✅ ' + dg['risk']}")

    # 综合门禁评估（score >= threshold 即为超标拦截）
    c_score = s['composite_score']
    t_dims = s['triggered_dimensions']
    is_passed = c_score < threshold

    print(f"\n{'=' * 60}")
    print(f"  触发维度: {t_dims}/10")
    print(f"  综合风险得分: {c_score:.2f} (设定门禁阈值: {threshold:.2f})")
    print(f"  门禁判定: {'🟢 通过 (PASSED)' if is_passed else '🔴 未通过 (EXCEEDED)'}")

    if co['count'] > 0 or dd['over_limit_paras'] > 0:
        print("  ⚠️ 语体警示: 检测到口语化热词或破折号过密，请对照 positive-style 改回规范书面表达。")
    if dg['has_issue']:
        print("  🚨 严重阻断: 正文存在大模型拒答词或自指泄漏，必须彻底清除。")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description='AIGC 与非虚构特征扫描器（10 核心维度）')
    parser.add_argument('file', help='待扫描的文本文件 (.txt/.md)')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    parser.add_argument('--threshold', type=float, default=0.5, help='综合风险门禁阈值 (默认 0.5，score >= threshold 时判定未通过并以退出码 1 退出)')
    args = parser.parse_args()

    text = load_text(args.file)
    result = scan(text)

    # 门禁判定：得分小于阈值判定为通过，大于或等于阈值判定为未通过
    is_passed = result['summary']['composite_score'] < args.threshold
    result['summary']['threshold'] = args.threshold
    result['summary']['passed'] = is_passed

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result, threshold=args.threshold)

    # CLI 退出状态码门禁支持
    if not is_passed:
        sys.exit(1)


if __name__ == '__main__':
    main()
