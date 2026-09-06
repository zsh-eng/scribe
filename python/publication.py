"""Fingerprint published inputs and record only successful deployments.

Includes all frontend tables, frontend source/configuration and budget CSVs.
Ingestion provenance and database storage details do not trigger publication.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

TABLES = ('sittings', 'members', 'ministries', 'bills', 'sections',
          'section_speakers', 'sitting_attendance', 'member_summaries')
ROOT = Path(__file__).resolve().parent.parent


def fingerprint(db_path, root=ROOT):
    digest = hashlib.sha256()

    def add(value):
        payload = json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
        digest.update(len(payload).to_bytes(8, 'big'))
        digest.update(payload)

    # One consistent read transaction; no WAL/checkpoint or timestamp noise.
    conn = sqlite3.connect(Path(db_path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        conn.execute('BEGIN')
        for table in TABLES:
            info = conn.execute(f'PRAGMA table_info({table})').fetchall()
            columns = [row[1] for row in info
                       if row[1] not in ('created_at', 'last_updated')]
            if not columns:
                raise ValueError(f'Missing publication table: {table}')
            names = ', '.join(f'"{column}"' for column in columns)
            keys = [row[1] for row in sorted(info, key=lambda row: row[5]) if row[5]]
            order = ', '.join(f'"{key}"' for key in keys)
            add([table, columns])
            for row in conn.execute(f'SELECT {names} FROM {table} ORDER BY {order}'):
                add(row)
    finally:
        conn.close()
    files = subprocess.check_output(
        ['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard', '--', 'astro'],
    ).decode().split('\0')
    paths = {root / name for name in files if name and not name.endswith('.DS_Store')}
    paths.update((root / 'data').glob('*.csv'))
    paths.update((root / 'data').glob('GovernmentBudgetandFiscalPositionAnnual/*.csv'))
    paths.update((root / 'data' / 'curated').rglob('*.json'))
    for path in sorted(paths):
        add(str(path.relative_to(root)))
        add(hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else 'MISSING')
    return digest.hexdigest()


def state_path(db_path):
    return Path(db_path).with_suffix('.published.json')


def last_published(db_path):
    path = state_path(db_path)
    if not path.exists():
        return 'UNPUBLISHED'
    return json.loads(path.read_text())['fingerprint']


def record_published(db_path, value):
    """Caller supplies the fingerprint captured before the successful build."""
    path = state_path(db_path)
    payload = json.dumps({'fingerprint': value,
                          'published_at': datetime.now(timezone.utc).isoformat()}, indent=2) + '\n'
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.published-')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(payload)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('fingerprint', 'last', 'record'))
    parser.add_argument('--db', required=True)
    parser.add_argument('--fingerprint')
    args = parser.parse_args()
    if args.action == 'fingerprint':
        print(fingerprint(args.db))
    elif args.action == 'last':
        print(last_published(args.db))
    else:
        if not args.fingerprint or len(args.fingerprint) != 64:
            parser.error('record requires a SHA-256 --fingerprint')
        record_published(args.db, args.fingerprint)
