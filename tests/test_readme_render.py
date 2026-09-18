"""Guards README.md against a rendering failure that already shipped once.

The bug: a two-column layout was written as HTML with blank lines inside the
<table> element. In GFM, a blank line ends an HTML block, and the next line --
indented six spaces for readability -- no longer matched the HTML-block start
condition, so it fell through to "indented code block" and rendered as literal
markup. The page looked like a wall of <td> tags.

The rule enforced here is the GFM rule, not a cruder approximation: a line is
only at risk if it is indented 4+ spaces *outside* an open HTML block. Inside a
contiguous HTML block, indentation is passed through raw and is harmless.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / 'README.md'

# GFM HTML-block type 6 tag names.
BLOCK_TAGS = (
    'address', 'article', 'aside', 'blockquote', 'body', 'caption', 'center', 'col',
    'colgroup', 'dd', 'details', 'dialog', 'dir', 'div', 'dl', 'dt', 'fieldset',
    'figcaption', 'figure', 'footer', 'form', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'head', 'header', 'hr', 'html', 'iframe', 'legend', 'li', 'link', 'main', 'menu',
    'nav', 'ol', 'p', 'section', 'summary', 'table', 'tbody', 'td', 'tfoot', 'th',
    'thead', 'tr', 'ul',
)


def render_risk_lines(text):
    """Lines that would render as an indented code block, with GFM block tracking.

    A blank line closes an open HTML block, so indentation only becomes dangerous
    once that block has been closed.
    """
    offenders = []
    in_html = False
    fenced = False
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith('```') or stripped.startswith('~~~'):
            fenced = not fenced
            continue
        if fenced or not stripped:
            in_html = False
            continue
        expanded = raw.replace('\t', '    ')
        indent = len(expanded) - len(expanded.lstrip(' '))
        lowered = stripped.lower()
        if not in_html and indent <= 3 and any(
                lowered.startswith('<%s' % tag) for tag in BLOCK_TAGS):
            in_html = True
            continue
        if in_html:
            continue
        if indent >= 4:
            offenders.append((number, raw[:60]))
    return offenders


class ReadmeRenderTests(unittest.TestCase):
    def test_no_line_renders_as_an_indented_code_block(self):
        offenders = render_risk_lines(README.read_text(encoding='utf-8'))
        self.assertEqual(
            offenders, [],
            'these lines are indented 4+ spaces outside any open HTML block and will '
            'render as literal code instead of content')

    def test_hero_table_is_one_contiguous_block(self):
        """Blank lines inside the hero <table> are what broke rendering before."""
        text = README.read_text(encoding='utf-8')
        start = text.find('<table')
        end = text.find('</table>', start)
        self.assertGreater(start, -1, 'hero <table> not found')
        self.assertGreater(end, start, 'hero </table> not found')
        # end points at the '<' of </table>, so drop the trailing partial line
        # (its leading indentation would otherwise look like a blank line).
        region = text[start:end]
        cut = region.rfind('\n')
        if cut != -1:
            region = region[:cut + 1]
        blanks = [line for line in region.splitlines() if not line.strip()]
        self.assertEqual(blanks, [],
                         'a blank line inside the hero <table> splits the HTML block, '
                         'and the indented lines after it render as code')

    def test_hero_references_the_author_photo(self):
        self.assertIn('assets/author.jpg', README.read_text(encoding='utf-8'))

    def test_guard_detects_the_original_bug(self):
        broken = '<table>\n  <tr>\n\n      <td>x</td>\n  </tr>\n</table>\n'
        self.assertEqual(render_risk_lines(broken), [(4, '      <td>x</td>')])

    def test_guard_allows_a_contiguous_indented_block(self):
        fine = '<table>\n  <tr>\n    <td>x</td>\n  </tr>\n</table>\n'
        self.assertEqual(render_risk_lines(fine), [])

    def test_guard_ignores_indentation_inside_code_fences(self):
        fenced = 'intro\n\n```text\n    indented in a fence is fine\n```\n'
        self.assertEqual(render_risk_lines(fenced), [])


if __name__ == '__main__':
    unittest.main()
