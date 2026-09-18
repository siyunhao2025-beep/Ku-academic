"""Tests for the three-level fact locks.

Most of these pin the refusals: a red fact may not vanish, may not change value,
may not be invented, and the definition of a term used in a red fact may not be
lost while the term is still used.
"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import locks


BASE = ("The anomaly reached 12.5 K, which is 3.1 times the quiet baseline level. "
        "The quiet baseline is defined as the 10-day median before onset. "
        "Sample size n = 48 orbits.")


class SentenceTests(unittest.TestCase):
    def test_splits_cjk_and_latin(self):
        got = locks.sentences('第一句。第二句！Third one? Fourth.')
        self.assertEqual(len(got), 4)

    def test_does_not_split_decimals_or_versions(self):
        got = locks.sentences('The value is 12.5 K.')
        self.assertEqual(len(got), 1)
        self.assertIn('12.5', got[0])

    def test_empty_input(self):
        self.assertEqual(locks.sentences(''), [])
        self.assertEqual(locks.sentences(None), [])


class ExtractionTests(unittest.TestCase):
    def test_finds_quantity_sample_count_and_time(self):
        found = locks.extract('温度在 95 km 上升 12.5 K，样本 n = 48，时间 2020-03-01。')
        kinds = {f['kind'] for f in found['facts'] if f['level'] == 'red'}
        self.assertIn('quantity', kinds)
        self.assertIn('sample_count', kinds)
        self.assertIn('time_window', kinds)

    def test_n_equals_is_not_counted_as_a_threshold(self):
        found = locks.extract('Sample size n = 48 orbits.')
        kinds = [f['kind'] for f in found['facts']]
        self.assertIn('sample_count', kinds)
        self.assertNotIn('threshold', kinds)

    def test_inequality_is_a_threshold(self):
        found = locks.extract('Only events with Dst > 50 nT were kept.')
        self.assertTrue(any(f['kind'] == 'threshold' for f in found['facts']))

    def test_date_parts_do_not_leak_as_extra_numbers(self):
        found = locks.extract('Observed on 2020-03-01.')
        derived = [f['value'] for f in found['facts'] if f['kind'] == 'derived_number']
        self.assertNotIn('2020', derived)
        self.assertNotIn('03', derived)

    def test_domain_terms_are_red_when_declared(self):
        found = locks.extract('We use SABER data.', ['SABER'])
        self.assertTrue(any(f['kind'] == 'domain_term' and f['level'] == 'red'
                            for f in found['facts']))

    def test_no_hardcoded_field_terms(self):
        """With no domain terms declared, no instrument name is ever red."""
        found = locks.extract('We use SABER and TIMED data.', [])
        self.assertFalse(any(f['kind'] == 'domain_term' for f in found['facts']))

    def test_counts_include_all_three_levels(self):
        found = locks.extract(BASE)
        self.assertEqual(set(found['counts']), {'red', 'yellow', 'green'})


class EscalationTests(unittest.TestCase):
    def test_definition_of_a_red_locked_term_escalates(self):
        found = locks.extract(BASE, [])
        self.assertEqual(len(found['escalated']), 1)
        self.assertIn('baseline', found['escalated'][0]['shared_terms'])

    def test_unrelated_definition_does_not_escalate(self):
        text = ('The anomaly reached 12.5 K. '
                'The network topology is defined as a set of nodes.')
        self.assertEqual(locks.extract(text, [])['escalated'], [])

    def test_non_definition_sentence_does_not_escalate(self):
        text = 'The quiet baseline was measured separately. Sample size n = 48.'
        self.assertEqual(locks.extract(text, [])['escalated'], [])


class VerifyTests(unittest.TestCase):
    def test_rewording_that_keeps_everything_is_ok(self):
        after = ("The anomaly was 12.5 K, i.e. 3.1 times the quiet baseline level. "
                 "The quiet baseline is defined as the 10-day median before onset. "
                 "Sample size n = 48 orbits.")
        self.assertTrue(locks.verify(BASE, after)['ok'])

    def test_changed_value_is_a_violation(self):
        after = ("The anomaly reached 21 K, 3.1 times the quiet baseline level. "
                 "The quiet baseline is defined as the 10-day median before onset. "
                 "Sample size n = 48 orbits.")
        report = locks.verify(BASE, after)
        self.assertFalse(report['ok'])
        self.assertTrue(report['red_changed'])

    def test_lost_fact_is_a_violation(self):
        after = 'The anomaly reached 12.5 K.'
        report = locks.verify(BASE, after)
        self.assertFalse(report['ok'])
        self.assertTrue(report['red_missing'])

    def test_invented_number_is_a_violation(self):
        after = BASE + ' The threshold was 7 nT.'
        report = locks.verify(BASE, after)
        self.assertFalse(report['ok'])
        self.assertTrue(report['red_added'])

    def test_losing_the_definition_is_a_violation(self):
        after = ("The anomaly reached 12.5 K, which is 3.1 times the quiet baseline level. "
                 "Sample size n = 48 orbits.")
        report = locks.verify(BASE, after)
        self.assertFalse(report['ok'])
        self.assertIn('baseline', report['red_escalated_lost'])

    def test_recall_is_one_when_there_are_no_red_facts(self):
        report = locks.verify('All sentences here are background.', 'Background only.')
        self.assertTrue(report['ok'])
        self.assertEqual(report['red_recall'], 1.0)
        self.assertEqual(report['red_facts_before'], 0)

    def test_recall_is_reported_when_facts_are_dropped(self):
        report = locks.verify(BASE, 'The anomaly reached 12.5 K.')
        self.assertLess(report['red_recall'], 1.0)

    def test_yellow_drops_are_listed(self):
        after = ("The anomaly reached 12.5 K, which is 3.1 times the quiet baseline level. "
                 "The quiet baseline is defined as the median before onset. "
                 "Sample size n = 48 orbits.")
        report = locks.verify(BASE, after)
        self.assertTrue(report['yellow_dropped'] or report['ok'])

    def test_assert_intact_raises_with_a_label(self):
        with self.assertRaises(ValueError) as ctx:
            locks.assert_intact(BASE, 'The anomaly reached 21 K.', None, 'gate4')
        self.assertIn('gate4', str(ctx.exception))

    def test_assert_intact_passes_through_clean_rewrites(self):
        self.assertTrue(locks.assert_intact(BASE, BASE)['ok'])


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_extract_command(self):
        p = self.dir / 'a.txt'
        p.write_text(BASE, encoding='utf-8')
        self.assertEqual(locks.main(['extract', str(p)]), 0)

    def test_verify_command_exit_codes(self):
        a, b = self.dir / 'a.txt', self.dir / 'b.txt'
        a.write_text(BASE, encoding='utf-8')
        b.write_text(BASE, encoding='utf-8')
        self.assertEqual(locks.main(['verify', str(a), str(b)]), 0)
        b.write_text('The anomaly reached 21 K.', encoding='utf-8')
        self.assertEqual(locks.main(['verify', str(a), str(b)]), 2)

    def test_missing_file_returns_2(self):
        self.assertEqual(locks.main(['extract', 'no/such/file.txt']), 2)


if __name__ == '__main__':
    unittest.main()
