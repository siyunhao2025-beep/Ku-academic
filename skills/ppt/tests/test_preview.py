"""Behavioral tests for approximate previews, independent of Feishu services."""
import base64
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "xml2svg.py"
spec = importlib.util.spec_from_file_location("preview", SCRIPT)
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)
SVG = "{http://www.w3.org/2000/svg}"


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def render(self, content, namespace="", assets_dir=None):
        xml = self.folder / "example.xml"
        xml.write_text(f'<slide {namespace}><data>{content}</data></slide>', encoding="utf-8")
        issues = []
        result = preview.xml_to_svg(xml, assets_dir=assets_dir, diagnostics=issues)
        return ET.fromstring(result), issues

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str,args)], cwd=self.folder, text=True, capture_output=True)

    def test_namespace_equivalence_and_rich_text_preservation(self):
        body = ('<shape type="text" width="500" height="90"><content fontSize="20" color="#171717">'
                '<p>开头<span bold="true" color="rgb(255, 90, 95)">加粗<span italic="true">嵌套</span>尾</span>结尾 &amp; 完毕</p>'
                '<p textAlign="right">下一行<br/>换行后</p></content></shape>')
        outputs = []
        for ns in ('', 'xmlns="https://www.larkoffice.com/sml/2.0"'):
            tree, issues = self.render(body, ns)
            lines = tree.findall(f'.//{SVG}g[@data-preview-text="true"]/{SVG}text')
            texts = ["".join(line.itertext()) for line in lines]
            self.assertEqual(texts, ["开头加粗嵌套尾结尾 & 完毕", "下一行", "换行后"])
            self.assertEqual(lines[1].get("text-anchor"), "end")
            spans = lines[0].findall(f"{SVG}tspan")
            self.assertEqual(spans[1].get("font-weight"), "bold")
            self.assertEqual(spans[1].get("fill"), "#FF5A5F")
            self.assertEqual(spans[2].get("font-style"), "italic")
            self.assertEqual(issues, [])
            outputs.append(texts)
        xml = self.folder / "prefix.xml"
        xml.write_text('<s:slide xmlns:s="https://www.larkoffice.com/sml/2.0"><s:data>'+re.sub(r'(<\/?)([A-Za-z][\w]*)',r'\1s:\2',body)+'</s:data></s:slide>')
        tree = ET.fromstring(preview.xml_to_svg(xml, diagnostics=[]))
        self.assertEqual(["".join(e.itertext()) for e in tree.findall(f'.//{SVG}g[@data-preview-text="true"]/{SVG}text')], outputs[0])

    def test_wrapping_alignment_and_no_autofit(self):
        tree, issues = self.render('<shape type="text" topLeftX="10" topLeftY="20" width="40" height="100"><content fontSize="20" textAlign="center" verticalAlign="middle" autoFit="normal-auto-fit"><p>甲乙丙丁</p></content></shape>')
        lines = tree.findall(f'.//{SVG}g[@data-preview-text="true"]/{SVG}text')
        self.assertEqual(["".join(line.itertext()) for line in lines], ["甲乙","丙丁"])
        self.assertTrue(all(line.get("x") == "30" for line in lines))
        self.assertEqual(lines[0].find(f"{SVG}tspan").get("font-size"), "20")
        self.assertGreater(float(lines[0].get("y")), 37)
        self.assertEqual(issues, [])

    def test_speaker_notes_do_not_change_visual_output_or_diagnostics(self):
        for namespace in ('', 'xmlns="https://www.larkoffice.com/sml/2.0"'):
            with self.subTest(namespace=namespace):
                path = self.folder/'with-notes.xml'
                body = '<data><shape type="text" width="200" height="40"><content fontSize="16"><p>Visible title</p></content></shape></data>'
                path.write_text(f'<slide {namespace}>{body}</slide>')
                plain = preview.xml_to_svg(path, diagnostics=[])
                # Formatting and unsupported children inside notes must not affect
                # visual support warnings or leak into the SVG/metadata.
                note = '<note><content fontSize="2" color="hsl(0,50%,50%)"><p>Speaker-only source note <span underline="true">citation</span></p><unknown>private cue</unknown></content></note>'
                path.write_text(f'<slide {namespace}>{body}{note}</slide>')
                issues = []
                with_notes = preview.xml_to_svg(path, diagnostics=issues)
                self.assertEqual(issues, [])
                self.assertEqual(with_notes, plain)
                self.assertIn('Speaker-only source note', path.read_text())

    def test_table_retains_direct_and_rich_text(self):
        tree, _ = self.render('<table width="200"><colgroup><col width="200"/></colgroup><tr height="60"><td><content fontSize="14"><p>表格<span bold="true">内容</span>尾</p><p>第二行</p></content></td></tr></table>')
        lines = tree.findall(f'.//{SVG}g[@data-preview-text="true"]/{SVG}text')
        self.assertEqual(["".join(line.itertext()) for line in lines], ["表格内容尾","第二行"])

    def test_native_column_span_keeps_four_columns_at_their_actual_positions(self):
        labels = ['模式', '单模型对话', '多模型对话', 'Agent 工作']
        cells = ''.join(f'<td><content fontSize="18" textAlign="center"><p>{text}</p></content></td>' for text in labels)
        rows = f'<tr height="50">{cells}</tr>' * 5
        for span in ('3', '3.0', '3e0'):
            first_span = ' span="1"' if span == '3' else ''
            body = ('<table topLeftX="40" topLeftY="188" width="880" height="250"><colgroup>'
                    f'<col{first_span} width="160"/><col span="{span}" width="240"/></colgroup>{rows}</table>')
            for namespace in ('', 'xmlns="https://www.larkoffice.com/sml/2.0"'):
                with self.subTest(span=span, namespace=namespace):
                    tree, issues = self.render(body, namespace)
                    self.assertEqual(issues, [])
                    rects = tree.findall(f"{SVG}rect[@y='188']")
                    self.assertEqual([(float(e.get('x')), float(e.get('width'))) for e in rects],
                                     [(40, 160), (200, 240), (440, 240), (680, 240)])
                    lines = tree.findall(f'.//{SVG}g[@data-preview-text="true"]/{SVG}text')
                    self.assertEqual([''.join(e.itertext()) for e in lines], labels * 5)
                    self.assertEqual([float(e.get('x')) for e in lines], [120, 320, 560, 800] * 5)

    def test_invalid_column_span_does_not_draw_a_misaligned_table(self):
        for span in ('0', '-1', '1.5', 'NaN', 'INF', 'nope', '3_0', ''):
            body = ('<table topLeftX="40" topLeftY="188" width="880" height="50"><colgroup>'
                    f'<col width="160"/><col span="{span}" width="240"/></colgroup>'
                    '<tr height="50">' + '<td><content fontSize="18"><p>文字</p></content></td>' * 4 + '</tr></table>')
            for namespace in ('', 'xmlns="https://www.larkoffice.com/sml/2.0"'):
                with self.subTest(span=span, namespace=namespace):
                    tree, issues = self.render(body, namespace)
                    self.assertEqual([(i['severity'], i['code']) for i in issues], [('error', 'invalid_table_column_span')])
                    self.assertFalse(tree.findall(f'.//{SVG}g[@data-preview-text="true"]'))
                    self.assertIn('Invalid table column span', ''.join(tree.itertext()))

    def test_huge_column_span_reports_resource_limit_without_expansion(self):
        for namespace in ('', 'xmlns="https://www.larkoffice.com/sml/2.0"'):
            tree, issues = self.render('<table width="880"><colgroup><col width="1" span="1e12"/></colgroup>'
                                      '<tr height="50"><td><content fontSize="18"><p>Cell</p></content></td></tr></table>', namespace)
            self.assertEqual([(i['severity'], i['code']) for i in issues], [('error', 'table_column_limit_exceeded')])
            self.assertIn('tool resource limit, not an SML schema restriction', issues[0]['message'])
            self.assertFalse(tree.findall(f'.//{SVG}g[@data-preview-text="true"]'))

    def test_content_padding_changes_wrap_area_and_alignment(self):
        for align, expected_x in (('left',25), ('center',55), ('right',85)):
            with self.subTest(align=align):
                tree, issues = self.render(
                    '<shape type="text" topLeftX="10" topLeftY="20" width="100" height="60">'
                    f'<content fontSize="10" lineSpacing="multiple:1" textAlign="{align}" verticalAlign="middle" '
                    'paddingLeft="15" paddingRight="25" paddingTop="7" paddingBottom="13">'
                    '<p>甲乙丙丁戊己庚辛</p></content></shape>')
                self.assertEqual(issues, [])
                lines = tree.findall(f'.//{SVG}g[@data-preview-text="true"]/{SVG}text')
                self.assertEqual([''.join(line.itertext()) for line in lines], ['甲乙丙丁戊己','庚辛'])
                self.assertTrue(all(float(line.get('x')) == expected_x for line in lines))
                self.assertAlmostEqual(float(lines[0].get('y')),45.5)
                self.assertAlmostEqual(float(lines[1].get('y')),55.5)

    def test_native_table_padding_is_applied_once_and_defaults_to_eight(self):
        for attrs, expected_x in (('',18), ('paddingLeft="16" paddingRight="12" paddingTop="12" paddingBottom="12"',26),
                                  ('paddingLeft="0" paddingRight="0" paddingTop="0" paddingBottom="0"',10)):
            with self.subTest(attrs=attrs):
                tree, issues = self.render('<table topLeftX="10" topLeftY="20" width="100"><colgroup><col width="100"/></colgroup>'
                                          f'<tr height="60"><td><content fontSize="15" {attrs}><p>正文</p></content></td></tr></table>')
                self.assertEqual(issues, [])
                self.assertEqual(float(tree.find(f'.//{SVG}g[@data-preview-text="true"]/{SVG}text').get('x')),expected_x)

    def test_invalid_or_excessive_content_padding_is_reported(self):
        for value in ('-1', 'nan', '1585', '101'):
            with self.subTest(value=value):
                tree, issues = self.render(f'<shape type="text" width="100" height="60"><content paddingLeft="{value}"><p>Text</p></content></shape>')
                self.assertEqual([i['code'] for i in issues], ['invalid_text_padding'])
                self.assertEqual(issues[0]['severity'], 'error')
                self.assertFalse(tree.findall(f'.//{SVG}g[@data-preview-text="true"]'))

    def test_native_line_preserves_endpoints_defaults_and_paint_order(self):
        body = ('<line startX="120.5" startY="90" endX="35" endY="210" alpha="0.6"><border/></line>'
                '<shape type="ellipse" topLeftX="20" topLeftY="180" width="30" height="60"/>')
        for namespace in ('', 'xmlns="https://www.larkoffice.com/sml/2.0"'):
            with self.subTest(namespace=namespace):
                tree, issues = self.render(body, namespace)
                group = tree.find(f'{SVG}g[@data-preview-line="true"]')
                line = group.find(f'{SVG}line')
                self.assertEqual([float(line.get(k)) for k in ("x1", "y1", "x2", "y2")], [120.5, 90, 35, 210])
                self.assertEqual(line.get("stroke"), "#2B2F36")
                self.assertEqual(line.get("stroke-width"), "2")
                self.assertEqual(group.get("opacity"), "0.6")
                self.assertLess(list(tree).index(group), list(tree).index(tree.find(f'{SVG}ellipse')))
                self.assertEqual(issues, [])

    def test_arrowheads_follow_both_endpoints_in_all_directions(self):
        for end in ((150, 100), (50, 100), (100, 150), (100, 50), (140, 160), (40, 70)):
            with self.subTest(end=end):
                body = (f'<line type="line" startX="100" startY="100" endX="{end[0]}" endY="{end[1]}">'
                        '<border color="rgba(255, 90, 95, 1)" width="2"/>'
                        '<startArrow type="solid-triangle" widthScale="sm" heightScale="sm"/>'
                        '<endArrow type="solid-triangle" widthScale="lg" heightScale="lg"/></line>')
                tree, issues = self.render(body)
                arrows = {e.get("data-preview-arrow"): e for e in tree.findall(f'.//{SVG}polygon[@data-preview-arrow]')}
                self.assertEqual(set(arrows), {"start", "end"})
                lengths = {}
                for position, tip, direction in (("start", (100, 100), (100-end[0], 100-end[1])),
                                                  ("end", end, (end[0]-100, end[1]-100))):
                    points = [tuple(map(float, pair.split(","))) for pair in arrows[position].get("points").split()]
                    self.assertEqual(points[0], tip)
                    midpoint = tuple((points[1][i]+points[2][i])/2 for i in (0, 1))
                    back = (midpoint[0]-tip[0], midpoint[1]-tip[1])
                    self.assertLess(sum(back[i]*direction[i] for i in (0, 1)), 0)
                    self.assertAlmostEqual(back[0]*direction[1]-back[1]*direction[0], 0, delta=0.1)
                    lengths[position] = math.hypot(*back)
                    self.assertEqual(arrows[position].get("fill"), "#FF5A5F")
                self.assertGreater(lengths["end"], lengths["start"])
                self.assertEqual(issues, [])

    def test_basic_none_and_unsupported_arrowheads_are_explicit(self):
        tree, issues = self.render('<line startX="0" startY="0" endX="20" endY="30"><border/>'
                                  '<startArrow type="none"/><endArrow type="arrow"/></line>')
        arrow = tree.find(f'.//{SVG}path[@data-preview-arrow="end"]')
        self.assertIsNotNone(arrow)
        self.assertEqual(arrow.get("fill"), "none")
        self.assertEqual(issues, [])
        tree, issues = self.render('<line startX="0" startY="0" endX="20" endY="30"><border/>'
                                  '<endArrow type="empty-circle"/></line>')
        self.assertEqual([i["code"] for i in issues], ["unsupported_arrow"])
        self.assertIsNotNone(tree.find(f'.//{SVG}g[@data-preview-line="true"]/{SVG}line'))
        self.assertFalse([e for e in tree.iter() if e.get("data-preview-arrow")])

    def test_invalid_line_endpoints_are_not_silently_drawn(self):
        for attrs in ('startX="10" startY="20" endX="30"',
                      'startX="NaN" startY="20" endX="30" endY="40"',
                      'startX="10" startY="20" endX="inf" endY="40"',
                      'startX="10" startY="20" endX="10" endY="20"'):
            with self.subTest(attrs=attrs):
                tree, issues = self.render(f'<line {attrs}><border/></line>')
                self.assertTrue(any(i["code"] == "invalid_line_geometry" and i["severity"] == "error" for i in issues))
                self.assertIsNone(tree.find(f'.//{SVG}g[@data-preview-line="true"]'))

    def test_invalid_line_styles_and_zero_width(self):
        for children, attrs in (("", ""), ('<border width="-1"/>', ""),
                                ('<border width="NaN"/>', ""), ('<border width="1.5"/>', ""),
                                ('<border/>', 'alpha="2"'), ('<border/>', 'alpha="NaN"')):
            with self.subTest(children=children, attrs=attrs):
                tree, issues = self.render(f'<line startX="10" startY="20" endX="30" endY="40" {attrs}>{children}</line>')
                self.assertTrue(any(i["severity"] == "error" for i in issues))
                self.assertIsNone(tree.find(f'.//{SVG}g[@data-preview-line="true"]'))
        tree, issues = self.render('<line startX="0" startY="0" endX="20" endY="30"><border width="0"/>'
                                  '<endArrow type="solid-triangle"/></line>')
        self.assertEqual(issues, [])
        self.assertEqual(tree.find(f'.//{SVG}g[@data-preview-line="true"]/{SVG}line').get("stroke-width"), "0")
        self.assertFalse([e for e in tree.iter() if e.get("data-preview-arrow")])

    def test_cycle_template_keeps_native_connectors_under_nodes(self):
        source = ROOT / "templates" / "slide28.xml"
        data = preview.find(ET.parse(source).getroot(), "data")
        lines = preview.children(data, "line")
        shapes = preview.children(data, "shape")
        nodes = [e for e in shapes if e.get("type") in {"round-rect", "ellipse"}]
        self.assertEqual(len(nodes), 4)
        self.assertGreaterEqual(len(lines), len(nodes))
        self.assertTrue(all(list(data).index(line) < min(list(data).index(node) for node in nodes) for line in lines))
        self.assertFalse([e for e in shapes if e.get("type") == "rect" and
                          min(float(e.get("height", 20)), float(e.get("width", 20))) <= 3])
        boxes = [preview.geometry(node) for node in nodes]

        def vertex(point):
            px, py = point
            attached = []
            for index, (x, y, width, height) in enumerate(boxes):
                self.assertFalse(x+1e-6 < px < x+width-1e-6 and y+1e-6 < py < y+height-1e-6,
                                 "A connector endpoint must not penetrate a stage node")
                if x-1e-6 <= px <= x+width+1e-6 and y-1e-6 <= py <= y+height+1e-6:
                    attached.append(index)
            self.assertLessEqual(len(attached), 1)
            return ("stage", attached[0]) if attached else ("bend", round(px, 6), round(py, 6))

        # Contract the straight return-path segments into one logical edge. This
        # verifies a four-stage directed cycle without assuming a particular layout
        # or limiting a connector to a single segment.
        graph, incoming, endpoints = {}, {}, []
        for line in lines:
            coords = tuple(float(line.get(key)) for key in preview.LINE_ENDPOINTS)
            self.assertTrue(all(math.isfinite(value) for value in coords))
            self.assertNotEqual(coords[:2], coords[2:])
            start, end = vertex(coords[:2]), vertex(coords[2:])
            self.assertNotIn(start, graph, "Each stage/bend must have one outgoing segment")
            graph[start] = end
            incoming[end] = incoming.get(end, 0)+1
            endpoints.append(coords)
            arrow = preview.find(line, "endArrow")
            if end[0] == "stage":
                self.assertIsNotNone(arrow, "Every arrival at a stage must show its direction")
                self.assertEqual(arrow.get("type"), "solid-triangle")
        self.assertEqual(set(graph), set(incoming), "The return path must not have a dangling bend")
        self.assertTrue(all(count == 1 for count in incoming.values()))
        successors = {}
        for index in range(len(nodes)):
            origin = ("stage", index)
            current, seen = graph[origin], {origin}
            while current[0] == "bend":
                self.assertNotIn(current, seen, "A return path must reach another stage")
                seen.add(current)
                current = graph[current]
            self.assertNotEqual(current, origin)
            successors[origin] = current
        current, visited = ("stage", 0), set()
        for _ in nodes:
            self.assertNotIn(current, visited)
            visited.add(current)
            current = successors[current]
        self.assertEqual(current, ("stage", 0))
        self.assertEqual(len(visited), len(nodes))

        issues = []
        tree = ET.fromstring(preview.xml_to_svg(source, diagnostics=issues))
        self.assertEqual(issues, [])
        rendered = tree.findall(f'{SVG}g[@data-preview-line="true"]/{SVG}line')
        self.assertEqual(len(rendered), len(lines))
        for expected, actual in zip(endpoints, rendered):
            self.assertEqual(tuple(float(actual.get(k)) for k in ("x1", "y1", "x2", "y2")), expected)
        self.assertEqual(len(tree.findall(f'.//{SVG}polygon[@data-preview-arrow="end"]')), len(nodes))

    def test_all_five_library_charts_have_real_marks(self):
        chart_types, marks = [], []
        expected_types = []
        expected_marks = {'bar':0,'line':0,'point':0,'slice':0}
        for page in range(21,25):
            diagnostics = []
            source = ET.parse(ROOT/'templates'/f'slide{page}.xml').getroot()
            source_charts = [e for e in source.iter() if preview.local_name(e.tag) == 'chart']
            for source_chart in source_charts:
                kind = preview.find(source_chart,'chartPlotArea/chartPlot').get('type')
                self.assertIn(kind,{'column','line','pie'})
                expected_types.append(kind)
                fields = preview.children(preview.find(source_chart,'chartData/dim2'),'chartField')
                series = [[float(value) for value in ''.join(field.itertext()).split(',')] for field in fields]
                if kind == 'column':
                    expected_marks['bar'] += sum(len(values) for values in series)
                elif kind == 'line':
                    expected_marks['line'] += len(series)
                    expected_marks['point'] += sum(len(values) for values in series)
                else:
                    expected_marks['slice'] += sum(value > 0 for value in series[0])
            tree = ET.fromstring(preview.xml_to_svg(ROOT / "templates" / f"slide{page}.xml", diagnostics=diagnostics))
            self.assertFalse(any(issue["severity"] == "error" for issue in diagnostics))
            charts = tree.findall(f'.//{SVG}g[@data-preview-chart]')
            chart_types.extend(chart.get("data-preview-chart") for chart in charts)
            marks.extend(e.get("data-chart-mark") for e in tree.iter() if e.get("data-chart-mark"))
            if page == 21:
                source_chart = source_charts[0]
                field = preview.find(source_chart,'chartData/dim2/chartField')
                values = [float(value) for value in ''.join(field.itertext()).split(',')]
                axes = preview.children(preview.find(source_chart,'chartPlotArea/chartAxes'),'chartAxis')
                numeric_axis = next(axis for axis in axes if axis.get('type') == 'y')
                low, high = float(numeric_axis.get('min')), float(numeric_axis.get('max'))
                bars = tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]')
                self.assertEqual(len(bars),len(values))
                clip_height = float(tree.find(f'.//{SVG}clipPath/{SVG}rect').get('height'))
                baseline = min(high,max(low,0))
                for value,bar in zip(values,bars):
                    expected_height = abs(min(high,max(low,value))-baseline)/(high-low)*clip_height
                    self.assertAlmostEqual(float(bar.get('height')),expected_height,places=3)
                    self.assertIn(f': {value:g}',bar.find(f'{SVG}title').text)
                labels = tree.findall(f'.//{SVG}text[@data-chart-value]')
                self.assertEqual([float(label.get('data-chart-value')) for label in labels],values)
                self.assertEqual([label.text for label in labels],[f'{value:.0f}' for value in values])
                tick_values = [float(tick.get('data-axis-value')) for tick in tree.findall(f'.//{SVG}text[@data-chart-axis="y"]')]
                self.assertEqual((min(tick_values),max(tick_values)),(low,high))
        self.assertEqual(len(expected_types),5)
        self.assertEqual(chart_types,expected_types)
        for kind,count in expected_marks.items():
            self.assertEqual(marks.count(kind),count)

    def chart_body(self, values="9,5,4,2,4,13", *, y_axis='min="0" max="15"',
                   bars='', labels='', extra_axis='', kind='column', second_series=''):
        categories = ','.join(f'M{i+1}' for i in range(len(values.split(','))))
        return (f'<chart topLeftX="40" topLeftY="202" width="650" height="250"><chartPlotArea>'
                f'<chartPlot type="{kind}">{bars}{labels}</chartPlot><chartAxes>'
                f'<chartAxis type="x" {extra_axis}><chartLabel fontSize="12" angle="0"/></chartAxis>'
                f'<chartAxis type="y" position="left" {y_axis}><chartLabel fontSize="12" format="0"/></chartAxis>'
                f'</chartAxes></chartPlotArea><chartData><dim1><chartField>{categories}</chartField></dim1>'
                f'<dim2><chartField name="Count" valueType="number">{values}</chartField>{second_series}</dim2>'
                '</chartData></chart>')

    def horizontal_chart_body(self, values='223,60', *, limits='', bar_width=36,
                              series_color='', point_index=2, kind='bar'):
        # Same supported schema shape as the native release-record comparison:
        # one-based series/bar overrides, outside counts, logical x/y axes.
        count = len(values.split(','))
        categories = '非预发布,预发布标记' if count == 2 else ','.join(f'C{i+1}' for i in range(count))
        return (f'<chart topLeftX="340" topLeftY="181" width="580" height="227">'
                f'<chartPlotArea><chartPlot type="{kind}">'
                f'<chartBars color="rgba(67,103,199,1)" width="{bar_width}"/>'
                '<chartLabels position="outside" value="true" category="false" fontSize="15" '
                'color="rgba(30,34,44,1)" format="0"/>'
                f'<chartSeriesList><chartSeries index="1"><chartBars {series_color}>'
                f'<chartBar index="{point_index}" color="rgba(233,70,93,1)"/>'
                '</chartBars></chartSeries></chartSeriesList></chartPlot><chartAxes>'
                '<chartAxis type="x"><chartLabel fontSize="12" color="rgba(93,101,116,1)"/></chartAxis>'
                f'<chartAxis type="y" {limits}><chartLabel fontSize="12" color="rgba(93,101,116,1)"/></chartAxis>'
                '</chartAxes></chartPlotArea><chartData><dim1><chartField name="发布标记" valueType="string">'
                f'{categories}</chartField></dim1><dim2><chartField name="可见记录" valueType="number">'
                f'{values}</chartField></dim2></chartData><chartStyle><chartBackground color="rgba(255,255,255,1)"/>'
                '<chartBorder width="0"/><chartColorTheme><color value="rgba(67,103,199,1)"/>'
                '</chartColorTheme></chartStyle></chart>')

    def test_horizontal_bars_preserve_values_orientation_labels_and_point_color(self):
        for namespace in ('', 'xmlns="https://www.larkoffice.com/sml/2.0"'):
            with self.subTest(namespace=namespace):
                tree, issues = self.render(self.horizontal_chart_body(), namespace)
                self.assertEqual(issues, [])
                self.assertEqual(tree.get('data-preview-approximate'), 'true')
                self.assertIn('Feishu', tree.find(f'{SVG}desc').text)
                self.assertIsNotNone(tree.find(f'.//{SVG}g[@data-preview-chart="bar"]'))
                bars = tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]')
                self.assertEqual(len(bars), 2)
                self.assertTrue(all(b.get('data-chart-orientation') == 'horizontal' for b in bars))
                self.assertTrue(all(b.get('height') == '36' for b in bars))
                self.assertAlmostEqual(float(bars[0].get('width')) / float(bars[1].get('width')), 223/60, places=4)
                self.assertEqual(bars[0].get('x'), bars[1].get('x'))
                self.assertLess(float(bars[0].get('y')), float(bars[1].get('y')))
                self.assertEqual([b.get('fill') for b in bars], ['#4367C7', '#E9465D'])
                baseline = tree.find(f'.//{SVG}line[@data-chart-zero-baseline="true"]')
                self.assertEqual(baseline.get('x1'), baseline.get('x2'))
                self.assertEqual(baseline.get('x1'), bars[0].get('x'))
                labels = tree.findall(f'.//{SVG}text[@data-chart-value]')
                self.assertEqual([e.text for e in labels], ['223', '60'])
                for bar, label in zip(bars, labels):
                    self.assertEqual(label.get('font-size'), '15')
                    self.assertEqual(label.get('fill'), '#1E222C')
                    self.assertEqual(label.get('text-anchor'), 'start')
                    self.assertGreater(float(label.get('x')), float(bar.get('x'))+float(bar.get('width')))
                category_labels = tree.findall(f'.//{SVG}text[@data-chart-axis="x"]')
                self.assertEqual([e.text for e in category_labels], ['非预发布', '预发布标记'])
                self.assertTrue(all(float(e.get('x')) < float(bars[0].get('x')) for e in category_labels))
                ticks = tree.findall(f'.//{SVG}text[@data-chart-axis="y"]')
                self.assertEqual([e.text for e in ticks], ['0','50','100','150','200','250'])
                clipped = tree.find(f'.//{SVG}g[@data-chart-marks="true"]')
                self.assertFalse(clipped.findall(f'{SVG}text[@data-chart-value]'))

    def test_horizontal_negative_zero_and_positive_values_share_a_zero_baseline(self):
        tree, issues = self.render(self.horizontal_chart_body('-5,0,10', limits='min="-5" max="10"', bar_width=20))
        self.assertEqual(issues, [])
        bars = tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]')
        baseline = float(tree.find(f'.//{SVG}line[@data-chart-zero-baseline="true"]').get('x1'))
        self.assertAlmostEqual(float(bars[0].get('x'))+float(bars[0].get('width')), baseline, places=3)
        self.assertEqual(float(bars[1].get('width')), 0)
        self.assertAlmostEqual(float(bars[1].get('x')), baseline, places=3)
        self.assertAlmostEqual(float(bars[2].get('x')), baseline, places=3)
        self.assertAlmostEqual(float(bars[2].get('width'))/float(bars[0].get('width')), 2, places=4)
        labels = tree.findall(f'.//{SVG}text[@data-chart-value]')
        self.assertEqual([e.text for e in labels], ['-5','0','10'])
        self.assertEqual(labels[0].get('text-anchor'), 'end')
        self.assertLess(float(labels[0].get('x')), float(bars[0].get('x')))

    def test_fill_overrides_are_one_based_and_bounded_to_bar_and_column_charts(self):
        tree, issues = self.render(self.horizontal_chart_body(series_color='color="rgba(30,126,130,1)"'))
        self.assertEqual(issues, [])
        bars = tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]')
        self.assertEqual([b.get('fill') for b in bars], ['#1E7E82', '#E9465D'])
        for index in (0, 3):
            with self.subTest(index=index):
                tree, issues = self.render(self.horizontal_chart_body(point_index=index))
                self.assertIn('invalid_chart_bar', [i['code'] for i in issues])
                self.assertFalse(tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]'))
        tree, issues = self.render(self.horizontal_chart_body(kind='column'))
        self.assertEqual(issues, [])
        bars = tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]')
        self.assertEqual([b.get('fill') for b in bars], ['#4367C7', '#E9465D'])
        self.assertTrue(all(b.get('width') == '36' for b in bars))
        self.assertNotEqual(bars[0].get('height'), bars[1].get('height'))
        _, issues = self.render(self.horizontal_chart_body(kind='line'))
        self.assertIn('unsupported_element', [i['code'] for i in issues])

    def test_horizontal_template_one_decimal_labels_preserve_trailing_zero(self):
        body = self.horizontal_chart_body('1,3.2').replace('format="0"', 'format="0.0"')
        tree, issues = self.render(body)
        self.assertEqual(issues, [])
        labels = tree.findall(f'.//{SVG}text[@data-chart-value]')
        self.assertEqual([e.text for e in labels], ['1.0','3.2'])
        bars = tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]')
        self.assertAlmostEqual(float(bars[1].get('width'))/float(bars[0].get('width')),3.2,places=4)
        self.assertEqual(preview.chart_number(1.05, '0.0'), '1.1')

    def test_series_label_override_cannot_silently_look_supported(self):
        # Native series-level labels may override the global visibility/style.
        # The preview deliberately supports only plot-level labels, so this
        # valid override must produce an actionable approximation diagnostic.
        for kind in ('bar', 'column'):
            for namespace in ('', 'xmlns="https://www.larkoffice.com/sml/2.0"'):
                with self.subTest(kind=kind, namespace=namespace):
                    body = self.horizontal_chart_body(kind=kind)
                    _, control_issues = self.render(body, namespace)
                    self.assertEqual(control_issues, [])
                    body = body.replace('</chartSeries>',
                        '<chartLabels position="outside" value="false" category="false" '
                        'series="false" percentage="false"/></chartSeries>')
                    tree, issues = self.render(body, namespace)
                    self.assertEqual([(i['severity'], i['code'], i['element']) for i in issues],
                                     [('warning', 'unsupported_series_chart_labels', 'chartLabels')])
                    self.assertIn('plot-level labels', issues[0]['message'])
                    self.assertEqual([e.text for e in tree.findall(f'.//{SVG}text[@data-chart-value]')],
                                     ['223', '60'])
                    self.assertEqual(tree.get('data-preview-approximate'), 'true')

    def test_horizontal_clipping_and_wide_axis_limits_are_safe(self):
        tree, issues = self.render(self.horizontal_chart_body('-5,0,10', limits='min="-2" max="8"', bar_width=20))
        self.assertEqual([i['code'] for i in issues], ['chart_data_clipped'])
        self.assertEqual([e.text for e in tree.findall(f'.//{SVG}text[@data-chart-value]')], ['0'])
        tree, issues = self.render(self.horizontal_chart_body(limits='min="0" max="1000000000"'))
        self.assertEqual(issues, [])
        self.assertLessEqual(len(tree.findall(f'.//{SVG}text[@data-chart-axis="y"]')), 7)
        for width in (-1, 300):
            tree, issues = self.render(self.horizontal_chart_body(bar_width=width))
            self.assertTrue(any(i['severity'] == 'error' for i in issues))
            self.assertFalse(tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]'))

    def test_explicit_axis_bar_width_color_and_outside_count_labels(self):
        body = self.chart_body(bars='<chartBars width="44" color="rgba(105,105,112,1)"/>',
                               labels='<chartLabels position="outside" value="true" fontSize="12" color="rgba(72,72,78,1)" format="0"/>')
        for namespace in ('', 'xmlns="https://www.larkoffice.com/sml/2.0"'):
            with self.subTest(namespace=namespace):
                tree, issues = self.render(body, namespace)
                self.assertEqual(issues, [])
                bars = tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]')
                labels = tree.findall(f'.//{SVG}text[@data-chart-value]')
                self.assertEqual([e.text for e in labels], ['9','5','4','2','4','13'])
                ticks = tree.findall(f'.//{SVG}text[@data-chart-axis="y"]')
                self.assertEqual([tick.text for tick in ticks], ['0','5','10','15'])
                for value, bar, label in zip((9,5,4,2,4,13),bars,labels):
                    self.assertEqual(bar.get('width'),'44')
                    self.assertEqual(bar.get('fill'),'#696970')
                    self.assertAlmostEqual(float(bar.get('height')), value/15*200, places=3)
                    self.assertAlmostEqual(float(label.get('x')),float(bar.get('x'))+22, places=3)
                    self.assertAlmostEqual(float(label.get('y')),float(bar.get('y'))-5, places=3)
                    self.assertEqual(label.get('font-size'),'12')
                    self.assertEqual(label.get('fill'),'#48484E')
                # Value labels must remain outside the plot clipping group.
                clipped = tree.find(f'.//{SVG}g[@data-chart-marks="true"]')
                self.assertFalse(clipped.findall(f'{SVG}text[@data-chart-value]'))

    def test_negative_value_labels_and_positive_axis_minimum(self):
        body = self.chart_body('-5,5,15', y_axis='min="-5" max="15"',
                               labels='<chartLabels position="outside" value="true" fontSize="12"/>')
        tree, issues = self.render(body)
        self.assertEqual(issues, [])
        bars = tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]')
        labels = tree.findall(f'.//{SVG}text[@data-chart-value]')
        self.assertGreater(float(labels[0].get('y')),float(bars[0].get('y'))+float(bars[0].get('height')))
        for bar,label in zip(bars[1:],labels[1:]):
            self.assertLess(float(label.get('y')),float(bar.get('y')))
        tree, issues = self.render(self.chart_body('10,15',y_axis='min="5" max="15"'))
        self.assertEqual(issues, [])
        bars = tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]')
        self.assertAlmostEqual(float(bars[1].get('height'))/float(bars[0].get('height')),2)

    def test_grouped_bar_gap_is_relative_to_pixel_width(self):
        second = '<chartField name="Second" valueType="number">4,8</chartField>'
        for style in ('width="20" gap="0.5"','gap="0.5"'):
            with self.subTest(style=style):
                tree, issues = self.render(self.chart_body('5,10',bars=f'<chartBars {style}/>',second_series=second))
                self.assertEqual(issues, [])
                bars = tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]')
                # Bars are serialized by series, so the paired same-category bars are 0/2.
                width = float(bars[0].get('width'))
                gap = float(bars[2].get('x'))-float(bars[0].get('x'))-width
                self.assertAlmostEqual(gap/width,.5,places=4)
                if 'width' in style:
                    self.assertEqual(width,20)

    def test_fixed_single_series_gap_boundary_is_explicit(self):
        tree, issues = self.render(self.chart_body('5,10',bars='<chartBars width="20" gap="0.5"/>'))
        self.assertEqual([i['code'] for i in issues],['chart_bar_gap_approximation'])
        self.assertEqual(tree.find(f'.//{SVG}rect[@data-chart-mark="bar"]').get('width'),'20')

    def test_invalid_axis_and_bar_parameters_are_not_rendered_as_valid(self):
        bodies = [self.chart_body(y_axis=attrs) for attrs in ('min="15" max="0"','min="1.5" max="15"','max="nan"')]
        bodies += [self.chart_body(bars=f'<chartBars {attrs}/>') for attrs in ('width="-1"','width="1.5"','gap="1.1"','gap="nan"','width="600"')]
        for body in bodies:
            with self.subTest(body=body):
                tree, issues = self.render(body)
                self.assertTrue(any(i['severity'] == 'error' for i in issues))
                self.assertFalse(tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]'))
        tree, issues = self.render(self.chart_body(bars='<chartBars width="0"/>'))
        self.assertEqual(issues,[])
        self.assertTrue(all(e.get('width') == '0' for e in tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]')))

    def test_unsupported_label_variants_and_category_limits_are_explicit(self):
        for attrs in ('position="inside"','position="outside" percentage="true"',
                      'position="outside" format="0%"','position="outside" category="true"'):
            with self.subTest(attrs=attrs):
                tree, issues = self.render(self.chart_body(labels=f'<chartLabels {attrs}/>'))
                self.assertIn('unsupported_chart_labels',[i['code'] for i in issues])
                self.assertFalse(tree.findall(f'.//{SVG}text[@data-chart-value]'))
        _, issues = self.render(self.chart_body(extra_axis='min="0" max="2"'))
        self.assertIn('unsupported_axis_range',[i['code'] for i in issues])
        _, issues = self.render(self.chart_body().replace('angle="0"','angle="30"').replace('format="0"','format="0%"'))
        self.assertTrue({'unsupported_axis_format','unsupported_axis_label_angle'} <= {i['code'] for i in issues})

    def test_line_bounds_clip_marks_and_warn_about_excluded_data(self):
        tree, issues = self.render(self.chart_body('0,4',kind='line',y_axis='min="1" max="3"'))
        self.assertEqual([i['code'] for i in issues],['chart_data_clipped'])
        ticks = tree.findall(f'.//{SVG}text[@data-chart-axis="y"]')
        self.assertEqual(ticks[0].get('data-axis-value'),'1')
        self.assertEqual(ticks[-1].get('data-axis-value'),'3')
        group = tree.find(f'.//{SVG}g[@data-chart-marks="true"]')
        self.assertTrue(group.get('clip-path').startswith('url(#preview-chart-clip-'))
        clip = tree.find(f'.//{SVG}clipPath/{SVG}rect')
        line = tree.find(f'.//{SVG}polyline[@data-chart-mark="line"]')
        ys = [float(point.split(',')[1]) for point in line.get('points').split()]
        self.assertGreater(ys[0],float(clip.get('y'))+float(clip.get('height')))
        self.assertLess(ys[1],float(clip.get('y')))

    def test_explicitly_disabled_pie_labels_preserve_slices_and_data(self):
        body = self.chart_body('988,4,4,4',kind='pie',y_axis='')
        default_tree, _ = self.render(body)
        self.assertTrue([e for e in default_tree.findall(f'.//{SVG}text') if '%' in (e.text or '')])
        hidden = '<chartLabels position="inside" value="false" percentage="false" category="false" series="false"/>'
        tree, issues = self.render(self.chart_body('988,4,4,4',kind='pie',y_axis='',labels=hidden))
        self.assertEqual([issue['code'] for issue in issues],['native_label_visibility_unverified'])
        self.assertEqual(issues[0]['severity'],'warning')
        self.assertIn('restoring default percentages',issues[0]['message'])
        self.assertIn('actual Feishu screenshot',issues[0]['message'])
        self.assertEqual(len([e for e in tree.iter() if e.get('data-chart-mark') == 'slice']),4)
        self.assertFalse([e for e in tree.findall(f'.//{SVG}text') if '%' in (e.text or '')])
        self.assertTrue([e for e in tree.findall(f'.//{SVG}title') if '988' in (e.text or '')])

    def test_all_templates_parse_with_images_and_approximation_label(self):
        paths = list((ROOT / "templates").glob("*.xml"))
        self.assertEqual(len(paths), 51)
        for path in paths:
            with self.subTest(path=path.name):
                issues = []
                tree = ET.fromstring(preview.xml_to_svg(path,diagnostics=issues))
                self.assertEqual(tree.get("data-preview-approximate"), "true")
                self.assertIn("Approximate preview",tree.find(f"{SVG}title").text)
                self.assertTrue(tree.findall(f".//{SVG}image"))
                expected = []
                source = ET.parse(path).getroot()
                if any(preview.local_name(e.tag) == 'chartSmooth' for e in preview.find(source,'data').iter()):
                    expected.append(('warning','chart_smoothing_approximation','chartSmooth'))
                # This exact native outside category+percentage pie layout is
                # intentionally left to real Feishu screenshot verification.
                if path.name == 'slide23.xml':
                    expected.append(('warning','unsupported_chart_labels','chartLabels'))
                self.assertEqual([(i['severity'],i['code'],i['element']) for i in issues],expected)
                if path.name == 'slide23.xml':
                    native_label = preview.find(ET.parse(path).getroot(),'data/chart/chartPlotArea/chartPlot/chartLabels')
                    self.assertEqual({key:native_label.get(key) for key in ('position','category','percentage','value')},
                                     {'position':'outside','category':'true','percentage':'true','value':'false'})
                    self.assertIn('this label variant is omitted',issues[0]['message'])

    def test_missing_image_is_visible_and_an_error(self):
        tree, issues = self.render('<img src="@./missing.png" width="100" height="40"/>')
        self.assertEqual(issues[0]["code"], "missing_image")
        self.assertEqual(issues[0]["severity"], "error")
        self.assertIsNotNone(tree.find(f'.//{SVG}g[@data-preview-placeholder="true"]'))
        result = self.cli("--input",self.folder/"example.xml","--output-dir",self.folder/"svg","--json")
        report = json.loads(result.stdout)
        self.assertEqual(result.returncode,1)
        self.assertFalse(report["passed"])
        self.assertEqual(report["summary"]["errors"],1)
        self.assertEqual(result.stderr,"")

    def test_xml_relative_images_override_assets(self):
        assets = self.folder / "assets"
        assets.mkdir()
        # Bytes need not be decoded by this test: the source chosen is the behavior under test.
        (assets / "picture.png").write_bytes(b"fallback")
        (self.folder / "picture.png").write_bytes(b"local")
        tree, issues = self.render('<img src="@./picture.png"/>', assets_dir=assets)
        self.assertEqual(issues,[])
        href = tree.find(f".//{SVG}image").get("href")
        self.assertEqual(base64.b64decode(href.split(",")[1]),b"local")
        (self.folder / "picture.png").unlink()
        tree, issues = self.render('<img src="@./picture.png"/>', assets_dir=assets)
        self.assertEqual(base64.b64decode(tree.find(f".//{SVG}image").get("href").split(",")[1]),b"fallback")

    def test_cli_cross_cwd_uses_installed_assets(self):
        output = self.folder / "other" / "svg"
        result = self.cli("--input",ROOT/"templates"/"slide21.xml","--output-dir",output,"--json")
        self.assertEqual(result.returncode,0,result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["summary"],{"files":1,"errors":0,"warnings":0})
        self.assertTrue((output/"slide21.svg").is_file())
        self.assertEqual(result.stderr,"")

    def test_cli_directory_accepts_non_slide_names(self):
        source = self.folder / "input"
        source.mkdir()
        (source/"custom.xml").write_text('<slide><data/></slide>')
        result = self.cli("--dir",source,"--output-dir",self.folder/"svg","--json")
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue((self.folder/"svg"/"custom.svg").exists())

    def test_input_failures_are_json_and_nonzero(self):
        for source in (self.folder/"missing.xml",self.folder/"bad.xml"):
            if source.name == "bad.xml":
                source.write_text('<broken')
            result = self.cli("--input",source,"--json")
            self.assertEqual(result.returncode,1)
            self.assertFalse(json.loads(result.stdout)["passed"])
        result = self.cli("--dir",self.folder/"nonexistent","--json")
        self.assertEqual(result.returncode,1)
        self.assertEqual(json.loads(result.stdout)["summary"]["errors"],1)

    def test_unknown_element_shape_and_attribute_are_reported(self):
        _, issues = self.render('<shape type="rect" rotation="30"/><shape type="star"/><video src="movie.mp4"/>')
        self.assertEqual({issue["code"] for issue in issues},{"unsupported_attribute","unsupported_shape","unsupported_element"})

    def test_invalid_chart_data_is_not_drawn_as_valid(self):
        for values in ("1", "1,nan", "a,2"):
            tree, issues = self.render('<chart width="200" height="100"><chartPlotArea><chartPlot type="column"/></chartPlotArea><chartData><dim1><chartField>A,B</chartField></dim1><dim2><chartField>'+values+'</chartField></dim2></chartData></chart>')
            self.assertEqual(issues[0]["code"],"invalid_chart_data")
            self.assertEqual(issues[0]["severity"],"error")
            self.assertFalse(tree.findall(f'.//{SVG}rect[@data-chart-mark="bar"]'))

    def test_rgb_rgba_and_transparency(self):
        self.assertEqual(preview.rgba_to_hex("rgb(255, 90, 95)"),"#FF5A5F")
        self.assertEqual(preview.rgba_to_hex("rgba(0, 0, 0, 0)"),"#00000000")
        self.assertEqual(preview.rgba_to_hex("#ABCD"),"#ABCD")

    def test_invalid_geometry_and_unsupported_color_are_explicit(self):
        _, issues = self.render('<shape type="rect" topLeftX="NaN" width="-2"><fill><fillColor color="hsl(0,100%,50%)"/></fill></shape>')
        self.assertEqual({issue["code"] for issue in issues},{"invalid_numeric_attribute","unsupported_color"})
        self.assertEqual(sum(issue["severity"] == "error" for issue in issues),2)

    def test_single_slice_pie_and_negative_columns(self):
        for kind,values,expected in (("pie","100,0","slice"),("column","-5,10","bar")):
            tree, issues = self.render(f'<chart width="200" height="120"><chartPlotArea><chartPlot type="{kind}"/></chartPlotArea><chartData><dim1><chartField>A,B</chartField></dim1><dim2><chartField>{values}</chartField></dim2></chartData></chart>')
            self.assertEqual(issues,[])
            marks = [e for e in tree.iter() if e.get("data-chart-mark") == expected]
            self.assertEqual(len(marks),1 if kind == "pie" else 2)
            if kind == "pie":
                self.assertEqual(marks[0].tag,f"{SVG}circle")
            else:
                self.assertTrue(all(float(mark.get("height")) > 0 for mark in marks))


if __name__ == "__main__":
    unittest.main()
