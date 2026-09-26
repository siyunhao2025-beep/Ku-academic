from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WritingRevisionContractTests(unittest.TestCase):
    def test_defensive_revision_dispositions_are_auditable(self):
        text = (ROOT / "modules" / "writing-review.md").read_text(encoding="utf-8")
        for disposition in ("KEEP", "TIGHTEN", "REFRAME", "RELOCATE", "CUT", "QUERY"):
            self.assertIn(f"`{disposition}`", text)
        self.assertIn("location | function | disposition", text)
        self.assertIn("隐藏不利结果", text)

    def test_humanizing_is_not_driven_by_detector_quotas(self):
        active_paths = (
            ROOT / "modules" / "deai-writing.md",
            ROOT / "assets" / "deai-checklist.md",
            ROOT / "docs" / "USE_CASES.md",
        )
        active_text = "\n".join(path.read_text(encoding="utf-8") for path in active_paths)
        module = active_paths[0].read_text(encoding="utf-8")
        checklist = (ROOT / "assets" / "deai-checklist.md").read_text(encoding="utf-8")
        retired_claims = (
            "logit 恶化约 +0.72",
            "句子词数范围 | 12–55",
            "每 1000 字左右",
            "句式节奏是单项收益最大的干预",
            "找连续三个以上长度接近的句子",
            "实测只删词不重组会让 AI 分数变差",
            "长短交替，见第二节",
            "长短句交替 | 见第二节",
            "留两个，第三个改成不同结构",
        )
        for claim in retired_claims:
            self.assertNotIn(claim, active_text)
        self.assertIn("不设“噪声预算”", module)
        self.assertIn("只为了检测器分数", module)
        self.assertIn("不按配额机械处理", checklist)

    def test_active_entrypoints_frame_style_revision_around_readers(self):
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        ladder = (ROOT / "modules" / "polishing-ladder.md").read_text(encoding="utf-8")
        active_text = "\n".join((skill, readme, ladder))
        retired_claims = (
            "reduce AI traces in academic prose",
            "Reduce AI traces in academic prose",
            "先锁死数字，再改句式节奏",
            "连续多个长度接近的句子要重组",
            "长短句结合，不要全是长句，也不要全是短句",
            "本项目把两个最接近的来源融合",
        )
        for claim in retired_claims:
            self.assertNotIn(claim, active_text)
        self.assertIn("without targeting AI-detector scores", skill)
        self.assertIn("读者能否一次读清楚", readme)


if __name__ == "__main__":
    unittest.main()
