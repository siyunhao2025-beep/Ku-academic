"""Guards for the independently installed figures4papers Skill.

The upstream Skill and five references are CC BY-NC 4.0 adapted material.
These tests keep provenance, license separation, pinned demos, local scientific
guardrails, and distribution completeness from drifting.
"""
from pathlib import Path
import hashlib
import json
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "skills" / "scientific-figure-making"
COMMIT = "3c181f85e82c6f24948fcaaf3be6696102b41d8d"
LICENSE_SHA256 = "0afca3145596cd005f6f6ed977313ea31928094fc5b4aaabc21bb765ea369d09"
EXPECTED = {
    "SKILL.md",
    "SOURCE.md",
    "LICENSE",
    "agents/openai.yaml",
    "references/api.md",
    "references/common-patterns.md",
    "references/design-theory.md",
    "references/demos.md",
    "references/tutorials.md",
}


class ScientificFigureSkillTests(unittest.TestCase):
    def test_complete_bounded_tree_is_present(self):
        actual = {
            p.relative_to(VENDOR).as_posix()
            for p in VENDOR.rglob("*")
            if p.is_file()
        }
        self.assertEqual(actual, EXPECTED)
        self.assertFalse((VENDOR / "scripts").exists())
        self.assertFalse((VENDOR / "assets").exists())

    def test_independently_triggerable_skill_and_interface(self):
        skill = (VENDOR / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(skill.startswith("---\n"))
        self.assertIn("name: scientific-figure-making\n", skill)
        self.assertIn("figures4papers style", skill)
        self.assertIn("Mandatory Ku-academic policy gate", skill)
        interface = (VENDOR / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn('display_name: "Scientific Figure Making"', interface)
        self.assertIn("$scientific-figure-making", interface)
        self.assertIn("allow_implicit_invocation: true", interface)

    def test_full_license_and_mit_exclusion_are_preserved(self):
        payload = (VENDOR / "LICENSE").read_bytes()
        payload = payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        self.assertEqual(hashlib.sha256(payload).hexdigest(), LICENSE_SHA256)
        self.assertTrue(payload.startswith(b"Attribution-NonCommercial 4.0 International"))
        source = (VENDOR / "SOURCE.md").read_text(encoding="utf-8")
        self.assertIn(COMMIT, source)
        self.assertIn("CC BY-NC 4.0", source)
        self.assertIn("root MIT license expressly does not relicense", source)
        root_license = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("skills/scientific-figure-making/", root_license)
        self.assertIn("does not relicense", root_license)

    def test_demo_links_are_immutable(self):
        demos = (VENDOR / "references/demos.md").read_text(encoding="utf-8")
        self.assertNotIn("/tree/main/", demos)
        pinned = re.findall(
            r"https://github\.com/ChenLiu-1996/figures4papers/tree/"
            + COMMIT
            + r"/figure_[A-Za-z0-9_]+",
            demos,
        )
        self.assertEqual(len(pinned), 8)

    def test_local_guardrails_override_risky_upstream_patterns(self):
        skill = (VENDOR / "SKILL.md").read_text(encoding="utf-8")
        for phrase in (
            "source_data -> plot_script -> outputs -> caption_or_explanation",
            "Start quantitative bars at zero",
            "Do not hide category labels",
            "hue or alpha",
            "red/green semantics",
            "ultra-wide canvases as a reference-only",
            "radar and 3D figures as reference-only",
        ):
            self.assertIn(phrase, skill)
        refs = {
            p.name: p.read_text(encoding="utf-8")
            for p in (VENDOR / "references").glob("*.md")
        }
        self.assertEqual(len(refs), 5)
        self.assertTrue(all("Ku-academic" in text for text in refs.values()))
        self.assertNotIn("ax.set_ylim(0.7, 1.0)", refs["tutorials.md"])
        self.assertIn("ax.set_ylim(0, 1.0)", refs["tutorials.md"])
        self.assertIn("rejects alpha-only encoding", refs["design-theory.md"])
        self.assertIn("Quantitative bars keep a zero baseline", refs["common-patterns.md"])

    def test_root_route_and_upstream_registry_point_to_installed_skill(self):
        root_skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("skills/scientific-figure-making/SKILL.md", root_skill)
        lock = json.loads((ROOT / "config/upstream.lock.json").read_text(encoding="utf-8"))
        entry = next(x for x in lock["sources"] if x["id"] == "figures4papers")
        self.assertEqual(entry["commit"], COMMIT)
        self.assertEqual(entry["declared_license"], "CC BY-NC 4.0")
        self.assertEqual(
            entry["status"],
            "pinned_repository_skill_installed_not_host_installed",
        )
        self.assertEqual(entry["local_skill"], "skills/scientific-figure-making/SKILL.md")
        self.assertEqual(entry["local_license"], "skills/scientific-figure-making/LICENSE")

    def test_all_installed_files_and_guard_are_distributed(self):
        manifest = json.loads(
            (ROOT / "config/distribution-files.json").read_text(encoding="utf-8")
        )
        files = set(manifest["files"])
        for name in EXPECTED:
            self.assertIn("skills/scientific-figure-making/" + name, files)
        self.assertIn("tests/test_vendor_scientific_figure.py", files)

    def test_nested_relative_markdown_links_resolve(self):
        missing = []
        for page in VENDOR.rglob("*.md"):
            text = page.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", text):
                if target.startswith(("http://", "https://", "#")):
                    continue
                rel = target.split("#", 1)[0]
                if rel and not (page.parent / rel).resolve().is_file():
                    missing.append(f"{page.relative_to(VENDOR)} -> {target}")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
