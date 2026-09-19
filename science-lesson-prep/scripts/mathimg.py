# -*- coding: utf-8 -*-
"""公式矢量降级输出：LaTeX -> SVG / PNG（经 MathJax + resvg）。

何时使用本模块：
    默认情况下公式走 Office 原生对象（omml.py）。只有在以下情形才降级为图片——
      1. 目标环境不保证支持原生公式（老版本 PowerPoint、部分 WPS）；
      2. 某条公式原生转换失败，需要兜底；
      3. 教师明确要求公式不可编辑、只求显示效果。

本模块不依赖 LaTeX 发行版；MathJax 输出的 SVG 字形是 <path>，不含字体依赖。
Node 与依赖目录的定位统一交给 env.py，不锁定任何固定路径。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import env  # noqa: E402

_HERE = os.path.dirname(os.path.abspath(__file__))
_JS = os.path.join(_HERE, "mathjax_tex2svg.js")


def node_workspace() -> str:
    """Node 包所在的工作目录（node_modules 的父目录）。"""
    return os.path.dirname(env.node_modules_path())


def find_node() -> str | None:
    """定位 Node 解释器：环境变量 > PATH > 缓存目录 > 平台目录。"""
    return env.find_node()


def node_modules_path() -> str:
    """定位 node_modules：已装齐的优先，否则返回安装目标。"""
    return env.node_modules_path()


def available() -> tuple[bool, str]:
    """检查降级链路是否可用。"""
    node = find_node()
    if not node:
        return False, "未找到 Node 解释器"
    found = env.resolve_node_modules()
    if not found:
        return False, "未安装 mathjax-full（可运行 bootstrap.py 自动安装）"
    return True, node


def render(items: list[dict], out_dir: str, *, raster: bool = True,
           png_scale: int = 4, timeout: int = 300) -> dict[str, dict]:
    """批量把 LaTeX 转成 SVG（可选同时输出 PNG）。

    items: [{"id": "f1", "latex": "x^2", "display": False, "color": "1F3864"}]
    返回:  {id: {"ok":bool, "svg":str, "svgPath":str, "pngPath":str,
                 "width":float, "height":float, "descent":float, "error":str}}
    """
    ok, node = available()
    if not ok:
        return {it.get("id", str(i)): {"ok": False, "error": node}
                for i, it in enumerate(items)}

    os.makedirs(out_dir, exist_ok=True)
    payload = {
        "outDir": out_dir,
        "items": [{**it, "raster": raster, "pngScale": png_scale} for it in items],
    }
    e = dict(os.environ)
    # 把候选目录全部串起来，而不是锁死单一目录——
    # 这样全局安装或技能目录内的依赖都能被 Node 解析到。
    e["NODE_PATH"] = env.node_path_env()

    proc = subprocess.run(
        [node, _JS],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True, timeout=timeout, env=e,
    )
    if proc.returncode != 0 and not proc.stdout.strip():
        err = (proc.stderr or b"").decode("utf-8", "replace")[:400]
        return {it.get("id", str(i)): {"ok": False, "error": f"Node 执行失败：{err}"}
                for i, it in enumerate(items)}

    try:
        data = json.loads(proc.stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        err = (proc.stderr or b"").decode("utf-8", "replace")[:400]
        return {it.get("id", str(i)): {"ok": False, "error": f"输出解析失败：{err}"}
                for i, it in enumerate(items)}

    return {r["id"]: r for r in data.get("results", [])}


def render_one(latex: str, out_dir: str, *, name: str = "eq", display: bool = False,
               color: str | None = None, raster: bool = True,
               png_scale: int = 4) -> dict:
    """单条公式转 SVG/PNG。"""
    res = render(
        [{"id": name, "latex": latex, "display": display, "color": color}],
        out_dir, raster=raster, png_scale=png_scale,
    )
    return res.get(name, {"ok": False, "error": "无返回"})
