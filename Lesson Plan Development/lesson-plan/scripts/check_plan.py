#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_plan.py - 教案结构与教学质量自动化自检脚本

按照 lesson-plan 技能规范对 Markdown 教案进行全面自检：
1. 12 大标准板块完整性（锚定匹配 + 合法后缀拓展，杜绝复合标题欺骗与漏判）
2. 教学过程每个环节的四要素（教师活动、学生活动、设计意图、评价点）
3. 课时基准支持（支持 --period 参数与课题信息正向自动推断，涵盖 35/40/45/50 分钟，未检出时透明提示）
4. 各环节用时计算与课时/机动时间弹性匹配（支持环节内留白，防止重复加算）
5. 教学目标编号（T1, T2...）规范与「目标—活动—评价对照表」闭环落实
6. 教学目标中避免使用空泛动词（理解/掌握/了解/体会/认识）单独作谓语
7. 【教学质量核心质检】学情分析深度核查（拦截通用套话，50字实质门槛与前概念上下文校验）
8. 【教学质量核心质检】难点突破实操性质检（20字实质展开门槛与教学法具体支架校验，拦截无效多练）
9. 【教学质量核心质检】生本导向与活动时长（15字环节门槛，学生活动时长占50%对齐 quality-checklist）
10. 【教学质量核心质检】微观可开课度核查（检查教师具体提问话术与学生生成性预设）
11. 商业用语与套话检测（亮点、赋能、抓手、打造等）
12. 公式与字符规范（检测 Unicode 上下标，提醒使用标准 LaTeX）

退出码：
- 0: 全部必检项通过（可有轻微温馨建议；若开 --strict 则有警告即为 1）
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
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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

FLUFF_STUDENT_WORDS = [
    "基础较好", "基础一般", "基础薄弱", "参差不齐", "思维活跃",
    "兴趣浓厚", "积极性高", "已有一定认知", "已有一定生活经验", "好奇心强"
]

STUDENT_CONCEPT_ANCHORS = [
    "前概念", "迷思", "易错", "误区", "盲区", "卡点",
    "障碍", "定势", "混淆", "困难", "思维偏差", "认知冲突"
]

INEFFECTIVE_STRATEGIES = [
    "加强练习", "多做练习", "反复练习", "多加练习", "多练",
    "教师耐心讲解", "耐心讲解", "多做题", "反复刷题", "单纯练习", "教师讲授"
]

SCAFFOLD_ANCHORS = [
    "认知冲突", "对比实验", "反例", "直观", "模型", "问题阶梯",
    "问题链", "变式", "表格", "示意图", "图象", "动画", "任务驱动",
    "为什么难", "卡在哪", "认知障碍", "实物", "操作体验", "类比",
    "几何直观", "化归", "脚手架", "微课", "探究单", "记录单"
]

PASSIVE_ACTIVITIES = [
    "认真听讲", "仔细聆听", "做好笔记", "认真记笔记",
    "端正坐姿", "安静听讲", "听教师讲解", "听老师讲"
]

ACTIVE_VERBS = [
    "讨论", "推导", "计算", "互查", "辩论", "画图", "操作",
    "设计", "比较", "归纳", "汇报", "纠错", "梳理", "提出",
    "实验", "总结", "填表", "分析", "尝试", "合作", "探究"
]

UNICODE_SUBS_SUPS = [
    ("²", "$^2$"),
    ("³", "$^3$"),
    ("₁", "$_1$"),
    ("₂", "$_2$"),
    ("₃", "$_3$"),
    ("₄", "$_4$"),
]

# 允许的单板块合法名词后缀变体（如 课题信息表、板书设计图、教学思路架构 等）
VALID_SUFFIXES = r"(?:表|图|单|方案|说明|要求|安排|架构|概况|报告)?"


def clean_section_title(title):
    """去除标题前后的序号与修饰符，如 '一、', '1. ', '【', '】' 等"""
    t = re.sub(r"^(?:第[一二三四五六七八九十\d]+[部分板块章节]*[、.:：\s]+|[一二三四五六七八九十\d]+[、.:：\s]+|[【\[（\(])", "", title.strip())
    t = re.sub(r"[】\]）\)]$", "", t).strip()
    return t


def matches_alias(clean_title, alias):
    """校验标题是否精准匹配别名（全字匹配或以别名+合法单板块后缀结尾，杜绝包含多板块欺骗）"""
    if clean_title == alias:
        return True
    pattern = rf"^{re.escape(alias)}{VALID_SUFFIXES}(?:[\s:：(（【\[].*)?$"
    return bool(re.match(pattern, clean_title))


class LessonPlanChecker:
    def __init__(self, filepath, strict=False, period=None):
        self.filepath = filepath
        self.strict = strict
        self.cli_period = period
        self.target_period = period
        self.inferred_period = None
        self.errors = []
        self.warnings = []
        self.passed = []
        self.content = ""
        self.clean_content = ""
        self.sections = {}          # 去除注释和 > 旁注的正文
        self.raw_sections = {}      # 包含原始全部内容的板块
        self.step_bodies = []

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

        # 生成去除注释、【设计说明】旁注（包含多行引用 >）与代码块的内容，供文本规则检查
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
            # 过滤任何以 > 开头的引用说明与设计旁注
            if stripped.startswith(">"):
                continue
            clean_lines.append(line)
        self.clean_content = "\n".join(clean_lines)
        return True

    def split_sections(self):
        # 按照二级标题 ## 划分板块
        lines = self.content.splitlines()
        current_sec = None
        raw_body = []
        clean_body = []
        h1_candidates = []

        in_comment = False
        in_code = False

        for line in lines:
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
                in_code = not in_code

            # 记录是否有 # 一级标题充当板块
            m1 = re.match(r"^#\s+(.+)$", stripped)
            if m1 and not in_code:
                h1_title = m1.group(1).strip()
                for canonical, aliases in REQUIRED_SECTIONS:
                    if any(matches_alias(clean_section_title(h1_title), a) for a in aliases):
                        h1_candidates.append(h1_title)
                        break

            m2 = re.match(r"^##\s+(.+)$", stripped)
            if m2 and not in_code:
                if current_sec:
                    self.raw_sections[current_sec] = "\n".join(raw_body)
                    self.sections[current_sec] = "\n".join(clean_body)
                current_sec = m2.group(1).strip()
                raw_body = []
                clean_body = []
            else:
                if current_sec is not None:
                    raw_body.append(line)
                    if not stripped.startswith(">"):
                        clean_body.append(line)

        if current_sec:
            self.raw_sections[current_sec] = "\n".join(raw_body)
            self.sections[current_sec] = "\n".join(clean_body)

        if h1_candidates and (not self.sections or len(h1_candidates) >= 2):
            self.errors.append(
                f"检测到使用了 # 一级标题表示大板块（如 # {h1_candidates[0]} 等，共 {len(h1_candidates)} 个）。"
                "规范要求：所有 12 大板块必须使用 ## 二级标题，教学环节使用 ### 三级标题。"
            )

    def infer_period(self):
        """【修复 ①】增强课时识别：支持表格单元格与文本，推不出时透明报告"""
        if self.cli_period:
            self.target_period = self.cli_period
            self.passed.append(f"课时基准指定: 命令行已明确指定为 {self.cli_period} 分钟")
            return

        sec_info = ""
        for k, v in self.sections.items():
            clean_k = clean_section_title(k)
            if any(matches_alias(clean_k, a) for a in ["课题信息", "基本信息"]):
                lines = [line for line in v.splitlines() if not line.strip().startswith(">")]
                sec_info = "\n".join(lines)
                break

        if sec_info:
            # 1. 匹配表格单元格，如：| 课时 | 45分钟 |, | 课时 | 第1课时（40分钟） |, | 授课时长 | 35 min |
            # 允许跨越单元格分割线 '|' 以及单元格内任意前缀说明，使用 \d{2,3} 避免三位数被截断
            m_table = re.search(
                r"\|\s*(?:课时|时长|授课时长|时间)\s*\|[^|\r\n]*?[（\(【\[]?\s*(?<!\d)(\d{2,3})\s*(?:分钟|min)[）\)】\]]?[^|\r\n]*?\|",
                sec_info,
                re.IGNORECASE
            )
            if m_table:
                val = int(m_table.group(1))
                if 20 <= val <= 120:
                    self.inferred_period = val
                    self.target_period = val
                    self.passed.append(f"课时基准识别: 从课题信息表格推断课时为 {val} 分钟")
                    return

            # 2. 匹配非表格的文本定义，如：课时：40分钟, 课时 40 min, 授课时长: 35分钟
            m_text = re.search(
                r"(?:课时|时长|授课时长)[：:\s]+[^|\r\n]*?[（\(【\[]?\s*(?<!\d)(\d{2,3})\s*(?:分钟|min)[）\)】\]]?",
                sec_info,
                re.IGNORECASE
            )
            if m_text:
                val = int(m_text.group(1))
                if 20 <= val <= 120:
                    self.inferred_period = val
                    self.target_period = val
                    self.passed.append(f"课时基准识别: 从课题信息正文推断课时为 {val} 分钟")
                    return

            # 3. 匹配课题信息内出现的典型独立课时数字（如 35/40/45/50/60/90/120 分钟）
            m_indep = re.search(r"[（\(【\[\s|]*\b(35|40|45|50|60|90|120)\s*(?:分钟|min)[）\)】\]\s|]*", sec_info, re.IGNORECASE)
            if m_indep:
                val = int(m_indep.group(1))
                self.inferred_period = val
                self.target_period = val
                self.passed.append(f"课时基准识别: 从课题信息匹配到课时长度为 {val} 分钟")
                return

        # 4. 未能推断出具体分钟数时，绝不静默，明确在报告中提示兜底模式
        self.passed.append("课时基准核算: 课题信息中未检出具体课时分钟数，默认按 40/45 分钟标准课时兜底核算")

    def check_sections(self):
        sec_names = list(self.sections.keys())
        missing = []
        claimed_actuals = set()

        for canonical, aliases in REQUIRED_SECTIONS:
            matched_actual = None
            for alias in aliases:
                for actual in sec_names:
                    if actual in claimed_actuals:
                        continue
                    clean_actual = clean_section_title(actual)
                    if matches_alias(clean_actual, alias):
                        matched_actual = actual
                        break
                if matched_actual:
                    claimed_actuals.add(matched_actual)
                    break
            if not matched_actual:
                missing.append(canonical)

        if missing:
            self.errors.append(f"缺少必填板块 ({len(missing)}个): {', '.join(missing)}")
        else:
            self.passed.append("12 大必填板块完整无缺（含独立的「教学思路」顶层设计板块，锚定校验通过）")

    def check_teaching_thinking(self):
        thinking_text = ""
        for name, text in self.sections.items():
            clean_name = clean_section_title(name)
            if any(matches_alias(clean_name, a) for a in ["教学思路", "设计思路", "教学构想", "教学整体构想"]):
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

    def check_student_profile_depth(self):
        """【教学质量核查 ②】学情分析深度核查：设置50字实质门槛与前概念上下文校验，杜绝堆词作弊"""
        profile_text = ""
        for name, text in self.sections.items():
            clean_name = clean_section_title(name)
            if matches_alias(clean_name, "学情分析"):
                profile_text = text
                break

        if not profile_text:
            return

        p_chars = len(re.findall(r"[\u4e00-\u9fff]", profile_text))

        # 检查泛化套话
        fluff_found = [w for w in FLUFF_STUDENT_WORDS if w in profile_text]
        if fluff_found:
            self.warnings.append(
                f"学情分析出现泛化套话: 【{', '.join(fluff_found)}】。学情应指向本课具体概念掌握情况与认知基础，避免通用泛化表述"
            )

        # 检查实质长度门槛（≥50汉字）
        if p_chars < 50:
            self.warnings.append(
                f"学情分析内容过简（仅 {p_chars} 字，未达到 50 字实质分析门槛），缺少对已有认知基础、具体前概念与思维卡点的详实展开"
            )
            return

        # 检查前概念锚点词是否具备上下文（所在语句纯汉字字数 ≥ 12 字，防止只写“前概念。”堆词作弊）
        sentences = [s.strip() for s in re.split(r"[。；;\n]", profile_text) if s.strip()]
        valid_anchor_sentences = []
        for s in sentences:
            if any(k in s for k in STUDENT_CONCEPT_ANCHORS):
                if len(re.findall(r"[\u4e00-\u9fff]", s)) >= 12:
                    valid_anchor_sentences.append(s)

        if not valid_anchor_sentences:
            self.warnings.append(
                "学情分析深度不足: 未检测到关于本课具体「前概念 / 认知迷思 / 易错点 / 思维障碍」的实质描述语句（需结合具体概念深入展开，不可仅罗列孤立词汇）"
            )
        else:
            self.passed.append(f"学情分析深度达标: 包含详实的学生前概念与认知障碍剖析（有效文本 {p_chars} 字）")

    def check_difficulty_breakthrough_quality(self):
        """【教学质量核查 ②】难点突破实操性质检：设置20字实质展开门槛与教学法支架校验，拦截假突破"""
        diff_text = ""
        for name, text in self.sections.items():
            clean_name = clean_section_title(name)
            if any(matches_alias(clean_name, a) for a in ["教学重点与难点", "教学重难点", "教学重点和难点"]):
                diff_text = text
                break

        if not diff_text:
            return

        # 提取突破策略标签后的具体描述内容
        strat_match = re.search(
            r"(?:突破策略|突破方法|突破手段|突破路径|突破支架|化解策略)[：:\s]*(.*?)(?=(?:\n\s*-\s*\*\*|\n\s*##|$))",
            diff_text,
            re.DOTALL
        )

        if not strat_match:
            self.warnings.append("教学难点缺少明确的突破策略: 难点必须明确设立「突破策略/化解路径」")
            return

        strat_content = strat_match.group(1).strip()
        strat_chars = len(re.findall(r"[\u4e00-\u9fff]", strat_content))

        # 实质长度门槛（≥20汉字，杜绝只写“突破策略：反例”这类极短堆词）
        if strat_chars < 20:
            self.warnings.append(
                f"教学难点突破策略描述过简（仅 {strat_chars} 字，如只有'{strat_content[:15]}'），未达到 20 字实质门槛，必须详写卡点成因与具体教学法支架"
            )
            return

        bad_found = [w for w in INEFFECTIVE_STRATEGIES if w in strat_content]
        has_concrete_scaffold = any(k in strat_content for k in SCAFFOLD_ANCHORS)

        if bad_found:
            self.warnings.append(
                f"教学难点突破策略疑似无效套话: 检测到 【{', '.join(bad_found)}】。突破策略应为具体的教学支架（如对比实验、具象化模型、反例引导、图表支架等），而非简单多练多讲"
            )

        if not has_concrete_scaffold:
            self.warnings.append(
                "教学难点突破手段偏空泛: 虽有突破说明，但未检测到具体的教学法支架（如反例、对比实验、模型、问题阶梯、具象化图表等）"
            )
        else:
            self.passed.append(f"教学难点设计达标: 突破策略详实（{strat_chars} 字），包含具体教学法化解支架与认知破局路径")

    def check_process_elements(self):
        process_text = ""
        for name, text in self.sections.items():
            clean_name = clean_section_title(name)
            if matches_alias(clean_name, "教学过程"):
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
        step_headers = []
        self.step_bodies = []

        for i in range(1, len(steps), 2):
            header = steps[i].strip()
            body = steps[i+1] if i+1 < len(steps) else ""
            step_count += 1
            step_headers.append(header)
            self.step_bodies.append((header, body))

            # 提取环节用时（宽松正则：支持 (约5min), 【10分钟】, 5~8分钟区间, 无括号等）
            time_match = re.search(
                r"[（\(\[【]?\s*(?:约|共|建议|用时)?\s*(\d+)(?:\s*[-~～至]\s*(\d+))?\s*(?:分钟|min|mins)[）\)\]】]?",
                header,
                re.IGNORECASE
            )
            if time_match:
                if time_match.group(2):
                    durations.append(int(time_match.group(2)))
                else:
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

        # 检查时间合计与课时核算
        if durations:
            total_step_time = sum(durations)
            has_reserve_step = any(re.search(r"机动|预留", h) for h in step_headers)

            reserve_match = re.search(r"(?:机动|预留)\s*[:：]?\s*(\d+)\s*分钟", process_text)
            reserve_text_time = int(reserve_match.group(1)) if reserve_match else 0

            reserve_time = 0 if has_reserve_step else reserve_text_time
            effective_total = total_step_time + reserve_time

            period_info_str = f"（目标课时: {self.target_period} 分钟）" if self.target_period else ""

            if self.target_period:
                if effective_total == self.target_period:
                    self.passed.append(
                        f"时间分配闭环: 各环节合计 {total_step_time} 分钟" +
                        (f" + 机动 {reserve_time} 分钟" if reserve_time > 0 else "") +
                        f" = {effective_total} 分钟 {period_info_str}"
                    )
                elif (self.target_period - 5) <= total_step_time <= self.target_period:
                    self.passed.append(
                        f"时间分配合理: 各环节合计 {total_step_time} 分钟，已按规范预留 {self.target_period - total_step_time} 分钟弹性机动 {period_info_str}"
                    )
                else:
                    self.warnings.append(
                        f"课时用时核算: 各环节合计 {total_step_time} 分钟 (机动: {reserve_time} 分钟)，与目标课时 {self.target_period} 分钟偏差较大（规范建议环节用时为 {self.target_period - 5}～{self.target_period} 分钟）"
                    )
            else:
                if effective_total in (40, 45):
                    self.passed.append(
                        f"时间分配闭环: 各环节合计 {total_step_time} 分钟" +
                        (f" + 机动 {reserve_time} 分钟" if reserve_time > 0 else "") +
                        f" = {effective_total} 分钟 (标准课时)"
                    )
                elif (35 <= total_step_time <= 40) or (40 <= total_step_time <= 45):
                    self.passed.append(
                        f"时间分配合理: 各环节合计 {total_step_time} 分钟 (机动: {reserve_time} 分钟)，符合 40 或 45 分钟标准课时规范"
                    )
                else:
                    self.warnings.append(
                        f"课时用时核算: 各环节合计 {total_step_time} 分钟 (机动: {reserve_time} 分钟)，请核对是否符合 40 或 45 分钟标准课时要求"
                    )

    def check_student_agency_and_ratio(self):
        """【教学质量核查 ②】生本导向与学生活动时长核查：对齐 quality-checklist 第 10 条（时长≥50%），加设15字完整度门槛"""
        if not self.step_bodies:
            return

        total_student_chars = 0
        total_teacher_chars = 0
        total_explicit_mins = 0
        total_estimated_mins = 0.0
        passive_step_issues = []
        short_activity_issues = []

        # 确定课堂总基准时长
        lesson_period = self.target_period if self.target_period else 45

        for header, body in self.step_bodies:
            s_match = re.search(r"(?:\*\*学生活动\*\*|学生活动[：:])\s*(.*?)(?=(?:\n\s*-\s*\*\*|$))", body, re.DOTALL)
            t_match = re.search(r"(?:\*\*教师活动\*\*|教师活动[：:])\s*(.*?)(?=(?:\n\s*-\s*\*\*|$))", body, re.DOTALL)

            s_text = s_match.group(1).strip() if s_match else ""
            t_text = t_match.group(1).strip() if t_match else ""

            s_chars = len(re.findall(r"[\u4e00-\u9fff]", s_text))
            t_chars = len(re.findall(r"[\u4e00-\u9fff]", t_text))

            total_student_chars += s_chars
            total_teacher_chars += t_chars

            step_title = header.replace("###", "").strip()

            # 1. 环节活动实质门槛：单环节教师活动与学生活动均需 ≥ 15 汉字（杜绝只写“讲”等堆词作弊）
            if t_chars < 15:
                short_activity_issues.append(f"{step_title}: 教师活动描述过简（仅 {t_chars} 字），缺少具体发问与主导细节")
            if s_chars < 15:
                short_activity_issues.append(f"{step_title}: 学生活动描述过简（仅 {s_chars} 字），缺少实质性探究动作")

            # 2. 检查纯被动应答行为
            if s_text:
                has_passive = any(p in s_text for p in PASSIVE_ACTIVITIES)
                has_active = any(a in s_text for a in ACTIVE_VERBS)
                if has_passive and not has_active:
                    passive_step_issues.append(f"{step_title}: 仅有被动听讲/记笔记，缺乏主动思维动作")

            # 3. 提取环节总用时
            tm = re.search(r"[（\(\[【]?\s*(\d+)\s*(?:分钟|min)", header)
            step_duration = int(tm.group(1)) if tm else 5

            # 4. 显式学生活动用时提取
            # 兼容：- **学生活动（25分钟）**：、- **学生活动**：（25分钟）、- **学生活动**【25分钟】、正文中用时25分钟等
            sm = re.search(
                r"(?:\*\*学生活动[^\*]*\*\*|学生活动)[：:\s]*[（\(【\[]?\s*(?:约|用时)?\s*(\d+)\s*(?:分钟|min)[）\)】\]]?",
                body
            )
            if not sm:
                sm = re.search(r"[（\(【\[]\s*(?:约|用时)?\s*(\d+)\s*(?:分钟|min)[）\)】\]]", s_text[:60])
            if not sm:
                sm = re.search(r"(?:用时|探究|讨论|练习|操作|思考|独立完成|实验)\s*[:：]?\s*(\d+)\s*(?:分钟|min)", s_text)

            explicit_min = None
            if sm and int(sm.group(1)) <= step_duration:
                explicit_min = int(sm.group(1))

            if explicit_min is not None:
                total_explicit_mins += explicit_min
            else:
                # 未显式标注时的粗略估算值（仅供提示参考，绝不凭估算发放 PASS）
                if s_chars + t_chars > 0:
                    weight = min(0.85, max(0.15, s_chars / (s_chars + t_chars)))
                else:
                    weight = 0.5
                total_estimated_mins += (step_duration * weight)

        if short_activity_issues:
            self.warnings.append(
                f"教学环节存在活动内容过简（未达到 15 字实质门槛）:\n    - " + "\n    - ".join(short_activity_issues)
            )

        if passive_step_issues:
            self.warnings.append(
                f"教学环节存在纯被动学习设计:\n    - " + "\n    - ".join(passive_step_issues)
            )

        # 【核心定性】：将显式标注时长作为生本比达标的必要条件，杜绝堆词作弊
        if total_explicit_mins > 0:
            explicit_ratio = total_explicit_mins / lesson_period
            if explicit_ratio >= 0.45:
                self.passed.append(
                    f"课堂生本导向达标: 显式标注学生活动总时长 {int(total_explicit_mins)} 分钟（占总课时 {explicit_ratio:.1%}，符合 quality-checklist 第 10 条学生活动时长≥50%规范）"
                )
            else:
                self.warnings.append(
                    f"课堂生本度偏低: 显式标注学生活动总时长仅 {int(total_explicit_mins)} 分钟（占总课时 {explicit_ratio:.1%}，低于 50% 门槛），建议在核心探究与练习环节增加学生活动时长"
                )
        else:
            # 未显式标注用时，绝不给 PASS，一律降级为 WARN 提示明确标注
            est_m = int(round(total_estimated_mins))
            est_ratio = est_m / lesson_period
            self.warnings.append(
                f"学生活动时长未显式标注: 虽按文本占比粗略估算约 {est_m} 分钟（占总课时约 {est_ratio:.1%}），但各环节未显式标注学生活动用时（如'学生活动（25分钟）：……'）。为落实 quality-checklist 第 10 条（学生活动时长≥50%），建议在核心探究/练习环节中显式注明学生活动具体用时"
            )

    def check_classroom_actionability(self):
        """【教学质量核查】微观可开课度核查（发问话术与生成性预设）"""
        if not self.step_bodies:
            return

        all_teacher_text = ""
        all_student_text = ""
        all_eval_text = ""

        for header, body in self.step_bodies:
            t_match = re.search(r"(?:\*\*教师活动\*\*|教师活动[：:])\s*(.*?)(?=(?:\n\s*-\s*\*\*|$))", body, re.DOTALL)
            s_match = re.search(r"(?:\*\*学生活动\*\*|学生活动[：:])\s*(.*?)(?=(?:\n\s*-\s*\*\*|$))", body, re.DOTALL)
            e_match = re.search(r"(?:\*\*评价点\*\*|评价点[：:])\s*(.*?)(?=(?:\n\s*-\s*\*\*|$))", body, re.DOTALL)

            if t_match:
                all_teacher_text += t_match.group(1) + "\n"
            if s_match:
                all_student_text += s_match.group(1) + "\n"
            if e_match:
                all_eval_text += e_match.group(1) + "\n"

        # 检查核心发问（提问句）
        has_questions = bool(re.search(r"[“\"].*?[？\?][”\"]|[？\?]", all_teacher_text))
        if not has_questions:
            self.warnings.append(
                "微观可开课度提示: 教师活动中未检测到具体提问话术（未见？号或引语提问），建议写明具体的引导发问与追问细节"
            )
        else:
            self.passed.append("微观教学设计详实: 教师活动包含具体的主干提问与追问话术")

        # 检查学生生成反应与错误预设
        has_presupposition = any(k in (all_student_text + all_teacher_text) for k in [
            "预设", "预期", "预想", "可能出现", "可能回答", "典型错误", "易错回答",
            "学生若答", "若学生", "学生会", "有学生会", "卡壳", "错答", "卡点"
        ])
        if not has_presupposition:
            self.warnings.append(
                "生成性预设不足: 教学过程建议补充「预期学生回答」或「可能出现的典型错误/思维卡点」，防范课堂推进受阻"
            )
        else:
            self.passed.append("教学过程包含学生生成性回答与典型卡点预设")

        # 检查评价点是否过空
        vague_eval_words = ["评价学生表现", "观察学生态度", "看学生是否认真", "考查学生积极性", "了解学生掌握情况"]
        vague_found = [w for w in vague_eval_words if w in all_eval_text]
        if vague_found:
            self.warnings.append(
                f"过程性评价建议具体化: 检测到抽象评价表述 【{', '.join(vague_found)}】。评价点应写明具体的达标证据（如能说出/能写出/正确率/互查证据）"
            )
        else:
            self.passed.append("过程性评价指标清晰: 环节评价点均落实到具体观察点与达标证据")

    def check_objectives_and_alignment(self):
        obj_text = ""
        for name, text in self.sections.items():
            clean_name = clean_section_title(name)
            if matches_alias(clean_name, "教学目标"):
                obj_text = text
                break

        table_text = ""
        for name, text in self.sections.items():
            clean_name = clean_section_title(name)
            if any(matches_alias(clean_name, a) for a in [
                "目标—活动—评价对照表", "目标-活动-评价对照表", "目标、活动、评价对照表", "目标—活动—评价三栏对照表"
            ]):
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
            self.warnings.append(f"检测到非教师日常用语/商业套话: 【{', '.join(found_buzzwords)}】，建议根据学科教学实际替换")

        if "闭环" in self.clean_content:
            self.warnings.append("正文中出现'闭环'一词；教案正文中建议使用教师惯用语'目标、过程、评价三者一致'或'前后呼应'")

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
        self.infer_period()
        self.check_sections()
        self.check_teaching_thinking()
        self.check_student_profile_depth()
        self.check_difficulty_breakthrough_quality()
        self.check_process_elements()
        self.check_student_agency_and_ratio()
        self.check_classroom_actionability()
        self.check_objectives_and_alignment()
        self.check_buzzwords_and_formatting()
        return len(self.errors) == 0

    def print_report(self):
        """【修复 ③】将判据提取为统一变量，严格模式下的退出码与报告打印保持完全一致"""
        basename = os.path.basename(self.filepath)
        print("=" * 65)
        print(f"教案质量与教学法自检报告: {basename}")
        print("=" * 65)

        if self.passed:
            print("\n[√ 通过项 (PASS)]")
            for p in self.passed:
                print(f"  √ {p}")

        if self.warnings:
            print("\n[! 教学质量深度建议 (WARN)]")
            for w in self.warnings:
                print(f"  ! {w}")

        if self.errors:
            print("\n[× 未通过硬性错误项 (FAIL)]")
            for e in self.errors:
                print(f"  × {e}")

        # 判定是否整体通过（严格模式下有警告即不通过）
        is_passed = (len(self.errors) == 0) and not (self.strict and len(self.warnings) > 0)
        exit_code = 0 if is_passed else 1

        print("\n" + "-" * 65)
        if is_passed:
            print(f"自检结果: 审核通过 (EXIT CODE {exit_code}) - 共 {len(self.passed)} 项指标达标，{len(self.warnings)} 项教学优化建议")
        else:
            reasons = []
            if self.errors:
                reasons.append(f"{len(self.errors)} 项硬性指标未达标")
            if self.strict and self.warnings:
                reasons.append(f"严格模式触发（存在 {len(self.warnings)} 项警告提示）")
            print(f"自检结果: 未通过 (EXIT CODE {exit_code}) - 存在 {', '.join(reasons)}，请修改后重新检测")
        print("-" * 65)
        return is_passed


def main():
    parser = argparse.ArgumentParser(description="教案自动化质量与结构自检工具")
    parser.add_argument("filepath", help="要检查的教案 Markdown 文件路径")
    parser.add_argument("--strict", action="store_true", help="严格模式（有警告即退出码1）")
    parser.add_argument("--period", type=int, default=None, help="指定课时长度（分钟，如 35/40/45/50，默认自适应或从教案推断）")
    args = parser.parse_args()

    checker = LessonPlanChecker(args.filepath, strict=args.strict, period=args.period)
    checker.run_all_checks()
    is_passed = checker.print_report()

    sys.exit(0 if is_passed else 1)


if __name__ == "__main__":
    main()
