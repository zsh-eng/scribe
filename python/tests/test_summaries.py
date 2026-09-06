"""Summary provenance tests use a fake provider and temporary databases."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from generate_summaries_sqlite import run_jobs
from summary_jobs import (SummaryJob, content_hash, member_jobs, review_job, save_attempt,
                          sitting_jobs)

ROOT = Path(__file__).resolve().parents[2]


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.conn = sqlite3.connect(Path(self.temp.name) / 'test.db')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        self.conn.executescript((ROOT / 'python/schema.sql').read_text())
        with self.conn:
            self.conn.execute("INSERT INTO sittings(id,date,parliament) VALUES ('s','2026-08-05',15)")
            self.conn.execute("INSERT INTO sections(id,sitting_id,section_type,category,section_title,content_plain) VALUES ('q','s','OA','question','Title',?)", ('Source text. ' * 150,))
        self.job = next(sitting_jobs(self.conn, '2026-08-05', '2026-08-05'))
        self.call = AsyncMock(return_value=SimpleNamespace(text='New summary', usage_metadata=SimpleNamespace(total_token_count=123)))
        self.client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=self.call)))

    def run_jobs(self, jobs=None, **kwargs):
        return asyncio.run(run_jobs(self.conn, jobs or [self.job], client=self.client, cooldown=0, **kwargs))

    def current(self):
        return self.conn.execute("SELECT summary FROM sections WHERE id='q'").fetchone()[0]

    def test_success_commits_summary_and_provenance(self):
        result = self.run_jobs(model='model-a')
        self.assertEqual(1, result['success'])
        self.assertEqual('New summary', self.current())
        attempt = self.conn.execute('SELECT * FROM summary_attempts').fetchone()
        self.assertEqual(self.job.input_hash, attempt['input_hash'])
        self.assertEqual(self.job.prompt_version, attempt['prompt_version'])
        self.assertEqual('model-a', attempt['model'])
        self.assertEqual(content_hash('New summary'), attempt['summary_hash'])
        self.assertEqual(123, json.loads(attempt['usage_json'])['total_token_count'])

    def test_model_and_prompt_changes_are_review_only(self):
        self.run_jobs(model='model-a')
        changed = replace(self.job, summary=self.current(), template=self.job.template + '\nNew instruction')
        result = self.run_jobs([changed], model='model-b')
        self.assertEqual(1, result['existing'])
        self.assertEqual(1, self.call.await_count)
        review = review_job(self.conn, changed, 'model-b', 20000)
        self.assertEqual(['prompt_changed', 'model_changed'], review['reasons'])
        self.assertEqual('model-a', review['model'])

    def test_failed_regeneration_preserves_previous_summary_and_success_metadata(self):
        self.run_jobs(model='model-a')
        changed = replace(self.job, summary=self.current(), inputs={**self.job.inputs, 'text': 'Changed text'})
        self.call.side_effect = RuntimeError('Provider error')
        result = self.run_jobs([changed], model='model-b', regenerate=True)
        self.assertEqual(1, result['failed'])
        self.assertEqual('New summary', self.current())
        review = review_job(self.conn, changed, 'model-b', 20000)
        self.assertEqual('failed', review['last_attempt_status'])
        self.assertEqual('model-a', review['model'])
        self.assertIn('input_changed', review['reasons'])

    def test_long_inputs_are_blocked_not_truncated(self):
        long = replace(self.job, inputs={**self.job.inputs, 'text': 'x' * 21000 + 'THE END'})
        result = self.run_jobs([long])
        self.assertEqual(1, result['blocked'])
        self.call.assert_not_awaited()
        self.assertIsNone(self.current())
        self.run_jobs([long], input_limit=30000)
        sent = self.call.await_args.kwargs['contents']
        self.assertIn('THE END', sent)
        self.assertIn('x' * 21000, sent)

    def test_empty_response_is_a_failed_attempt(self):
        self.call.return_value.text = '   '
        self.assertEqual(1, self.run_jobs()['failed'])
        self.assertIsNone(self.current())

    def test_unknown_legacy_provenance_is_not_fabricated(self):
        job = replace(self.job, summary='Legacy summary')
        self.conn.execute('DROP TABLE summary_attempts')
        review = review_job(self.conn, job, 'model-a', 20000)
        self.assertEqual(['provenance_unknown'], review['reasons'])
        self.assertIsNone(review['generated_at'])
        self.assertIsNone(review['model'])

    def test_summary_and_provenance_roll_back_together(self):
        self.conn.execute("CREATE TRIGGER reject_history BEFORE INSERT ON summary_attempts BEGIN SELECT RAISE(ABORT, 'fail'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            save_attempt(self.conn, self.job, 'model-a', 'success', summary='Must roll back')
        self.assertIsNone(self.current())

    def test_member_without_summary_row_is_eligible(self):
        with self.conn:
            self.conn.execute("INSERT INTO members(id,name) VALUES ('m','Example Member')")
            self.conn.execute("INSERT INTO sitting_attendance(sitting_id,member_id) VALUES ('s','m')")
            self.conn.execute("INSERT INTO section_speakers(section_id,member_id) VALUES ('q','m')")
        jobs = list(member_jobs(self.conn))
        self.assertEqual(1, len(jobs))
        self.assertIsNone(jobs[0].summary)
        self.run_jobs(jobs)
        self.assertEqual('New summary', self.conn.execute("SELECT summary FROM member_summaries WHERE member_id='m'").fetchone()[0])

    def test_existing_summaries_do_not_initialize_provider(self):
        with patch('generate_summaries_sqlite.genai.Client') as client:
            asyncio.run(run_jobs(self.conn, [replace(self.job, summary='Already exists')]))
            client.assert_not_called()


if __name__ == '__main__':
    unittest.main()
