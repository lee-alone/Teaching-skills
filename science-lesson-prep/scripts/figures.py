# -*- coding: utf-8 -*-
"""函数图象生成：按 JSON 规格用 matplotlib 绘制，输出 PNG 与 SVG。

规格示例（Markdown 中以 ```plot 代码块书写）：
    {
      "title": "二次函数 y = x² - 2x - 3 的图象",
      "x": [-4, 6], "y": [-6, 8],
      "curves": [
        {"expr": "x**2 - 2*x - 3", "label": "y = x² - 2x - 3"},
        {"expr": "2*x + 1", "label": "y = 2x + 1", "style": "--"}
      ],
      "points": [{"x": 1, "y": -4, "label": "顶点 (1, -4)"}],
      "vlines": [{"x": 1, "label": "对称轴 x = 1"}],
      "hlines": [{"y": 0, "label": "y = 0"}]
    }

表达式为 x 的 NumPy 写法：x**2、np.sqrt(x+1)、np.sin(x)、np.abs(x) 等。
分两栏并排：加 "layout": [1, 2] 与 "panels": [ {面板1}, {面板2} ]。
"""
from __future__ import annotations

import json
import os
import re
import sys

# 与 env.py 同因：Windows 下重定向输出时默认编码可能无法编码中文，
# 本模块直接运行时（__main__）会向 stdout 打印含中文的 JSON。
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import font_manager  # noqa: E402

CJK_CANDIDATES = ["SimHei", "Microsoft YaHei", "SimSun", "KaiTi", "FangSong",
                  "Noto Sans CJK SC", "WenQuanYi Zen Hei", "PingFang SC"]

PALETTE = ["#185FA5", "#D85A30", "#0F6E56", "#993556", "#BA7517", "#534AB7"]

# 表达式求值白名单：只放数学函数，不放内置函数
_ALLOWED = {
    "x": None,
    "np": np,
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "arcsin": np.arcsin, "arccos": np.arccos, "arctan": np.arctan,
    "exp": np.exp, "log": np.log, "ln": np.log, "log10": np.log10,
    "sqrt": np.sqrt, "abs": np.abs, "fabs": np.fabs,
    "floor": np.floor, "ceil": np.ceil, "sign": np.sign,
    "power": np.power, "maximum": np.maximum, "minimum": np.minimum,
    "where": np.where, "pi": np.pi, "e": np.e, "inf": np.inf,
    "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh,
    "arcsinh": np.arcsinh, "arctanh": np.arctanh,
    "degrees": np.degrees, "radians": np.radians,
}


def setup_fonts() -> str | None:
    """让 matplotlib 能正确显示中文与负号。返回选用的中文字体名。"""
    installed = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((n for n in CJK_CANDIDATES if n in installed), None)
    if chosen:
        matplotlib.rcParams["font.sans-serif"] = [chosen] + CJK_CANDIDATES
    else:
        matplotlib.rcParams["font.sans-serif"] = CJK_CANDIDATES
    matplotlib.rcParams["axes.unicode_minus"] = False
    matplotlib.rcParams["svg.fonttype"] = "path"  # 文字转路径，避免 SVG 依赖字体
    return chosen


def _eval(expr: str, x: np.ndarray) -> np.ndarray:
    ns = dict(_ALLOWED)
    ns["x"] = x
    return eval(expr, {"__builtins__": {}}, ns)  # noqa: S307 受白名单约束


# Unicode 上下标 -> mathtext。
# 中文字体（SimHei/宋体）普遍没有 ²、₁ 这类字形，直接写会渲染成方框，
# 因此统一转成 matplotlib 的数学文本，交给数学字体渲染。
_SUP = {"\u2070": "0", "\u00b9": "1", "\u00b2": "2", "\u00b3": "3", "\u2074": "4",
        "\u2075": "5", "\u2076": "6", "\u2077": "7", "\u2078": "8", "\u2079": "9",
        "\u207f": "n", "\u207a": "+", "\u207b": "-", "\u207d": "(", "\u207e": ")"}
_SUB = {"\u2080": "0", "\u2081": "1", "\u2082": "2", "\u2083": "3", "\u2084": "4",
        "\u2085": "5", "\u2086": "6", "\u2087": "7", "\u2088": "8", "\u2089": "9",
        "\u2099": "n", "\u208a": "+", "\u208b": "-"}

_CJK = re.compile(r"[\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]")


def _script_to_tex(seg: str) -> str:
    """把一段纯文本里的 Unicode 上下标合并成 ^{...} / _{...}。"""
    out, i, n = [], 0, len(seg)
    while i < n:
        ch = seg[i]
        table, marker = (_SUP, "^") if ch in _SUP else ((_SUB, "_") if ch in _SUB else (None, None))
        if table is None:
            out.append(ch)
            i += 1
            continue
        buf = []
        while i < n and seg[i] in table:
            buf.append(table[seg[i]])
            i += 1
        out.append(f"{marker}{{{''.join(buf)}}}")
    return "".join(out)


def mathify(text: str) -> str:
    """让含 Unicode 上下标的标签能正常显示。

    只对非中文片段做转换并包进 $...$，中文部分保持原样，
    这样「二次函数 y = x² - 2x - 3 的图象」不会因整体转数学模式而丢掉汉字。
    已经写成 $...$ 的片段不做处理。
    """
    if not text or "$" in text:
        return text

    parts, buf, buf_is_cjk = [], [], None
    for ch in text:
        is_cjk = bool(_CJK.match(ch))
        if buf_is_cjk is None or is_cjk == buf_is_cjk:
            buf.append(ch)
            buf_is_cjk = is_cjk
        else:
            parts.append((buf_is_cjk, "".join(buf)))
            buf, buf_is_cjk = [ch], is_cjk
    if buf:
        parts.append((buf_is_cjk, "".join(buf)))

    result = []
    for is_cjk, seg in parts:
        if is_cjk or not any(c in _SUP or c in _SUB for c in seg):
            result.append(seg)
        else:
            # 首尾空格留在 $ 之外，保证中文与公式之间仍有间隔
            core = seg.strip()
            lead = seg[: len(seg) - len(seg.lstrip())]
            trail = seg[len(seg.rstrip()):]
            result.append(f"{lead}${_script_to_tex(core)}${trail}")
    return "".join(result)


# 字号缩放：课件投影时图象内部文字需要放大，否则投到大屏上偏小
_FS = 1.0


def _fs(x: float) -> float:
    return x * _FS


def _draw_panel(ax, spec: dict, show_legend: bool = True) -> None:
    xr = spec.get("x", [-5, 5])
    xs = np.linspace(float(xr[0]), float(xr[1]), int(spec.get("samples", 1200)))

    for i, curve in enumerate(spec.get("curves", [])):
        cr = curve.get("xrange", xr)
        cx = np.linspace(float(cr[0]), float(cr[1]), int(spec.get("samples", 1200)))
        with np.errstate(all="ignore"):
            cy = _eval(curve["expr"], cx)
        cy = np.asarray(cy, dtype=float)
        if cy.shape != cx.shape:
            cy = np.broadcast_to(cy, cx.shape).astype(float)
        color = curve.get("color") or PALETTE[i % len(PALETTE)]
        ax.plot(
            cx, cy,
            color=color,
            linestyle=curve.get("style", "-"),
            linewidth=float(curve.get("width", 2.0)),
            label=mathify(curve.get("label")),
            zorder=3,
        )

    for v in spec.get("vlines", []):
        ax.axvline(float(v["x"]), color=v.get("color", "#888780"),
                   linestyle=v.get("style", "--"), linewidth=1.0,
                   label=mathify(v.get("label")), zorder=2)
    for h in spec.get("hlines", []):
        ax.axhline(float(h["y"]), color=h.get("color", "#888780"),
                   linestyle=h.get("style", "--"), linewidth=1.0,
                   label=mathify(h.get("label")), zorder=2)

    for p in spec.get("points", []):
        ax.plot([float(p["x"])], [float(p["y"])], marker=p.get("marker", "o"),
                markersize=float(p.get("size", 7)),
                color=p.get("color", "#A32D2D"), zorder=5,
                label=mathify(p.get("label")))
        if p.get("label") and p.get("annotate", True):
            ax.annotate(mathify(p["label"]), (float(p["x"]), float(p["y"])),
                        textcoords="offset points", xytext=(8, 8),
                        fontsize=_fs(11), color=p.get("color", "#A32D2D"))

    for t in spec.get("texts", []):
        ax.text(float(t["x"]), float(t["y"]), mathify(t.get("text", "")),
                fontsize=_fs(float(t.get("size", 11))),
                color=t.get("color", "#2C2C2A"),
                ha=t.get("ha", "left"), va=t.get("va", "bottom"))

    if spec.get("title"):
        ax.set_title(mathify(spec["title"]), fontsize=_fs(13))
    ax.set_xlabel(mathify(spec.get("xlabel", "x")), fontsize=_fs(12))
    ax.set_ylabel(mathify(spec.get("ylabel", "y")), fontsize=_fs(12))

    if spec.get("y"):
        ax.set_ylim(float(spec["y"][0]), float(spec["y"][1]))
    ax.set_xlim(float(xr[0]), float(xr[1]))

    if spec.get("grid", True):
        ax.grid(True, linestyle=":", linewidth=0.6, color="#B4B2A9", alpha=0.8)
    if spec.get("axis", True):
        ax.axhline(0, color="#5F5E5A", linewidth=0.8, zorder=1)
        ax.axvline(0, color="#5F5E5A", linewidth=0.8, zorder=1)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(labelsize=_fs(10))

    handles, labels = ax.get_legend_handles_labels()
    if show_legend and labels:
        ax.legend(fontsize=_fs(10), loc="best", framealpha=0.9)


def render_figure(spec: dict, out_dir: str, name: str = "fig",
                  *, dpi: int = 200, font_scale: float = 1.0) -> dict:
    """绘制图象，返回 {"ok", "pngPath", "svgPath", "width", "height", "error"}。

    font_scale 用于整体放大图象内部的文字：课件投影建议 1.6~2.0，
    教案打印保持 1.0 即可。
    """
    global _FS
    _FS = float(font_scale or 1.0)
    setup_fonts()
    os.makedirs(out_dir, exist_ok=True)

    try:
        panels = spec.get("panels") or [spec]
        layout = spec.get("layout") or [1, len(panels)]
        rows, cols = int(layout[0]), int(layout[1])
        size = spec.get("size", [7.2, 4.4] if len(panels) == 1 else [4.6, 4.0])

        fig, axes = plt.subplots(rows, cols, figsize=(float(size[0]), float(size[1])),
                                 dpi=dpi, squeeze=False)
        for idx, ax in enumerate(axes.ravel()):
            if idx < len(panels):
                _draw_panel(ax, panels[idx], show_legend=len(panels) == 1)
            else:
                ax.axis("off")

        if spec.get("suptitle"):
            fig.suptitle(mathify(spec["suptitle"]), fontsize=_fs(14))
        fig.tight_layout()

        png_path = os.path.join(out_dir, f"{name}.png")
        svg_path = os.path.join(out_dir, f"{name}.svg")
        fig.savefig(png_path, dpi=dpi, bbox_inches="tight", facecolor="white")
        fig.savefig(svg_path, bbox_inches="tight", facecolor="white")
        plt.close(fig)

        from PIL import Image
        with Image.open(png_path) as im:
            w, h = im.size
        return {"ok": True, "pngPath": png_path, "svgPath": svg_path,
                "width": w, "height": h}
    except Exception as exc:  # noqa: BLE001
        plt.close("all")
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def render_from_json(spec_json: str, out_dir: str, name: str = "fig",
                     **kw) -> dict:
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        return {"ok": False, "error": f"图象规格不是合法 JSON：{exc}"}
    return render_figure(spec, out_dir, name, **kw)


if __name__ == "__main__":
    import sys

    spec = json.load(open(sys.argv[1], encoding="utf-8"))
    out = sys.argv[2] if len(sys.argv) > 2 else "."
    print(json.dumps(render_figure(spec, out), ensure_ascii=False))
