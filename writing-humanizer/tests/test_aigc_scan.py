import sys
import json
import subprocess
import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "aigc_scan.py"
SPEC = importlib.util.spec_from_file_location("aigc_scan", MODULE_PATH)
aigc_scan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aigc_scan)


class ProtectedSpansTests(unittest.TestCase):
    def test_code_blocks_and_inline_code_are_masked(self):
        text = (
            "这里是正文陈述。\n"
            "```python\n"
            "# 这事儿搞定了，踩坑记录\n"
            "print('hello world——test')\n"
            "```\n"
            "代码行内调用 `test_搞定_踩坑` 结果正常。\n"
            "~~~bash\n"
            "# 另外的代码围栏: 这事儿搞定了，手感拉满\n"
            "~~~"
        )
        masked = aigc_scan.mask_protected_spans(text)
        result_colloquial = aigc_scan.count_colloquial_terms(masked)
        self.assertEqual(result_colloquial["count"], 0)

        scan_res = aigc_scan.scan(text)
        self.assertEqual(scan_res["colloquial"]["count"], 0)

    def test_latex_formulas_and_urls_are_masked(self):
        text = (
            "系统满足公式 $$E = mc^2$$ 以及行内参数 $x \\in [0, 1]$。\n"
            "同时支持 LaTeX 环境：\n"
            "\\[\n"
            "\\int_{0}^{1} f(x)dx = 1 + \\text{搞定}\n"
            "\\]\n"
            "以及行内括号公式 \\( a^2 + b^2 = c^2 \\text{手感} \\)。\n"
            "参考来源见 https://example.com/test--path-搞定。"
        )
        scan_res = aigc_scan.scan(text)
        self.assertEqual(scan_res["colloquial"]["count"], 0)

    def test_markdown_quote_blocks_are_masked(self):
        text = (
            "正文客观分析如下：\n"
            "> 专家原话引用：这事儿我们已经搞定了，手感拉满——绝无问题。\n"
            "以上为引文记录，正文继续展开论述。"
        )
        scan_res = aigc_scan.scan(text)
        self.assertEqual(scan_res["colloquial"]["count"], 0)
        self.assertEqual(scan_res["dash_density"]["over_limit_paras"], 0)

    def test_direct_quotes_are_masked(self):
        # 验证单行与跨行中文双引号、中文单引号、直角引号及英文双引号内的直接引语
        text = (
            '研究者指出：“这事儿已经搞定了，\n'
            '前期确实踩坑很多，但手感拉满。”\n'
            '专家在评审中直言：‘这事儿已经搞定了，手感拉满’。\n'
            '调查对象补充道：「我们踩坑很多，但绝不摆烂。」\n'
            'Foreign author said: "As an AI, this is totally fine."'
        )
        scan_res = aigc_scan.scan(text)
        self.assertEqual(scan_res["colloquial"]["count"], 0)
        self.assertFalse(scan_res["degeneration"]["has_issue"])

    def test_unclosed_quotes_do_not_leak_across_paragraphs(self):
        # 引语跨行受限于段落内，绝不能越过空行（空行代表段落切换）
        text = (
            "这是一个未闭合的“引语开头。\n\n"
            "这是下一段的普通正文，这事儿需要严肃对待。”"
        )
        scan_res = aigc_scan.scan(text)
        # 下一段的正文不应被引语遮罩，应当被检出口语词“这事儿”
        self.assertGreater(scan_res["colloquial"]["count"], 0)


class SentenceSplittingTests(unittest.TestCase):
    def test_ascii_period_and_abbreviations_do_not_falsely_split(self):
        text = "由 Smith et al. 提出的模型精度为 3.14 左右. 本文在此基础上进行了扩展。"
        sents = aigc_scan.split_sentences(text)
        self.assertEqual(len(sents), 2)
        self.assertIn("3.14", sents[0])
        self.assertIn("Smith et al.", sents[0])

    def test_short_valid_sentences_are_preserved(self):
        text = "系统启动。完成。退出。"
        sents = aigc_scan.split_sentences(text)
        self.assertEqual(sents, ["系统启动", "完成", "退出"])


class TemplatePatternTests(unittest.TestCase):
    def test_paired_contrast_templates_are_counted(self):
        text = (
            "这不是数据不足，而是采样范围太窄。"
            "模型结果不代表真实疗效。"
            "但至少提供了一个方向。"
        )
        result = aigc_scan.count_template_matches(text)
        self.assertEqual(result["count"], 3)


class NestedNumberTests(unittest.TestCase):
    def test_equation_math_and_citation_numbers_are_not_flagged(self):
        # 排除公式 (5)、运算表达式 (1)+(2)、文献引用 (1), (2)
        texts = [
            "如式 (5) 所示，该现象由文献 (2021) 首先发现。",
            "计算项由 (1)+(2) 共同给出，而文献 (1), (2) 也支持此结论。",
            "由公式 (1) 与 式(2) 可得结果。"
        ]
        for t in texts:
            result = aigc_scan.count_nested_numbers([t])
            self.assertEqual(result["sequences"], 0, f"误报了数学/引用编号: {t}")

    def test_real_nested_number_sequences_are_flagged(self):
        text = "该方案包含两项改进：（1）降低锁粒度；（2）引入本地缓存机制。"
        paragraphs = [text]
        result = aigc_scan.count_nested_numbers(paragraphs)
        self.assertGreater(result["sequences"], 0)
        self.assertEqual(result["count"], 2)


class ColonListTests(unittest.TestCase):
    def test_colon_with_semicolons_is_flagged(self):
        para = "核心指标如下：响应时间减少 20%；内存占用降低 15%；吞吐量提升 30%。"
        res = aigc_scan.count_colon_lists([para])
        self.assertGreater(res["count"], 0)

    def test_colon_with_commas_is_flagged(self):
        para = "该组件支持三种格式：JSON，YAML，以及 XML 格式。"
        res = aigc_scan.count_colon_lists([para])
        self.assertGreater(res["count"], 0)


class DashDensityTests(unittest.TestCase):
    def test_both_single_and_double_em_dashes_are_detected(self):
        para1 = "这是一个结论——它很重要——需要验证。"
        para2 = "另一个结论—非常关键—不可忽视。"
        res = aigc_scan.analyze_dash_density([para1, para2])
        self.assertEqual(res["over_limit_paras"], 2)
        self.assertEqual(res["total_dashes"], 4)

    def test_single_dash_per_paragraph_passes(self):
        para = "这是一个结论——它需要进一步验证。"
        res = aigc_scan.analyze_dash_density([para])
        self.assertEqual(res["over_limit_paras"], 0)


class DegenerationAndLeakageTests(unittest.TestCase):
    def test_full_meta_leakage_text_is_reported(self):
        text = "作为一个大语言模型，我无法完成该请求，此处省略500字。"
        sents = aigc_scan.split_sentences(text)
        result = aigc_scan.analyze_degeneration_and_leakage(text, sents)

        self.assertTrue(result["has_issue"])
        self.assertIn("作为一个大语言模型", result["leak_hits"])
        self.assertIn("我无法完成该请求", result["leak_hits"])
        self.assertTrue(any("此处省略" in h for h in result["leak_hits"]))

    def test_normal_vocabulary_is_not_falsely_flagged(self):
        # 严格杜绝“策略模型”、“误差略有差异”、“以下略”等正常中文词汇误判为占位符
        normal_texts = [
            "两个系统的计算误差略有差异，但总体可控。",
            "本文提出了一种自适应策略模型以提升效率。",
            "对于实验配置，以下简略说明主要环境参数。"
        ]
        for t in normal_texts:
            sents = aigc_scan.split_sentences(t)
            res = aigc_scan.analyze_degeneration_and_leakage(t, sents)
            self.assertFalse(res["has_issue"], f"正常词汇被误判为泄漏: {t}")
            self.assertEqual(len(res["leak_hits"]), 0)


class ThresholdAndCompositeScoreTests(unittest.TestCase):
    def test_dimension_weights_constant_coverage_and_sum(self):
        # 1. 验证脚本公开导出了 DIMENSION_WEIGHTS 模块常量
        self.assertTrue(hasattr(aigc_scan, "DIMENSION_WEIGHTS"))
        weights = aigc_scan.DIMENSION_WEIGHTS
        # 2. 验证覆盖全部 10 个维度
        expected_dims = {
            'template_phrases', 'passive_voice', 'burstiness', 'para_symmetry',
            'nested_numbers', 'colon_lists', 'punctuation', 'colloquial',
            'dash_density', 'degeneration'
        }
        self.assertEqual(set(weights.keys()), expected_dims)
        # 3. 验证权重精确求和等于 1.00，杜绝超标或缩水
        self.assertAlmostEqual(sum(weights.values()), 1.00, places=4)

    def test_all_ten_dimensions_triggered_sample_scores_exact_one(self):
        # 构造一个能真实同时触发全部 10 个维度的综合样本：
        # 1. 包含 >= 3 段且长度偏差 < 20% 的刻板对称段落 (para_symmetry)
        # 2. 包含 >= 5 句且长度标准差极小 (burstiness CV < 0.35)
        # 3. 模板句式命中 > 3 (template_phrases)
        # 4. 被动标记比例 > 0.4 (passive_voice)
        # 5. 嵌套编号序列 > 1 (nested_numbers)
        # 6. 冒号列举结构 > 1 (colon_lists)
        # 7. 句均逗号 > 2.5 (punctuation)
        # 8. 命中口语词 (colloquial)
        # 9. 每段破折号 > 1 (dash_density)
        # 10. 命中大模型自指与元信息 (degeneration)
        p1 = (
            "综上所述，数据被系统检测，核心指标如下：（1）降低时延；（2）提升吞吐，参数由算法完成——指标——确实稳。"
            "由此可见，模型经实验分析，方案表现如下：（1）精简内存；（2）加速收敛，这事儿搞定了，，，效果拉满。"
        )
        p2 = (
            "总而言之，样本被系统测定，核心指标如下：（1）降低时延；（2）提升吞吐，流程由算法完成——指标——确实稳。"
            "这不是问题，而是挑战，方案表现如下：（1）精简内存；（2）加速收敛，作为一个大语言模型，，，完全搞定。"
        )
        p3 = (
            "本研究通过数据验证，指标参数如下：（1）降低时延；（2）提升吞吐，系统经计算分析——指标——确实稳。"
            "在实验条件下，指标表现如下：（1）精简内存；（2）加速收敛，此处省略500字，，，真的强。"
        )
        full_sample = f"{p1}\n\n{p2}\n\n{p3}"

        scan_res = aigc_scan.scan(full_sample)
        # 验证 10 维全中
        self.assertEqual(scan_res["summary"]["triggered_dimensions"], 10)
        self.assertEqual(scan_res["summary"]["total_dimensions"], 10)
        for dim, triggered in scan_res["dimension_risks"].items():
            self.assertTrue(triggered, f"维度 {dim} 未能成功触发")

        # 验证得分严格等于 1.00，既不溢出也不欠缺
        self.assertEqual(scan_res["summary"]["composite_score"], 1.00)

    def test_threshold_logic_and_dimension_consistency(self):
        high_risk_text = "这方法真的强——手感拉满——作为一个AI，说白了就是好用——确实稳。"
        scan_res = aigc_scan.scan(high_risk_text)

        self.assertEqual(scan_res["summary"]["total_dimensions"], 10)
        self.assertIn("colon_lists", scan_res["dimension_risks"])
        self.assertEqual(len(scan_res["dimension_risks"]), 10)
        self.assertLessEqual(scan_res["summary"]["composite_score"], 1.0)
        self.assertGreater(scan_res["summary"]["composite_score"], 0.5)

    def test_clean_text_passes_threshold(self):
        clean_text = (
            "本文提出了一种基于自适应滑动窗口的边界样本检测方法。\n\n"
            "实验数据表明该方法在低信噪比条件下的平均准确率为 89.2%（P < 0.05）。\n\n"
            "这一结果支持原假设，但工业级放大表现仍有待后续验证。"
        )
        scan_res = aigc_scan.scan(clean_text)
        self.assertEqual(scan_res["summary"]["triggered_dimensions"], 0)
        self.assertEqual(scan_res["summary"]["composite_score"], 0.0)


class CliGateExecutionTests(unittest.TestCase):
    """验证 CLI 实际执行下的退出码与门禁行为"""
    def setUp(self):
        self.test_dir = Path(__file__).parent
        self.clean_file = self.test_dir / "_test_clean.txt"
        self.high_risk_file = self.test_dir / "_test_high_risk.txt"

        self.clean_file.write_text(
            "本文提出了一种基于自适应滑动窗口的边界样本检测方法。\n\n"
            "实验数据表明该方法在低信噪比条件下的平均准确率为 89.2%（P < 0.05）。\n\n"
            "这一结果支持原假设，但工业级放大表现仍有待后续验证。",
            encoding="utf-8"
        )
        self.high_risk_file.write_text(
            "这方法真的强——手感拉满——作为一个大语言模型，说白了就是好用——确实稳。",
            encoding="utf-8"
        )

    def tearDown(self):
        if self.clean_file.exists():
            self.clean_file.unlink()
        if self.high_risk_file.exists():
            self.high_risk_file.unlink()

    def test_cli_passes_clean_file_exit_zero(self):
        res = subprocess.run(
            [sys.executable, str(MODULE_PATH), str(self.clean_file), "--threshold", "0.5"],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("门禁判定: 🟢 通过 (PASSED)", res.stdout)

    def test_cli_blocks_high_risk_file_exit_one(self):
        res = subprocess.run(
            [sys.executable, str(MODULE_PATH), str(self.high_risk_file), "--threshold", "0.5"],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("门禁判定: 🔴 未通过 (EXCEEDED)", res.stdout)

    def test_cli_boundary_score_equals_threshold_exits_one(self):
        # 探测 high_risk_file 的准确分数
        scan_res = aigc_scan.scan(self.high_risk_file.read_text(encoding="utf-8"))
        exact_score = scan_res["summary"]["composite_score"]

        # 当 threshold 恰好等于 exact_score 时，判定为超标拦截（score >= threshold），退出码 1
        res = subprocess.run(
            [sys.executable, str(MODULE_PATH), str(self.high_risk_file), "--threshold", str(exact_score)],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("门禁判定: 🔴 未通过 (EXCEEDED)", res.stdout)

    def test_cli_json_mode_output_and_passed_field(self):
        res = subprocess.run(
            [sys.executable, str(MODULE_PATH), str(self.clean_file), "--threshold", "0.5", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8"
        )
        self.assertEqual(res.returncode, 0)
        data = json.loads(res.stdout)
        self.assertTrue(data["summary"]["passed"])
        self.assertEqual(data["summary"]["threshold"], 0.5)


if __name__ == "__main__":
    unittest.main()
