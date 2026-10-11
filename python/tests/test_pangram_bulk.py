"""Pangram bulk runner tests use a fake HTTP session and a temporary export directory."""
import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

import requests

import run_pangram_bulk as bulk


class FakeResponse:
    def __init__(self, data, status_code=200):
        self.data, self.status_code, self.text = data, status_code, json.dumps(data)

    def json(self):
        return self.data


class FakePangram:
    """Accepts one bulk job per POST and reports it running once before success."""

    def __init__(self, post_error=None):
        self.posts, self.gets, self.jobs, self.post_error = [], [], {}, post_error

    def post(self, url, json=None, timeout=None):
        if self.post_error:
            raise self.post_error
        self.posts.append(json)
        bulk_id = f'blk_{len(self.posts)}'
        self.jobs[bulk_id] = {'items': json['items'], 'polls': 0}
        return FakeResponse({'bulk_id': bulk_id, 'status': 'queued', 'total_items': len(json['items'])}, 202)

    def get(self, url, params=None, timeout=None):
        self.gets.append(url)
        if url.endswith('/models'):
            return FakeResponse({'models': ['default', 'pangram-4']})
        bulk_id = url.split('/bulk/')[1].split('/')[0]
        job = self.jobs[bulk_id]
        if url.endswith('/results'):
            items, failed = [], []
            for i, item in enumerate(job['items'][params['offset']:params['offset'] + params['limit']]):
                if 'FAIL' in item['text']:
                    failed.append({'index': i, 'id': item['id'], 'task_id': None,
                                   'stage': 'STAGE_FAILED', 'error': 'bad text'})
                else:
                    items.append({'index': i, 'id': item['id'], 'task_id': f't{i}', 'stage': 'STAGE_SUCCESS',
                                  'error': None, 'result': {'stage': 'STAGE_SUCCESS', 'version': '4.0',
                                                            'fraction_ai': 0.0, 'fraction_human': 1.0,
                                                            'prediction_short': 'Human', 'windows': []}})
            return FakeResponse({'bulk_id': bulk_id, 'offset': params['offset'], 'limit': params['limit'],
                                 'total_items': len(job['items']), 'items': items, 'failed_items': failed})
        job['polls'] += 1
        status = 'running' if job['polls'] == 1 else 'partial'
        return FakeResponse({'bulk_id': bulk_id, 'status': status, 'total_items': len(job['items'])})


def speech(sid, year, words, office=False, text=None):
    return {'speech_id': sid, 'upload_batch': year, 'words': words, 'is_office_holder': office,
            'text': text or ' '.join(['word'] * words)}


class BulkRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.export = Path(self.temp.name)
        rows = [speech('a', '2020', 450), speech('b', '2020', 450), speech('c', '2020', 120, text='FAIL'),
                speech('m', '2020', 900, office=True), speech('z', '2025', 300)]
        (self.export / 'speeches.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
        self.state = self.export / 'pangram'

    def run_bulk(self, *argv, session=None):
        args = bulk.parse_args(['--export-dir', str(self.export), '--poll-seconds', '0', *argv])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            bulk.run(args, session=session, sleep=lambda _: None)
        return out.getvalue()

    def results(self):
        return bulk.read_jsonl(self.state / 'results.jsonl')

    def test_chunks_stay_within_unit_limit(self):
        groups = bulk.chunk([speech(str(i), '2020', 450) for i in range(5)], max_units=10)
        self.assertEqual([len(g) for g in groups], [2, 2, 1])

    def test_dry_run_estimates_cost_without_requests(self):
        fake = FakePangram()
        out = self.run_bulk('--years', '2020', '--exclude-office-holders', session=fake)
        self.assertIn('Selected 3 unsent speeches, 1,020 words, 12 units, ~$0.48', out)
        self.assertEqual((fake.posts, fake.gets), ([], []))

    def test_submit_saves_raw_results_and_never_resends(self):
        fake = FakePangram()
        self.run_bulk('--years', '2020', '--exclude-office-holders', '--max-units', '10', '--submit', session=fake)
        self.assertEqual([[i['id'] for i in p['items']] for p in fake.posts], [['a', 'b'], ['c']])
        self.assertEqual({p['model'] for p in fake.posts}, {'pangram-4'})
        self.assertEqual({(r['speech_id'], r['status']) for r in self.results()},
                         {('a', 'success'), ('b', 'success'), ('c', 'failed')})
        self.assertTrue((self.state / 'raw' / 'blk_1' / 'results-00000.json').exists())

        out = self.run_bulk('--years', '2020', '--exclude-office-holders', '--submit', session=fake)
        self.assertIn('Selected 0 unsent speeches', out)
        self.assertEqual(len(fake.posts), 2)
        self.assertEqual(len(self.results()), 3)

    def test_write_csv_skips_scanned_speeches_and_sends_nothing(self):
        self.state.mkdir()
        (self.state / 'results.jsonl').write_text(json.dumps(
            {'speech_id': 'a', 'source': 'dashboard', 'bulk_id': None, 'status': 'success', 'result': {}}) + '\n')
        upload = self.export / 'upload.csv'
        session = FakePangram()
        self.run_bulk('--years', '2020', '--exclude-office-holders', '--write-csv', str(upload), session=session)
        with open(upload, newline='') as f:
            self.assertEqual([r['tag'] for r in csv.DictReader(f)], ['b', 'c'])
        self.assertEqual(session.posts + session.gets, [])

    def test_unknown_submission_outcome_is_not_resent(self):
        fake = FakePangram(post_error=requests.ConnectionError('reset'))
        with self.assertRaises(SystemExit):
            self.run_bulk('--years', '2025', '--submit', session=fake)
        jobs = bulk.read_jsonl(self.state / 'jobs.jsonl')
        self.assertEqual([(j['bulk_id'], j['speech_ids']) for j in jobs], [(None, ['z'])])
        out = self.run_bulk('--years', '2025', '--submit', session=FakePangram())
        self.assertIn('Selected 0 unsent speeches', out)
        self.assertIn('1 submission(s) have an unknown outcome', out)

    def test_pending_jobs_are_collected_without_submit(self):
        fake = FakePangram()
        fake.jobs['blk_old'] = {'items': [{'id': 'a', 'text': 'x'}], 'polls': 0}
        self.state.mkdir()
        bulk.append_jsonl(self.state / 'jobs.jsonl', [{'bulk_id': 'blk_old', 'model': 'pangram-4',
                                                      'speech_ids': ['a']}])
        self.run_bulk('--years', '2020', session=fake)
        self.assertEqual(fake.posts, [])
        self.assertEqual([(r['speech_id'], r['bulk_id']) for r in self.results()], [('a', 'blk_old')])


if __name__ == '__main__':
    unittest.main()
