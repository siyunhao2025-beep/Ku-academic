"""Tests for the four-box compressor.

The refusals matter most: box C may not be compressed, the original archive is
immutable, caps may not be exceeded, and export must never read a compressed copy.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import boxes


INTRO = ("中层大气研究已有数十年历史。温度观测手段不断丰富。"
         "本研究关注扰动期间的响应幅度与时间尺度，样本 n = 48。"
         "过去的研究多集中在高纬地区。相关背景在此不再赘述。")
RESULTS = "扰动期间中层温度上升 12.5 K。该变化在 95 km 处最明显。响应持续 6 h。"
GREEN_ONLY = "第一句是背景。第二句是过渡。第三句是重复描述。第四句是铺垫。"


class InitTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_four_boxes(self):
        made = boxes.init_workspace(self.ws)
        self.assertEqual(made, list(boxes.BOXES))
        for box in boxes.BOXES:
            self.assertTrue(boxes.archive_path(self.ws, box).is_file())

    def test_caps_match_the_specification(self):
        self.assertEqual(boxes.BOX_CAPS['A'], 6.0)
        self.assertEqual(boxes.BOX_CAPS['B'], 3.0)
        self.assertEqual(boxes.BOX_CAPS['C'], 1.0)
        self.assertEqual(boxes.BOX_CAPS['D'], 2.0)

    def test_init_is_idempotent(self):
        boxes.init_workspace(self.ws)
        self.assertEqual(boxes.init_workspace(self.ws), [])

    def test_append_requires_init(self):
        with self.assertRaises(ValueError):
            boxes.append_paragraph(self.ws, 'A', 'text')


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        boxes.init_workspace(self.ws)

    def tearDown(self):
        self._tmp.cleanup()

    def test_append_grows_archive_and_records_hash(self):
        meta = boxes.append_paragraph(self.ws, 'A', '第一句。第二句。')
        self.assertEqual(meta['original_sentences'], 2)
        self.assertTrue(meta['original_sha256'])
        self.assertEqual(len(meta['paragraphs']), 1)

    def test_empty_text_rejected(self):
        with self.assertRaises(ValueError):
            boxes.append_paragraph(self.ws, 'A', '   ')

    def test_unknown_box_rejected(self):
        with self.assertRaises(ValueError):
            boxes.append_paragraph(self.ws, 'Z', 'text')

    def test_external_tampering_is_detected(self):
        boxes.append_paragraph(self.ws, 'A', '原始句子。')
        path = boxes.archive_path(self.ws, 'A')
        path.write_text(path.read_text(encoding='utf-8') + '外部写入。', encoding='utf-8')
        with self.assertRaises(ValueError):
            boxes.append_paragraph(self.ws, 'A', '新句子。')


class LockSummaryTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        boxes.init_workspace(self.ws)

    def tearDown(self):
        self._tmp.cleanup()

    def test_summary_classifies_sentences(self):
        boxes.append_paragraph(self.ws, 'A', INTRO)
        summary = boxes.locks_summary(self.ws, 'A')
        self.assertEqual(summary['sentences'],
                         summary['red_sentences'] + summary['yellow_sentences']
                         + summary['green_sentences'])
        self.assertGreaterEqual(summary['green_sentences'], 2)

    def test_droppable_order_is_green_before_yellow(self):
        boxes.append_paragraph(self.ws, 'A', INTRO)
        summary = boxes.locks_summary(self.ws, 'A')
        self.assertEqual(len(summary['droppable_order']),
                         summary['yellow_sentences'] + summary['green_sentences'])


class CompressionTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        boxes.init_workspace(self.ws)
        boxes.append_paragraph(self.ws, 'A', INTRO)
        boxes.append_paragraph(self.ws, 'B', '本研究使用深度学习方法。训练集覆盖 2002–2020 年。')
        boxes.append_paragraph(self.ws, 'C', RESULTS)
        boxes.append_paragraph(self.ws, 'D', GREEN_ONLY)

    def tearDown(self):
        self._tmp.cleanup()

    def test_box_c_refuses_compression(self):
        with self.assertRaises(ValueError):
            boxes.compress(self.ws, 'C', 0.5)

    def test_compression_is_extractive_and_keeps_order(self):
        result = boxes.compress(self.ws, 'A', 0.5)
        text = Path(result['path']).read_text(encoding='utf-8')
        original = boxes.archive_path(self.ws, 'A').read_text(encoding='utf-8')
        for sentence in [s for s in boxes.locks.sentences(text) if s]:
            self.assertIn(sentence, original)
        self.assertTrue(result['order_preserved'])
        self.assertEqual(result['method'], 'extractive_only')

    def test_red_recall_is_complete(self):
        result = boxes.compress(self.ws, 'A', 0.4)
        self.assertEqual(result['red_recall'], 1.0)
        self.assertTrue(result['red_lock_check']['ok'])

    def test_dropped_items_are_listed(self):
        result = boxes.compress(self.ws, 'A', 0.5)
        self.assertTrue(result['dropped_items'])
        for item in result['dropped_items']:
            self.assertIn(item['level'], ('green', 'yellow'))

    def test_cap_is_enforced(self):
        with self.assertRaises(ValueError):
            boxes.compress(self.ws, 'D', 0.05)   # 20x would exceed D's 2x cap

    def test_missing_box_rejected(self):
        with self.assertRaises(ValueError):
            boxes.compress(self.ws, 'E', 0.5)

    def test_original_archive_untouched_by_compression(self):
        before = boxes.archive_path(self.ws, 'A').read_text(encoding='utf-8')
        boxes.compress(self.ws, 'A', 0.5)
        after = boxes.archive_path(self.ws, 'A').read_text(encoding='utf-8')
        self.assertEqual(before, after)

    def test_compressed_path_differs_from_archive(self):
        result = boxes.compress(self.ws, 'A', 0.5)
        self.assertNotEqual(Path(result['path']), boxes.archive_path(self.ws, 'A'))


class SearchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        boxes.init_workspace(self.ws)
        boxes.append_paragraph(self.ws, 'A', INTRO)
        boxes.append_paragraph(self.ws, 'C', RESULTS)
        boxes.append_paragraph(self.ws, 'D', GREEN_ONLY)

    def tearDown(self):
        self._tmp.cleanup()

    def test_box_c_max_ratio_is_one(self):
        out = boxes.search_max_ratio(self.ws, 'C')
        self.assertEqual(out['max_ratio'], 1.0)
        self.assertTrue(out['capped'])

    def test_search_never_exceeds_the_cap(self):
        for box in ('A', 'D'):
            out = boxes.search_max_ratio(self.ws, box)
            self.assertLessEqual(out['max_ratio'], boxes.BOX_CAPS[box] + 1e-9)

    def test_search_finds_compression_for_an_all_green_box(self):
        out = boxes.search_max_ratio(self.ws, 'D')
        self.assertGreater(out['max_ratio'], 1.0)

    def test_probes_are_recorded(self):
        out = boxes.search_max_ratio(self.ws, 'A')
        self.assertTrue(out['probes'])
        self.assertTrue(all('ratio' in p and 'feasible' in p for p in out['probes']))

    def test_box_with_every_sentence_red_cannot_compress(self):
        boxes.append_paragraph(self.ws, 'B', '样本 n = 48，温度上升 12.5 K。')
        out = boxes.search_max_ratio(self.ws, 'B')
        self.assertEqual(out['max_ratio'], 1.0)


class BudgetTests(unittest.TestCase):
    def test_unknown_inputs_are_reported_not_guessed(self):
        out = boxes.budget(None, None, None, None)
        self.assertEqual(out['status'], 'unknown')
        self.assertEqual(len(out['unknown_inputs']), 4)
        self.assertIn('rather than estimating', out['action'])

    def test_warn_threshold(self):
        self.assertEqual(boxes.budget(100000, 70000, 5000, 6000)['status'], 'warn')

    def test_brake_threshold(self):
        self.assertEqual(boxes.budget(100000, 80000, 5000, 6000)['status'], 'brake')

    def test_ok_status(self):
        out = boxes.budget(100000, 10000, 5000, 5000)
        self.assertEqual(out['status'], 'ok')
        self.assertEqual(out['headroom'], 80000)

    def test_partial_input_is_unknown(self):
        out = boxes.budget(100000, None, 5000, 5000)
        self.assertEqual(out['status'], 'unknown')
        self.assertEqual(out['unknown_inputs'], ['history'])


class ExportTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        boxes.init_workspace(self.ws)
        boxes.append_paragraph(self.ws, 'A', INTRO)
        boxes.append_paragraph(self.ws, 'B', '本研究使用深度学习方法。')
        boxes.append_paragraph(self.ws, 'C', RESULTS)
        boxes.append_paragraph(self.ws, 'D', GREEN_ONLY)

    def tearDown(self):
        self._tmp.cleanup()

    def test_export_uses_original_archives(self):
        boxes.compress(self.ws, 'A', 0.3)
        text, provenance = boxes.export_full_text(self.ws)
        for row in provenance:
            self.assertEqual(row['source'], 'original_archive')
        # every original sentence must be present, including the dropped ones
        for sentence in boxes.locks.sentences(INTRO):
            self.assertIn(sentence, text)

    def test_export_concatenates_all_four_boxes_in_order(self):
        text, provenance = boxes.export_full_text(self.ws)
        self.assertEqual([p['box'] for p in provenance], ['A', 'B', 'C', 'D'])
        self.assertLess(text.index('中层大气研究'), text.index('扰动期间中层温度上升'))
        self.assertIn('第一句是背景', text)

    def test_export_never_reads_a_compressed_copy(self):
        source = Path(boxes.__file__).read_text(encoding='utf-8')
        body = source.split('def export_full_text')[1].split('def read_json')[0]
        self.assertIn('archive_path', body)
        self.assertNotIn('compressed_path', body)

    def test_results_box_text_is_byte_identical(self):
        text, provenance = boxes.export_full_text(self.ws)
        for sentence in boxes.locks.sentences(RESULTS):
            self.assertIn(sentence, text)

    def test_export_cli_refuses_overwrite(self):
        out = self.ws / 'full.md'
        self.assertEqual(boxes.main(['export', str(self.ws), '--out', str(out)]), 0)
        self.assertEqual(boxes.main(['export', str(self.ws), '--out', str(out)]), 2)

    def test_missing_box_breaks_export(self):
        (boxes.archive_path(self.ws, 'C')).unlink()
        with self.assertRaises(ValueError):
            boxes.export_full_text(self.ws)


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_init_then_add_then_locks(self):
        self.assertEqual(boxes.main(['init', str(self.ws)]), 0)
        self.assertEqual(boxes.main(['add', str(self.ws), 'A', '--text', '一句。']), 0)
        self.assertEqual(boxes.main(['locks', str(self.ws), 'A']), 0)

    def test_search_report_written(self):
        boxes.main(['init', str(self.ws)])
        boxes.main(['add', str(self.ws), 'A', '--text', INTRO])
        report = self.ws / 'report.md'
        self.assertEqual(boxes.main(['search', str(self.ws), '--report', str(report)]), 0)
        self.assertTrue(report.is_file())
        plan = json.loads((self.ws / 'boxes' / 'compression-plan.json').read_text(encoding='utf-8'))
        self.assertEqual(len(plan['results']), 4)

    def test_uninitialised_workspace_returns_2(self):
        self.assertEqual(boxes.main(['add', str(self.ws), 'A', '--text', 'x']), 2)


if __name__ == '__main__':
    unittest.main()
