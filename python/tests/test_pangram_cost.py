"""Cost estimator tests use a temporary database."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

import estimate_pangram_cost as cost

ROOT = Path(__file__).resolve().parents[2]
SPEECH = ' '.join(['word'] * 250)


def turns(*speakers):
    return ''.join(f'<p><strong>{s}</strong>: {SPEECH}</p>' for s in speakers)


class EstimateTests(unittest.TestCase):
    def test_counts_prepared_speeches_by_type_and_office(self):
        with tempfile.TemporaryDirectory() as temp:
            conn = sqlite3.connect(Path(temp) / 'test.db')
            conn.executescript((ROOT / 'python/schema.sql').read_text())
            sections = [
                ('a', 'motion', 'OS', "President's Speech", turns('Mr Speaker', 'Mr Alpha Tan (Jurong)')),
                ('b', 'motion', 'OS', 'Committee of Supply - Head K (Ministry of Education)',
                 turns('The Chairman', 'The Minister for Education (Mr Gamma Lee)')),
                ('c', 'bill', 'BP', 'Example Bill', turns('Mr Alpha Tan (Jurong)', 'Mr Gamma Lee')),
                ('d', 'adjournment_motion', 'OS', 'Example Adjournment', turns('Mr Alpha Tan (Jurong)')),
                ('e', 'question', 'OA', 'Example Question', turns('Mr Alpha Tan (Jurong)')),
            ]
            with conn:
                conn.execute("INSERT INTO sittings(id,date,parliament) VALUES ('s','2023-04-17',14)")
                conn.execute("INSERT INTO members(id,name) VALUES ('m1','Alpha Tan'),('m2','Gamma Lee')")
                conn.execute("INSERT INTO sitting_attendance(sitting_id,member_id,constituency,designation) VALUES "
                             "('s','m1','Jurong',NULL),('s','m2','Bishan','Minister for Education')")
                conn.executemany("INSERT INTO sections(id,sitting_id,category,section_type,section_title,content_html,"
                                 "section_order) VALUES (?, 's', ?, ?, ?, ?, 1)", sections)

            totals, sittings = cost.estimate(conn, [2023], 150)
            conn.close()

        got = {k: (v['speeches'], v['words'], v['units']) for k, v in totals.items()}
        self.assertEqual(got, {
            ('2023', 'address', 'mp'): (1, 250, 3),
            ('2023', 'budget', 'office'): (1, 250, 3),
            ('2023', 'bills', 'mp'): (1, 250, 3),
            ('2023', 'bills', 'office'): (1, 250, 3),
            ('2023', 'adjournment', 'mp'): (1, 250, 3),
        })
        self.assertEqual(sittings, {'2023': 1})
        self.assertIn('$0', cost.report(totals, sittings, [2023], 150))


if __name__ == '__main__':
    unittest.main()
