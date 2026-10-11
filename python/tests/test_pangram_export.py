"""Pangram export tests use a temporary database and output directory."""
import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import sys

import export_pangram_speeches as export

ROOT = Path(__file__).resolve().parents[2]
SPEECH = ' '.join(['word'] * 160)
HTML = (
    '<p><strong>Mr Speaker</strong>: Mr Alpha.</p>'
    f'<p><strong>Mr Alpha Tan (Jurong)</strong>: {SPEECH}</p>'
    '<p><strong>[Deputy Speaker (Mr Beta) in the Chair]</strong></p>'
    f'<p>{SPEECH} Sir, in Malay, please.</p>'
    '<p><em>(In Malay): </em>translated words here</p>'
    '<p><em>(In English): </em>Back in English.</p>'
    f'<p><strong>The Minister for Education (Mr Gamma Lee)</strong>: {SPEECH}</p>'
    '<p><strong>Mr Alpha Tan</strong>: Short clarification.</p>'
)


class SplitTurnsTests(unittest.TestCase):
    def test_chair_notice_does_not_split_and_translation_is_removed(self):
        turns = export.split_turns(HTML)
        self.assertEqual([t.label for t in turns],
                         ['Mr Speaker', 'Mr Alpha Tan (Jurong)', 'The Minister for Education (Mr Gamma Lee)', 'Mr Alpha Tan'])
        alpha = turns[1]
        self.assertEqual(alpha.translated_words_removed, 3)
        self.assertNotIn('translated', alpha.text)
        self.assertTrue(alpha.text.endswith('Back in English.'))
        self.assertEqual(len(alpha.text.split()), 320 + 4 + 3)

    def test_slug_matches_site(self):
        self.assertEqual(export.slugify("Debate on the President's Address ", 'a50b7054-x'),
                         'debate-on-the-presidents-address-a50b7054')


class ExportTests(unittest.TestCase):
    def test_export_writes_mappings_and_upload_csv(self):
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / 'test.db'
            conn = sqlite3.connect(db_path)
            conn.executescript((ROOT / 'python/schema.sql').read_text())
            with conn:
                conn.execute("INSERT INTO sittings(id,date,parliament) VALUES ('s','2025-09-22',15)")
                conn.execute("INSERT INTO members(id,name) VALUES ('m1','Alpha Tan'),('m2','Gamma Lee')")
                conn.execute("INSERT INTO sitting_attendance(sitting_id,member_id,constituency,designation) VALUES "
                             "('s','m1','Jurong',NULL),('s','m2','Bishan','Minister for Education')")
                conn.execute("INSERT INTO sections(id,sitting_id,category,section_type,section_title,content_html,section_order) "
                             "VALUES ('abcdef1234','s','motion','OS',?,?,1)", ("President's Speech", HTML))
            conn.close()

            out = Path(temp) / 'out'
            argv = ['export', '--db', str(db_path), '--out-dir', str(out), '--years', '2025']
            with patch.object(sys, 'argv', argv), patch('builtins.print'):
                export.main()

            speeches = [json.loads(line) for line in (out / 'speeches.jsonl').read_text().splitlines()]
            self.assertEqual([(s['member_id'], s['is_office_holder'], s['first_parliament']) for s in speeches],
                             [('m1', False, True), ('m2', True, True)])
            self.assertEqual(speeches[0]['secondreading_url'],
                             'https://secondreading.app/motions/presidents-speech-abcdef12')
            with open(out / 'pangram_upload_2025.csv', newline='') as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r['tag'] for r in rows], [s['speech_id'] for s in speeches])
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(manifest['excluded_turns'], {'presiding_officer': 1, 'under_150_words': 1})
            self.assertEqual(manifest['by_year']['2025']['billed_words'], 400 + 200)

    def test_prepared_scope_covers_motions_adjournments_and_bill_debates(self):
        turn = f'<p><strong>Mr Alpha Tan (Jurong)</strong>: {SPEECH}</p>'
        with tempfile.TemporaryDirectory() as temp:
            db_path = Path(temp) / 'test.db'
            conn = sqlite3.connect(db_path)
            conn.executescript((ROOT / 'python/schema.sql').read_text())
            with conn:
                conn.execute("INSERT INTO sittings(id,date,parliament) VALUES ('s','2026-02-24',15),('late','2026-11-03',15)")
                conn.execute("INSERT INTO members(id,name) VALUES ('m1','Alpha Tan')")
                conn.execute("INSERT INTO sections(id,sitting_id,category,section_type,section_title,content_html,section_order) "
                             "VALUES ('late0001aa','late','motion','OS','After the cutoff',?,1)", (turn,))
                conn.execute("INSERT INTO bills(id,title) VALUES ('bill0001aa','Example Bill')")
                conn.executemany(
                    "INSERT INTO sections(id,sitting_id,bill_id,category,section_type,section_title,content_html,section_order) "
                    "VALUES (?, 's', ?, ?, ?, ?, ?, ?)", [
                        ('mot00001aa', None, 'motion', 'OS', 'Annual Budget Statement', turn, 1),
                        ('bil00001aa', 'bill0001aa', 'bill', 'BP', 'Example Bill', turn, 2),
                        ('bil00002aa', 'bill0001aa', 'bill', 'BI', 'Example Bill', turn, 3),
                        ('adj00001aa', None, 'adjournment_motion', 'OS', 'Example Adjournment', turn, 4),
                        ('que00001aa', None, 'question', 'OA', 'Example Question', turn, 5),
                    ])
            conn.close()

            out = Path(temp) / 'out'
            argv = ['export', '--scope', 'prepared', '--db', str(db_path), '--out-dir', str(out), '--years', '2026',
                    '--through', '09-10']
            with patch.object(sys, 'argv', argv), patch('builtins.print'):
                export.main()

            speeches = [json.loads(line) for line in (out / 'speeches.jsonl').read_text().splitlines()]
            self.assertEqual([(s['speech_id'], s['debate_type'], s['secondreading_url']) for s in speeches], [
                ('bu-2026-02-24-mot00001-t000', 'budget', 'https://secondreading.app/motions/annual-budget-statement-mot00001'),
                ('bp-2026-02-24-bil00001-t000', 'bills', 'https://secondreading.app/bills/example-bill-bill0001'),
                ('am-2026-02-24-adj00001-t000', 'adjournment', 'https://secondreading.app/motions/example-adjournment-adj00001'),
            ])
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(manifest['by_debate_type']['bills']['speeches'], 1)
            self.assertEqual((manifest['parameters']['scope'], manifest['parameters']['through']), ('prepared', '09-10'))


if __name__ == '__main__':
    unittest.main()
