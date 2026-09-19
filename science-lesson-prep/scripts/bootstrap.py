#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""环境自检与依赖自动安装。

用法：
    python bootstrap.py            # 检查并在缺依赖时自动安装
    python bootstrap.py --check    # 只检查，不安装

退出码：0 = 环境就绪；1 = 环境不可用（需人工处理）

输出最后一行是 JSON，供主代理解析：
    {"ok": true, "python": "<解释器路径>", "missing": [], "installed": [...],
     "node": "<node 路径>", "node_modules": "<目录>", "fonts": {...}}

路径策略见同目录 env.py：不假设任何平台专有目录存在，
``~/.workbuddy-ai/...`` 仅作兼容回退。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import env  # noqa: E402

# 依赖：import 名 -> pip 包名（与 env.py 共用同一份清单）
REQUIRED = env.PIP_PACKAGES

# 教学材料需要的中文字体：用途 -> 候选字体文件
CJK_FONTS = {
    "宋体": ["simsun.ttc", "simsun.ttf"],
    "黑体": ["simhei.ttf"],
    "楷体": ["simkai.ttf"],
    "仿宋": ["simfang.ttf"],
    "微软雅黑": ["msyh.ttc"],
}

# 非 Windows 平台常见中文字体（供 Linux/macOS 使用）
CJK_FONTS_POSIX = {
    "宋体": ["NotoSansCJK-Regular.ttc", "NotoSerifCJK-Regular.ttc",
             "SourceHanSansSC-Regular.otf", "SourceHanSerifSC-Regular.otf"],
    "黑体": ["NotoSansCJK-Bold.ttc", "SourceHanSansSC-Bold.otf"],
    "楷体": ["NotoSerifCJK-Regular.ttc"],
    "仿宋": ["NotoSerifCJK-Regular.ttc"],
    "微软雅黑": ["NotoSansCJK-Regular.ttc", "SourceHanSansSC-Regular.otf"],
}

CJK_FONT_DIRS_POSIX = [
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
    "/System/Library/Fonts",
    "/Library/Fonts",
    os.path.expanduser("~/Library/Fonts"),
]


# ==========================================================================
# Python 环境
# ==========================================================================
def ensure_interpreter() -> tuple[str, str | None]:
    """确保存在可用的虚拟环境解释器，返回 (解释器路径, 创建信息)。

    优先复用已存在的虚拟环境（避免重复下载依赖）；
    不存在时在可移植的缓存目录下新建。
    """
    existing = env.existing_venv_dir()
    if existing:
        return env.venv_python(existing), None

    bases = env.base_python_candidates()
    if not bases:
        raise RuntimeError("未找到可用于创建虚拟环境的 Python 解释器")

    env_dir = env.preferred_venv_dir()
    last_err = ""
    for base in bases:
        os.makedirs(os.path.dirname(env_dir), exist_ok=True)
        proc = subprocess.run([base, "-m", "venv", env_dir],
                              capture_output=True, text=True, timeout=900)
        vp = env.venv_python(env_dir)
        if proc.returncode == 0 and os.path.isfile(vp):
            return vp, f"已创建虚拟环境 {env_dir}（基于 {base}）"
        last_err = (proc.stderr or proc.stdout or "").strip()[:300]

    raise RuntimeError(f"创建虚拟环境失败：{last_err or '未知错误'}")


def check_missing(python: str) -> list[str]:
    """返回缺失的 pip 包名列表。"""
    missing_modules = env.missing_in(python, list(REQUIRED))
    return [REQUIRED[m] for m in missing_modules]


def install(python: str, packages: list[str]) -> tuple[bool, str]:
    """把依赖装进隔离的虚拟环境（不使用 --user，也不动全局环境）。"""
    cmd = [python, "-m", "pip", "install", "--disable-pip-version-check", *packages]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if proc.returncode == 0:
        tail = proc.stdout.strip().splitlines()
        return True, tail[-1] if tail else "安装完成"
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return False, " | ".join(tail[-3:]) if tail else "未知错误"


# ==========================================================================
# Node 环境（公式降级链路）
# ==========================================================================
def check_node(node_modules: str) -> list[str]:
    """返回缺失的 Node 包列表。"""
    return [p for p in env.NODE_PACKAGES
            if not os.path.isdir(os.path.join(node_modules, p))]


def install_node(node: str, npm: str, packages: list[str]) -> tuple[bool, str]:
    """把 Node 包装进隔离目录，不使用 -g。"""
    workspace = os.path.dirname(env.preferred_node_modules())
    os.makedirs(workspace, exist_ok=True)
    cmd = [*env.npm_argv(node, npm), "install", *packages, "--no-audit", "--no-fund"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              cwd=workspace, timeout=3600)
    except OSError as exc:
        return False, f"执行 npm 失败：{exc}"
    if proc.returncode == 0:
        return True, "安装完成"
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return False, " | ".join(tail[-3:]) if tail else "未知错误"


# ==========================================================================
# 字体
# ==========================================================================
def _scan_font_dir(font_dir: str) -> dict[str, str]:
    names = {}
    if not os.path.isdir(font_dir):
        return names
    for root, _dirs, files in os.walk(font_dir):
        for f in files:
            names.setdefault(f.lower(), os.path.join(root, f))
    return names


def check_fonts() -> dict[str, str | None]:
    """检查系统中文字体是否可用（DOCX/PPTX 与 matplotlib 都需要）。"""
    found: dict[str, str | None] = {}
    if os.name == "nt":
        font_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        names = {f.lower(): f for f in os.listdir(font_dir)} if os.path.isdir(font_dir) else {}
        for label, cands in CJK_FONTS.items():
            hit = next((names[c] for c in cands if c in names), None)
            found[label] = os.path.join(font_dir, hit) if hit else None
        return found

    names: dict[str, str] = {}
    for d in CJK_FONT_DIRS_POSIX:
        names.update(_scan_font_dir(d))
    for label, cands in CJK_FONTS_POSIX.items():
        hit = next((names[c.lower()] for c in cands if c.lower() in names), None)
        found[label] = hit
    return found


# ==========================================================================
# 主流程
# ==========================================================================
def main() -> int:
    only_check = "--check" in sys.argv
    result = {"ok": False, "python": None, "missing": [], "installed": [],
              "messages": [], "fonts": {}, "cache_root": env.cache_root()}

    try:
        python, created = ensure_interpreter()
        result["python"] = python
        if created:
            result["messages"].append(created)
    except Exception as exc:  # noqa: BLE001
        result["messages"].append(str(exc))
        print(json.dumps(result, ensure_ascii=False))
        return 1

    missing = check_missing(python)
    result["missing"] = missing

    if missing and not only_check:
        print(f"[bootstrap] 缺少依赖：{', '.join(missing)}，正在安装…")
        ok, msg = install(python, missing)
        if not ok:
            result["messages"].append(f"安装失败：{msg}")
            print(json.dumps(result, ensure_ascii=False))
            return 1
        result["installed"] = missing
        still = check_missing(python)
        if still:
            result["missing"] = still
            result["messages"].append(f"安装后仍缺失：{', '.join(still)}")
            print(json.dumps(result, ensure_ascii=False))
            return 1
        result["missing"] = []

    fonts = check_fonts()
    result["fonts"] = fonts
    if not any(fonts.values()):
        result["messages"].append("未检测到中文字体，图象中的中文可能显示为方框")

    # ---- Node 降级链路（公式转矢量图 / 复杂公式兜底）----
    node = env.find_node()
    result["node"] = node
    result["node_missing"] = []
    if node:
        npm = env.find_npm(node)
        result["npm"] = npm
        node_modules = env.resolve_node_modules() or env.preferred_node_modules()
        result["node_modules"] = node_modules
        node_missing = check_node(node_modules)
        result["node_missing"] = node_missing
        if node_missing and not only_check:
            if npm:
                print(f"[bootstrap] 缺少 Node 包：{', '.join(node_missing)}，正在安装…")
                ok, msg = install_node(node, npm, node_missing)
                if ok:
                    result["node_installed"] = node_missing
                    result["node_modules"] = env.resolve_node_modules() or node_modules
                    result["node_missing"] = check_node(result["node_modules"])
                else:
                    result["messages"].append(f"Node 包安装失败：{msg}")
            else:
                result["messages"].append(
                    "未找到 npm，无法自动安装 Node 包；"
                    "可手动安装后设 SCIENCE_LESSON_PREP_NODE_MODULES 指向 node_modules")
    else:
        result["messages"].append(
            "未找到 Node，公式降级为矢量图的能力不可用（原生公式不受影响）")

    result["ok"] = not result["missing"]
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
