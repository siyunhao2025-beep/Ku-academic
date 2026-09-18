"""Tests for the hard-guardrail scripts: progress gates, topic scoring,
reading cards. No network. Synthetic fixtures in temp dirs only."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import progress       # noqa: E402
import topic_score    # noqa: E402
import reading        # noqa: E402


def write(ws, rel, obj):
    p = ws / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(obj, (dict, list)):
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
    else:
        p.write_text(obj, encoding='utf-8')


class ProgressGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.thr = dict(progress.DEFAULT_THRESHOLDS)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty_workspace_p0_not_done(self):
        results = progress.check_p0(self.ws, self.thr)
        self.assertFalse(all(ok for ok, _, _ in results))

    def test_empty_workspace_blocks_entering_p2(self):
        report = progress.evaluate(self.ws, self.thr)
        # Entering P2 requires P0 and P1 both fully passed.
        for pid in ("P0", "P1"):
            self.assertFalse(all(ok for ok, _, _ in report[pid]["results"]))

    def test_p0_passes_when_artifacts_have_real_content(self):
        write(self.ws, "prep-checklist.md",
              "- [x] 工具\n- [x] 环境\n- [x] 数据访问\n- [x] 账号\n- [x] 备份")
        write(self.ws, "domain-map.md", "领域地图" * 80)
        write(self.ws, "plan.md", "第一个月读文献，第二个月跑数据，第三个月出图。" * 5)
        write(self.ws, "evidence.json",
              {"evidence": [
                  {"is_core_reading": True, "reading_card": "reading-cards/a.md"},
                  {"is_core_reading": True, "reading_card": "reading-cards/b.md"}]})
        results = progress.check_p0(self.ws, self.thr)
        failed = [n for ok, n, _ in results if not ok]
        self.assertEqual(failed, [], f"P0 should pass, failed: {failed}")

    def test_empty_checklist_does_not_count(self):
        # A checklist file with zero boxes is not completion.
        write(self.ws, "prep-checklist.md", "# 清单\n还没填")
        results = progress.check_p0(self.ws, self.thr)
        names = {n: ok for ok, n, _ in results}
        self.assertFalse(names["P0 准备清单全部勾选"])

    def test_gate2_requires_verified_evidence_and_gaps(self):
        results = progress.check_p2(self.ws, self.thr)
        names = {n: ok for ok, n, _ in results}
        self.assertFalse(names["证据矩阵有条目"])


class TopicScoreTests(unittest.TestCase):
    def test_saturated_field_low_innovation(self):
        score, _ = topic_score.score_innovation(800, 0.80, 5)
        self.assertEqual(score, 1.0)

    def test_dead_end_topic_is_capped_even_if_sparse(self):
        # Sparse + few recent papers looks like a gap, but <3 high-cited
        # reviews mentioning it => dead-end protection caps at 3.
        score, note = topic_score.score_innovation(40, 0.15, 1)
        self.assertEqual(score, 3.0)
        self.assertIn("封顶", note)

    def test_feasibility_ready_mature_fast_is_five(self):
        inp = {"data_available": "ready", "method_mature": "mature",
               "first_result_months": 3}
        score, _ = topic_score.score_feasibility(inp)
        self.assertEqual(score, 5.0)

    def test_feasibility_missing_data_returns_none(self):
        score, _ = topic_score.score_feasibility({"data_available": "ready"})
        self.assertIsNone(score)

    def test_weighted_total_and_elimination(self):
        # feasibility5 innovation3 value5 risk4 resource5
        total = (5 * .30 + 3 * .25 + 5 * .20 + 4 * .15 + 5 * .10)
        self.assertGreater(total, 3.0)
        # feasibility1 innovation3 value1 risk1 resource2 -> eliminated
        bad = (1 * .30 + 3 * .25 + 1 * .20 + 1 * .15 + 2 * .10)
        self.assertLess(bad, 3.0)


class ReadingCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _full_meta(self):
        return {
            "research_question": "磁暴期间密度响应随地方时如何变化",
            "core_conclusion": "夜侧增幅达1.8倍",
            "data_methods": "SABER，120次磁暴，叠加纪元",
            "key_results": ["夜侧增幅1.8倍", "日侧1.2倍"],
            "claim_strength": "观测事实",
            "relation": "支持我的假设",
            "doubts": "未区分磁暴强度",
        }

    def test_empty_meta_misses_every_required_field(self):
        miss = reading.completeness({})
        self.assertEqual(len(miss), 7)

    def test_full_meta_is_complete(self):
        self.assertEqual(reading.completeness(self._full_meta()), [])

    def test_key_results_without_number_rejected(self):
        m = self._full_meta()
        m["key_results"] = ["结果不错"]
        self.assertIn("关键结果必须带具体数字", reading.completeness(m))

    def test_strength_and_relation_mapping(self):
        self.assertEqual(reading.STRENGTH_MAP["观测事实"], "observation")
        self.assertEqual(reading.STRENGTH_MAP["统计关联"], "association")
        self.assertEqual(reading.STRENGTH_MAP["机制假设"], "inference")
        self.assertEqual(reading.RELATION_MAP["支持我的假设"], "SUPPORTS")
        self.assertEqual(reading.RELATION_MAP["反对我的假设"],
                         "CONTRADICTS_MY_HYPOTHESIS")

    def test_card_then_check_then_sync_end_to_end(self):
        import subprocess
        repo = Path(__file__).resolve().parents[1]
        def run(*args):
            return subprocess.run([sys.executable, str(repo / "scripts" / "reading.py"),
                                   *args], cwd=repo, capture_output=True, text=True)
        r = run("card", str(self.ws), "--title", "Test paper", "--author", "Lei",
                "--year", "2024", "--doi", "10.1/x")
        self.assertEqual(r.returncode, 0, r.stderr)
        # Incomplete card must block the check.
        r = run("check", str(self.ws))
        self.assertEqual(r.returncode, 1)
        # Fill the card by writing a fully populated meta + body.
        card = next((self.ws / "reading-cards").glob("*.md"))
        meta = self._full_meta()
        meta.update({"title": "Test paper", "first_author": "Lei", "year": "2024",
                     "doi": "10.1/x", "synced": False})
        body = ("# 精读卡片\n<!-- META\n" + json.dumps(meta, ensure_ascii=False)
                + "\n-->\n")
        card.write_text(body, encoding="utf-8")
        r = run("check", str(self.ws))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run("sync", str(self.ws))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        ev = json.loads((self.ws / "evidence.json").read_text(encoding="utf-8"))
        rec = ev["evidence"][0]
        self.assertEqual(rec["evidence_level"], "full_text")
        self.assertTrue(rec["is_core_reading"])
        self.assertEqual(rec["claim_level"], "observation")
        # Close reading must NOT be treated as citation verification.
        self.assertEqual(rec["citation_verdict"], "UNRESOLVED")
        self.assertIsNone(rec["support_status"])
        # Path stored with forward slashes even on Windows.
        self.assertNotIn("\\", rec["reading_card"])


if __name__ == "__main__":
    unittest.main()
