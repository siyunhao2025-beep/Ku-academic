"""Tests for the five-gate pipeline.

The important ones: gates run in a fixed order with no way to skip, the first
rejection stops the paragraph, gate 1 does not delete a sentence about the
study's own model, and gate 4 refuses a polish that moved a red-locked fact.
"""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import gates


def manuscript(paragraphs, **overrides):
    base = {
        'core_thesis': '量化中层温度对地磁扰动的响应幅度与时间尺度',
        'core_questions': ['中层温度在扰动期间的变化幅度是多少',
                           '该变化的持续时间有多长'],
        'domain_keywords': ['middle atmosphere'],
        'citation_domain_keywords': ['middle atmosphere'],
        'references': [
            {'key': 'R1', 'title': 'Middle atmosphere temperature response', 'doi': '10.1/a'},
            {'key': 'R2', 'title': 'Network coding for storage', 'doi': '10.1/b'},
        ],
        'paragraphs': paragraphs,
    }
    base.update(overrides)
    return base


GOOD = {
    'id': 'P1', 'box': 'results',
    'text': '中层温度在扰动期间上升 12.5 K，高于前人的 8 K [R1]，说明温度对扰动有响应。',
    'figures': [{'id': '2', 'values': ['12.5', '8']}],
    'citations': ['R1'],
}


class OrderTests(unittest.TestCase):
    def test_gate_order_is_fixed(self):
        self.assertEqual(gates.GATES,
                         ('content_filter', 'topic_anchoring', 'bullseye',
                          'deai_polish', 'citation'))

    def test_no_skip_or_only_switch_is_accepted(self):
        """The sequencing guarantee is behavioural: the switch does not exist."""
        with tempfile.TemporaryDirectory() as t:
            src = Path(t) / 'm.json'
            src.write_text('{"paragraphs": []}', encoding='utf-8')
            out = str(Path(t) / 'g.json')
            for flag in ('--only', '--skip', '--gates'):
                with self.assertRaises(SystemExit, msg=flag):
                    gates.main(['run', str(src), '--out', out, flag, 'citation'])

    def test_rejection_stops_the_paragraph(self):
        led = gates.run_pipeline(manuscript([{
            'id': 'X', 'box': 'results', 'text': '中层温度升高 12.5 K。'}]), None)
        row = led['results'][0]
        self.assertEqual(row['blocked_at'], 'bullseye')
        self.assertEqual(row['gates_not_run'], ['deai_polish', 'citation'])

    def test_gates_after_a_pass_all_run(self):
        led = gates.run_pipeline(manuscript([dict(GOOD, text_after=GOOD['text'])]), None)
        self.assertEqual(led['results'][0]['gates_not_run'], [])
        self.assertEqual(len(led['results'][0]['gates']), 5)


class ContentFilterTests(unittest.TestCase):
    def test_meta_narration_is_rejected(self):
        out = gates.gate_content_filter('受限于上下文窗口，我无法处理全部数据。')
        self.assertEqual(out['verdict'], 'reject')

    def test_study_model_sentence_is_kept(self):
        out = gates.gate_content_filter('本研究采用深度学习方法重建温度场。')
        self.assertEqual(out['verdict'], 'pass')

    def test_study_model_mentioning_a_blacklisted_word_is_kept(self):
        """A blacklisted word inside a study description must not kill the sentence."""
        out = gates.gate_content_filter('本研究使用的神经网络模型训练了 200 轮。')
        self.assertNotEqual(out['verdict'], 'reject')
        self.assertEqual(out['details']['hits'], [])

    def test_ambiguous_hit_is_flagged_not_deleted(self):
        out = gates.gate_content_filter('token 是输入的基本单位。')
        self.assertEqual(out['verdict'], 'flag')
        self.assertEqual(out['details']['flagged'], 1)

    def test_report_states_that_flagged_text_may_not_be_deleted(self):
        out = gates.gate_content_filter('大模型的参数规模不断增长。')
        self.assertIn('semantic', out['report'])


class TopicAnchoringTests(unittest.TestCase):
    def test_off_topic_conclusion_is_rejected(self):
        out = gates.gate_topic_anchoring(
            '神经网络加速卡的采购成本在过去五年下降了 40%。',
            manuscript=manuscript([]), box='conclusion')
        self.assertEqual(out['verdict'], 'reject')

    def test_anchored_text_passes(self):
        out = gates.gate_topic_anchoring(
            '中层温度在扰动期间的响应幅度达到 12.5 K。',
            manuscript=manuscript([]), box='results')
        self.assertEqual(out['verdict'], 'pass')
        self.assertTrue(out['details']['paragraph_anchors'])

    def test_reports_which_question_is_supported(self):
        out = gates.gate_topic_anchoring(
            '中层温度在扰动期间的变化幅度为 12.5 K。',
            manuscript=manuscript([]), box='results')
        self.assertIn('变化幅度', out['details']['supports_question'] or '')

    def test_missing_core_thesis_cannot_be_checked(self):
        out = gates.gate_topic_anchoring('任意文本。',
                                         manuscript={'core_questions': []}, box='results')
        self.assertEqual(out['verdict'], 'flag')
        self.assertTrue(out['details']['cannot_check'])

    def test_labels_the_method_as_heuristic(self):
        out = gates.gate_topic_anchoring('中层温度响应。', manuscript=manuscript([]), box='results')
        self.assertIn('heuristic', out['details']['method'])


class BullseyeTests(unittest.TestCase):
    def test_figure_not_provided_is_rejected(self):
        out = gates.gate_bullseye('如图 5 所示，中层温度上升 12.5 K。',
                                  paragraph={'figures': [{'id': '2', 'values': ['12.5']}]},
                                  box='results')
        self.assertEqual(out['verdict'], 'reject')

    def test_no_figure_data_reports_cannot_check(self):
        out = gates.gate_bullseye('中层温度上升 12.5 K。', paragraph={}, box='results')
        self.assertEqual(out['details']['figure_status'], 'cannot_check')

    def test_number_absent_from_figure_is_flagged(self):
        out = gates.gate_bullseye('中层温度上升 12.5 K，持续 9 h。',
                                  paragraph={'figures': [{'id': '2', 'values': ['12.5']}]},
                                  box='results')
        kinds = [p['type'] for p in out['details']['figure_problems']]
        self.assertIn('number_not_found_in_figure', kinds)

    def test_quantities_without_a_stated_target_is_rejected(self):
        out = gates.gate_bullseye('中层温度升高 12.5 K，持续 6 h。',
                                  paragraph={}, box='results')
        self.assertEqual(out['verdict'], 'reject')
        self.assertTrue(out['details']['off_target'])

    def test_data_listing_is_detected(self):
        out = gates.gate_bullseye('中层温度升高 12.5 K，样本 48 个，高度 95 km。',
                                  paragraph={}, box='results')
        self.assertTrue(out['details']['data_listing_sentences'])


class DeaiTests(unittest.TestCase):
    def test_missing_polish_result_cannot_pass(self):
        out = gates.gate_deai_polish('中层温度上升 12.5 K，说明温度有响应。', paragraph={})
        self.assertEqual(out['verdict'], 'flag')
        self.assertIn('text_after', out['report'])

    def test_polish_that_preserves_red_locks_passes(self):
        before = '中层温度在扰动期间上升 12.5 K，持续 6 h。'
        after = '中层温度在扰动期间上升 12.5 K，持续 6 h。'
        out = gates.gate_deai_polish(before, paragraph={}, text_after=after)
        self.assertEqual(out['verdict'], 'pass')

    def test_polish_that_changes_a_value_is_rejected(self):
        before = '中层温度在扰动期间上升 12.5 K，持续 6 h。'
        after = '中层温度在扰动期间上升 21 K，持续 6 h。'
        out = gates.gate_deai_polish(before, paragraph={}, text_after=after)
        self.assertEqual(out['verdict'], 'reject')
        self.assertIn('12.5', out['report'])

    def test_cliche_is_flagged(self):
        out = gates.gate_deai_polish('综上所述，中层温度上升 12.5 K。', paragraph={})
        self.assertIn('综上所述', out['details']['cliche_phrases'])

    def test_uniform_rhythm_is_detected(self):
        text = '第一句长度差不多。第二句长度差不多。第三句长度差不多。第四句长度差不多。'
        out = gates.gate_deai_polish(text, paragraph={}, text_after=text)
        self.assertTrue(out['details']['uniform_rhythm'])


class CitationTests(unittest.TestCase):
    def test_unknown_key_is_rejected(self):
        out = gates.gate_citation('中层温度上升 12.5 K。',
                                  paragraph={'citations': ['R9']},
                                  manuscript=manuscript([]), box='results')
        self.assertEqual(out['verdict'], 'reject')

    def test_under_cited_conclusion_is_flagged(self):
        out = gates.gate_citation('中层温度对扰动有响应，与前人一致。',
                                  paragraph={'citations': []},
                                  manuscript=manuscript([]), box='conclusion')
        self.assertEqual(out['verdict'], 'flag')
        self.assertIn('conclusion', out['report'])

    def test_recommendations_only_reuse_existing_references(self):
        out = gates.gate_citation('中层温度对扰动有响应。', paragraph={'citations': []},
                                  manuscript=manuscript([]), box='conclusion')
        keys = [r['key'] for r in out['details']['recommended_existing_references']]
        self.assertIn('R1', keys)
        self.assertNotIn('R2', keys)
        self.assertIn('never invents', out['details']['note'])

    def test_resolved_citations_pass(self):
        out = gates.gate_citation('中层温度在扰动期间上升 12.5 K [R1]。',
                                  paragraph={'citations': ['R1']},
                                  manuscript=manuscript([]), box='results')
        self.assertEqual(out['verdict'], 'pass')


class PipelineTests(unittest.TestCase):
    def test_summary_counts_and_archivable_list(self):
        paragraphs = [
            dict(GOOD, id='OK', text_after=GOOD['text']),
            {'id': 'META', 'box': 'results', 'text': '我无法处理，受限于上下文窗口。'},
        ]
        led = gates.run_pipeline(manuscript(paragraphs), None)
        s = led['summary']
        self.assertEqual(s['paragraphs'], 2)
        self.assertEqual(s['rejected'], 1)
        self.assertIn('OK', s['archivable'])
        self.assertIn('META', s['not_archivable'])

    def test_render_report_contains_gate_names(self):
        led = gates.run_pipeline(manuscript([dict(GOOD, text_after=GOOD['text'])]), None)
        text = gates.render_report(led)
        for gate in gates.GATES:
            self.assertIn(gate, text)

    def test_blocked_counts_are_reported_per_gate(self):
        paragraphs = [
            {'id': 'A', 'box': 'results', 'text': '我无法处理，受限于上下文窗口。'},
            {'id': 'B', 'box': 'results', 'text': '中层温度升高 12.5 K。'},
        ]
        led = gates.run_pipeline(manuscript(paragraphs), None)
        self.assertEqual(led['summary']['blocked_at']['content_filter'], 1)
        self.assertEqual(led['summary']['blocked_at']['bullseye'], 1)


if __name__ == '__main__':
    unittest.main()
