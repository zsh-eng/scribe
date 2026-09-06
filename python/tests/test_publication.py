"""Publication recovery tests run the real shell wrapper with fake external commands."""
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from publication import fingerprint, last_published, record_published, state_path

ROOT = Path(__file__).resolve().parents[2]


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ['data', 'astro', 'python', 'scripts', 'bin']:
            (self.root / folder).mkdir()
        self.db_path = self.root / 'data' / 'parliament.db'
        conn = sqlite3.connect(self.db_path)
        conn.executescript((ROOT / 'python/schema.sql').read_text())
        today = datetime.now(ZoneInfo('Asia/Singapore')).strftime('%Y-%m-%d')
        conn.execute('INSERT INTO sittings (id, date) VALUES (?, ?)', ('today', today))
        conn.commit()
        conn.close()
        (self.root / 'astro/page.astro').write_text('<p>Test page</p>')
        (self.root / 'data/budget.csv').write_text('year,amount\n2026,1\n')
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)

    def test_fingerprint_covers_all_published_inputs_but_not_ingestion_provenance(self):
        initial = fingerprint(self.db_path, self.root)
        conn = sqlite3.connect(self.db_path)
        with conn:
            conn.execute("UPDATE sittings SET created_at='different'")
            conn.execute("INSERT INTO sections (id, sitting_id, category, section_type, section_title) VALUES ('q', 'today', 'question', 'OA', 'Question')")
        with_section = fingerprint(self.db_path, self.root)
        self.assertNotEqual(initial, with_section)
        with conn:
            conn.execute("INSERT INTO section_sources VALUES ('today', 'source-1', 'q')")
        self.assertEqual(with_section, fingerprint(self.db_path, self.root))
        with conn:
            conn.execute("UPDATE sittings SET created_at='another timestamp'")
        self.assertEqual(with_section, fingerprint(self.db_path, self.root))
        with conn:
            conn.execute("INSERT INTO members (id,name) VALUES ('m','Example')")
            conn.execute("INSERT INTO member_summaries (member_id,summary) VALUES ('m','Profile')")
        with_profile = fingerprint(self.db_path, self.root)
        self.assertNotEqual(with_section, with_profile)
        conn.close()
        (self.root / 'data/budget.csv').write_text('year,amount\n2026,2\n')
        with_budget = fingerprint(self.db_path, self.root)
        self.assertNotEqual(with_profile, with_budget)
        (self.root / 'astro/page.astro').write_text('<p>Changed</p>')
        self.assertNotEqual(with_budget, fingerprint(self.db_path, self.root))

    def executable(self, name, body):
        path = self.root / 'bin' / name
        path.write_text(f'#!{sys.executable}\n' + body)
        path.chmod(0o755)

    def setup_wrapper(self):
        shutil.copy(ROOT / 'python/publication.py', self.root / 'python/publication.py')
        shell = (ROOT / 'scripts/daily_pipeline.sh').read_text()
        shell = shell.replace('LAUNCHD_PATH_PREFIX="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin"',
                              f'LAUNCHD_PATH_PREFIX="{self.root / "bin"}"')
        (self.root / 'scripts/daily_pipeline.sh').write_text(shell)
        real_git = shutil.which('git')
        self.executable('git', f'''import os, sys
if 'rev-parse' in sys.argv:
    print('main')
elif 'status' in sys.argv:
    pass
else:
    os.execv({real_git!r}, [{real_git!r}] + sys.argv[1:])
''')
        self.executable('uv', '''import os, sys
if sys.argv[1:3] != ['run', 'publication.py']:
    raise RuntimeError('Unexpected ingestion or paid summary call: ' + repr(sys.argv))
os.execv(sys.executable, [sys.executable] + sys.argv[2:])
''')
        self.executable('bun', f'''import sys
from pathlib import Path
root = Path({str(self.root)!r})
with (root / 'calls').open('a') as f:
    f.write(' '.join(sys.argv[1:]) + '\\n')
if sys.argv[1:] == ['run', 'build'] and (root / 'change_during_build').exists():
    (root / 'astro/page.astro').write_text('Changed during build')
if sys.argv[1:] == ['run', 'deploy'] and (root / 'fail_deploy').exists():
    sys.exit(1)
''')

    def run_wrapper(self, *args):
        env = dict(os.environ, PARLIAMENT_DB_PATH=str(self.db_path))
        return subprocess.run(['bash', str(self.root / 'scripts/daily_pipeline.sh'), *args],
                              env=env, capture_output=True, text=True)

    def calls(self):
        path = self.root / 'calls'
        return path.read_text().splitlines() if path.exists() else []

    def test_failed_deploy_retries_even_when_latest_sitting_is_today(self):
        self.setup_wrapper()
        self.assertEqual('UNPUBLISHED', last_published(self.db_path))
        (self.root / 'fail_deploy').touch()
        self.assertNotEqual(0, self.run_wrapper('--publish-only').returncode)
        self.assertFalse(state_path(self.db_path).exists())
        (self.root / 'fail_deploy').unlink()
        # Normal daily invocation has no dates left, but must still retry publication.
        result = self.run_wrapper()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(fingerprint(self.db_path, self.root), last_published(self.db_path))
        count = len(self.calls())
        self.assertEqual(0, self.run_wrapper().returncode)
        self.assertEqual(count, len(self.calls()))
        self.assertEqual(0, self.run_wrapper('--force-deploy').returncode)
        self.assertEqual(count + 2, len(self.calls()))

    def test_skip_and_dry_run_do_not_mark_inputs_published(self):
        self.setup_wrapper()
        for flag in ['--skip-deploy', '--dry-run']:
            self.assertEqual(0, self.run_wrapper('--publish-only', flag).returncode)
            self.assertFalse(state_path(self.db_path).exists())
        self.assertEqual([], self.calls())

    def test_changed_inputs_during_build_do_not_deploy_or_mark_success(self):
        self.setup_wrapper()
        previous = fingerprint(self.db_path, self.root)
        record_published(self.db_path, previous)
        (self.root / 'change_during_build').touch()
        self.assertNotEqual(0, self.run_wrapper('--publish-only', '--force-deploy').returncode)
        self.assertEqual(['run build'], self.calls())
        self.assertEqual(previous, last_published(self.db_path))


if __name__ == '__main__':
    unittest.main()
