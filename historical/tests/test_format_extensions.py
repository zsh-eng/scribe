"""Archive-only format and loss-audit regressions, with no database calls."""
import gzip
import json
from pathlib import Path
import unittest

from legacy_hansard import parse_legacy

FIXTURES = Path(__file__).parent / 'fixtures' / 'reports'


def fixture(date):
    return json.loads(gzip.decompress((FIXTURES / f'{date}.json.gz').read_bytes()))['htmlFullContent']


class FormatExtensionsTests(unittest.TestCase):
    def test_word_export_retains_report_and_questions(self):
        sitting = parse_legacy('14-02-2011', fixture('14-02-2011'))
        self.assertEqual('word-export', sitting.parse_audit['format'])
        self.assertEqual(53, len(sitting.sections))
        self.assertEqual((91, 1), (len(sitting.present_members), len(sitting.absent_members)))
        self.assertEqual(0, sitting.parse_audit['text_coverage']['tokens_outside_sections'])
        by_title = {section['title']: section for section in sitting.sections}
        self.assertEqual('OA', by_title['RECENT DEATHS OF NSMEN']['section_type'])
        self.assertEqual('WANA', by_title['PATERNITY LEAVE AS PART OF EMPLOYEE BENEFITS']['section_type'])
        self.assertIn('Report preamble', by_title)
        self.assertIn('ATTENDANCE', by_title)
        self.assertEqual('attendance', by_title['ATTENDANCE']['category'])
        self.assertIn('safety time-out', by_title['RECENT DEATHS OF NSMEN']['content_plain'])

    def test_institution_is_separate_from_source_parliament_number(self):
        sitting = parse_legacy('22-04-1955', fixture('22-04-1955'))
        self.assertEqual('Legislative Assembly', sitting.metadata['institution']['name'])
        self.assertEqual('report masthead', sitting.metadata['institution']['evidence'])
        modern = parse_legacy('09-01-2012', fixture('09-01-2012'))
        self.assertEqual('Parliament of Singapore', modern.metadata['institution']['name'])
        unknown = parse_legacy('01-01-1950', '<body><p>An old report.</p></body>')
        self.assertIsNone(unknown.metadata['institution']['name'])
        council = parse_legacy('01-01-1950', '<body>LEGISLATIVE COUNCIL<p>Business</p></body>')
        self.assertEqual('Legislative Council', council.metadata['institution']['name'])

    def test_malformed_word_source_preserves_tail_and_unknown_metadata(self):
        html = '<html><body><p>Preface<!--SECTION_NAME:BUSINESS--><div>First<body><p>Second<!--TITLE_NAME:TAIL--><p>Final &amp; complete'
        sitting = parse_legacy('01-01-2009', html)
        self.assertEqual('Preface First Second Final & complete', sitting.parse_audit['retained_source_text'])
        self.assertEqual(['Preface', 'First Second', 'Final & complete'],
                         [s['content_plain'] for s in sitting.sections])
        self.assertIsNone(sitting.metadata['sitting_no'])
        self.assertTrue(sitting.parse_audit['warnings'])
        self.assertEqual(0, sitting.parse_audit['text_coverage']['tokens_outside_sections'])

    def test_unknown_layout_is_explicit_fallback_not_segmentation_success(self):
        sitting = parse_legacy('01-01-2009', '<body><p>First<div>Last &amp; whole')
        self.assertEqual('unsegmented', sitting.parse_audit['format'])
        self.assertEqual('unsegmented', sitting.parse_audit['segmentation_status'])
        self.assertEqual('First Last & whole', sitting.parse_audit['retained_source_text'])
        self.assertEqual('Unsegmented report', sitting.sections[0]['title'])
        self.assertIsNone(sitting.sections[0]['section_type'])
        self.assertTrue(any('no PRESENT roster' in w for w in sitting.parse_audit['warnings']))

    def test_unmapped_semantic_text_is_retained_and_audited(self):
        html = '<body>UNMAPPED PREFIX<div class="hansardContent"><h1 class="topictitle1">Topic</h1><p>Known body</p></div><footer>UNMAPPED TAIL</footer></body>'
        sitting = parse_legacy('01-01-2009', html)
        self.assertEqual('UNMAPPED PREFIX Topic Known body UNMAPPED TAIL', sitting.parse_audit['retained_source_text'])
        self.assertEqual(4, sitting.parse_audit['text_coverage']['tokens_outside_sections'])
        self.assertEqual({'UNMAPPED': 2, 'PREFIX': 1, 'TAIL': 1},
                         sitting.parse_audit['text_coverage']['outside_sections_token_counts'])

    def test_malformed_attendance_declaration(self):
        html = '<body><!SECTION_NAME:ATTENDANCE><b>PRESENT:</b><br>Mr Example (Place).<br><!--SECTION_NAME:BUSINESS--><p>Speech</p></body>'
        sitting = parse_legacy('03-03-2005', html)
        self.assertEqual('word-export', sitting.parse_audit['format'])
        self.assertEqual(1, len(sitting.present_members))
        self.assertEqual('attendance', sitting.sections[0]['category'])
        self.assertEqual('Speech', sitting.sections[1]['content_plain'])

    def test_semantic_attendance_keeps_procedural_text(self):
        html = '<body><div class="hansardContent"><h1 class="topictitle1">Attendance</h1><h2>Present:</h2><ul><li>Mr Example (Place).</li></ul><p>The House met.</p></div></body>'
        sitting = parse_legacy('01-01-2012', html)
        self.assertEqual('attendance', sitting.sections[0]['category'])
        self.assertIn('The House met.', sitting.sections[0]['content_plain'])
        self.assertEqual(0, sitting.parse_audit['text_coverage']['tokens_outside_sections'])

    def test_source_date_alternatives_and_corruption(self):
        for value in ('2006-11-09', '09-11-2006', '20/f-28-0502ont>'):
            html = '<body><table><tr><td>Sitting Date:</td><td>' + value + '</td></tr></table><p>Retained text</p></body>'
            sitting = parse_legacy('09-11-2006', html)
            self.assertEqual('09-11-2006', sitting.metadata['date'])
            if value.startswith('20/f'):
                self.assertTrue(any('Unrecognised source date' in warning for warning in sitting.parse_audit['warnings']))
        with self.assertRaisesRegex(ValueError, 'Requested'):
            parse_legacy('09-11-2006', '<table><tr><td>Sitting Date:</td><td>2006-11-10</td></tr></table>')

    def test_flat_attendance_keeps_procedure_before_next_heading(self):
        # Procedural lines from the 1977-02-07 and 1986-02-20 source reports.
        procedure = 'At 2.30 p.m. the Serjeant at Arms laid the Mace below the Table.'
        introduction = 'On the Clerk announcing "The President", the President delivered his Opening Speech.'
        html = '<body><div align="center"><b>PRESENT:</b></div>Mr Example (Place).<br>' + procedure + '<br>' + introduction + '<div align="center"><b>PRESIDENT ADDRESS</b></div><p>Speech</p></body>'
        sitting = parse_legacy('20-02-1986', html)
        attendance = sitting.sections[0]
        self.assertEqual('attendance', attendance['category'])
        self.assertIsNone(attendance['section_type'])
        self.assertIn(procedure, attendance['content_plain'])
        self.assertIn(introduction, attendance['content_plain'])
        self.assertEqual(0, sitting.parse_audit['text_coverage']['tokens_outside_sections'])

    def test_word_repeated_titles_use_explicit_columns(self):
        html = '<body><!--SECTION_NAME:BUSINESS--><!--TITLE_NAME:SAME--><!--END_COL_TITLE:SAME:::10--><p>First</p><!--TITLE_NAME:SAME--><!--END_COL_TITLE:SAME:::20--><p>Second</p>'
        sitting = parse_legacy('01-01-2009', html)
        ids = [s['source_ids'][0] for s in sitting.sections]
        self.assertEqual(2, len(set(ids)))
        self.assertFalse(any('occurrence' in value for value in ids))
        corrected = parse_legacy('01-01-2009', html.replace('First', 'Corrected first'))
        self.assertEqual(ids, [s['source_ids'][0] for s in corrected.sections])


if __name__ == '__main__':
    unittest.main()
