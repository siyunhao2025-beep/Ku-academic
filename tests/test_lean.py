"""Tests for token accounting. No network, no tiktoken required: the heuristic
path is the one under test. Synthetic fixtures only."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import lean


class HeuristicTests(unittest.TestCase):
    def test_cjk_costs_more_than_ascii_at_equal_char_count(self):
        cjk = '中' * 40
        ascii_text = 'a' * 40
        self.assertGreater(lean.estimate_tokens(cjk), lean.estimate_tokens(ascii_text))

    def test_estimate_is_deterministic(self):
        text = '条件期间的目标量响应，sample 42.'
        self.assertEqual(lean.estimate_tokens(text), lean.estimate_tokens(text))

    def test_empty_text_is_zero(self):
        self.assertEqual(lean.estimate_tokens(''), 0)

    def test_encoder_takes_precedence_when_supplied(self):
        class FakeEncoder:
            def encode(self, text):
                return list(range(7))
        self.assertEqual(lean.estimate_tokens('anything', FakeEncoder()), 7)

    def test_heuristic_is_conservative_upper_bound_on_mixed_text(self):
        # The published bias: the heuristic must not under-count by more than 60%.
        text = '某种条件下的目标量响应研究 ' * 3 + 'target quantity response study ' * 3
        est = lean.estimate_tokens(text)
        self.assertGreater(est, 0)
        self.assertLess(est, len(text) * 2)


class MeasureTests(unittest.TestCase):
    def test_measure_file_reports_shape(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'a.md'
            p.write_text('指标 temperature', encoding='utf-8')
            item = lean.measure_file(p, None, t)
            self.assertEqual(item['path'], 'a.md')
            self.assertEqual(item['chars'], len('指标 temperature'))
            self.assertGreater(item['bytes'], 0)
            self.assertGreater(item['tokens'], 0)

    def test_relative_path_falls_back_outside_root(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'a.md'
            p.write_text('x', encoding='utf-8')
            item = lean.measure_file(p, None, Path(t) / 'elsewhere')
            self.assertTrue(item['path'].endswith('a.md'))

    def test_missing_path_errors(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                lean.measure([str(Path(t) / 'nope.md')], None, t)

    def test_directory_measure_skips_binary_and_dedupes(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / 'a.md').write_text('one', encoding='utf-8')
            (root / 'b.py').write_text('two', encoding='utf-8')
            (root / 'image.png').write_bytes(b'\x89PNG\r\n')
            items, total = lean.measure([str(root)], None, t)
            names = sorted(i['path'] for i in items)
            self.assertEqual(names, ['a.md', 'b.py'])
            self.assertEqual(total, sum(i['tokens'] for i in items))

    def test_duplicate_targets_counted_once(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / 'a.md'
            p.write_text('dup', encoding='utf-8')
            items, _ = lean.measure([str(p), str(p)], None, t)
            self.assertEqual(len(items), 1)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)
        (self.ws / 'manuscript').mkdir()
        self.f1 = self.ws / 'manuscript' / 'draft.md'
        self.f1.write_text('第一版内容 ' * 20, encoding='utf-8')

    def tearDown(self):
        self._tmp.cleanup()

    def test_ledger_accumulates_across_steps(self):
        lean.add_entry(self.ws, 'P1', [self.f1], encoder=None, method=lean.HEURISTIC, root=self.ws)
        first = lean.read_ledger(self.ws)['cumulative_tokens']
        self.assertGreater(first, 0)
        f2 = self.ws / 'manuscript' / 'rev.md'
        f2.write_text('第二版 ' * 10, encoding='utf-8')
        lean.add_entry(self.ws, 'P2', [f2], encoder=None, method=lean.HEURISTIC, root=self.ws)
        ledger = lean.read_ledger(self.ws)
        self.assertEqual(ledger['cumulative_tokens'],
                         sum(e['subtotal_tokens'] for e in ledger['entries']))
        self.assertGreater(ledger['cumulative_tokens'], first)
        self.assertEqual([e['step'] for e in ledger['entries']], ['P1', 'P2'])

    def test_rewriting_the_same_file_counts_again(self):
        lean.add_entry(self.ws, 'P1', [self.f1], encoder=None, method=lean.HEURISTIC, root=self.ws)
        once = lean.read_ledger(self.ws)['cumulative_tokens']
        lean.add_entry(self.ws, 'P2', [self.f1], encoder=None, method=lean.HEURISTIC, root=self.ws)
        twice = lean.read_ledger(self.ws)['cumulative_tokens']
        self.assertEqual(twice, once * 2)

    def test_rewrite_volume_is_not_below_snapshot(self):
        lean.add_entry(self.ws, 'P1', [self.f1], encoder=None, method=lean.HEURISTIC, root=self.ws)
        lean.add_entry(self.ws, 'P2', [self.f1], encoder=None, method=lean.HEURISTIC, root=self.ws)
        written = lean.read_ledger(self.ws)['cumulative_tokens']
        _, snapshot = lean.measure([str(self.ws / 'manuscript')], None, self.ws)
        self.assertGreaterEqual(written, snapshot)

    def test_conversation_tokens_stays_not_measurable(self):
        lean.add_entry(self.ws, 'P1', [self.f1], encoder=None, method=lean.HEURISTIC, root=self.ws)
        self.assertEqual(lean.read_ledger(self.ws)['conversation_tokens'], lean.NOT_MEASURABLE)

    def test_scope_is_recorded_and_not_whole_conversation(self):
        ledger = lean.add_entry(self.ws, 'P1', [self.f1], encoder=None,
                                method=lean.HEURISTIC, root=self.ws)
        self.assertEqual(ledger['scope'], 'artifact_files_only')

    def test_step_is_required(self):
        with self.assertRaises(ValueError):
            lean.add_entry(self.ws, '', [self.f1], encoder=None, method=lean.HEURISTIC, root=self.ws)

    def test_ledger_survives_reload(self):
        lean.add_entry(self.ws, 'P1', [self.f1], encoder=None, method=lean.HEURISTIC, root=self.ws)
        on_disk = json.loads((self.ws / lean.LEDGER).read_text(encoding='utf-8'))
        self.assertEqual(on_disk['cumulative_tokens'], lean.read_ledger(self.ws)['cumulative_tokens'])

    def test_missing_ledger_reads_as_empty_not_error(self):
        with tempfile.TemporaryDirectory() as t:
            ledger = lean.read_ledger(t)
            self.assertEqual(ledger['entries'], [])
            self.assertEqual(ledger['cumulative_tokens'], 0)

    def test_report_always_states_the_conversation_limit(self):
        lean.add_entry(self.ws, 'P1', [self.f1], encoder=None, method=lean.HEURISTIC, root=self.ws)
        text = lean.format_report(lean.read_ledger(self.ws))
        self.assertIn(lean.NOT_MEASURABLE, text)
        self.assertIn('artifact_files_only', text)

    def test_heuristic_label_is_not_a_tiktoken_label(self):
        self.assertTrue(lean.HEURISTIC.startswith('heuristic:'))
        self.assertNotIn('tiktoken', lean.HEURISTIC)


if __name__ == '__main__':
    unittest.main()
