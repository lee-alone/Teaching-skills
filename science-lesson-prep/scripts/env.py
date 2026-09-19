# -*- coding: utf-8 -*-
"""运行环境解析层：解释器、Node/npm、依赖目录。

为什么需要这个模块
------------------
技能目录要能被复制到任意一台电脑上运行，因此**不能假设**某个平台专有目录
（例如 ``~/.workbuddy-ai/...``）一定存在。本模块把「去哪儿找 Python / Node /
依赖」的判断集中到一处，统一按下面的顺序探测：

    环境变量  >  技能自带  >  通用缓存目录  >  平台目录（兼容回退）

``~/.workbuddy-ai/...`` 只作为**最后一级回退**保留，不再是唯一来源；
在普通电脑上它不存在也不会影响任何功能。

设计约束
--------
只用标准库。本模块会在「依赖尚未安装」的时刻被导入，不能引入第三方依赖。

环境变量（全部可选，用于特殊环境下重定向）
------------------------------------------
SCIENCE_LESSON_PREP_HOME          缓存根目录
SCIENCE_LESSON_PREP_PYTHON        直接指定解释器（最高优先级）
SCIENCE_LESSON_PREP_BASE_PYTHON   创建虚拟环境时使用的基础解释器
SCIENCE_LESSON_PREP_VENV          虚拟环境目录
SCIENCE_LESSON_PREP_NODE          指定 node 可执行文件
SCIENCE_LESSON_PREP_NODE_ROOT     node 各版本目录的父目录
SCIENCE_LESSON_PREP_NPM           指定 npm（可执行文件或 npm-cli.js）
SCIENCE_LESSON_PREP_NODE_MODULES  指定 node_modules 目录
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys

# Windows 下 stdout/stderr 被重定向到文件或管道时，Python 默认按系统 ANSI 代码页
# （如 cp936 / cp1252）编码，输出中文会抛 UnicodeEncodeError。本模块会向 stderr
# 写中文诊断信息，若此时编码不兼容，异常会从 ensure_runtime 抛出，
# 反而把它本要处理的"自动切换解释器"流程打断。故在此统一改为 UTF-8。
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001  非标准流（如被替换为 StringIO）时忽略
            pass

# --------------------------------------------------------------------------
# 依赖清单：import 名 -> pip 包名（bootstrap 安装与运行时自检共用）
# --------------------------------------------------------------------------
PIP_PACKAGES = {
    "docx": "python-docx",
    "pptx": "python-pptx",
    "lxml": "lxml",
    "latex2mathml": "latex2mathml",
    "mathml2omml": "mathml2omml",
    "matplotlib": "matplotlib",
    "numpy": "numpy",
    "PIL": "Pillow",
}

# 渲染公式与文档必需的模块
CORE_MODULES = ("lxml", "latex2mathml", "mathml2omml", "docx", "pptx")
# 绘制函数图象额外需要的模块
FIGURE_MODULES = ("matplotlib", "numpy")

# 公式降级链路（LaTeX -> SVG/PNG）需要的 Node 包
NODE_PACKAGES = ("mathjax-full", "@resvg/resvg-js")

_SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_LEGACY_ROOT = "~/.workbuddy-ai"          # 平台目录，仅作兼容回退
_REEXEC_FLAG = "SCIENCE_LESSON_PREP_REEXEC"


# ==========================================================================
# 基础路径
# ==========================================================================
def skill_root() -> str:
    """技能根目录（scripts 的上一级）。"""
    return _SKILL_ROOT


def scripts_dir() -> str:
    """脚本目录。"""
    return _SCRIPTS_DIR


def cache_root() -> str:
    """跨平台缓存根目录，用于存放虚拟环境与 Node 包。"""
    override = os.environ.get("SCIENCE_LESSON_PREP_HOME")
    if override:
        return os.path.abspath(os.path.expanduser(override))
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Caches")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "science-lesson-prep")


def _legacy(*parts: str) -> str:
    return os.path.join(os.path.expanduser(_LEGACY_ROOT), *parts)


def _writable_dir(path: str) -> bool:
    """判断 path 能否创建/写入：向上找到最近的已存在祖先再试权限。"""
    probe = path
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            return False
        probe = parent
    return os.path.isdir(probe) and os.access(probe, os.W_OK)


def _dedup(paths) -> list[str]:
    seen, out = set(), []
    for p in paths:
        if not p:
            continue
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            out.append(os.path.abspath(p))
    return out


# ==========================================================================
# Python 解释器
# ==========================================================================
def venv_python(venv_dir: str) -> str:
    """虚拟环境内的解释器路径。"""
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def venv_candidates() -> list[str]:
    """可能存在的虚拟环境目录（按优先级）。"""
    out = []
    env = os.environ.get("SCIENCE_LESSON_PREP_VENV")
    if env:
        out.append(os.path.expanduser(env))
    out.append(os.path.join(_SKILL_ROOT, ".venv"))          # 技能自带
    out.append(os.path.join(cache_root(), "venv"))          # 通用缓存
    out.append(_legacy("binaries", "python", "envs", "default"))  # 平台回退
    return _dedup(out)


def preferred_venv_dir() -> str:
    """创建虚拟环境时使用的位置：缓存目录（不污染技能目录）。"""
    env = os.environ.get("SCIENCE_LESSON_PREP_VENV")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(cache_root(), "venv")


def existing_venv_dir() -> str | None:
    """返回第一个已存在且可用的虚拟环境目录。"""
    for d in venv_candidates():
        if os.path.isfile(venv_python(d)):
            return d
    return None


def base_python_candidates() -> list[str]:
    """可用于创建虚拟环境的基础解释器（按优先级）。"""
    out = []
    env = os.environ.get("SCIENCE_LESSON_PREP_BASE_PYTHON")
    if env:
        out.append(os.path.expanduser(env))
    out.append(sys.executable)
    for name in (("python3", "python") if os.name != "nt" else ("python", "python3")):
        found = shutil.which(name)
        if found:
            out.append(found)
    # 平台托管的 Python 版本目录（兼容回退）
    roots = []
    env_root = os.environ.get("SCIENCE_LESSON_PREP_PYTHON_ROOT")
    if env_root:
        roots.append(os.path.expanduser(env_root))
    roots.append(os.path.join(cache_root(), "python"))
    roots.append(_legacy("binaries", "python", "versions"))
    for root in roots:
        if not os.path.isdir(root):
            continue
        for ver in sorted(os.listdir(root), reverse=True):
            for exe in ("python.exe", os.path.join("bin", "python3"), os.path.join("bin", "python")):
                p = os.path.join(root, ver, exe)
                if os.path.isfile(p):
                    out.append(p)
    return _dedup([p for p in out if p and os.path.isfile(p)])


def python_candidates() -> list[str]:
    """所有候选解释器（已存在的），按优先级排列。"""
    out = []
    env = os.environ.get("SCIENCE_LESSON_PREP_PYTHON")
    if env:
        out.append(os.path.expanduser(env))
    out.append(sys.executable)                     # 当前解释器优先
    for d in venv_candidates():
        out.append(venv_python(d))
    for name in (("python3", "python") if os.name != "nt" else ("python", "python3")):
        found = shutil.which(name)
        if found:
            out.append(found)
    return _dedup([p for p in out if p and os.path.isfile(p)])


def missing_in_current(modules) -> list[str]:
    """当前解释器缺少的模块（不启子进程，快）。"""
    miss = []
    for m in modules:
        try:
            if importlib.util.find_spec(m) is None:
                miss.append(m)
        except Exception:  # noqa: BLE001  导入期异常一律视为缺失
            miss.append(m)
    return miss


def missing_in(python: str, modules) -> list[str]:
    """指定解释器缺少的模块（启子进程探测）。"""
    code = (
        "import importlib.util, json\n"
        "out = []\n"
        "for m in " + repr(list(modules)) + ":\n"
        "    try:\n"
        "        if importlib.util.find_spec(m) is None: out.append(m)\n"
        "    except Exception:\n"
        "        out.append(m)\n"
        "print(json.dumps(out))\n"
    )
    try:
        proc = subprocess.run([python, "-c", code], capture_output=True,
                              text=True, timeout=180)
        if proc.returncode != 0:
            return list(modules)
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:  # noqa: BLE001
        return list(modules)


def resolve_python(modules) -> str | None:
    """返回第一个满足依赖要求的解释器；都没有则返回 None。"""
    for p in python_candidates():
        if not missing_in(p, modules):
            return p
    return None


def ensure_runtime(modules, *, label: str = "脚本") -> None:
    """若当前解释器缺少关键依赖，自动切换到可用解释器重新执行本脚本。

    必须在导入任何第三方库**之前**调用。用环境变量标记防止无限重启。
    找不到合适解释器时静默返回，由后续导入抛出原始错误，便于排查。
    """
    if os.environ.get(_REEXEC_FLAG):
        return
    if not missing_in_current(modules):
        return

    target = resolve_python(modules)
    if not target:
        return
    if os.path.normcase(os.path.abspath(target)) == os.path.normcase(os.path.abspath(sys.executable)):
        return

    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if not script or not os.path.isfile(script):
        return

    sys.stderr.write(f"[env] {label}：当前解释器缺少依赖，改用 {target} 重新执行\n")
    sys.stderr.flush()
    os.environ[_REEXEC_FLAG] = "1"
    try:
        if os.name == "nt":
            code = subprocess.call([target, script, *sys.argv[1:]])
            sys.exit(code)
        else:
            os.execv(target, [target, script, *sys.argv[1:]])
    except OSError as exc:  # 切换失败则继续用当前解释器，让错误自然暴露
        sys.stderr.write(f"[env] 切换解释器失败：{exc}\n")


# ==========================================================================
# Node / npm
# ==========================================================================
def find_node() -> str | None:
    """定位 node：环境变量 > PATH > 平台目录。"""
    env = os.environ.get("SCIENCE_LESSON_PREP_NODE")
    if env and os.path.isfile(os.path.expanduser(env)):
        return os.path.abspath(os.path.expanduser(env))

    found = shutil.which("node")
    if found:
        return found

    roots = []
    env_root = os.environ.get("SCIENCE_LESSON_PREP_NODE_ROOT")
    if env_root:
        roots.append(os.path.expanduser(env_root))
    roots.append(os.path.join(cache_root(), "node"))
    roots.append(_legacy("binaries", "node", "versions"))
    for root in roots:
        if not os.path.isdir(root):
            continue
        for ver in sorted(os.listdir(root), reverse=True):
            exe = os.path.join(root, ver, "node.exe" if os.name == "nt" else os.path.join("bin", "node"))
            if os.path.isfile(exe):
                return exe
    return None


def find_npm(node: str | None = None) -> str | None:
    """定位 npm：环境变量 > PATH > node 同目录。返回可执行文件或 npm-cli.js。"""
    env = os.environ.get("SCIENCE_LESSON_PREP_NPM")
    if env and os.path.isfile(os.path.expanduser(env)):
        return os.path.abspath(os.path.expanduser(env))

    for name in (("npm.cmd", "npm") if os.name == "nt" else ("npm",)):
        found = shutil.which(name)
        if found:
            return found

    if node:
        d = os.path.dirname(node)
        for cand in (
            os.path.join(d, "npm.cmd"),
            os.path.join(d, "npm"),
            os.path.join(d, "node_modules", "npm", "bin", "npm-cli.js"),
            os.path.join(d, "..", "lib", "node_modules", "npm", "bin", "npm-cli.js"),
        ):
            if os.path.isfile(cand):
                return os.path.abspath(cand)
    return None


def npm_argv(node: str, npm: str) -> list[str]:
    """把 npm 路径转换成可执行的命令前缀（.js 需要 node 拉起）。"""
    if npm.endswith(".js"):
        return [node, npm]
    return [npm]


def node_modules_candidates() -> list[str]:
    """可能存放 Node 包的 node_modules 目录（按优先级）。"""
    out = []
    env = os.environ.get("SCIENCE_LESSON_PREP_NODE_MODULES")
    if env:
        out.append(os.path.expanduser(env))
    out.append(os.path.join(_SCRIPTS_DIR, "node_modules"))            # 技能自带
    out.append(os.path.join(cache_root(), "node", "node_modules"))    # 通用缓存
    out.append(_legacy("binaries", "node", "workspace", "node_modules"))  # 平台回退
    # 系统级全局安装目录
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            out.append(os.path.join(appdata, "npm", "node_modules"))
    else:
        out.append("/usr/local/lib/node_modules")
        out.append("/usr/lib/node_modules")
    return _dedup(out)


def preferred_node_modules() -> str:
    """安装 Node 包的目标目录：缓存目录（不污染技能目录）。"""
    env = os.environ.get("SCIENCE_LESSON_PREP_NODE_MODULES")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(cache_root(), "node", "node_modules")


def resolve_node_modules(packages=NODE_PACKAGES) -> str | None:
    """返回第一个已装齐 packages 的 node_modules 目录。"""
    for d in node_modules_candidates():
        if os.path.isdir(d) and all(os.path.isdir(os.path.join(d, p)) for p in packages):
            return d
    return None


def node_modules_path() -> str:
    """当前应使用的 node_modules：已装齐的优先，否则返回安装目标。"""
    return resolve_node_modules() or preferred_node_modules()


def node_path_env() -> str:
    """构造 NODE_PATH：把所有可能的目录都串起来，避免锁死单一路径。

    这样即使依赖装在全局或技能目录，也能被 Node 解析到。
    """
    parts = [d for d in node_modules_candidates() if os.path.isdir(d)]
    cur = os.environ.get("NODE_PATH")
    if cur:
        parts.extend(cur.split(os.pathsep))
    return os.pathsep.join(_dedup(parts))
