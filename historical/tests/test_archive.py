"""Archive files remain outside the active database; network requests are mocked."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

import archive

FIXTURE = Path(__file__).parent / 'fixtures/reports/09-01-2012.json.gz'


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch = patch.object(archive, 'DATA', Path(self.temp.name))
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_fetch_resumes_and_transformation_is_deterministic(self):
        response = Mock()
        response.json.return_value = json.loads(gzip.decompress(FIXTURE.read_bytes()))
        with patch.object(archive.requests, 'post', return_value=response) as post:
            self.assertEqual(('2012-01-09', 'fetched'), archive.fetch('2012-01-09'))
            post.assert_called_once_with(archive.URL, json={'sittingDate':'09-01-2012'}, timeout=(15,60))
            self.assertEqual(('2012-01-09', 'cached'), archive.fetch('2012-01-09'))
            self.assertEqual(1, post.call_count)
        self.assertEqual(('2012-01-09', 'parsed'), archive.transform('2012-01-09'))
        raw, output, state = archive.paths('2012-01-09')
        first = output.read_bytes()
        archive.transform('2012-01-09')
        self.assertEqual(first, output.read_bytes())
        record = archive.read_json(output)
        self.assertEqual(58, len(record['sections']))
        self.assertTrue(record['audit']['retained_source_text'])
        self.assertEqual('ok', archive.read_json(state)['fetch_status'])

    def test_failed_fetch_is_visible_and_can_be_retried(self):
        with patch.object(archive.requests, 'post', side_effect=archive.requests.HTTPError('failure')), patch.object(archive.time,'sleep'):
            self.assertEqual(('2000-01-01', 'failed'), archive.fetch('2000-01-01'))
        raw, output, state = archive.paths('2000-01-01')
        self.assertFalse(raw.exists())
        self.assertEqual('failed', archive.read_json(state)['fetch_status'])

    def test_incorrect_date_keeps_text_with_review_status(self):
        raw, output, _ = archive.paths('2012-01-10')
        raw.parent.mkdir(parents=True)
        raw.write_bytes(FIXTURE.read_bytes())
        self.assertEqual(('2012-01-10','needs_review'), archive.transform('2012-01-10'))
        record = archive.read_json(output)
        self.assertIn('Requested',record['error'])
        self.assertGreater(len(record['full_text']), 10000)
        self.assertEqual([],record['sections'])


if __name__ == '__main__':
    unittest.main()
