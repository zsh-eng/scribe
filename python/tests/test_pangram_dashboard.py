"""Dashboard import tests use a temporary export directory and a fake extension download."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import import_pangram_dashboard as dashboard


def report(uuid, tag, prompt, stage='STAGE_SUCCESS'):
    windows = [{'label': 'Human', 'confidence': 'High', 'start_index': 0, 'end_index': 5, 'word_count': 90, 'ai_likelihood': 0.01},
               {'label': 'AI-Generated', 'confidence': 'High', 'start_index': 5, 'end_index': 9, 'word_count': 80, 'ai_likelihood': 0.9}]
    return {'id': uuid, 'label': tag, 'status': 200, 'fetchedAt': '2026-10-07T15:46:18Z', 'error': None,
            'json': {'uuid': uuid, 'file_name': tag, 'prompt': prompt, 'timestamp': '2026-10-07T11:23:12-04:00',
                     'response_payload': {'stage': stage, 'version': '4.0', 'task_id': 't1', 'text': prompt,
                                          'fraction_ai': 0.44, 'windows': windows}}}


class DashboardImportTests(unittest.TestCase):
    def test_imports_matching_reports_once_with_api_window_fields(self):
        with tempfile.TemporaryDirectory() as temp:
            export = Path(temp) / 'export'
            export.mkdir()
            speeches = [{'speech_id': 'bp-a', 'text': 'Sir, I rise.'}, {'speech_id': 'bp-b', 'text': 'Sir, I object.'}]
            (export / 'speeches.jsonl').write_text(''.join(json.dumps(s) + '\n' for s in speeches))
            download = Path(temp) / 'pangram-history-reports.jsonl'
            records = [
                report('u1', 'bp-a', 'Sir, I rise.'),
                report('u2', 'bp-b', 'Sir, I object!'),            # text differs from the export
                report('u3', 'bp-zzz', 'Unknown speech'),          # not in the export
                {'id': 'u4', 'label': 'bp-b', 'status': 429, 'body': '{}'},
                report('u5', 'bp-b', 'Sir, I object.', stage='STAGE_FAILED'),
            ]
            download.write_text(''.join(json.dumps(r) + '\n' for r in records))

            with contextlib.redirect_stdout(io.StringIO()):
                first = dashboard.import_reports([download], export)
                second = dashboard.import_reports([download], export)

            self.assertEqual(first, {'imported': 1, 'text_differs': 1, 'not_in_export': 1, 'not_fetched': 1, 'failed': 1})
            self.assertEqual(second['already_imported'], 2)
            rows = [json.loads(line) for line in (export / 'pangram/results.jsonl').read_text().splitlines()]
            self.assertEqual([(r['speech_id'], r['status'], r['report_uuid']) for r in rows],
                             [('bp-a', 'success', 'u1'), ('bp-b', 'failed', 'u5')])
            windows = rows[0]['result']['windows']
            self.assertEqual([w['label'] for w in windows], ['Human Written', 'AI-Generated'])
            self.assertEqual([w['ai_assistance_score'] for w in windows], [0.01, 0.9])
            self.assertEqual(len(list((export / 'pangram/raw/dashboard').iterdir())), 1)


if __name__ == '__main__':
    unittest.main()
