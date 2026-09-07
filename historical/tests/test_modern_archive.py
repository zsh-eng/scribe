"""Archive contracts for an official structured report and malformed source rows.

Fixture provenance: POST https://sprs.parl.gov.sg/search/getHansardReport/
JSON body {"sittingDate": "10-09-2012"}, retrieved 2026-09-08.
The gzip contains the unchanged HTTP response body (not re-serialized JSON).
"""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import unittest

from legacy_hansard import clean_fragment, text
from modern_hansard import parse_modern

FIXTURE = Path(__file__).parent / 'fixtures/reports/10-09-2012.json.gz'
DATE = '10-09-2012'


def source():
    return json.loads(gzip.decompress(FIXTURE.read_bytes()))


class ModernArchiveTests(unittest.TestCase):
    def test_fixture_provenance(self):
        self.assertEqual(hashlib.sha256(gzip.decompress(FIXTURE.read_bytes())).hexdigest(),
                         'c7d81d0bb8f8c1cf2dfa20e3575e4010d81fd4740c5c32fdd2db09cf2ea59271')

    def test_all_source_sections_survive_in_order(self):
        raw = source()
        result = parse_modern(DATE, raw)
        self.assertEqual(len(result.sections), 71)
        self.assertEqual(result.metadata['sitting_no'], 6)
        self.assertEqual(result.metadata['parliament'], 12)
        self.assertEqual([s['title'] for s in result.sections], [r['title'] for r in raw['takesSectionVOList']])
        self.assertEqual([s['content_plain'] for s in result.sections],
                         [text(clean_fragment(r['content'])) for r in raw['takesSectionVOList']])
        self.assertEqual(len({s['source_ids'][0] for s in result.sections}), 71)
        # The short procedural announcement is deliberately retained.
        self.assertEqual(result.sections[0]['title'], 'Estimates Committee')
        self.assertIn('Standing Order No 102', result.sections[0]['content_plain'])
        self.assertEqual(result.parse_audit['raw_section_count'], 71)

    def test_null_attendance_row_retained_without_crash(self):
        raw = source()
        result = parse_modern(DATE, raw)
        unresolved = result.parse_audit['unresolved_attendance']
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0]['row'], raw['attendanceList'][0])
        self.assertEqual(len(result.present_members) + len(result.absent_members), 98)

    def test_unknown_empty_and_duplicate_sections_are_not_filtered_or_merged(self):
        raw = source()
        raw['takesSectionVOList'] = [
            {'title': 'Duplicate', 'sectionType': 'UNRECOGNISED', 'content': '<p>First.</p>'},
            {'title': 'Duplicate', 'sectionType': 'OS', 'content': '<p>Second.</p>'},
            {'title': 'Empty', 'sectionType': None, 'content': None},
            None,
        ]
        result = parse_modern(DATE, raw)
        self.assertEqual(len(result.sections), 4)
        self.assertEqual(result.sections[0]['category'], 'other')
        self.assertEqual(result.sections[0]['section_type'], 'UNRECOGNISED')
        self.assertEqual(result.sections[1]['content_plain'], 'Second.')
        self.assertEqual(len(result.parse_audit['unknown_section_types']), 3)
        self.assertTrue(result.parse_audit['warnings'])

    def test_full_response_and_extra_text_survive_without_mutation(self):
        raw = source()
        raw['annexureList'] = [{'unknownField': '<p>Supplement sentinel</p>'}]
        raw['takesSectionVOList'][0]['footNotes'] = 'Footnote sentinel'
        before = deepcopy(raw)
        result = parse_modern(DATE, raw)
        self.assertEqual(raw, before)
        self.assertEqual(result.parse_audit['source_response'], before)
        self.assertIn('Supplement sentinel', result.parse_audit['retained_source_text'])
        self.assertIn('Footnote sentinel', result.parse_audit['retained_source_text'])
        raw['annexureList'].clear()
        self.assertEqual(len(result.parse_audit['source_response']['annexureList']), 1)

    def test_date_and_shape_validation(self):
        with self.assertRaises(ValueError):
            parse_modern('11-09-2012', source())
        with self.assertRaises(ValueError):
            parse_modern(DATE, {'error': 'not a report'})


if __name__ == '__main__':
    unittest.main()
