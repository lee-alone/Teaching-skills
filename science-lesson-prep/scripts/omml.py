# -*- coding: utf-8 -*-
"""
omml.py —— LaTeX 公式 -> Office 原生数学对象（OMML）转换引擎

处理链路：
    LaTeX  --latex2mathml-->  MathML  --mathml2omml-->  OMML
                                   |
                            修复层（本模块）
                                   |
                     Word / PowerPoint 原生可编辑公式

修复层处理 mathml2omml 的已知缺陷：
  1. <m:groupChrPr> 标签不闭合          -> 直接导致 XML 解析失败
  2. \\vec / \\bar 被转成 groupChr       -> 改为 Word 原生的 m:acc / m:bar
  3. \\hat \\tilde \\dot \\overline
     被转成 m:limUpp（上限样式）        -> 改为 m:acc / m:bar，否则符号飘在远处
  4. \\mathbb{R} 直出 Unicode 字符       -> 改为 m:scr double-struck，避免字体缺字
  5. 公式内中文没有指定中文字体          -> 注入 w:rFonts eastAsia，避免方框乱码
  6. m:box 冗余包裹                      -> 展开，避免整条公式不能断行
"""
from __future__ import annotations

import re

from lxml import etree
from latex2mathml.converter import convert as _tex2mathml
import mathml2omml

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
A14_NS = "http://schemas.microsoft.com/office/drawing/2010/main"

NSMAP = {"m": M_NS, "w": W_NS}
M = lambda t: f"{{{M_NS}}}{t}"
W = lambda t: f"{{{W_NS}}}{t}"

CJK_RE = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")

# 双线数集：Unicode 字符 -> 拉丁字母（配合 m:scr double-struck）
DOUBLE_STRUCK = {
    "\u211d": "R",  # ℝ
    "\u2124": "Z",  # ℤ
    "\u2115": "N",  # ℕ
    "\u211a": "Q",  # ℚ
    "\u2102": "C",  # ℂ
    "\u2119": "P",  # ℙ
}

# 单个字符的重音符号：limUpp 里的符号 -> 正确的重音元素
#   key = limUpp 中 m:lim 里的字符
ACCENT_CHARS = {
    "^": ("acc", "\u0302"),      # ̂  帽
    "~": ("acc", "\u0303"),      # ̃  波浪
    "\u02d9": ("acc", "\u0307"), # ˙  点
    "\u0307": ("acc", "\u0307"),
    "\u00af": ("bar", None),     # ¯  横线
    "\u2015": ("bar", None),     # ―  长横
    "\u2192": ("acc", "\u20d7"), # →  向量箭头
    "\u20d7": ("acc", "\u20d7"),
    "\u0304": ("bar", None),
}


# --------------------------------------------------------------------------
# 第 0 层：MathML 阶段的间距处理
# --------------------------------------------------------------------------
def _normalize_spacing(mml: str) -> str:
    """把 <mspace/> 换成不换行空格文本。

    原因：latex2mathml 把 \\quad \\, 等间距命令转成 <mspace/>，mathml2omml 再转成
    <m:t> </m:t> 这种纯空白 run；而 XML 解析器会把纯空白文本节点直接丢掉，
    导致公式里 \\quad 产生的间隔全部消失（例如「AB ∥ CD, AB ⊥ CD」挤成一团）。
    改用 U+00A0（不换行空格）承载间距，既不会被丢弃，也能正常显示。
    """
    def _rep(m):
        w = m.group(1) or ""
        n = 2 if ("1em" in w or "2em" in w) else 1
        return "<mtext>" + "&#x00A0;" * n + "</mtext>"

    return re.sub(r"<mspace\b[^>]*width=\"([^\"]*)\"[^>]*/>", _rep, mml)


# --------------------------------------------------------------------------
# 第 1 层：修复 mathml2omml 的字符串级缺陷
# --------------------------------------------------------------------------
def _repair_strings(omml: str, target: str = "docx") -> str:
    # 缺陷 1：<m:groupChrPr>...</m:groupChr>  缺少 </m:groupChrPr>
    #   正确写法应是 </m:groupChrPr>，即把那个错误的闭合标签"改名"而不是补一个
    omml = re.sub(
        r"(<m:groupChrPr>.*?)</m:groupChr>",
        r"\1</m:groupChrPr>",
        omml,
        flags=re.S,
    )
    # 补上缺失的命名空间声明（mathml2omml 输出不带 xmlns:m）
    if "<m:oMath" in omml and "xmlns:m=" not in omml:
        extra = f' xmlns:a="{A_NS}"' if target == "pptx" else f' xmlns:w="{W_NS}"'
        omml = omml.replace(
            "<m:oMath>",
            f'<m:oMath xmlns:m="{M_NS}"{extra}>',
            1,
        )
    return omml


# --------------------------------------------------------------------------
# 第 2 层：在 XML 树上做语义修复
# --------------------------------------------------------------------------
def _apply_run_props(run, cjk_font, math_font, size_pt, target="docx"):
    """给 <m:r> 注入字体 / 字号，必须插在 m:t 之前、m:rPr 之后。

    DOCX 与 PPTX 的 run 属性属于不同命名空间，不可混用：
        DOCX -> <w:rPr><w:rFonts w:ascii=... w:eastAsia=.../><w:sz w:val="21"/>
        PPTX -> <a:rPr lang="zh-CN" sz="2100"><a:latin typeface=.../><a:ea typeface=.../>
    """
    if not any([cjk_font, math_font, size_pt]):
        return
    half_pt = int(round((size_pt or 12) * 2))
    if target == "pptx":
        # DrawingML 的 sz 单位是"百分之一磅"：18pt -> 1800（不是 half_pt*100）
        rpr = etree.Element(f"{{{A_NS}}}rPr")
        rpr.set("lang", "zh-CN")
        rpr.set("sz", str(int(round((size_pt or 12) * 100))))
        if math_font:
            etree.SubElement(rpr, f"{{{A_NS}}}latin").set("typeface", math_font)
        etree.SubElement(rpr, f"{{{A_NS}}}ea").set("typeface", cjk_font or "宋体")
    else:
        rpr = etree.Element(W("rPr"))
        f = etree.SubElement(rpr, W("rFonts"))
        if math_font:
            f.set(W("ascii"), math_font)
            f.set(W("hAnsi"), math_font)
        if cjk_font:
            f.set(W("eastAsia"), cjk_font)
        etree.SubElement(rpr, W("sz")).set(W("val"), str(half_pt))
        etree.SubElement(rpr, W("szCs")).set(W("val"), str(half_pt))
    # 插到 m:t 之前
    t = run.find(M("t"))
    if t is not None:
        t.addprevious(rpr)
    else:
        run.append(rpr)


def _replace_elem_with_children(elem, new_children):
    """用给定节点列表替换 elem 自身"""
    parent = elem.getparent()
    idx = parent.index(elem)
    for i, child in enumerate(new_children):
        parent.insert(idx + i, child)
    parent.remove(elem)


def _unwrap_box(root):
    """展开没有 boxPr 的 m:box，避免整条公式被当成不可断行的盒子"""
    for box in list(root.iter(M("box"))):
        if box.find(M("boxPr")) is not None:
            continue
        e = box.find(M("e"))
        if e is None:
            continue
        kids = [c for c in e]
        if not kids:
            continue
        _replace_elem_with_children(box, kids)


def _fix_groupchr(root, cjk_font, math_font, size_pt):
    """\\vec -> m:acc；\\bar -> m:bar"""
    for gc in list(root.iter(M("groupChr"))):
        chr_el = gc.find(f"{M('groupChrPr')}/{M('chr')}")
        ch = chr_el.get(M("val")) if chr_el is not None else None
        e = gc.find(M("e"))
        if e is None or ch not in ACCENT_CHARS:
            continue
        kind, glyph = ACCENT_CHARS[ch]
        parent = gc.getparent()
        idx = parent.index(gc)
        if kind == "bar":
            new = etree.Element(M("bar"))
            pr = etree.SubElement(new, M("barPr"))
            etree.SubElement(pr, M("pos")).set(M("val"), "top")
            new.append(e)
        else:
            new = etree.Element(M("acc"))
            pr = etree.SubElement(new, M("accPr"))
            etree.SubElement(pr, M("chr")).set(M("val"), glyph)
            new.append(e)
        parent.insert(idx, new)
        parent.remove(gc)


def _fix_limupp(root, cjk_font, math_font, size_pt):
    """\\hat \\tilde \\dot \\overline 被误转成 limUpp，改回 m:acc / m:bar"""
    for lu in list(root.iter(M("limUpp"))):
        e = lu.find(M("e"))
        lim = lu.find(M("lim"))
        if e is None or lim is None:
            continue
        # 仅当 lim 中只有一个字符时才认为是重音
        txt = "".join(t.text or "" for t in lim.iter(M("t")))
        if len(txt.strip()) != 1 or txt.strip() not in ACCENT_CHARS:
            continue
        kind, glyph = ACCENT_CHARS[txt.strip()]
        parent = lu.getparent()
        idx = parent.index(lu)
        if kind == "bar":
            new = etree.Element(M("bar"))
            pr = etree.SubElement(new, M("barPr"))
            etree.SubElement(pr, M("pos")).set(M("val"), "top")
            new.append(e)
        else:
            new = etree.Element(M("acc"))
            pr = etree.SubElement(new, M("accPr"))
            etree.SubElement(pr, M("chr")).set(M("val"), glyph)
            new.append(e)
        parent.insert(idx, new)
        parent.remove(lu)


def _fix_double_struck(root):
    """\\mathbb{R} 直出的 Unicode 字符 -> m:scr double-struck"""
    for r in list(root.iter(M("r"))):
        t = r.find(M("t"))
        if t is None or not t.text:
            continue
        if not any(c in DOUBLE_STRUCK for c in t.text):
            continue
        if not all(c in DOUBLE_STRUCK or c.isspace() for c in t.text):
            continue
        latin = "".join(DOUBLE_STRUCK.get(c, c) for c in t.text)
        rpr = r.find(M("rPr"))
        if rpr is None:
            rpr = etree.Element(M("rPr"))
            r.insert(0, rpr)
        for tag in ("scr", "sty"):
            old = rpr.find(M(tag))
            if old is not None:
                rpr.remove(old)
        etree.SubElement(rpr, M("scr")).set(M("val"), "double-struck")
        etree.SubElement(rpr, M("sty")).set(M("val"), "p")
        t.text = latin


def _fix_empty_runs(root):
    """清理 \\quad \\, 等产生的空文本 run"""
    for r in list(root.iter(M("r"))):
        ts = r.findall(M("t"))
        if ts and all((t.text or "") == "" for t in ts):
            parent = r.getparent()
            if parent is not None:
                parent.remove(r)


def _inject_fonts(root, cjk_font, math_font, size_pt, target="docx"):
    """给每个数学 run 注入字体 / 字号；中文单独指定 eastAsia 字体"""
    for r in root.iter(M("r")):
        t = r.find(M("t"))
        text = t.text if t is not None else ""
        cjk = cjk_font if (text and CJK_RE.search(text)) else None
        _apply_run_props(r, cjk, math_font, size_pt, target)


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------
def latex_to_omml(
    latex: str,
    *,
    size_pt: float | None = None,
    math_font: str = "Cambria Math",
    cjk_font: str = "宋体",
    target: str = "docx",
) -> etree._Element:
    """LaTeX -> OMML 元素。

    target="docx" 时 run 属性用 w:rPr（Word）；
    target="pptx" 时 run 属性用 a:rPr（PowerPoint）。
    两者不可混用，否则目标软件会丢弃字体与字号设置。
    """
    mml = _tex2mathml(latex)
    mml = _normalize_spacing(mml)
    raw = mathml2omml.convert(mml)
    raw = _repair_strings(raw, target)
    root = etree.fromstring(raw.encode("utf-8"))
    _unwrap_box(root)
    _fix_groupchr(root, cjk_font, math_font, size_pt)
    _fix_limupp(root, cjk_font, math_font, size_pt)
    _fix_double_struck(root)
    _fix_empty_runs(root)
    _inject_fonts(root, cjk_font, math_font, size_pt, target)
    return root


def omml_string(latex: str, **kw) -> str:
    return etree.tostring(latex_to_omml(latex, **kw), encoding="unicode")


def split_latex(text: str):
    """把「文字 + $公式$ + 文字」拆成 [('t', 文字), ('m', LaTeX), ...]"""
    parts, pos = [], 0
    for m in re.finditer(r"\$\$(.+?)\$\$|\$(.+?)\$", text, flags=re.S):
        if m.start() > pos:
            parts.append(("t", text[pos:m.start()]))
        body = m.group(1) if m.group(1) is not None else m.group(2)
        parts.append(("d" if m.group(1) is not None else "m", body))
        pos = m.end()
    if pos < len(text):
        parts.append(("t", text[pos:]))
    return parts


# --------------------------------------------------------------------------
# DOCX 辅助
# --------------------------------------------------------------------------
def append_math_to_paragraph(paragraph, latex: str, **kw):
    """把公式追加到 python-docx 段落末尾（行内）"""
    paragraph._p.append(latex_to_omml(latex, **kw))


def add_display_math(doc, latex: str, align_center: bool = True, **kw):
    """添加独立居中展示公式"""
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    p = doc.add_paragraph()
    if align_center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p._p.append(latex_to_omml(latex, **kw))
    return p


# --------------------------------------------------------------------------
# PPTX 辅助
#
# PowerPoint 的公式段落结构（已用真实 PowerPoint 往返验证）：
#   行内：<a:p><a:r>文字</a:r><a14:m><m:oMath>…</m:oMath></a14:m><a:r>文字</a:r></a:p>
#   独立：<a:p><a14:m><m:oMathPara><m:oMath>…</m:oMath></m:oMathPara></a14:m></a:p>
# 注意 oMathPara 只用于独立成行的公式，行内公式用 oMath，否则会强制换行。
# --------------------------------------------------------------------------
_PPTX_NSMAP = {"a": A_NS, "a14": A14_NS, "m": M_NS}


def pptx_math_element(omml_root, display: bool = True) -> etree._Element:
    """构造 a14:m 元素（display=True 用 oMathPara，否则用 oMath）"""
    a14m = etree.Element(f"{{{A14_NS}}}m", nsmap=_PPTX_NSMAP)
    if display:
        holder = etree.SubElement(a14m, M("oMathPara"))
    else:
        holder = a14m
    holder.append(omml_root)
    return a14m


def pptx_math_paragraph(omml_root, display: bool = True) -> etree._Element:
    """构造完整的 PowerPoint 公式段落 a:p"""
    para = etree.Element(f"{{{A_NS}}}p", nsmap=_PPTX_NSMAP)
    para.append(pptx_math_element(omml_root, display))
    return para


def pptx_text_run(text: str, size_pt: float, *, bold: bool = False,
                  color: str | None = None, font: str = "微软雅黑") -> etree._Element:
    """构造 PowerPoint 普通文字 run（用于与公式混排）"""
    r = etree.Element(f"{{{A_NS}}}r", nsmap=_PPTX_NSMAP)
    rpr = etree.SubElement(r, f"{{{A_NS}}}rPr")
    rpr.set("lang", "zh-CN")
    rpr.set("sz", str(int(round(size_pt * 100))))
    rpr.set("dirty", "0")
    if bold:
        rpr.set("b", "1")
    if color:
        fill = etree.SubElement(rpr, f"{{{A_NS}}}solidFill")
        etree.SubElement(fill, f"{{{A_NS}}}srgbClr").set("val", color.replace("#", ""))
    etree.SubElement(rpr, f"{{{A_NS}}}latin").set("typeface", font)
    etree.SubElement(rpr, f"{{{A_NS}}}ea").set("typeface", font)
    t = etree.SubElement(r, f"{{{A_NS}}}t")
    t.text = text
    return r


def add_math_to_textframe(text_frame, latex: str, *, display: bool = True, **kw):
    """在 PPTX 文本框中追加一个原生公式段落"""
    tf_p = text_frame.add_paragraph()
    new_p = pptx_math_paragraph(latex_to_omml(latex, **kw), display)
    tf_p._p.addprevious(new_p)
    tf_p._p.getparent().remove(tf_p._p)
    return new_p
