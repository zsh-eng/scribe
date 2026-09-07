"""Historical contract tests against official full-report fixtures, never the live DB."""
import gzip
import hashlib
import json
from pathlib import Path
import unittest

from bs4 import BeautifulSoup, Comment

from legacy_hansard import clean_fragment, text, resolve_speakers, parse_legacy
from parliament_sitting import MP

FIXTURES = Path(__file__).parent / 'fixtures' / 'reports'


def source(date):
    return json.loads(gzip.decompress((FIXTURES / f'{date}.json.gz').read_bytes()))


def parse(date, data=None):
    return parse_legacy(date, (data or source(date))['htmlFullContent'])


class HistoricalTests(unittest.TestCase):
    def test_source_checksums(self):
        for item in json.loads((FIXTURES / 'sources.json').read_text()):
            raw = gzip.decompress((FIXTURES / item['file']).read_bytes())
            self.assertEqual(item['sha256'], hashlib.sha256(raw).hexdigest())

    def test_independently_reviewed_rosters_and_topic_counts(self):
        # Counts checked against the source's roster lists and topic headings.
        for date, sitting_no, present, absent, topics in [
            ('09-01-2012', 9, 78, 12, 58), ('17-10-2011', 2, 83, 7, 11),
            ('22-02-2000', 9, 83, 9, 24), ('31-10-1994', 7, 77, 8, 44),
        ]:
            with self.subTest(date=date):
                sitting = parse(date)
                self.assertEqual((sitting_no, present, absent, topics),
                                 (sitting.metadata['sitting_no'], len(sitting.present_members),
                                  len(sitting.absent_members), len(sitting.sections)))
                self.assertEqual(sitting.present_members[0].appointment, 'Speaker')

    def test_semantic_transcript_coverage_including_appendices_and_tables(self):
        for date in ['09-01-2012', '17-10-2011']:
            sitting = parse(date)
            original = BeautifulSoup(source(date)['htmlFullContent'], 'html.parser')
            # Every non-attendance topic and continuation must survive in source order.
            expected = []
            for block in original.select('.hansardContent'):
                heading = block.select_one('h1.topictitle1')
                if heading and heading.get_text(strip=True) == 'Attendance':
                    continue
                expected.append(text(clean_fragment(str(block))))
            actual = ' '.join(s['content_plain'] for s in sitting.sections if s['category'] != 'attendance')
            self.assertEqual(' '.join(expected), actual)
            self.assertEqual(len(original.select('.hansardContent table')),
                             sum(len(BeautifulSoup(s['content_html'], 'html.parser').find_all('table')) for s in sitting.sections))
        self.assertIn('Vernacular Speech by Mr Yeo Guat Kwang', actual)

    def test_flat_text_coverage_after_roster(self):
        # Independent boundary: start at the published permission heading, strip only columns.
        for date in ['22-02-2000', '31-10-1994']:
            raw = BeautifulSoup(source(date)['htmlFullContent'], 'html.parser')
            for comment in raw.find_all(string=lambda x: isinstance(x, Comment)):
                comment.extract()
            start = raw.find('h4', string='PERMISSION TO MEMBERS TO BE ABSENT').parent
            html = str(start) + ''.join(str(n) for n in start.next_siblings)
            expected = text(clean_fragment(html))
            # Group headings are routing metadata, retained explicitly in the audit below.
            actual = ' '.join(s['content_plain'] for s in parse(date).sections if s['category'] != 'attendance')
            import re
            expected = re.sub(r'\b(?:ORAL ANSWERS TO QUESTIONS|WRITTEN ANSWERS TO QUESTIONS|WRITTEN ANSWER TO QUESTION FOR ORAL ANSWER NOT ANSWERED BY 1.30 PM)\b', '', expected)
            self.assertEqual(' '.join(expected.split()), actual)

    def test_reviewed_questions_bill_readings_and_multiline_titles(self):
        sitting = parse('31-10-1994')
        by_title = {s['title']: s for s in sitting.sections}
        self.assertEqual('BI', by_title['MOTOR VEHICLES (THIRD PARTY RISKS AND COMPENSATION) (AMENDMENT) BILL']['section_type'])
        self.assertEqual('BP', by_title['INTERNATIONAL ARBITRATION BILL']['section_type'])
        self.assertEqual('WA', by_title['PARKING PROBLEM OUTSIDE EMBASSY OF PEOPLE\'S REPUBLIC OF CHINA']['section_type'])
        sitting = parse('22-02-2000')
        question = next(s for s in sitting.sections if s['title'] == 'RESTRICTED PASSPORTS (Discontinuation)')
        self.assertEqual('OA', question['section_type'])
        self.assertEqual({'J. B. Jeyaretnam', 'Ho Peng Kee', 'Leong Horn Kee', 'Chiam See Tong'}, {m.name for m in question['speakers']})
        self.assertIn('the actual number of passports that have been issued', question['content_plain'])
        self.assertNotIn('Column: 955', question['content_plain'])
        self.assertTrue(any(s['section_type'] == 'WANA' for s in sitting.sections))

    def test_flat_transcript_edits_keep_source_identity_and_unknowns(self):
        data = source('22-02-2000')
        original = parse('22-02-2000', data)
        data['htmlFullContent'] = data['htmlFullContent'].replace('falling demand', 'reduced demand')
        updated = parse('22-02-2000', data)
        self.assertEqual([s['source_ids'] for s in original.sections],
                         [s['source_ids'] for s in updated.sections])
        self.assertNotEqual([s['content_plain'] for s in original.sections], [s['content_plain'] for s in updated.sections])
        self.assertTrue(any(s['category'] == 'other' and s['section_type'] is None for s in updated.sections))

    def test_ambiguous_speaker_is_reported_not_assigned(self):
        body = BeautifulSoup('<b>Mr Tan:</b>', 'html.parser')
        matched, unresolved = resolve_speakers(body, [MP('Alex Tan', 'A'), MP('Ben Tan', 'B')])
        self.assertEqual([], matched)
        self.assertEqual(['Mr Tan'], unresolved)

    def test_wrong_date_fails_and_missing_roster_is_reported(self):
        with self.assertRaisesRegex(ValueError, 'Requested'):
            parse('10-01-2012', source('09-01-2012'))
        data = source('09-01-2012')
        data['htmlFullContent'] = data['htmlFullContent'].replace('>Attendance<!--', '>Not attendance<!--')
        sitting = parse('09-01-2012', data)
        self.assertTrue(sitting.parse_audit['warnings'])
        self.assertTrue(sitting.parse_audit['retained_source_text'])

    def test_repeat_transformation_preserves_source_identity(self):
        for date in ['31-10-1994', '22-02-2000', '17-10-2011', '09-01-2012']:
            first, second = parse(date), parse(date)
            self.assertEqual(first.metadata, second.metadata)
            self.assertEqual([(s['source_ids'], s['content_plain']) for s in first.sections],
                             [(s['source_ids'], s['content_plain']) for s in second.sections])


if __name__ == '__main__':
    unittest.main()
