# -*- coding: utf-8 -*-
"""教学材料生成后的自动质检。

用法：
    python qa_check.py 教案.docx
    python qa_check.py 课件.pptx --kind kejian
    python qa_check.py 教案.docx --kind jiaoan --json

检查项分两类：
  A. 数学公式专项 —— 残存 $ 定界符、裸露 LaTeX 命令、未修正的重音结构、
     空文本 run、公式内中文缺字体、公式对象数量
  B. 教学内容完整性 —— 教案必备板块是否齐备（学情/目标/重难点/过程/板书/作业/反思）
  C. 版面 —— 图片数量、PPT 形状是否越出画布

退出码：0 = 通过；1 = 存在必须修复的问题；2 = 文件无法读取
"""
from __future__ import annotations

import argparse
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

# 必备板块：每项是一组「同义写法」，命中任一即视为具备。
# 用同义组而不是单一词，是因为教师对同一板块的叫法不统一
# （例如"练习"也常写作"当堂检测""课堂练习"），按字面匹配会误报。
REQUIRED_SECTIONS = {
    "jiaoan": [
        ("学情分析", "学情"),
        ("教学目标",),
        ("重难点", "教学重点", "教学难点"),
        ("教学过程", "教学环节"),
        ("板书",),
        ("作业",),
        ("反思",),
    ],
    "xuean": [
        ("学习目标", "学习任务"),
        ("探究",),
        ("练习", "当堂检测", "当堂练习", "课堂练习", "巩固练习", "变式训练", "检测"),
        ("小结", "总结", "归纳"),
    ],
}

SECTION_LABEL = {"jiaoan": "教案", "xuean": "导学案"}


def read_parts(path: str, prefixes: tuple[str, ...]) -> dict[str, str]:
    """读出 OOXML 包内匹配前缀的 XML 文本。"""
    out = {}
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.endswith(".xml") and any(name.startswith(p) for p in prefixes):
                out[name] = z.read(name).decode("utf-8", "replace")
    return out


def check_math(parts: dict[str, str], issues: list, stats: dict, is_pptx: bool) -> None:
    total_math = 0
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

    stats["math_objects"] = total_math
    if total_math == 0 and parts:
        issues.append("[公式] 未发现任何原生公式对象；若材料本应含公式，请检查转换链路")


def check_docx(path: str, issues: list, stats: dict, kind: str | None) -> None:
    parts = read_parts(path, ("word/",))
    check_math(parts, issues, stats, is_pptx=False)

    doc = parts.get("word/document.xml", "")
    stats["images"] = len(re.findall(r"<a:blip", doc))
    stats["tables"] = doc.count("<w:tbl>")

    # 教学内容完整性
    if kind in REQUIRED_SECTIONS:
        missing = [group[0] for group in REQUIRED_SECTIONS[kind]
                   if not any(alt in doc for alt in group)]
        stats["sections_missing"] = missing
        if missing:
            label = SECTION_LABEL.get(kind, "材料")
            issues.append(f"[内容] {label}缺少必备板块：{'、'.join(missing)}")


def check_pptx(path: str, issues: list, stats: dict) -> None:
    parts = read_parts(path, ("ppt/slides/",))
    check_math(parts, issues, stats, is_pptx=True)

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
            check_docx(args.path, issues, stats, args.kind)
        elif ext == ".pptx":
            check_pptx(args.path, issues, stats)
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
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
