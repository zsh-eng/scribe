"""Archive output must not become a site publication input."""
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

from publication import fingerprint

ROOT = Path(__file__).resolve().parents[2]


class IsolationTests(unittest.TestCase):
    def test_archive_data_does_not_change_publication_fingerprint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git','init','-q',str(root)],check=True)
            (root/'astro').mkdir()
            (root/'astro/page.astro').write_text('<p>Site</p>')
            database = root/'test.db'
            with sqlite3.connect(database) as connection:
                connection.executescript((ROOT/'python/schema.sql').read_text())
            before = fingerprint(database,root)
            archive = root/'historical/data/normalized'
            archive.mkdir(parents=True)
            (archive/'report.json').write_text('{"transcript":"Historical report"}')
            self.assertEqual(before,fingerprint(database,root))
            (root/'astro/page.astro').write_text('<p>Changed site</p>')
            self.assertNotEqual(before,fingerprint(database,root))


if __name__ == '__main__':
    unittest.main()
