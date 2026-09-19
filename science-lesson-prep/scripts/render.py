# -*- coding: utf-8 -*-
"""教学材料渲染器：Markdown 中间表示 -> DOCX（教案/导学案）或 PPTX（课件）。

设计前提：内容生成与文件排版分离。
主代理只负责写出结构清晰的 Markdown（公式用 $...$），本脚本负责排版与公式落地。

用法：
    python render.py --kind jiaoan --input plan.md --output 教案.docx
    python render.py --kind xuean  --input plan.md --output 导学案.docx
    python render.py --kind kejian --input plan.md --output 课件.pptx
    python render.py --kind kejian --input plan.md --output 课件.pptx --math-mode image

支持的 Markdown 子集：
    # / ## / ###      标题
    普通段落           支持行内公式 $...$
    - / 1.            无序 / 有序列表
    > 引用            提示栏（楷体）
    | a | b |         表格
    $$...$$           独立居中公式
    ```plot ... ```   函数图象（内容为 JSON 规格）
    ::: blank N       插入 N 行留白（导学案演算区）
    ::: pagebreak     分页
    ---               分隔线
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import env  # noqa: E402

# 必须在导入 omml（依赖 lxml / latex2mathml）与 figures（依赖 matplotlib）
# 之前完成解释器自检：若当前解释器缺少依赖（例如直接用全局 Python 调起本脚本），
# 这里会自动切换到 bootstrap 装好的隔离解释器重新执行本脚本。
env.ensure_runtime(env.CORE_MODULES + env.FIGURE_MODULES, label="render.py")

try:
    import omml as O  # noqa: E402
except ImportError as exc:  # 依赖确实装不上，给出可操作的提示而不是堆栈
    sys.stderr.write(
        f"[render.py] 缺少依赖：{exc}\n"
        f"请先运行：python \"{os.path.join(_HERE, 'bootstrap.py')}\"\n")
    raise SystemExit(2)

# 排版规范
BODY_FONT = "宋体"
HEAD_FONT = "黑体"
NOTE_FONT = "楷体"
UI_FONT = "微软雅黑"
BODY_SIZE = 10.5
LINE_SPACING_PT = 20.0
MARGIN_CM = 2.2


# ==========================================================================
# 1. Markdown 解析
# ==========================================================================
def parse_front_matter(text: str) -> tuple[dict, str]:
    meta = {}
    if text.lstrip().startswith("---"):
        body = text.lstrip()[3:]
        end = body.find("\n---")
        if end != -1:
            head = body[:end]
            for line in head.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            return meta, body[end + 4:]
    return meta, text


def split_table_row(line: str) -> list[str]:
    """按 | 切分表格行，但 $...$ 内部的竖线不算分隔符。

    数学材料里 $|a|$、$|AB|$、$P(A|B)$ 都是常见写法，
    若按朴素方式切分，表格会被竖线拆碎、公式定界符失衡。
    """
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells, buf, in_math = [], [], False
    for ch in s:
        if ch == "$":
            in_math = not in_math
            buf.append(ch)
        elif ch == "|" and not in_math:
            cells.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    cells.append("".join(buf).strip())
    return cells


def parse_markdown(md: str) -> list[dict]:
    blocks: list[dict] = []
    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    n = len(lines)

    while i < n:
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 围栏代码块
        if stripped.startswith("```"):
            lang = stripped[3:].strip().lower()
            buf, i = [], i + 1
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            body = "\n".join(buf)
            if lang in ("plot", "figure", "chart"):
                blocks.append({"type": "figure", "spec": body})
            else:
                blocks.append({"type": "code", "lang": lang, "text": body})
            continue

        # 指令
        if stripped.startswith(":::"):
            parts = stripped[3:].strip().split()
            cmd = parts[0] if parts else ""
            if cmd == "blank":
                count = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 2
                blocks.append({"type": "blank", "count": count})
            elif cmd == "pagebreak":
                blocks.append({"type": "pagebreak"})
            i += 1
            continue

        # 分隔线
        if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", stripped):
            blocks.append({"type": "hr"})
            i += 1
            continue

        # 标题
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            blocks.append({"type": f"h{len(m.group(1))}", "text": m.group(2).strip()})
            i += 1
            continue

        # 独立公式
        if stripped.startswith("$$"):
            if stripped.endswith("$$") and len(stripped) > 4:
                blocks.append({"type": "dmath", "latex": stripped[2:-2].strip()})
                i += 1
                continue
            buf, i = [stripped[2:]], i + 1
            while i < n and not lines[i].strip().endswith("$$"):
                buf.append(lines[i])
                i += 1
            if i < n:
                buf.append(lines[i].strip()[:-2])
                i += 1
            blocks.append({"type": "dmath", "latex": "\n".join(buf).strip()})
            continue

        # 表格
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\|[\s:\-|]+\|$", lines[i + 1].strip()):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_table_row(lines[i]))
                i += 1
            header = rows[0]
            body_rows = rows[2:] if len(rows) > 1 else []
            blocks.append({"type": "table", "header": header, "rows": body_rows})
            continue

        # 引用
        if stripped.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(lines[i].strip().lstrip(">").strip())
                i += 1
            blocks.append({"type": "quote", "text": "\n".join(buf).strip()})
            continue

        # 列表
        m = re.match(r"^(\s*)([-*+]|\d+[.、)])\s+(.*)$", line)
        if m:
            ordered = bool(re.match(r"\d+", m.group(2)))
            items = []
            while i < n:
                mm = re.match(r"^(\s*)([-*+]|\d+[.、)])\s+(.*)$", lines[i])
                if not mm:
                    break
                indent = len(mm.group(1))
                items.append({"level": min(indent // 2, 2), "text": mm.group(3).strip()})
                i += 1
            blocks.append({"type": "ol" if ordered else "ul", "items": items})
            continue

        # 普通段落（合并连续行）
        buf = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith(("#", ">", "|", "```", ":::", "$$"))
                    or re.fullmatch(r"-{3,}", nxt)
                    or re.match(r"^([-*+]|\d+[.、)])\s+", nxt)):
                break
            buf.append(nxt)
            i += 1
        blocks.append({"type": "p", "text": join_cjk_lines(buf)})

    return blocks


def join_cjk_lines(lines: list[str]) -> str:
    """合并多行段落。若前后行接壤处均为 CJK 字符，则直接拼接；否则加空格。"""
    if not lines:
        return ""
    res = lines[0]
    for nxt in lines[1:]:
        if not nxt:
            continue
        c1 = res[-1]
        c2 = nxt[0]
        is_cjk_1 = '\u4e00' <= c1 <= '\u9fff' or '\u3000' <= c1 <= '\u303f' or '\uff00' <= c1 <= '\uffef'
        is_cjk_2 = '\u4e00' <= c2 <= '\u9fff' or '\u3000' <= c2 <= '\u303f' or '\uff00' <= c2 <= '\uffef'
        if is_cjk_1 and is_cjk_2:
            res += nxt
        else:
            res += " " + nxt
    return res


# ==========================================================================
# 2. 通用工具
# ==========================================================================
def safe_save(saver, path: str) -> tuple[str, str | None]:
    """安全写出：目标被 Office 占用时改存带时间戳的备用文件，不中断流程。"""
    try:
        saver(path)
        return path, None
    except PermissionError:
        root, ext = os.path.splitext(path)
        alt = f"{root}_{time.strftime('%H%M%S')}{ext}"
        saver(alt)
        return alt, f"{os.path.basename(path)} 正被 Word/PowerPoint 占用，已改存为 {os.path.basename(alt)}"


def clean_latex(latex: str) -> str:
    """统一处理全角字符、多余空白等常见书写问题。"""
    s = latex.strip()
    s = s.replace("\u3000", " ")
    s = re.sub(r"\s+", " ", s)
    return s


# ==========================================================================
# 3. DOCX 渲染（教案 / 导学案）
# ==========================================================================
def render_docx(blocks: list[dict], meta: dict, out_path: str, *,
                work_dir: str, math_mode: str = "native") -> dict:
    from docx import Document
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor

    doc = Document()
    st = doc.styles["Normal"]
    st.font.name = BODY_FONT
    st.font.size = Pt(BODY_SIZE)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT)
    sec = doc.sections[0]
    sec.top_margin = sec.bottom_margin = Cm(MARGIN_CM)
    sec.left_margin = sec.right_margin = Cm(MARGIN_CM)

    stats = {"math": 0, "figures": 0, "images": [], "warnings": []}

    def style_run(run, font=BODY_FONT, size=BODY_SIZE, bold=False, color=None):
        run.font.name = font
        run.font.size = Pt(size)
        run.bold = bold
        if color:
            run.font.color.rgb = RGBColor.from_string(color)
        run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
        run._element.rPr.rFonts.set(qn("w:ascii"), font)
        run._element.rPr.rFonts.set(qn("w:hAnsi"), font)

    def new_para(space_after=4, spacing=LINE_SPACING_PT, indent=None, align=None):
        p = doc.add_paragraph()
        pf = p.paragraph_format
        pf.line_spacing = Pt(spacing)
        pf.space_after = Pt(space_after)
        pf.space_before = Pt(0)
        if indent is not None:
            pf.left_indent = Cm(indent)
        if align is not None:
            p.alignment = align
        return p

    def add_rich(p, text, font=BODY_FONT, size=BODY_SIZE, bold=False, color=None):
        """把「文字 + $公式$ + 文字」按顺序写入段落，公式走原生对象或图片。"""
        for kind, val in O.split_latex(text):
            if kind == "t":
                if not val:
                    continue
                r = p.add_run(val)
                style_run(r, font, size, bold, color)
            else:
                val = clean_latex(val)
                if not val:
                    continue
                if math_mode == "image":
                    img = _math_image(val, work_dir, stats, size)
                    if img:
                        p.add_run().add_picture(img, height=Pt(size * 1.45))
                        continue
                try:
                    p._p.append(O.latex_to_omml(val, size_pt=size, cjk_font=BODY_FONT))
                    stats["math"] += 1
                except Exception as exc:  # noqa: BLE001
                    # auto：原生转换失败时退回矢量图片，图片也失败才保留原文
                    if math_mode == "auto":
                        img = _math_image(val, work_dir, stats, size)
                        if img:
                            p.add_run().add_picture(img, height=Pt(size * 1.45))
                            continue
                    stats["warnings"].append(f"公式转换失败，已按原文保留：{val}（{exc}）")
                    r = p.add_run(val)
                    style_run(r, font, size, bold, color)

    def shade(cell_or_para, hex_fill):
        el = cell_or_para._tc if hasattr(cell_or_para, "_tc") else cell_or_para._p.get_or_add_pPr()
        sh = OxmlElement("w:shd")
        sh.set(qn("w:val"), "clear")
        sh.set(qn("w:fill"), hex_fill)
        el.append(sh)

    # ---- 标题 ----
    title = meta.get("课题") or meta.get("标题") or ""
    if title:
        p = new_para(space_after=2, spacing=26, align=WD_ALIGN_PARAGRAPH.CENTER)
        style_run(p.add_run(title), HEAD_FONT, 16, True)
    subtitle_parts = [f"{k}：{meta[k]}" for k in ("学科", "年级", "册次", "课时", "授课教师", "班级")
                      if meta.get(k)]
    if subtitle_parts:
        p = new_para(space_after=10, spacing=20, align=WD_ALIGN_PARAGRAPH.CENTER)
        style_run(p.add_run("　".join(subtitle_parts)), BODY_FONT, 10.5)

    # ---- 正文 ----
    for blk in blocks:
        t = blk["type"]

        if t in ("h1", "h2", "h3", "h4"):
            level = int(t[1])
            size = {1: 15, 2: 13, 3: 12, 4: 11}[level]
            p = new_para(space_after=4, spacing=22)
            p.paragraph_format.space_before = Pt(8 if level <= 2 else 5)
            style_run(p.add_run(blk["text"]), HEAD_FONT, size, True)

        elif t == "p":
            p = new_para()
            add_rich(p, blk["text"])

        elif t == "dmath":
            latex = clean_latex(blk["latex"])
            if math_mode == "image":
                img = _math_image(latex, work_dir, stats, 12)
                if img:
                    p = new_para(space_after=6, align=WD_ALIGN_PARAGRAPH.CENTER)
                    p.add_run().add_picture(img, height=Pt(20))
                    continue
            p = new_para(space_after=6, spacing=22, align=WD_ALIGN_PARAGRAPH.CENTER)
            try:
                p._p.append(O.latex_to_omml(latex, size_pt=12, cjk_font=BODY_FONT))
                stats["math"] += 1
            except Exception as exc:  # noqa: BLE001
                # auto：原生转换失败时退回矢量图片（沿用已建好的居中段落）
                if math_mode == "auto":
                    img = _math_image(latex, work_dir, stats, 12)
                    if img:
                        p.add_run().add_picture(img, height=Pt(20))
                        continue
                stats["warnings"].append(f"公式转换失败：{latex}（{exc}）")
                style_run(p.add_run(latex))

        elif t in ("ul", "ol"):
            for idx, item in enumerate(blk["items"], 1):
                p = new_para(space_after=2)
                p.paragraph_format.left_indent = Cm(0.75 + item["level"] * 0.6)
                mark = f"{idx}. " if t == "ol" else "· "
                style_run(p.add_run(mark), BODY_FONT, BODY_SIZE)
                add_rich(p, item["text"])

        elif t == "quote":
            p = new_para(space_after=6, indent=0.6)
            add_rich(p, blk["text"], font=NOTE_FONT, size=BODY_SIZE, color="44546A")
            shade(p, "F2F5F9")

        elif t == "table":
            cols = len(blk["header"])
            table = doc.add_table(rows=1 + len(blk["rows"]), cols=cols)
            table.style = "Table Grid"
            table.alignment = WD_TABLE_ALIGNMENT.CENTER
            for j, cell_text in enumerate(blk["header"]):
                cell = table.cell(0, j)
                cell.text = ""
                p = cell.paragraphs[0]
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.line_spacing = Pt(18)
                add_rich(p, cell_text, font=HEAD_FONT, size=10.5, bold=True)
                shade(cell, "EDF2F8")
            for r_i, row in enumerate(blk["rows"], 1):
                for j in range(cols):
                    cell = table.cell(r_i, j)
                    cell.text = ""
                    p = cell.paragraphs[0]
                    p.paragraph_format.line_spacing = Pt(18)
                    add_rich(p, row[j] if j < len(row) else "")
            new_para(space_after=4)

        elif t == "figure":
            res = _render_figure(blk["spec"], work_dir, stats, font_scale=1.0)
            if res:
                p = new_para(space_after=8, align=WD_ALIGN_PARAGRAPH.CENTER)
                p.add_run().add_picture(res, width=Cm(13.0))

        elif t == "blank":
            for _ in range(blk["count"]):
                new_para(space_after=0, spacing=LINE_SPACING_PT)

        elif t == "pagebreak":
            doc.add_page_break()

        elif t == "hr":
            p = new_para(space_after=6)
            style_run(p.add_run("─" * 34), BODY_FONT, 9, color="B4B2A9")

    saved, note = safe_save(doc.save, out_path)
    if note:
        stats["warnings"].append(note)
    stats["output"] = saved
    return stats


def _math_image(latex: str, work_dir: str, stats: dict, size_pt: float) -> str | None:
    """把公式渲染为 PNG（降级路径）。"""
    try:
        import mathimg
    except ImportError:
        stats["warnings"].append("降级链路不可用，已退回原生公式")
        return None
    name = f"eq_{len(stats.get('images', []))}_{abs(hash(latex)) % 10 ** 6}"
    res = mathimg.render_one(latex, os.path.join(work_dir, "math"), name=name,
                             raster=True, png_scale=max(3, int(size_pt / 3)))
    if res.get("ok") and res.get("pngPath"):
        stats["math"] += 1
        return res["pngPath"]
    stats["warnings"].append(f"公式降级失败：{latex}（{res.get('error', '')}）")
    return None


def _render_figure(spec_text: str, work_dir: str, stats: dict,
                   font_scale: float = 1.0) -> str | None:
    try:
        import figures
    except ImportError:
        stats["warnings"].append("缺少 matplotlib，无法生成函数图象")
        return None
    name = f"fig_{len(stats.get('images', []))}"
    res = figures.render_from_json(spec_text, os.path.join(work_dir, "fig"), name,
                                   font_scale=font_scale)
    if res.get("ok"):
        stats["figures"] += 1
        stats.setdefault("images", []).append(res["pngPath"])
        return res["pngPath"]
    stats["warnings"].append(f"图象生成失败：{res.get('error', '')}")
    return None


# ==========================================================================
# 4. PPTX 渲染（课件）
# ==========================================================================
def render_pptx(blocks: list[dict], meta: dict, out_path: str, *,
                work_dir: str, math_mode: str = "native") -> dict:
    from lxml import etree
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Emu, Inches, Pt

    # PPTX 的文本模型（DrawingML）不支持把图片作为行内对象插入段落——
    # PowerPoint 里"文字中插图"实际是独立图形，不参与文字排版。
    # 因此 image 模式在课件上无法实现。这里必须**显式报错**：
    # 若静默退回 native，用户会以为已经拿到兼容模式，实际没有。
    if math_mode == "image":
        raise ValueError(
            "课件（PPTX）不支持 --math-mode image：PowerPoint 的文本模型无法把图片"
            "作为行内对象插入段落，公式图片不能随文字排版。"
            "请改用 --math-mode native；若目标环境是老版本 PowerPoint 或 WPS，"
            "建议改用 DOCX 教案（教案与导学案支持 image 模式）。")

    A = O.A_NS
    stats = {"math": 0, "figures": 0, "slides": 0, "warnings": []}

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]
    SW, SH = prs.slide_width, prs.slide_height
    ACCENT = "1F3864"

    def add_slide():
        s = prs.slides.add_slide(blank)
        stats["slides"] += 1
        return s

    def textbox(slide, l, t, w, h):
        box = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        return tf

    def set_para_style(p, size=18, bold=False, color=None, align=None, space_after=6):
        p.space_after = Pt(space_after)
        if align is not None:
            p.alignment = align
        for r in p.runs:
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.name = UI_FONT
            if color:
                r.font.color.rgb = RGBColor.from_string(color)

    def fill_paragraph(p_xml, text, size=18, bold=False, color=None, indent=0):
        """在已有 a:p 上按「文字 + 公式」顺序写入内容。"""
        if indent:
            ppr = etree.Element(f"{{{A}}}pPr")
            ppr.set("marL", str(int(indent * 457200)))
            p_xml.insert(0, ppr)
        for kind, val in O.split_latex(text):
            if kind == "t":
                if not val:
                    continue
                p_xml.append(O.pptx_text_run(val, size, bold=bold, color=color, font=UI_FONT))
            else:
                val = clean_latex(val)
                if not val:
                    continue
                try:
                    root = O.latex_to_omml(val, size_pt=size, cjk_font=UI_FONT, target="pptx")
                    p_xml.append(O.pptx_math_element(root, display=False))
                    stats["math"] += 1
                except Exception as exc:  # noqa: BLE001
                    stats["warnings"].append(f"公式转换失败：{val}（{exc}）")
                    p_xml.append(O.pptx_text_run(val, size, color=color, font=UI_FONT))

    def next_p(tf, state):
        """取下一个段落。首次复用占位段（先清空其内容），之后新建。"""
        if state["first"]:
            state["first"] = False
            p = tf.paragraphs[0]
            for child in list(p._p):
                p._p.remove(child)
            return p
        return tf.add_paragraph()

    def add_display_math(p, latex, size=20):
        latex = clean_latex(latex)
        try:
            p._p.append(O.pptx_math_element(
                O.latex_to_omml(latex, size_pt=size, cjk_font=UI_FONT, target="pptx"),
                display=True))
            stats["math"] += 1
        except Exception as exc:  # noqa: BLE001
            stats["warnings"].append(f"公式转换失败：{latex}（{exc}）")
            p.text = latex

    # ---- 封面 ----
    title = meta.get("课题") or meta.get("标题") or "教学课件"
    slide = add_slide()
    tf = textbox(slide, 1.0, 2.4, 11.3, 2.4)
    p = tf.paragraphs[0]
    p.text = title
    set_para_style(p, 40, True, ACCENT, PP_ALIGN.CENTER)
    info = "　".join(f"{k}：{meta[k]}" for k in ("学科", "年级", "册次", "课时") if meta.get(k))
    if info:
        p2 = tf.add_paragraph()
        p2.text = info
        set_para_style(p2, 18, False, "5F5E5A", PP_ALIGN.CENTER)

    # ---- 分节 ----
    sections: list[dict] = []
    current = None
    preamble: list[dict] = []
    for blk in blocks:
        if blk["type"] in ("h2", "h1"):
            current = {"title": blk["text"], "items": []}
            sections.append(current)
        elif blk["type"] == "h3":
            if current is None:
                current = {"title": "", "items": []}
                sections.append(current)
            current["items"].append({"kind": "h3", "text": blk["text"]})
        else:
            if current is None:
                preamble.append(blk)
            else:
                current["items"].append({"kind": blk["type"], "blk": blk})

    if preamble:
        sections.insert(0, {"title": "引入", "items": [
            {"kind": b["type"], "blk": b} for b in preamble]})

    for sec in sections:
        slide = add_slide()
        # 标题条
        tf_title = textbox(slide, 0.7, 0.35, 11.9, 0.95)
        p = tf_title.paragraphs[0]
        p.text = sec["title"] or "　"
        set_para_style(p, 30, True, ACCENT, PP_ALIGN.LEFT)

        figures = [it for it in sec["items"] if it["kind"] == "figure"]
        texts = [it for it in sec["items"] if it["kind"] != "figure"]

        # 先出图，才能按图象宽高比决定版式
        fig_paths = []
        for it in figures:
            path = _render_figure(it["blk"]["spec"], work_dir, stats, font_scale=1.8)
            if path:
                fig_paths.append(path)

        wide_fig = False
        if fig_paths:
            from PIL import Image
            with Image.open(fig_paths[0]) as im:
                wide_fig = (im.size[0] / max(1, im.size[1])) >= 1.6

        if not fig_paths:
            tf_body = textbox(slide, 0.7, 1.5, 11.9, 5.4)
        elif wide_fig:
            tf_body = textbox(slide, 0.7, 1.35, 11.9, 2.3)   # 文字在上
        else:
            tf_body = textbox(slide, 0.7, 1.5, 5.6, 5.4)      # 文字在左

        state = {"first": True}
        for it in texts:
            kind = it["kind"]
            if kind == "h3":
                p = next_p(tf_body, state)
                p.text = it["text"]
                set_para_style(p, 22, True, "2C2C2A", space_after=8)
            elif kind == "p":
                p = next_p(tf_body, state)
                fill_paragraph(p._p, it["blk"]["text"], 18)
                set_para_style(p, 18, space_after=8)
            elif kind in ("ul", "ol"):
                for i, item in enumerate(it["blk"]["items"], 1):
                    p = next_p(tf_body, state)
                    mark = f"{i}. " if kind == "ol" else "· "
                    fill_paragraph(p._p, mark + item["text"], 18, indent=item["level"])
                    set_para_style(p, 18, space_after=6)
            elif kind == "quote":
                p = next_p(tf_body, state)
                fill_paragraph(p._p, it["blk"]["text"], 17, color="44546A")
                set_para_style(p, 17, color="44546A", space_after=8)
            elif kind == "dmath":
                p = next_p(tf_body, state)
                add_display_math(p, it["blk"]["latex"], 22)
                set_para_style(p, 22, space_after=10)
            elif kind == "table":
                _pptx_table(slide, it["blk"], 0.7, 1.5,
                            11.9 if (not fig_paths or wide_fig) else 5.6,
                            fill_paragraph, stats)
            elif kind == "blank":
                for _ in range(it["blk"]["count"]):
                    next_p(tf_body, state)

        # 图象：宽图放文字下方通栏，方图放右侧
        if fig_paths:
            if wide_fig:
                area_l, area_t, area_w, area_h = 0.7, 3.8, 11.9, 3.4
            else:
                area_l, area_t, area_w, area_h = 6.6, 1.5, 6.0, 5.4
            count = len(fig_paths)
            cols = min(2, count) if count > 1 else 1
            rows = (count + cols - 1) // cols
            from PIL import Image
            for idx, res in enumerate(fig_paths):
                with Image.open(res) as im:
                    iw, ih = im.size
                cell_w = area_w / cols - 0.15
                cell_h = area_h / rows - 0.15
                scale = min(cell_w / iw, cell_h / ih)
                w_in, h_in = iw * scale, ih * scale
                col, row = idx % cols, idx // cols
                left = area_l + col * (area_w / cols) + (cell_w - w_in) / 2
                top = area_t + row * (area_h / rows) + (cell_h - h_in) / 2
                slide.shapes.add_picture(res, Inches(left), Inches(top),
                                         Inches(w_in), Inches(h_in))

    saved, note = safe_save(prs.save, out_path)
    if note:
        stats["warnings"].append(note)
    stats["output"] = saved
    return stats


def _pptx_table(slide, blk, left, top, width, fill_fn, stats):
    """PPTX 原生表格。单元格内容同样走「文字 + 原生公式」混排，
    否则表格里的 $a$ 会以美元符号原样显示。"""
    from pptx.util import Inches

    cols = len(blk["header"])
    rows = 1 + len(blk["rows"])
    shape = slide.shapes.add_table(rows, cols, Inches(left), Inches(top),
                                   Inches(width), Inches(0.45 * rows))
    table = shape.table

    def fill_cell(cell, text, size, bold=False, color=None):
        p = cell.text_frame.paragraphs[0]
        for child in list(p._p):
            p._p.remove(child)
        fill_fn(p._p, text, size, bold=bold, color=color)

    for j, txt in enumerate(blk["header"]):
        fill_cell(table.cell(0, j), txt, 15, bold=True, color="1F3864")
    for i, row in enumerate(blk["rows"], 1):
        for j in range(cols):
            fill_cell(table.cell(i, j), row[j] if j < len(row) else "", 14)


# ==========================================================================
# 5. 入口
# ==========================================================================
KIND_DEFAULT_EXT = {"jiaoan": ".docx", "xuean": ".docx", "kejian": ".pptx"}


def run(kind: str, input_path: str, output_path: str, work_dir: str,
        math_mode: str = "native") -> dict:
    with open(input_path, encoding="utf-8") as fh:
        raw = fh.read()
    meta, body = parse_front_matter(raw)
    blocks = parse_markdown(body)
    os.makedirs(work_dir, exist_ok=True)

    if kind in ("jiaoan", "xuean"):
        stats = render_docx(blocks, meta, output_path, work_dir=work_dir, math_mode=math_mode)
    elif kind == "kejian":
        stats = render_pptx(blocks, meta, output_path, work_dir=work_dir, math_mode=math_mode)
    else:
        raise ValueError(f"未知材料类型：{kind}")

    stats["kind"] = kind
    stats["blocks"] = len(blocks)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="教学材料渲染器")
    ap.add_argument("--kind", required=True, choices=["jiaoan", "xuean", "kejian"])
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--work-dir", default=None)
    ap.add_argument("--math-mode", default="native", choices=["native", "image", "auto"],
                    help="native=Office 原生公式（默认）；image=一律转矢量图片；auto=失败时自动降级")
    args = ap.parse_args()

    work_dir = args.work_dir or os.path.join(os.path.dirname(os.path.abspath(args.output)), "_assets")
    try:
        stats = run(args.kind, args.input, args.output, work_dir, args.math_mode)
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"},
                         ensure_ascii=False))
        return 1
    stats["ok"] = True
    print(json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
