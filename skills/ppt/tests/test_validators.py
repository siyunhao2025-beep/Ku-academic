"""Regression cases for silent passes and realistic equivalent SML inputs."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import review_design
import review_layout
from sml import TokenError, load_tokens, normalize_color

NS = 'https://www.larkoffice.com/sml/2.0'


def slide(body, namespace=NS):
    return f'<slide xmlns="{namespace}"><data>{body}</data></slide>' if namespace else f'<slide><data>{body}</data></slide>'


def text_shape(body='<p>文字</p>', width=200, height=80, font=12, style='', x=40, y=40):
    return f'<shape type="text" topLeftX="{x}" topLeftY="{y}" width="{width}" height="{height}"><content fontSize="{font}" {style}>{body}</content></shape>'


class ValidatorsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tokens = load_tokens()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def xml(self, source, name='presentation.xml'):
        path = self.folder / name
        path.write_text(source, encoding='utf-8')
        return path

    def review(self, source, module=review_layout):
        return module.review_slide(self.xml(source), tokens=self.tokens)['issues']

    def codes(self, source, module=review_layout):
        return {item['code'] for item in self.review(source, module)}

    def cli(self, module, *arguments):
        process = subprocess.run([sys.executable, str(ROOT / 'scripts' / f'{module}.py'), *map(str, arguments), '--json'],
                                 cwd=self.folder, text=True, capture_output=True)
        return process, json.loads(process.stdout)

    def test_namespace_forms_detect_same_overflow_and_report_estimates(self):
        body = text_shape('<p>一二三四五六七八九十</p>', width=20, height=30, font=48,
                          style='wrap="false" autoFit="normal-auto-fit" lineSpacing="fixed:60"')
        canonical = slide(body)
        root = ET.fromstring(canonical)
        # ElementTree writes a prefixed namespace, unlike the default namespace input.
        forms = [canonical, ET.tostring(root, encoding='unicode'), slide(body, namespace='')]
        outcomes = [self.review(source) for source in forms]
        for issues in outcomes:
            self.assertIn('text_overflow_no_wrap', {item['code'] for item in issues})
            self.assertTrue(all(item['level'] == 'warning' for item in issues))
            self.assertTrue(all('autoFit' in item['message'] for item in issues))
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0], outcomes[2])

    def test_content_paragraph_span_and_tail_styles_are_used(self):
        body = '<p>前<span fontSize="48">大字</span>尾尾尾</p>'
        issues = self.review(slide(text_shape(body, width=130, style='wrap="false"')))
        self.assertIn('text_overflow_no_wrap', {item['code'] for item in issues})
        fitting = '<p>前<span fontSize="48">大字</span></p>'
        self.assertNotIn('text_overflow_no_wrap', self.codes(slide(text_shape(fitting, width=130, style='wrap="false"'))))
        self.assertIn('text_overflow_no_wrap', self.codes(slide(text_shape('<p fontSize="48">一二三四</p>', width=100, style='wrap="false"'))))

    def test_fixed_spacing_and_multiple_paragraphs_are_not_confused(self):
        paragraphs = '<p>第一行</p><p>第二行</p>'
        fixed = slide(text_shape(paragraphs, height=25, font=20, style='lineSpacing="fixed:10"'))
        multiple = fixed.replace('fixed:10', 'multiple:2')
        self.assertNotIn('text_overflow_wrap', self.codes(fixed))
        self.assertIn('text_overflow_wrap', self.codes(multiple))

    def test_overlapping_text_is_detected_including_identical_boxes(self):
        body = text_shape('<p>相同位置文字</p>', width=150, height=30, font=20)
        self.assertIn('text_overlap', self.codes(slide(body + body)))
        separate = text_shape('<p>另一行文字</p>', width=150, height=30, font=20, y=100)
        self.assertNotIn('text_overlap', self.codes(slide(body + separate)))

    def test_geometry_and_local_resource_failures_are_errors(self):
        body = text_shape(width=100, x=900) + '<img src="@./absent.png" width="20" height="20" topLeftX="1" topLeftY="1"/>'
        issues = self.review(slide(body))
        self.assertTrue({'out_of_bounds', 'missing_image'}.issubset({item['code'] for item in issues if item['level'] == 'error'}))
        self.assertIn('invalid_geometry', self.codes(slide(text_shape(width='NaN'))))
        self.assertIn('invalid_geometry', self.codes(slide(text_shape(width=-2))))

    def test_line_endpoint_geometry_is_checked_without_a_schema(self):
        def source(sx='40', sy='40', ex='300', ey='200'):
            return slide(f'<line startX="{sx}" startY="{sy}" endX="{ex}" endY="{ey}"><border color="#171717" width="2"/></line>')
        self.assertFalse(self.codes(source()))
        self.assertFalse(self.codes(source(sx='300', ex='40')))
        self.assertIn('invalid_geometry', self.codes(source(ex='NaN')))
        self.assertIn('out_of_bounds', self.codes(source(ey='541')))
        self.assertIn('negative_coord', self.codes(source(sx='-1')))
        self.assertIn('zero_size', self.codes(source(ex='40', ey='40')))
        self.assertIn('missing_geometry', self.codes(slide('<line startX="40"/>')))

    def test_image_resolution_uses_xml_directory_and_explicit_asset_root(self):
        source = slide('<img src="@./asset.png" width="20" height="20" topLeftX="1" topLeftY="1"/>')
        path = self.xml(source)
        (self.folder / 'asset.png').write_bytes(b'local image fixture')
        self.assertNotIn('missing_image', {item['code'] for item in review_layout.review_slide(path, tokens=self.tokens)['issues']})
        assets = self.folder / 'images'
        assets.mkdir()
        (self.folder / 'asset.png').rename(assets / 'asset.png')
        self.assertIn('missing_image', {item['code'] for item in review_layout.review_slide(path, tokens=self.tokens)['issues']})
        self.assertNotIn('missing_image', {item['code'] for item in review_layout.review_slide(path, tokens=self.tokens, assets_dir=assets)['issues']})

    def test_remote_image_is_explicitly_unverified_without_network(self):
        issues = self.review(slide('<img src="https://example.invalid/a.png" width="20" height="20" topLeftX="1" topLeftY="1"/>'))
        self.assertEqual([(item['level'], item['code']) for item in issues], [('warning', 'image_not_verified')])

    def test_empty_text_is_not_a_valid_deliverable(self):
        self.assertIn('empty_text_shape', self.codes(slide(text_shape('<p/>'))))
        self.assertIn('empty_text_shape', self.codes(slide('<shape type="text" topLeftX="1" topLeftY="1" width="20" height="20"/>')))

    def test_missing_files_and_invalid_xml_fail_both_commands(self):
        malformed = self.xml('<slide')
        for module in ('review_layout', 'review_design'):
            for path, expected in ((self.folder / 'does-not-exist.xml', 'read_failed'), (malformed, 'invalid_xml')):
                with self.subTest(module=module, expected=expected):
                    process, report = self.cli(module, '--input', path)
                    self.assertEqual(process.returncode, 1)
                    self.assertGreater(report['summary']['errors'], 0)
                    self.assertIn(expected, {item['code'] for item in report['results'][0]['issues']})
                    self.assertEqual(set(report), {'summary', 'results'})
                    self.assertEqual(set(report['results'][0]), {'file', 'issues'})

    def test_json_directory_scans_non_slide_names_from_other_working_directory(self):
        self.xml(slide(text_shape()), 'custom-name.xml')
        for module in ('review_layout', 'review_design'):
            process, report = self.cli(module, '--dir', self.folder)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(report['summary'], {'files': 1, 'errors': 0, 'warnings': 0})
            self.assertTrue(report['results'][0]['file'].endswith('custom-name.xml'))

    def test_empty_input_selection_fails_with_parseable_json(self):
        for module in ('review_layout', 'review_design'):
            process, report = self.cli(module, '--dir', self.folder / 'missing')
            self.assertEqual(process.returncode, 1)
            self.assertEqual(report['summary']['files'], 0)
            self.assertGreater(report['summary']['errors'], 0)

    def test_strict_warnings_changes_exit_without_hiding_warnings(self):
        path = self.xml(slide(text_shape('<p>溢出的长标题</p>', width=20, font=48, style='wrap="false"')))
        ordinary, first = self.cli('review_layout', '--input', path)
        strict, second = self.cli('review_layout', '--input', path, '--strict-warnings')
        self.assertEqual(ordinary.returncode, 0)
        self.assertEqual(strict.returncode, 1)
        self.assertEqual(first, second)
        self.assertEqual(first['summary']['errors'], 0)
        self.assertGreater(first['summary']['warnings'], 0)

    def test_design_is_invariant_to_whitespace_order_and_color_notation(self):
        source = '<slide xmlns="' + NS + '"><style><fill><fillColor color="rgba(17,17,17,1)"/></fill></style><data><shape type="round-rect" topLeftY="460" topLeftX="40" height="34" width="800"><fill><fillColor color="rgba(253,235,237,1)"/></fill></shape></data></slide>'
        root = ET.fromstring(source)
        ET.indent(root)
        pretty = ET.tostring(root, encoding='unicode').replace('rgba(17,17,17,1)', '#111111').replace('rgba(253,235,237,1)', 'rgb(253, 235, 237)')
        expected = {'dark_page_banned', 'page_background_mismatch', 'bottom_pill_bar'}
        self.assertEqual(self.codes(source, review_design), expected)
        self.assertEqual(self.codes(pretty, review_design), expected)

    def test_dark_table_fill_is_not_confused_with_dark_text(self):
        fill = '<table><tr><td><fill><fillColor color="#171717"/></fill><content color="#FFFFFF" fontSize="12"><p>表头</p></content></td></tr></table>'
        self.assertIn('dark_fill_banned', self.codes(slide(fill), review_design))
        dark_text = slide(text_shape('<p>黑色正文</p>', style='color="#171717"'))
        self.assertNotIn('dark_fill_banned', self.codes(dark_text, review_design))

    def test_chart_theme_color_values_are_validated_without_treating_data_as_colors(self):
        body = '<chart><chartColorTheme><color value="rgb(1,2,3)"/></chartColorTheme><chartField value="7"/></chart>'
        issues = self.review(slide(body), review_design)
        self.assertEqual([item['code'] for item in issues], ['color_not_in_palette'])
        self.assertIn('/color[1]', issues[0]['element'])

    def test_chart_accents_count_used_series_or_slices_not_unused_palette(self):
        theme = '<chartColorTheme><color value="#FF5A5F"/><color value="rgb(88,158,247)"/><color value="rgb(43,201,209)"/></chartColorTheme>'
        series = '<chartField name="Series" valueType="number">1,2,3</chartField>'

        def chart(plot_type, series_fields=series, categories='A,B,C'):
            return slide('<chart><chartPlotArea><chartPlot type="' + plot_type + '"/></chartPlotArea><chartData><dim1><chartField valueType="string">' + categories + '</chartField></dim1><dim2>' + series_fields + '</dim2></chartData><chartStyle>' + theme + '</chartStyle></chart>')

        for plot_type in ('column', 'line'):
            self.assertNotIn('accent_overuse', self.codes(chart(plot_type), review_design))
            self.assertIn('accent_overuse', self.codes(chart(plot_type, series * 3), review_design))
        self.assertNotIn('accent_overuse', self.codes(chart('pie', categories='A'), review_design))
        self.assertIn('accent_overuse', self.codes(chart('pie'), review_design))
        # Even an unused candidate remains subject to the theme whitelist.
        unused_invalid = chart('column').replace('rgb(43,201,209)', 'rgb(1,2,3)')
        self.assertIn('color_not_in_palette', self.codes(unused_invalid, review_design))
        self.assertNotIn('accent_overuse', self.codes(unused_invalid, review_design))

    def test_span_font_minimum_is_checked(self):
        self.assertIn('font_below_min', self.codes(slide(text_shape('<p>正常<span fontSize="9">过小文字</span></p>')), review_design))

    def test_note_font_and_color_errors_are_ignored_but_visible_data_is_checked(self):
        cases = (
            ('missing_font_size', '<content><p>备注没有字号</p></content>'),
            ('font_below_min', '<content fontSize="1"><p>备注小字</p></content>'),
            ('invalid_font_size', '<content fontSize="NaN"><p>备注字号</p></content>'),
            ('color_not_in_palette', '<content fontSize="12" color="#010203"><p>备注颜色</p></content>'),
            ('invalid_color', '<content fontSize="12" color="invalid"><p>备注颜色</p></content>'),
        )
        for expected, content in cases:
            for namespace in (NS, ''):
                with self.subTest(expected=expected, namespace=namespace):
                    source = slide(text_shape(), namespace).replace('</slide>', f'<note>{content}</note></slide>')
                    forms = (source, ET.tostring(ET.fromstring(source), encoding='unicode'))
                    for form in forms:
                        self.assertEqual(self.codes(form, review_design), set())
                    visible = slide(f'<shape type="text">{content}</shape>', namespace)
                    issues = self.review(visible, review_design)
                    self.assertIn(expected, {item['code'] for item in issues})
                    self.assertTrue(all('/data[1]/' in item['element'] for item in issues))

    def test_note_styles_do_not_inflate_font_or_accent_counts(self):
        count = self.tokens['validation']['max_font_variants'] + 1
        paragraphs = ''.join(f'<p fontSize="{12 + index}">备注字号</p>' for index in range(count))
        accents = ('#FF5A5F', '#589EF7', '#2BC9D1')
        paragraphs += ''.join(f'<p color="{color}">备注强调色</p>' for color in accents)
        content = f'<content fontSize="12">{paragraphs}</content>'
        source = slide(text_shape()).replace('</slide>', f'<note>{content}</note></slide>')
        self.assertEqual(self.codes(source, review_design), set())
        visible = slide(f'<shape type="text">{content}</shape>')
        self.assertTrue({'font_hierarchy_too_many', 'accent_overuse'}.issubset(self.codes(visible, review_design)))

    def test_declared_gray_token_and_equivalent_colors_are_accepted(self):
        gray = self.tokens['colors']['bg_light_gray']['rgba']
        source = slide('<shape><fill><fillColor color="' + gray + '"/></fill></shape>')
        self.assertNotIn('color_not_in_palette', self.codes(source, review_design))
        self.assertEqual(normalize_color('#FF5A5F'), normalize_color('rgba(255, 90, 95, 1.0)'))
        self.assertEqual(normalize_color('rgb(255,90,95)'), normalize_color('#ff5a5f'))

    def test_bad_or_duplicate_configuration_never_uses_fallback(self):
        path = self.xml(slide(text_shape()))
        config = self.folder / 'tokens.yaml'
        for body in ('schema_version: 1\n', 'schema_version: [broken', 'schema_version: 1\nschema_version: 1\n'):
            config.write_text(body)
            with self.assertRaises(TokenError):
                load_tokens(config)
            for module in ('review_layout', 'review_design'):
                process, report = self.cli(module, '--input', path, '--tokens', config)
                self.assertEqual(process.returncode, 1)
                self.assertEqual(report['results'][0]['issues'][0]['code'], 'invalid_tokens')

    def test_explicit_theme_can_allow_dark_background_and_different_minimum(self):
        theme = yaml.safe_load((ROOT / 'tokens.yaml').read_text())
        theme['validation'].update(page_background='brand_black', forbid_dark_page=False,
                                   forbid_dark_fills=False, min_font_size=6)
        config = self.folder / 'other-brand.yaml'
        config.write_text(yaml.safe_dump(theme))
        source = '<slide><style><fill><fillColor color="#171717"/></fill></style><data>' + text_shape(font=8) + '</data></slide>'
        path = self.xml(source)
        self.assertIn('dark_page_banned', self.codes(source, review_design))
        process, report = self.cli('review_design', '--input', path, '--tokens', config)
        self.assertEqual(process.returncode, 0, process.stdout)
        self.assertEqual(report['summary']['errors'], 0)

    def test_table_dimension_errors_and_capacity_estimates_are_distinct(self):
        body = '<table topLeftX="40" topLeftY="40" width="20" height="20"><colgroup><col width="20"/></colgroup><tr height="20"><td><content fontSize="20" wrap="true"><p>这个单元格放不下这么多文字</p></content></td></tr></table>'
        issues = self.review(slide(body))
        self.assertIn(('warning', 'table_cell_text_overflow'), {(item['level'], item['code']) for item in issues})
        mismatched = body.replace('<tr height="20">', '<tr height="30">')
        self.assertIn('table_dimension_mismatch', self.codes(slide(mismatched)))

    def test_native_column_span_expands_four_column_table(self):
        # Feishu readback compresses page 25's four columns into two col nodes.
        cells = ''.join(f'<td><content fontSize="18" textAlign="center"><p>{text}</p></content></td>'
                        for text in ('模式', '单模型对话', '多模型对话', 'Agent 工作'))
        rows = f'<tr height="50">{cells}</tr>' * 5
        for span in ('3', '3.0', '3e0'):
            first_span = ' span="1"' if span == '3' else ''
            body = ('<table topLeftX="40" topLeftY="188" width="880" height="250"><colgroup>'
                    f'<col{first_span} width="160"/><col span="{span}" width="240"/></colgroup>{rows}</table>')
            canonical = slide(body)
            forms = (canonical, ET.tostring(ET.fromstring(canonical), encoding='unicode'), slide(body, namespace=''))
            for source in forms:
                with self.subTest(span=span, source=source[:65]):
                    self.assertEqual(self.review(source), [])
                    mismatch = source.replace('width="880"', 'width="900"')
                    errors = [i for i in self.review(mismatch) if i['level'] == 'error']
                    self.assertEqual([i['code'] for i in errors], ['table_dimension_mismatch'])
                    self.assertIn('sum 880', errors[0]['message'])

    def test_invalid_column_span_reports_definition_without_cell_cascade(self):
        for span in ('0', '-1', '1.5', 'NaN', 'INF', 'nope', '3_0', ''):
            body = ('<table topLeftX="40" topLeftY="188" width="880" height="50"><colgroup>'
                    f'<col width="160"/><col span="{span}" width="240"/></colgroup>'
                    '<tr height="50">' + '<td><content fontSize="18"><p>文字</p></content></td>' * 4 + '</tr></table>')
            for namespace in (NS, ''):
                with self.subTest(span=span, namespace=namespace):
                    issues = self.review(slide(body, namespace))
                    self.assertEqual([(i['level'], i['code']) for i in issues], [('error', 'invalid_table_column_span')])
                    self.assertTrue(issues[0]['element'].endswith('/colgroup[1]/col[2]'))

    def test_column_expansion_has_a_distinct_local_resource_limit(self):
        from sml import MAX_EXPANDED_TABLE_COLUMNS, expanded_table_columns
        limit = MAX_EXPANDED_TABLE_COLUMNS
        table = ET.fromstring(f'<table><colgroup><col span="{limit}" width="1"/></colgroup></table>')
        self.assertEqual(len(expanded_table_columns(table)), limit)
        # Test both a huge single declaration and several declarations whose sum
        # exceeds the limit; neither should be expanded or cascade into cells.
        for columns in ('<col span="1e12" width="1"/>', f'<col width="1"/><col span="{limit}" width="1"/>'):
            body = f'<table topLeftX="40" topLeftY="40" width="880" height="50"><colgroup>{columns}</colgroup><tr height="50"><td/></tr></table>'
            issues = self.review(slide(body))
            self.assertEqual([i['code'] for i in issues], ['table_column_limit_exceeded'])
            self.assertIn('tool resource limit, not an SML schema restriction', issues[0]['message'])

    def test_bundled_templates_have_no_structural_resource_or_theme_errors(self):
        failures = []
        for path in sorted((ROOT / 'templates').glob('*.xml')):
            for module in (review_layout, review_design):
                failures.extend((path.name, item['code'], item['message']) for item in module.review_slide(path, tokens=self.tokens)['issues'] if item['level'] == 'error')
        self.assertEqual(failures, [])


if __name__ == '__main__':
    unittest.main()
