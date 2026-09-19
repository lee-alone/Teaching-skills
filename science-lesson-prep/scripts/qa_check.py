# -*- coding: utf-8 -*-
"""理科文档公式与排版生成后的自动质检。

用法：
    python qa_check.py 文档.docx
    python qa_check.py 课件.pptx --kind kejian
    python qa_check.py 文档.docx --source-md plan.md     # 逐块清点（强烈建议）
    python qa_check.py 文档.docx --json

检查项分三类：
  A. 数学公式专项 —— 残存 $ 定界符、裸露 LaTeX 命令、未修正的重音结构、
     空文本 run、公式内中文缺字体、公式对象数量
  B. 版面与元素 —— 图片与表格统计、PPT 形状是否越出画布
  C. 内容完整性（需 --source-md）—— 行内 **加粗**/`等宽` 标记残留、
     Markdown 每一块内容是否都在成品里、列表编号是否与源文件一致

C 类是补上的关键一环：只查 $ 与 LaTeX 是不够的，正文里的 Markdown 语法残留
与整块内容丢失（代码块、板书图）恰恰都发生在 $ 之外。

退出码：0 = 通过；1 = 存在必须修复的问题；2 = 文件无法读取
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import zipfile

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 裸露的 LaTeX 命令（出现即说明公式没被转换，包括不被支持的 \ce）
LATEX_CMD = re.compile(r"\\(?:ce|frac|sqrt|sum|int|lim|begin|end|cdot|times|pm|leq|geq|neq|"
                       r"alpha|beta|theta|pi|infty|to|rightarrow|Rightarrow|vec|bar|hat|"
                       r"overline|mathbb|text|quad|qquad|left|right|sin|cos|tan|log|ln)\b")

# 公式中允许出现的 Unicode 数学符号（不视为问题）
ALLOWED_UNICODE_MATH = set("∈∉⊆⊂∪∩∅∞≤≥≠±×÷→←↔⇒⇔∵∴△∠⊥∥°′″√∑∫πθαβγλμσφωΩΔ")

ACCENT_CHARS = {"^", "~", "˙", "¯", "―", "→", "⃗", "̄", "̃", "̂", "̇"}


def read_parts(path: str, prefixes: tuple[str, ...]) -> dict[str, str]:
    """读出 OOXML 包内匹配前缀的 XML 文本。"""
    out = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.endswith(".xml") and any(name.startswith(p) for p in prefixes):
                out[name] = z.read(name).decode("utf-8", "replace")
    return out


# ==========================================================================
# C. 内容完整性
# ==========================================================================
def visible_texts(parts: dict[str, str]) -> list[str]:
    """取出所有「正文可见文字」run 的内容。

    只取正文/幻灯片本身，不取 styles.xml 等定义文件；
    公式 run（m:t）也一并纳入，用于查公式里漏出来的 LaTeX。
    """
    keep = re.compile(r"^(document\.xml|slide\d+\.xml|notesSlide\d+\.xml)$")
    out: list[str] = []
    for name, xml in parts.items():
        if not keep.match(os.path.basename(name)):
            continue
        for tag in ("w:t", "a:t", "m:t"):
            out.extend(re.findall(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, flags=re.S))
    return [html.unescape(t) for t in out]


def visible_paragraphs(parts: dict[str, str]) -> list[str]:
    """按段落/文本框段落聚合可见文字，用于「内容是否整块还在」的比对。

    刻意**不含 m:t（公式 run）**：源 Markdown 里的公式是 LaTeX 源码
    （\\frac{1}{x-2}），落到 OMML 后变成分式结构，两者文字无法比对。
    所以两侧都只看公式以外的正文，公式本身由 check_math 单独负责。
    """
    keep = re.compile(r"^(document\.xml|slide\d+\.xml)$")
    out: list[str] = []
    for name, xml in parts.items():
        if not keep.match(os.path.basename(name)):
            continue
        for pm in re.finditer(r"<(w:p|a:p)[ >].*?</\1>", xml, flags=re.S):
            txt = "".join(re.findall(r"<(?:w|a):t[^>]*>(.*?)</(?:w|a):t>",
                                     pm.group(0), flags=re.S))
            if txt:
                out.append(html.unescape(txt))
    return out


def normalize(s: str) -> str:
    """剥掉 Markdown 标记与公式、去掉全部空白，只留会落进 w:t / a:t 的可见字符。

    去掉全部空白是有意为之：渲染器会把中文换行直接拼合、给西文补空格，
    逐字比对会被这些排版差异淹没。去空白后比对的是「内容是否在」，这才是重点。
    """
    s = html.unescape(s)
    s = re.sub(r"\$\$.+?\$\$|\$.+?\$", "", s, flags=re.S)
    s = s.replace("**", "").replace("`", "")
    # 处理常见转义：Markdown 中转义的 \_、\*、\& 等在 Word 中渲染为无反斜杠字符
    s = re.sub(r"\\([_\\*&%#~{}[\]])", r"\1", s)
    return re.sub(r"\s+", "", s)


def check_markers(parts: dict[str, str], issues: list, stats: dict) -> None:
    """行内 Markdown 标记残留检查。

    **加粗** 与 `等宽` 必须被渲染成真正的富文本属性；
    一旦以字面星号/反引号出现在正文可见文字里，就是渲染器没解析行内标记。
    注意：
    - **加粗** 残留以成对或孤立的「**」为准，避免误伤正文中的合法单星号（如乘号、题注*）；
    - 代码块（带 F4F6F3 底纹或代码特定样式）中的字符属于字面展示，不计为语法残留。
    """
    keep = re.compile(r"^(document\.xml|slide\d+\.xml)$")
    double_star = 0
    tick = 0
    star_samples: list[str] = []
    tick_samples: list[str] = []

    for name, xml in parts.items():
        if not keep.match(os.path.basename(name)):
            continue
        for pm in re.finditer(r"<(w:p|a:p)[ >].*?</\1>", xml, flags=re.S):
            p_xml = pm.group(0)
            # 排除代码块段落：Word 中带 F4F6F3 底纹，PPTX 中带有代码块特定色值 3A3A38
            if "F4F6F3" in p_xml or "3A3A38" in p_xml:
                continue
            txt = "".join(re.findall(r"<(?:w|a):t[^>]*>(.*?)</(?:w|a):t>", p_xml, flags=re.S))
            txt = html.unescape(txt)
            if "**" in txt:
                cnt = txt.count("**")
                double_star += cnt
                if len(star_samples) < 3:
                    star_samples.append(txt.strip()[:34])
            if "`" in txt:
                cnt = txt.count("`")
                tick += cnt
                if len(tick_samples) < 3:
                    tick_samples.append(txt.strip()[:34])

    stats["residual_asterisk"] = double_star
    stats["residual_backtick"] = tick
    if double_star:
        issues.append(f"[格式] 可见文字中残留 {double_star} 处「**」—— **加粗** 未渲染成粗体，"
                      f"例如「{star_samples[0]}」")
    if tick:
        issues.append(f"[格式] 可见文字中残留 {tick} 个反引号 —— `等宽` 未渲染，"
                      f"例如「{tick_samples[0]}」")


def check_coverage(md_path: str, parts: dict[str, str], issues: list, stats: dict) -> None:
    """逐块清点：Markdown 里的每一段内容都必须在成品里找得到。

    旧版只查 $ 与 LaTeX，结果教案的「主线架构图」「板书设计」整块消失、
    列表编号错乱，全部零告警通过。这个检查就是为了堵住这类「静默丢内容」。

    顺带体检代码块宽度：方框图超过正文栏宽时只能压小字号才不折行，
    虽然不算错，但会小到难认，值得提示去 Markdown 里收窄。
    """
    import render as R  # 延迟导入：render 导入期会做解释器与依赖自检

    if not os.path.isfile(md_path):
        issues.append(f"[内容] 找不到源 Markdown：{md_path}")
        return

    paras = [normalize(p) for p in visible_paragraphs(parts)]
    joined = "".join(paras)

    with open(md_path, encoding="utf-8") as fh:
        _meta, body = R.parse_front_matter(fh.read())

    items: list[tuple[str, str]] = []
    narrow_limit = int(R.CODE_AVAIL_PT / R.CODE_SIZE_COMFORT)
    for blk in R.parse_markdown(body):
        t = blk["type"]
        if t in ("h1", "h2", "h3", "h4", "p", "quote"):
            items.append((t, blk["text"]))
        elif t == "list":
            for it in blk["items"]:
                mark = f"{it['num']}. " if it.get("ordered") else "· "
                items.append(("列表项", mark + it["text"]))
        elif t == "table":
            for cell in blk["header"]:
                items.append(("表头", cell))
            for row in blk["rows"]:
                for cell in row:
                    items.append(("表格", cell))
        elif t == "code":
            lines = blk["text"].split("\n")
            for ln in lines:
                if ln.strip():
                    items.append(("代码块", ln))
            widest = R.code_block_width(lines)
            if widest > narrow_limit:
                stats.setdefault("notes", []).append(
                    f"代码块偏宽：最宽约 {widest:.0f} 字符当量，超过正文栏宽能舒适容纳的 "
                    f"{narrow_limit} 字符，只能压到 {R.CODE_AVAIL_PT / widest:.1f}pt 显示；"
                    f"建议在 Markdown 中收窄到 {narrow_limit} 字符以内")

    missing: list[str] = []
    for kind, txt in items:
        key = normalize(txt)
        if not key:
            continue
        if not any(key in p for p in paras) and key not in joined:
            missing.append(f"{kind}｜{txt.strip()[:56]}")

    stats["md_items"] = len(items)
    stats["md_items_missing"] = len(missing)
    if missing:
        stats["missing"] = missing
        for line in missing[:8]:
            issues.append(f"[内容] 成品中缺失：{line}")
        if len(missing) > 8:
            issues.append(f"[内容] 另有 {len(missing) - 8} 处缺失，见 --json 输出的 missing 字段")


def check_math(parts: dict[str, str], issues: list, stats: dict, is_pptx: bool) -> None:
    total_math = 0
    total_images = 0
    for name, xml in parts.items():
        label = os.path.basename(name)

        # 1) 残存 $ 定界符
        dollars = xml.count("$")
        if dollars:
            issues.append(f"[公式] {label} 中残留 {dollars} 个 $ 定界符")

        # 2) 裸露 LaTeX 命令（只在可见文本 <m:t>/<a:t>/<w:t> 里查，避免误判命名空间）
        for tag in ("m:t", "a:t", "w:t"):
            for m in re.finditer(rf"<{tag}[^>]*>(.*?)</{tag}>", xml, flags=re.S):
                text = m.group(1)
                if LATEX_CMD.search(text):
                    issues.append(f"[公式] {label} 可见文本中残留 LaTeX 命令：{text[:40]}")
                    break

        # 3) 未修正的重音结构：limUpp 里塞了单个重音符号
        for m in re.finditer(r"<m:limUpp>(.*?)</m:limUpp>", xml, flags=re.S):
            body = m.group(1)
            lim = re.search(r"<m:lim>(.*?)</m:lim>", body, flags=re.S)
            if not lim:
                continue
            chars = "".join(re.findall(r"<m:t[^>]*>([^<]*)</m:t>", lim.group(1))).strip()
            if len(chars) == 1 and chars in ACCENT_CHARS:
                issues.append(f"[公式] {label} 存在未修正的重音结构 limUpp('{chars}')，"
                              f"会导致符号飘离字符")

        # 4) 空文本 run
        empty = len(re.findall(r"<m:t\s*/>|<m:t[^>]*></m:t>", xml))
        if empty:
            issues.append(f"[公式] {label} 中存在 {empty} 个空文本 run")

        # 5) 公式内中文缺字体
        for m in re.finditer(r"<m:r>(.*?)</m:r>", xml, flags=re.S):
            body = m.group(1)
            text = "".join(re.findall(r"<m:t[^>]*>([^<]*)</m:t>", body))
            if re.search(r"[\u4e00-\u9fff]", text):
                has_ea = ("eastAsia" in body) or ("<a:ea" in body)
                if not has_ea:
                    issues.append(f"[公式] {label} 公式内中文未指定中文字体：{text[:20]}")
                    break

        total_math += len(re.findall(r"<m:oMath[ >]", xml))
        total_images += len(re.findall(r"<a:blip", xml))

    stats["math_objects"] = total_math
    stats["math_images"] = total_images
    # 公式数量为 0 时不要一律判错：--math-mode image 模式下公式本就以图片形式存在。
    # 只有「既没有原生公式对象、也没有任何图片」时才可能是转换链路真出了问题。
    if total_math == 0 and total_images == 0 and parts:
        issues.append("[公式] 未发现任何原生公式对象；若材料本应含公式，请检查转换链路")
    elif total_math == 0 and total_images and parts:
        stats.setdefault("notes", []).append(
            "未发现原生公式对象，但检测到图片——若本次使用 --math-mode image，"
            "这是预期结果（公式以矢量图片呈现）；若预期原生公式，请改用 --math-mode native 重跑。"
        )


def check_docx(path: str, issues: list, stats: dict, kind: str | None = None,
               source_md: str | None = None) -> None:
    parts = read_parts(path, ("word/",))
    check_math(parts, issues, stats, is_pptx=False)
    check_markers(parts, issues, stats)

    doc = parts.get("word/document.xml", "")
    stats["images"] = len(re.findall(r"<a:blip", doc))
    stats["tables"] = doc.count("<w:tbl>")
    stats["code_block_paragraphs"] = doc.count("F4F6F3")   # 代码块底纹，用于确认未丢块
    if source_md:
        check_coverage(source_md, parts, issues, stats)


def check_pptx(path: str, issues: list, stats: dict, source_md: str | None = None) -> None:
    parts = read_parts(path, ("ppt/slides/",))
    check_math(parts, issues, stats, is_pptx=True)
    check_markers(parts, issues, stats)
    if source_md:
        check_coverage(source_md, parts, issues, stats)

    slides = [k for k in parts if re.match(r"ppt/slides/slide\d+\.xml$", k)]
    stats["slides"] = len(slides)
    stats["images"] = sum(len(re.findall(r"<a:blip", v)) for v in parts.values())

    # 检查形状是否越出画布（16:9，13.333 x 7.5 英寸 = 12192000 x 6858000 EMU）
    W, H = 12192000, 6858000
    for name, xml in parts.items():
        label = os.path.basename(name)
        for m in re.finditer(r'<a:off x="(-?\d+)" y="(-?\d+)"/><a:ext cx="(\d+)" cy="(\d+)"', xml):
            x, y, cx, cy = (int(g) for g in m.groups())
            if x < -20000 or y < -20000 or x + cx > W + 20000 or y + cy > H + 20000:
                issues.append(f"[版面] {label} 有形状越出幻灯片边界"
                              f"（x={x/914400:.2f}in, y={y/914400:.2f}in, "
                              f"w={cx/914400:.2f}in, h={cy/914400:.2f}in）")
                break


def main() -> int:
    ap = argparse.ArgumentParser(description="教学材料质检")
    ap.add_argument("path")
    ap.add_argument("--kind", default=None, choices=["jiaoan", "xuean", "kejian"])
    ap.add_argument("--source-md", default=None,
                    help="渲染所用的 Markdown 源文件；给出后启用逐块内容清点")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not os.path.isfile(args.path):
        print(json.dumps({"ok": False, "error": f"文件不存在：{args.path}"}, ensure_ascii=False))
        return 2

    issues: list[str] = []
    stats: dict = {}
    ext = os.path.splitext(args.path)[1].lower()

    try:
        if ext == ".docx":
            check_docx(args.path, issues, stats, args.kind, args.source_md)
        elif ext == ".pptx":
            check_pptx(args.path, issues, stats, args.source_md)
        else:
            print(json.dumps({"ok": False, "error": f"不支持的格式：{ext}"}, ensure_ascii=False))
            return 2
    except zipfile.BadZipFile:
        print(json.dumps({"ok": False, "error": "文件不是有效的 Office 文档（可能生成中断）"},
                         ensure_ascii=False))
        return 2

    result = {"ok": not issues, "file": args.path, "issues": issues, "stats": stats}
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"文件：{args.path}")
        print(f"统计：{json.dumps(stats, ensure_ascii=False)}")
        if issues:
            print(f"发现 {len(issues)} 个问题：")
            for it in issues:
                print("  -", it)
        else:
            print("质检通过：未发现问题。")
        for note in stats.get("notes", []):
            print(f"  提示：{note}")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
