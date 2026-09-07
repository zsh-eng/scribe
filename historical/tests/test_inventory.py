"""Inventory must exhaust the official index and compare the database read-only."""
from datetime import date
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import inventory


def row(day, parliament, total):
    return {'sittingDate': day, 'parlNo': parliament, 'maxResult': total, 'reportVersion':'sprs2'}


class InventoryTests(unittest.TestCase):
    def test_exhaustion_and_era_separation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = root / 'active.db'
            with sqlite3.connect(db) as connection:
                connection.execute('CREATE TABLE sittings (date TEXT)')
                connection.execute("INSERT INTO sittings VALUES ('2016-01-15')")
            before = db.read_bytes()
            responses = [[row('15-01-2016',13,5),row('08-12-1965',1,5)],
                         [row('22-04-1955',0,1)]]
            with patch.object(inventory, 'fetch_page', side_effect=responses):
                result = inventory.build_inventory(root/'inventory',db,date(2026,9,8))
            self.assertTrue(result['complete'])
            self.assertEqual(3,result['summary']['total'])
            self.assertEqual(2,result['summary']['missing'])
            self.assertEqual('legislative-assembly',result['sittings'][0]['era'])
            self.assertEqual('parliament',result['sittings'][1]['era'])
            self.assertEqual(before,db.read_bytes())

    def test_inconsistent_count_does_not_claim_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(inventory,'fetch_page',side_effect=[
                [row('15-01-2016',13,5)], [row('08-12-1965',1,5)]
            ]):
                with self.assertRaisesRegex(ValueError,'did not decrease'):
                    inventory.build_inventory(Path(directory),Path(directory)/'unused.db',date(2026,9,8))
            self.assertFalse((Path(directory)/'inventory.json').exists())


if __name__ == '__main__':
    unittest.main()
