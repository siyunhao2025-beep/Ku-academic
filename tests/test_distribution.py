"""Standalone distribution checks. All demo content is explicitly non-scientific."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_distribution as build
import check_repository
import quickstart


class DistributionTests(unittest.TestCase):
    def test_repository_links_and_paths(self):
        self.assertEqual(check_repository.check(), [])

    def test_builds_are_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = build.build(root / "one")
            second = build.build(root / "two")
            self.assertEqual(first["sha256"], second["sha256"])

    def test_zip_has_single_skill_root_and_no_private_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            build.build(Path(directory))
            with zipfile.ZipFile(Path(directory) / build.ASSET) as archive:
                names = archive.namelist()
            self.assertTrue(all(n.startswith("research-mother/") for n in names))
            self.assertIn("research-mother/SKILL.md", names)
            self.assertFalse(any(n.endswith((".pdf", ".nc", ".pkl")) for n in names))
            self.assertFalse(any("vendor-cache/" in n or "/private/" in n for n in names))

    def test_existing_package_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            build.build(Path(directory))
            with self.assertRaises(FileExistsError):
                build.build(Path(directory))

    def test_missing_manifest_entry_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/distribution-files.json").write_text(json.dumps({"files": ["missing.md"]}))
            with self.assertRaises(ValueError):
                build.source_files(root)

    def test_traversal_manifest_entry_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "config").mkdir()
            (root / "config/distribution-files.json").write_text(json.dumps({"files": ["../private.txt"]}))
            with self.assertRaises(ValueError):
                build.source_files(root)

    def test_offline_demo_is_labelled_not_a_research_result(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "demo"
            report = quickstart.create_demo(target)
            self.assertEqual(report["status"], "demonstration_only")
            self.assertFalse(report["scientific_results_generated"])
            self.assertEqual(report["dependency_check"]["status"], "hashes_current")
            self.assertTrue((target / "INSTALLATION_DEMO.md").is_file())

    def test_existing_demo_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "demo"
            quickstart.create_demo(target)
            before = (target / "project.json").read_bytes()
            with self.assertRaises(FileExistsError):
                quickstart.create_demo(target)
            self.assertEqual((target / "project.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
