"""Tests for the stdlib-only OOXML writers. No dependency, no Office needed:
validity is checked by reopening the package and parsing every XML part."""
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ooxml


BLOCKS = [
    {'kind': 'h1', 'text': '标题一'},
    {'kind': 'p', 'text': '正文段落'},
    {'kind': 'bullet', 'text': '要点'},
    {'kind': 'numbered', 'marker': '1.', 'text': '步骤'},
    {'kind': 'quote', 'text': '引用'},
    {'kind': 'callout', 'label': '注意', 'text': '提示内容'},
    {'kind': 'table', 'rows': [['列A', '列B'], ['1', '2']]},
    {'kind': 'pagebreak'},
    {'kind': 'h2', 'text': '标题二'},
]


class HelpersTests(unittest.TestCase):
    def test_escaping_covers_xml_specials(self):
        self.assertEqual(ooxml.esc('a<b>&"c'), 'a&lt;b&gt;&amp;&quot;c')

    def test_mm_conversions(self):
        self.assertEqual(ooxml.mm_to_emu(25.4), 914400)
        self.assertEqual(ooxml.mm_to_twips(25.4), 1440)

    def test_slug_keeps_cjk_and_drops_junk(self):
        self.assertEqual(ooxml.slug('海报 Poster! v2'), '海报-Poster-v2')
        self.assertEqual(ooxml.slug(''), 'untitled')


class DocxTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_package_is_well_formed(self):
        target = self.dir / 'a.docx'
        ooxml.write_docx(BLOCKS, target, title='讲解版')
        self.assertEqual(ooxml.verify(target)['problems'], [])

    def test_required_parts_present(self):
        target = self.dir / 'b.docx'
        ooxml.write_docx(BLOCKS, target)
        with zipfile.ZipFile(target) as z:
            names = set(z.namelist())
        for part in ('[Content_Types].xml', '_rels/.rels', 'word/document.xml',
                     'word/_rels/document.xml.rels', 'word/styles.xml'):
            self.assertIn(part, names)

    def test_content_and_escaping_survive(self):
        target = self.dir / 'c.docx'
        ooxml.write_docx([{'kind': 'p', 'text': 'a<b>&c'}], target, title='T')
        with zipfile.ZipFile(target) as z:
            doc = z.read('word/document.xml').decode('utf-8')
        self.assertIn('a&lt;b&gt;&amp;c', doc)
        self.assertNotIn('<w:tbl>', doc)

    def test_table_block_emits_table(self):
        target = self.dir / 'd.docx'
        ooxml.write_docx([{'kind': 'table', 'rows': [['a', 'b']]}], target)
        with zipfile.ZipFile(target) as z:
            doc = z.read('word/document.xml').decode('utf-8')
        self.assertIn('<w:tbl>', doc)
        self.assertIn('insideH', doc)

    def test_never_overwrites(self):
        target = self.dir / 'e.docx'
        ooxml.write_docx(BLOCKS, target)
        with self.assertRaises(FileExistsError):
            ooxml.write_docx(BLOCKS, target)

    def test_output_is_deterministic(self):
        a, b = self.dir / 'x.docx', self.dir / 'y.docx'
        ooxml.write_docx(BLOCKS, a, title='T')
        ooxml.write_docx(BLOCKS, b, title='T')
        self.assertEqual(a.read_bytes(), b.read_bytes())

    def test_title_required_error_is_clear(self):
        with self.assertRaises(ValueError):
            ooxml.build_docx_from_spec({'blocks': []}, self.dir / 'z.docx')


class PptxTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.spec = {
            'width_emu': ooxml.mm_to_emu(841),
            'height_emu': ooxml.mm_to_emu(1189),
            'background': 'FFFFFF',
            'boxes': [{
                'name': 'title',
                'x': 0, 'y': 0, 'cx': ooxml.mm_to_emu(400), 'cy': ooxml.mm_to_emu(100),
                'fill': '1B1035',
                'paragraphs': [{'text': '标题', 'size': 30, 'bold': True, 'color': 'FFFFFF'}],
            }],
        }

    def tearDown(self):
        self._tmp.cleanup()

    def test_package_is_well_formed(self):
        target = self.dir / 'a.pptx'
        ooxml.write_pptx_slide(self.spec, target)
        self.assertEqual(ooxml.verify(target)['problems'], [])

    def test_standard_pptx_part_set(self):
        target = self.dir / 'b.pptx'
        ooxml.write_pptx_slide(self.spec, target)
        with zipfile.ZipFile(target) as z:
            names = set(z.namelist())
        for part in ('[Content_Types].xml', '_rels/.rels', 'ppt/presentation.xml',
                     'ppt/slides/slide1.xml', 'ppt/slideMasters/slideMaster1.xml',
                     'ppt/slideLayouts/slideLayout1.xml', 'ppt/theme/theme1.xml'):
            self.assertIn(part, names)

    def test_slide_size_matches_spec(self):
        target = self.dir / 'c.pptx'
        ooxml.write_pptx_slide(self.spec, target)
        with zipfile.ZipFile(target) as z:
            pres = z.read('ppt/presentation.xml').decode('utf-8')
        self.assertIn('cx="%d"' % self.spec['width_emu'], pres)
        self.assertIn('cy="%d"' % self.spec['height_emu'], pres)

    def test_bullets_requested_become_bu_char(self):
        target = self.dir / 'd.pptx'
        spec = dict(self.spec)
        spec['boxes'] = [dict(self.spec['boxes'][0],
                             paragraphs=[{'text': 'x', 'size': 12, 'bullet': True}])]
        ooxml.write_pptx_slide(spec, target)
        with zipfile.ZipFile(target) as z:
            slide = z.read('ppt/slides/slide1.xml').decode('utf-8')
        self.assertIn('buChar', slide)

    def test_never_overwrites(self):
        target = self.dir / 'e.pptx'
        ooxml.write_pptx_slide(self.spec, target)
        with self.assertRaises(FileExistsError):
            ooxml.write_pptx_slide(self.spec, target)


class VerifyTests(unittest.TestCase):
    def test_verify_reports_missing_content_types(self):
        with tempfile.TemporaryDirectory() as t:
            bad = Path(t) / 'bad.zip'
            with zipfile.ZipFile(bad, 'w') as z:
                z.writestr('word/document.xml', '<broken>')
            report = ooxml.verify(bad)
            self.assertFalse(report['ok'])
            self.assertTrue(any('Content_Types' in p for p in report['problems']))

    def test_verify_detects_malformed_xml(self):
        with tempfile.TemporaryDirectory() as t:
            bad = Path(t) / 'bad2.zip'
            with zipfile.ZipFile(bad, 'w') as z:
                z.writestr('[Content_Types].xml', '<Types>')
            report = ooxml.verify(bad)
            self.assertFalse(report['ok'])
            self.assertTrue(any('well-formed' in p for p in report['problems']))


if __name__ == '__main__':
    unittest.main()
