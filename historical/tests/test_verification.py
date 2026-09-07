"""The corpus verifier must detect absent and altered normalized content."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import archive
from verify_archive import verify

FIXTURE = Path(__file__).parent / 'fixtures/reports/09-01-2012.json.gz'


class VerificationTests(unittest.TestCase):
    def test_complete_then_detects_corrupt_text_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(archive,'DATA',Path(directory)):
            data = Path(directory)
            archive.write_json(data/'inventory/inventory.json', {'complete':True,'coverage':'test',
                'sittings':[{'date':'2012-01-09','present_in_active':False,'era':'parliament','parliament':12}]})
            with patch.object(archive.requests,'post') as post:
                post.return_value.json.return_value=json.loads(gzip.decompress(FIXTURE.read_bytes()))
                archive.fetch('2012-01-09')
            archive.transform('2012-01-09')
            result, catalog = verify(data)
            self.assertTrue(result['complete'],result['errors'])
            self.assertEqual(1,len(catalog))
            _, output, _ = archive.paths('2012-01-09')
            record=archive.read_json(output)
            record['audit']['retained_source_text']='truncated'
            archive.write_json(output,record)
            result,_=verify(data)
            self.assertFalse(result['complete'])
            self.assertIn('Normalized full source text mismatch: 2012-01-09',result['errors'])
            output.unlink()
            result,_=verify(data)
            self.assertFalse(result['complete'])
            self.assertEqual(0,result['verified_sittings'])


if __name__ == '__main__':
    unittest.main()
