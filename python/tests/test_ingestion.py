"""Offline regression tests; every write uses a temporary database."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import requests

import batch_process_sqlite as batch
import db_sqlite as db
from hansard_api import HansardAPI

FIXTURE = Path(__file__).parent / 'fixtures' / 'sitting.json'


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        db.close_connection()
        self.patch = patch.object(db, 'DB_PATH', str(Path(self.temp.name) / 'parliament.db'))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(db.close_connection)
        db.init_db()

    def ingest(self, data=None):
        if data is None:
            return batch.ingest_sitting('05-08-2026', FIXTURE)
        source = Path(self.temp.name) / 'source.json'
        source.write_text(json.dumps(data))
        return batch.ingest_sitting(data['metadata']['sittingDate'], source)

    def snapshot(self):
        conn = db.get_connection()
        tables = ['sittings', 'members', 'bills', 'sections', 'section_sources',
                  'section_speakers', 'sitting_attendance']
        return {t: sorted(tuple(row) for row in conn.execute(f'SELECT * FROM {t}')) for t in tables}

    def test_replay_preserves_ids_summaries_and_links(self):
        sid = self.ingest()
        conn = db.get_connection()
        with conn:
            conn.execute("UPDATE sections SET summary = 'Existing summary'")
            conn.execute("UPDATE bills SET summary = 'Bill summary'")
        before = self.snapshot()
        self.assertEqual(sid, self.ingest())
        self.assertEqual(before, self.snapshot())
        self.assertEqual(3, len(before['sections']))
        self.assertEqual(4, len(before['section_sources']))
        self.assertEqual(1, len(before['bills']))
        linked = conn.execute("SELECT DISTINCT bill_id FROM sections WHERE section_type IN ('BI','BP')").fetchall()
        self.assertEqual(1, len(linked))
        self.assertIsNotNone(linked[0][0])

    def test_legacy_adoption_preserves_manual_corrections(self):
        self.ingest()
        conn = db.get_connection()
        with conn:
            conn.execute('DELETE FROM section_sources')
            conn.execute("UPDATE sections SET section_title='Corrected title', category='motion', ministry_id='05', summary='Kept' WHERE section_type='OA'")
        before = conn.execute("SELECT id, section_title, category, ministry_id, summary FROM sections WHERE section_type='OA'").fetchone()
        self.ingest()
        after = conn.execute("SELECT id, section_title, category, ministry_id, summary FROM sections WHERE section_type='OA'").fetchone()
        self.assertEqual(tuple(before), tuple(after))

    def test_rollback_covers_sitting_members_bills_and_relationships(self):
        before = self.snapshot()
        original = batch.process_section
        count = 0

        def fail_later(*args):
            nonlocal count
            count += 1
            if count == 2:
                raise RuntimeError('Injected mid-sitting failure')
            return original(*args)

        with patch.object(batch, 'process_section', side_effect=fail_later):
            with self.assertRaisesRegex(RuntimeError, 'Injected'):
                self.ingest()
        self.assertEqual(before, self.snapshot())
        self.ingest()
        self.assertEqual(3, db.get_section_count())

    def test_removed_section_rolls_back_existing_sitting(self):
        self.ingest()
        before = self.snapshot()
        data = json.loads(FIXTURE.read_text())
        data['takesSectionVOList'] = [s for s in data['takesSectionVOList'] if s['sectionType'] != 'OA']
        with self.assertRaisesRegex(ValueError, 'absent'):
            self.ingest(data)
        self.assertEqual(before, self.snapshot())

    def test_split_merged_section_requires_review(self):
        self.ingest()
        before = self.snapshot()
        data = json.loads(FIXTURE.read_text())
        data['takesSectionVOList'][3]['title'] = 'Separate question'
        with self.assertRaisesRegex(ValueError, 'split'):
            self.ingest(data)
        self.assertEqual(before, self.snapshot())

    def test_fetch_failure_stops_before_watermark_can_skip_failed_date(self):
        with patch.object(HansardAPI, 'discover_dates', return_value=['05-08-2026', '07-08-2026']), \
                patch.object(batch, 'ingest_sitting', side_effect=requests.HTTPError('500')) as ingest:
            with self.assertRaises(requests.HTTPError):
                batch.batch_process('05-08-2026', '07-08-2026')
        ingest.assert_called_once_with('05-08-2026')

    def test_empty_indexed_report_stops_before_later_date(self):
        with patch.object(HansardAPI, 'discover_dates', return_value=['05-08-2026', '07-08-2026']), \
                patch.object(batch, 'ingest_sitting', return_value=None) as ingest:
            with self.assertRaisesRegex(ValueError, 'Indexed sitting 05-08-2026'):
                batch.batch_process('05-08-2026', '07-08-2026')
        ingest.assert_called_once_with('05-08-2026')

    def test_batch_fetches_only_discovered_dates(self):
        with patch.object(HansardAPI, 'discover_dates', return_value=['05-08-2026', '07-08-2026']), \
                patch.object(batch, 'ingest_sitting', return_value='sitting') as ingest:
            batch.batch_process('05-08-2026', '07-08-2026')
        self.assertEqual(['05-08-2026', '07-08-2026'], [call.args[0] for call in ingest.call_args_list])

    def test_discovery_failure_or_empty_window_never_fetches_reports(self):
        for failure in (True, False):
            with patch.object(HansardAPI, 'discover_dates', side_effect=requests.HTTPError('index') if failure else None,
                              return_value=[]), patch.object(batch, 'ingest_sitting') as ingest:
                if failure:
                    with self.assertRaises(requests.HTTPError):
                        batch.batch_process('05-08-2026', '07-08-2026')
                else:
                    batch.batch_process('05-08-2026', '07-08-2026')
                ingest.assert_not_called()

    def test_ambiguous_legacy_rows_are_not_deleted_or_replaced(self):
        self.ingest()
        conn = db.get_connection()
        with conn:
            conn.execute('DELETE FROM section_sources')
            conn.execute("""INSERT INTO sections (id, sitting_id, category, section_type, section_title, source_url)
                            SELECT 'duplicate', sitting_id, category, section_type, section_title, source_url
                            FROM sections WHERE section_type='OA'""")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            self.ingest()
        self.assertEqual(before, self.snapshot())

    def test_transcript_changes_preserve_public_id_and_summary(self):
        self.ingest()
        conn = db.get_connection()
        with conn:
            conn.execute("UPDATE sections SET summary='Kept' WHERE section_type='OA'")
        row = conn.execute("SELECT id FROM sections WHERE section_type='OA'").fetchone()
        data = json.loads(FIXTURE.read_text())
        data['takesSectionVOList'][1]['content'] = '<p>Updated answer.</p>'
        self.ingest(data)
        after = conn.execute('SELECT content_plain, summary FROM sections WHERE id=?', (row[0],)).fetchone()
        self.assertIn('Updated answer.', after[0])
        self.assertEqual('Kept', after[1])

    def test_same_title_introductions_on_different_dates_remain_distinct(self):
        self.ingest()
        data = json.loads(FIXTURE.read_text())
        data['metadata']['sittingDate'] = '06-08-2026'
        for section in data['takesSectionVOList']:
            section['sectionId'] += '-next'
        self.ingest(data)
        self.assertEqual(2, db.get_bill_count())
        self.ingest()
        self.assertEqual(2, db.get_bill_count())

    def test_backfill_does_not_link_to_future_bill(self):
        data = json.loads(FIXTURE.read_text())
        data['metadata']['sittingDate'] = '06-08-2026'
        self.ingest(data)
        with db.get_connection():
            result = db.find_bill_for_second_reading('Example Bill', reading_date='04-08-2026')
        self.assertIsNone(db.get_connection().execute('SELECT first_reading_date FROM bills WHERE id=?', (result,)).fetchone()[0])
        with db.get_connection():
            self.assertEqual(result, db.find_bill_for_second_reading('Example Bill', reading_date='04-08-2026'))

    def test_second_reading_uses_introduction_over_empty_duplicates_without_deleting_them(self):
        self.ingest()
        conn = db.get_connection()
        original = conn.execute('SELECT id FROM bills').fetchone()[0]
        with conn:
            for duplicate in ['orphan-1', 'orphan-2']:
                conn.execute('''INSERT INTO bills (id,title,first_reading_date,first_reading_sitting_id)
                                SELECT ?,title,first_reading_date,first_reading_sitting_id FROM bills WHERE id=?''',
                             (duplicate, original))
            self.assertEqual(original, db.find_bill_for_second_reading('Example Bill', reading_date='06-08-2026'))
        self.assertEqual(3, db.get_bill_count())
        with conn:
            conn.execute("UPDATE bills SET summary='Curated content' WHERE id='orphan-1'")
            with self.assertRaisesRegex(ValueError, 'Ambiguous bill reading'):
                db.find_bill_for_second_reading('Example Bill', reading_date='06-08-2026')
            conn.execute("UPDATE bills SET summary=NULL WHERE id='orphan-1'")
            conn.execute('''INSERT INTO sections (id,sitting_id,category,section_type,section_title,bill_id)
                            SELECT 'duplicate-intro',sitting_id,category,section_type,section_title,'orphan-1'
                            FROM sections WHERE section_type='BI' LIMIT 1''')
            with self.assertRaisesRegex(ValueError, 'Ambiguous bill reading'):
                db.find_bill_for_second_reading('Example Bill', reading_date='06-08-2026')


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.api = HansardAPI()
        self.addCleanup(self.api.session.close)

    def test_discovery_deduplicates_pages_and_returns_oldest_first(self):
        pages = [
            [{'sittingDate': '10-9-2026', 'maxResult': '100'}] * 20,
            [{'sittingDate': '9-9-2026', 'maxResult': '80'}] * 20,
            [{'sittingDate': '5-8-2026', 'maxResult': '60'}] * 20,
        ]
        with patch.object(self.api.session, 'post', side_effect=[Mock(json=Mock(return_value=p)) for p in pages]) as post:
            self.assertEqual(['09-09-2026', '10-09-2026'], self.api.discover_dates('06-08-2026', '19-09-2026'))
        self.assertEqual(['19', '9', '8'], [call.kwargs['json']['today'] for call in post.call_args_list])
        self.assertTrue(all(call.kwargs['json']['fromyear'] == '1955' for call in post.call_args_list))

    def test_discovery_empty_window_and_exhausted_index(self):
        for rows, expected in [([], []),
                               ([{'sittingDate': '5-8-2026', 'maxResult': 1}], []),
                               ([{'sittingDate': '10-9-2026', 'maxResult': 1}], ['10-09-2026'])]:
            with patch.object(self.api.session, 'post', return_value=Mock(json=Mock(return_value=rows))) as post:
                self.assertEqual(expected, self.api.discover_dates('06-08-2026', '19-09-2026'))
                self.assertEqual(1, post.call_count)

    def test_discovery_rejects_malformed_or_inconsistent_pages(self):
        for rows in [{'errorCode': 500}, [{}], [None],
                     [{'sittingDate': 'invalid', 'maxResult': 1}],
                     [{'sittingDate': '20-9-2026', 'maxResult': 1}],
                     [{'sittingDate': '10-9-2026', 'maxResult': 0}],
                     [{'sittingDate': '9-9-2026', 'maxResult': 2}, {'sittingDate': '10-9-2026', 'maxResult': 2}]]:
            with self.subTest(rows=rows), patch.object(self.api.session, 'post', return_value=Mock(json=Mock(return_value=rows))):
                with self.assertRaises(ValueError):
                    self.api.discover_dates('06-08-2026', '19-09-2026')

    def test_discovery_rejects_non_decreasing_counts_and_http_failures(self):
        pages = [[{'sittingDate': date, 'maxResult': 100}] for date in ['10-9-2026', '9-9-2026']]
        with patch.object(self.api.session, 'post', side_effect=[Mock(json=Mock(return_value=p)) for p in pages]):
            with self.assertRaisesRegex(ValueError, 'did not decrease'):
                self.api.discover_dates('06-08-2026', '19-09-2026')
        with patch.object(self.api.session, 'post', return_value=Mock(raise_for_status=Mock(side_effect=requests.HTTPError('500')))):
            with self.assertRaises(requests.HTTPError):
                self.api.discover_dates('06-08-2026', '19-09-2026')

    def test_empty_report_differs_from_http_failure_and_invalid_payload(self):
        self.assertIsNone(self.api.parse_response('05-08-2026', {'takesSectionVOList': []}))
        with self.assertRaises(ValueError):
            self.api.parse_response('05-08-2026', {'error': 'unavailable'})
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError('500')
        with patch.object(self.api.session, 'post', return_value=response):
            with self.assertRaises(requests.HTTPError):
                self.api.fetch_by_date('05-08-2026')

    def test_fetch_saves_replayable_source_and_provenance(self):
        data = json.loads(FIXTURE.read_text())
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'HANSARD_RAW_DIR': directory}):
            response = Mock()
            response.json.return_value = data
            with patch.object(self.api.session, 'post', return_value=response) as post:
                fetched = self.api.fetch_by_date('05-08-2026')
            post.assert_called_once_with(self.api.BASE_URL, json={'sittingDate': '05-08-2026'}, timeout=(10, 30))
            files = list(Path(directory).rglob('*.json'))
            self.assertEqual(2, len(files))
            source = next(f for f in files if not f.name.endswith('.meta.json'))
            replayed = self.api.read_source('05-08-2026', source)
            self.assertEqual(fetched.get_metadata(), replayed.get_metadata())
            self.assertEqual(['question-1', 'question-2'], replayed.sections[1]['source_ids'])
            self.api.save_source('05-08-2026', data)
            self.assertEqual(2, len(list(Path(directory).rglob('*.json'))))

    def test_wrong_date_and_legacy_format_fail(self):
        with self.assertRaisesRegex(ValueError, 'Requested'):
            self.api.parse_response('06-08-2026', json.loads(FIXTURE.read_text()))
        with self.assertRaisesRegex(ValueError, 'legacy'):
            self.api.parse_response('05-08-2026', {'htmlFullContent': '<p>Old report</p>'})


if __name__ == '__main__':
    unittest.main()
