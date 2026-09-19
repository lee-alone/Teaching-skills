#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_plan.py - 教案结构与质量自动化自检脚本

按照 lesson-plan 技能规范对 Markdown 教案进行全面自检：
1. 11 大标准板块完整性
2. 教学过程每个环节的四要素（教师活动、学生活动、设计意图、评价点）
3. 各环节用时计算与课时（40/45分钟）/机动时间匹配
4. 教学目标编号（T1, T2...）规范与「目标—活动—评价对照表」闭环落实
5. 教学目标中避免使用空泛动词（理解/掌握/了解/体会/认识）单独作谓语
6. 商业用语与套话检测（亮点、赋能、抓手、打造等）
7. 公式与字符规范（检测 Unicode 上下标，提醒使用标准 LaTeX）

退出码：
- 0: 全部必检项通过（可有轻微警告）
- 1: 存在未达标错误项（必须修正）
"""

import sys
import os
import re
import argparse
import io

# 确保在 Windows 控制台下正确输出 UTF-8 字符
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

REQUIRED_SECTIONS = [
    ("课题信息", ["课题信息", "基本信息"]),
    ("教材分析", ["教材分析"]),
    ("学情分析", ["学情分析"]),
    ("教学目标", ["教学目标"]),
    ("教学重点与难点", ["教学重点与难点", "教学重难点", "教学重点和难点"]),
    ("教学思路", ["教学思路", "设计思路", "教学整体构想", "教学构想"]),
    ("教学准备", ["教学准备"]),
    ("教学过程", ["教学过程"]),
    ("目标—活动—评价对照表", ["目标—活动—评价对照表", "目标-活动-评价对照表", "目标、活动、评价对照表", "目标—活动—评价三栏对照表"]),
    ("板书设计", ["板书设计"]),
    ("作业设计", ["作业设计"]),
    ("教学反思", ["教学反思"]),
]

FOUR_ELEMENTS = [
    ("教师活动", [r"\*\*教师活动\*\*", r"教师活动[：:]"]),
    ("学生活动", [r"\*\*学生活动\*\*", r"学生活动[：:]"]),
    ("设计意图", [r"\*\*设计意图\*\*", r"设计意图[：:]"]),
    ("评价点", [r"\*\*评价点\*\*", r"评价点[：:]"]),
]

BANNED_BUZZWORDS = ["亮点", "赋能", "抓手", "打造"]

HOLLOW_VERBS = ["理解", "掌握", "了解", "体会", "认识"]

UNICODE_SUBS_SUPS = [
    ("²", "$^2$"),
    ("³", "$^3$"),
    ("₁", "$_1$"),
    ("₂", "$_2$"),
    ("₃", "$_3$"),
    ("₄", "$_4$"),
]


class LessonPlanChecker:
    def __init__(self, filepath, strict=False):
        self.filepath = filepath
        self.strict = strict
        self.errors = []
        self.warnings = []
        self.passed = []
        self.content = ""
        self.clean_content = ""
        self.sections = {}

    def load_file(self):
        if not os.path.exists(self.filepath):
            self.errors.append(f"文件不存在: {self.filepath}")
            return False
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                self.content = f.read()
        except UnicodeDecodeError:
            try:
                with open(self.filepath, "r", encoding="gbk") as f:
                    self.content = f.read()
            except Exception as e:
                self.errors.append(f"读取文件失败: {e}")
                return False
        except Exception as e:
            self.errors.append(f"读取文件失败: {e}")
            return False

        # 生成去除注释、【设计说明】旁注与代码块的内容，供文本规则检查
        clean_lines = []
        in_comment = False
        in_code_block = False
        for line in self.content.splitlines():
            stripped = line.strip()
            if stripped.startswith("<!--"):
                if not stripped.endswith("-->"):
                    in_comment = True
                continue
            if in_comment:
                if stripped.endswith("-->"):
                    in_comment = False
                continue
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue
            if in_code_block:
                continue
            if stripped.startswith("> 【设计说明】") or stripped.startswith("> 【说明】"):
                continue
            if stripped.startswith(">") and "【设计说明】" in stripped:
                continue
            clean_lines.append(line)
        self.clean_content = "\n".join(clean_lines)
        return True

    def split_sections(self):
        # 按照二级标题 ## 划分板块
        lines = self.content.splitlines()
        current_sec = None
        current_body = []
        for line in lines:
            m = re.match(r"^##\s+(.+)$", line.strip())
            if m:
                if current_sec:
                    self.sections[current_sec] = "\n".join(current_body)
                current_sec = m.group(1).strip()
                current_body = []
            else:
                if current_sec is not None:
                    current_body.append(line)
        if current_sec:
            self.sections[current_sec] = "\n".join(current_body)

    def check_sections(self):
        sec_names = list(self.sections.keys())
        missing = []
        for canonical, aliases in REQUIRED_SECTIONS:
            found = False
            for alias in aliases:
                for actual in sec_names:
                    if alias in actual:
                        found = True
                        break
                if found:
                    break
            if not found:
                missing.append(canonical)

        if missing:
            self.errors.append(f"缺少必填板块 ({len(missing)}个): {', '.join(missing)}")
        else:
            self.passed.append("12 大必填板块完整无缺（含独立的「教学思路」顶层设计板块）")

    def check_teaching_thinking(self):
        thinking_text = ""
        for name, text in self.sections.items():
            if any(k in name for k in ["教学思路", "设计思路", "教学构想"]):
                thinking_text = text
                break

        if not thinking_text:
            return

        missing_parts = []
        if not any(k in thinking_text for k in ["整体构想", "设计理念", "核心理念", "构想", "思路"]):
            missing_parts.append("整体构想/设计理念")
        if not any(k in thinking_text for k in ["主线", "问题链", "任务链", "架构图", "架构树", "主问题"]):
            missing_parts.append("主线架构图/问题链")
        if not any(k in thinking_text for k in ["难点", "障碍", "攻坚", "突破", "路线图", "转折"]):
            missing_parts.append("难点攻坚路线图")

        if missing_parts:
            self.warnings.append(f"「教学思路」建议补齐以下要素: {', '.join(missing_parts)}")
        else:
            self.passed.append("教学思路顶层设计完整: 包含整体构想、主线问题链架构与难点攻坚路径")

    def check_process_elements(self):
        process_text = ""
        for name, text in self.sections.items():
            if "教学过程" in name:
                process_text = text
                break

        if not process_text:
            self.errors.append("未找到「教学过程」板块，无法检查教学环节")
            return

        # 匹配各个环节，如 ### 环节一：情境导入（5 分钟）
        steps = re.split(r"(^###\s+.+$)", process_text, flags=re.MULTILINE)
        if len(steps) < 3:
            self.errors.append("「教学过程」未发现使用 ### 标明的分环节内容")
            return

        step_count = 0
        element_issues = []
        durations = []

        for i in range(1, len(steps), 2):
            header = steps[i].strip()
            body = steps[i+1] if i+1 < len(steps) else ""
            step_count += 1

            # 提取环节用时
            time_match = re.search(r"[（\(](\d+)\s*(?:分钟|min)[）\)]", header)
            if time_match:
                durations.append(int(time_match.group(1)))
            else:
                self.warnings.append(f"环节标题未标明具体用时: {header[:30]}...")

            # 检查四要素
            missing_elems = []
            for elem_name, patterns in FOUR_ELEMENTS:
                has_elem = any(re.search(p, body) for p in patterns)
                if not has_elem:
                    missing_elems.append(elem_name)
            if missing_elems:
                element_issues.append(f"{header.replace('###', '').strip()} 缺少: {', '.join(missing_elems)}")

        if element_issues:
            self.errors.append(f"教学过程存在环节四要素不全:\n    - " + "\n    - ".join(element_issues))
        else:
            self.passed.append(f"教学过程共 {step_count} 个环节，四要素（教师/学生/意图/评价）均齐全")

        # 检查时间合计
        if durations:
            total_step_time = sum(durations)
            # 搜索机动时间
            reserve_match = re.search(r"机动\s*(\d+)\s*分钟", process_text)
            reserve_time = int(reserve_match.group(1)) if reserve_match else 0

            total_with_reserve = total_step_time + reserve_time
            if total_with_reserve in (40, 45):
                self.passed.append(f"时间分配闭环: 各环节合计 {total_step_time} 分钟 + 机动 {reserve_time} 分钟 = {total_with_reserve} 分钟 (标准课时)")
            elif total_step_time in (35, 36, 37, 40, 41, 42) and reserve_time > 0:
                self.passed.append(f"时间分配合理: 各环节合计 {total_step_time} 分钟 + 机动 {reserve_time} 分钟 = {total_with_reserve} 分钟")
            else:
                self.warnings.append(f"课时用时核算: 各环节合计 {total_step_time} 分钟 (机动: {reserve_time} 分钟)，请核对是否符合 40 或 45 分钟标准课时要求")

    def check_objectives_and_alignment(self):
        obj_text = ""
        for name, text in self.sections.items():
            if "教学目标" in name:
                obj_text = text
                break

        table_text = ""
        for name, text in self.sections.items():
            if "对照表" in name or ("目标" in name and "评价" in name):
                table_text = text
                break

        if not obj_text:
            self.errors.append("未找到「教学目标」板块")
            return

        # 提取目标编号 T1, T2, T3...
        target_ids = re.findall(r"\b(T\d+)\b", obj_text)
        target_ids = sorted(list(set(target_ids)))

        if not target_ids:
            self.errors.append("「教学目标」中未发现标准编号 (T1, T2, T3…)，每条目标必须带有编号以供闭环索引")
        else:
            self.passed.append(f"教学目标编号规范: 包含 {', '.join(target_ids)}")

        # 检查空泛动词
        hollow_issues = []
        for line in obj_text.splitlines():
            line_str = line.strip()
            if not line_str.startswith("-") and not line_str.startswith("*"):
                continue
            # 检测是否含有空泛动词单独作为前缀谓语，例如 "能理解"、"理解……"、"掌握……"
            for verb in HOLLOW_VERBS:
                bad_pattern = rf"(?:[能会]|引导学生)?\s*{verb}[^，。；\n]{{0,15}}(?:概念|意义|定理|方法|思想|规律|内涵)?[，。；\n]"
                if re.search(bad_pattern, line_str):
                    if not any(good in line_str for good in ["说出", "写出", "算出", "比较", "判断", "指出", "解释", "证明", "设计", "梳理", "概括"]):
                        hollow_issues.append(f"目标表述疑似空泛 (包含'{verb}'): {line_str[:40]}...")

        if hollow_issues:
            self.warnings.append(f"教学目标含空泛动词建议优化:\n    - " + "\n    - ".join(hollow_issues))

        # 检查目标—活动—评价对照表
        if not table_text:
            self.errors.append("未找到「目标—活动—评价对照表」板块")
            return

        missing_in_table = []
        for tid in target_ids:
            if tid not in table_text:
                missing_in_table.append(tid)

        if missing_in_table:
            self.errors.append(f"对照表中遗漏目标: {', '.join(missing_in_table)} 未在对照表第一列找到落点")
        else:
            self.passed.append("目标闭环检查: 所有目标编号均已进入「目标—活动—评价对照表」")

        # 检查对照表单元格是否留空或只有占位符
        table_lines = [l for l in table_text.splitlines() if "|" in l and not l.strip().startswith("| ---")]
        empty_cell_found = False
        for line in table_lines[1:]:
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 4:
                for c in cells:
                    if c in ("", "……", "...", "　"):
                        empty_cell_found = True
                        break
        if empty_cell_found:
            self.warnings.append("对照表中存在未填写的占位符单元格（如 '……' 或空白），建议补全具体达标证据与评价方式")

    def check_buzzwords_and_formatting(self):
        found_buzzwords = []
        for word in BANNED_BUZZWORDS:
            if word in self.clean_content:
                found_buzzwords.append(word)

        if found_buzzwords:
            self.warnings.append(f"检测到非教师教学日常用词/商业套话: {', '.join(found_buzzwords)}，建议根据学科教学实际行为替换")

        # 检测 "闭环" 是否直接出现在教案正文
        if "闭环" in self.clean_content:
            self.warnings.append("正文中出现'闭环'一词；教案正文中建议使用教师惯用语'目标、过程、评价三者一致'或'前后呼应'")

        # 检测 Unicode 上下标，提示使用 LaTeX
        unicode_found = []
        for char, latex_equiv in UNICODE_SUBS_SUPS:
            if char in self.clean_content:
                unicode_found.append(f"'{char}' -> 建议改用 LaTeX '{latex_equiv}'")

        if unicode_found:
            self.warnings.append("公式字符规范: 检测到 Unicode 上下标字符，建议改用标准 LaTeX 格式:\n    - " + "\n    - ".join(unicode_found))

    def run_all_checks(self):
        if not self.load_file():
            return False
        self.split_sections()
        self.check_sections()
        self.check_teaching_thinking()
        self.check_process_elements()
        self.check_objectives_and_alignment()
        self.check_buzzwords_and_formatting()
        return len(self.errors) == 0

    def print_report(self):
        basename = os.path.basename(self.filepath)
        print("=" * 60)
        print(f"教案质量自检报告: {basename}")
        print("=" * 60)

        if self.passed:
            print("\n[√ 通过项]")
            for p in self.passed:
                print(f"  √ {p}")

        if self.warnings:
            print("\n[! 提示与建议 (WARN)]")
            for w in self.warnings:
                print(f"  ! {w}")

        if self.errors:
            print("\n[× 未通过错误项 (FAIL)]")
            for e in self.errors:
                print(f"  × {e}")

        print("\n" + "-" * 60)
        if not self.errors:
            print(f"自检结果: 审核通过 (EXIT CODE 0) - 共 {len(self.passed)} 项通过，{len(self.warnings)} 项温馨建议")
            print("-" * 60)
            return True
        else:
            print(f"自检结果: 未通过 (EXIT CODE 1) - 存在 {len(self.errors)} 项硬性指标未达标，请修改后重新检测")
            print("-" * 60)
            return False


def main():
    parser = argparse.ArgumentParser(description="教案自动化质量与结构自检工具")
    parser.add_argument("filepath", help="要检查的教案 Markdown 文件路径")
    parser.add_argument("--strict", action="store_true", help="严格模式（有警告即退出码1）")
    args = parser.parse_args()

    checker = LessonPlanChecker(args.filepath, strict=args.strict)
    success = checker.run_all_checks()
    checker.print_report()

    if not success or (args.strict and checker.warnings):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
