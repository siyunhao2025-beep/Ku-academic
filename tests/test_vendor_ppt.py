"""Guards for the vendored PPT skill.

The vendored tree is third-party content. The 31 markdown files are preserved
verbatim except for three documented sibling-path fixes. In 2026-09 the
originally-missing executable toolchain was completed by vendoring the upstream
full implementation `YinsenWANG/feishu-ppt-skill` (MIT). These tests pin what
must stay true, and keep the honest declaration of what is still NOT provided
(namely: the old script-name files and the `lark-cli` runtime).
"""
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / 'skills' / 'ppt'

EXPECTED_MD = [
    'SKILL.md',
    'references/style/slide-taxonomy.md',
    'references/style/academic-research.md',
    'references/style/brand-storytelling.md',
    'references/style/business-pitch.md',
    'references/style/business-review.md',
    'references/style/fallback.md',
    'references/style/learning-and-training.md',
    'references/style/strategy-and-analysis.md',
    'references/style/technical-presentation.md',
    'references/xml/xml-schema-quick-ref.md',
    'references/xml/fonts.md',
    'references/xml/iconpark.md',
    'references/cli/lark-slides-create.md',
    'references/cli/lark-slides-add-slide.md',
    'references/cli/lark-slides-xml-presentations-get.md',
    'references/cli/lark-slides-replace-slide.md',
    'references/cli/lark-slides-update-slide.md',
    'references/cli/lark-slides-delete-slide.md',
    'references/cli/lark-slides-media-upload.md',
    'references/cli/lark-slides-screenshot.md',
    'references/cli/lark-slides-history.md',
    'references/cli/lark-slides-xml-presentation-slide-get.md',
    'references/cli/lark-slides-xml-presentation-slide-replace.md',
    'references/workflow/slides-editing.md',
    'references/workflow/template-editing.md',
    'references/workflow/error-handling.md',
    'references/workflow/validation-xml.md',
    'references/workflow/validation-visual.md',
    'references/workflow/windows-compat.md',
    'references/workflow/local-compat.md',
]

# Old script-name files referenced by the original merged doc dump. They are NOT
# created under these exact names; the upstream toolchain uses different command
# names (validate.py / xml2svg.py / ...). See MISSING_DEPENDENCIES.md mapping.
LEGACY_NAMES_NOT_SHIPPED = [
    'references/xml/slides_chart_demo.xml',
    'references/xml/slides_xml_schema_definition.xml',
    'scripts/xml_lint.py',
    'scripts/xml_inspect.py',
    'scripts/iconpark_tool.py',
    'scripts/color_contrast_check.py',
    'scripts/gen_svg_charts.py',
]

# Actually present after the 2026-09 upstream completion.
EXPECTED_VENDORED = [
    'scripts/preflight.py',
    'scripts/validate.py',
    'scripts/review_layout.py',
    'scripts/review_design.py',
    'scripts/xml2svg.py',
    'scripts/template_fields.py',
    'scripts/compare_slides.py',
    'scripts/sml.py',
    'templates/INDEX.md',
    'templates/fields.json',
    'templates/slide01.xml',
    'templates/slide51.xml',
    'tokens.yaml',
    'requirements.txt',
    'assets/Lucide-LICENSE',
    'tests/test_validators.py',
]


class VendorTreeTests(unittest.TestCase):
    def test_every_markdown_file_is_present(self):
        absent = [r for r in EXPECTED_MD if not (VENDOR / r).is_file()]
        self.assertEqual(absent, [])
        self.assertEqual(len(EXPECTED_MD), 31)

    def test_skill_frontmatter_kept(self):
        text = (VENDOR / 'SKILL.md').read_text(encoding='utf-8')
        self.assertTrue(text.startswith('---\n'))
        self.assertIn('name: ppt\n', text)
        self.assertIn('lark-cli', text)

    def test_missing_dependencies_page_exists(self):
        self.assertTrue((VENDOR / 'MISSING_DEPENDENCIES.md').is_file())

    def test_every_legacy_name_is_still_documented(self):
        page = (VENDOR / 'MISSING_DEPENDENCIES.md').read_text(encoding='utf-8')
        for artifact in LEGACY_NAMES_NOT_SHIPPED:
            self.assertIn(Path(artifact).name, page,
                          'legacy name not documented: %s' % artifact)

    def test_legacy_names_are_not_shipped_under_old_paths(self):
        for artifact in LEGACY_NAMES_NOT_SHIPPED:
            self.assertFalse((VENDOR / artifact).exists(),
                             'a legacy name was invented: %s' % artifact)

    def test_vendored_toolchain_is_present(self):
        missing = [p for p in EXPECTED_VENDORED if not (VENDOR / p).is_file()]
        self.assertEqual(missing, [], 'vendored PPT toolchain incomplete: %s' % missing)

    def test_lark_cli_requirement_is_documented(self):
        page = (VENDOR / 'MISSING_DEPENDENCIES.md').read_text(encoding='utf-8')
        self.assertIn('lark-cli', page)

    def test_no_root_relative_sibling_links_remain(self):
        """The three documented fixes: sibling files must link by bare filename."""
        offenders = []
        for name in ('references/workflow/local-compat.md',
                     'references/workflow/slides-editing.md',
                     'references/workflow/template-editing.md'):
            text = (VENDOR / name).read_text(encoding='utf-8')
            for target in re.findall(r'\[[^\]]*\]\(([^)\s]+)\)', text):
                if target.startswith('references/workflow/'):
                    offenders.append('%s -> %s' % (name, target))
        self.assertEqual(offenders, [])

    def test_sibling_links_resolve(self):
        workflow = VENDOR / 'references' / 'workflow'
        for name in ('local-compat.md', 'slides-editing.md', 'template-editing.md'):
            text = (workflow / name).read_text(encoding='utf-8')
            for target in re.findall(r'\[[^\]]*\]\(([^)\s]+)\)', text):
                if target.endswith('.md'):
                    self.assertTrue((workflow / target).is_file(),
                                    '%s links to absent %s' % (name, target))

    def test_vendor_tree_is_in_the_distribution_manifest(self):
        import json
        manifest = json.loads((ROOT / 'config/distribution-files.json').read_text(encoding='utf-8'))
        files = set(manifest['files'])
        for name in EXPECTED_MD + ['MISSING_DEPENDENCIES.md']:
            self.assertIn('skills/ppt/%s' % name, files)

    def test_readme_points_at_the_gap(self):
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('MISSING_DEPENDENCIES', readme.replace(' ', ''))


if __name__ == '__main__':
    unittest.main()
