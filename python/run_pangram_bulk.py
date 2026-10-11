"""Send exported speeches to the Pangram Bulk API and store every response.

Reads speeches.jsonl from export_pangram_speeches.py. Without --submit it only prints the
plan and estimated cost; with --submit it sends unsent speeches in requests under the
per-request unit limit. Every run first collects results for jobs already submitted.
--write-csv instead writes the same selection as a tag,text CSV for the Pangram dashboard;
speeches with a saved result, including imported dashboard reports, are never selected.
Pangram keeps bulk results for 48 hours, so raw pages are written as soon as they arrive.

State lives in <export-dir>/pangram/: jobs.jsonl (append-only submissions), raw/<bulk_id>/
(unmodified API responses) and results.jsonl (one line per speech). A speech recorded in
jobs.jsonl is never sent again; delete its job line by hand to resend it.
"""
import argparse
import csv
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from export_pangram_speeches import DEFAULT_OUT

BASE_URL = 'https://text.external-api.pangram.com'
WORDS_PER_UNIT = 100
USD_PER_UNIT = 0.04  # $0.05 realtime rate less the 20% bulk discount
API_UNIT_LIMIT = 1000
TERMINAL = {'succeeded', 'failed', 'partial'}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def units(words):
    return max(1, math.ceil(words / WORDS_PER_UNIT))


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def append_jsonl(path, rows):
    with open(path, 'a', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
        f.flush()
        os.fsync(f.fileno())


def chunk(speeches, max_units):
    """Group speeches in order so each request stays within max_units."""
    chunks, current, used = [], [], 0
    for s in speeches:
        need = units(s['words'])
        if current and used + need > max_units:
            chunks.append(current)
            current, used = [], 0
        current.append(s)
        used += need
    return chunks + ([current] if current else [])


def make_session(api_key):
    session = requests.Session()
    session.headers['x-api-key'] = api_key
    # Only GETs are retried: a repeated POST /bulk could bill the same speeches twice.
    retry = Retry(total=3, backoff_factor=1, allowed_methods={'GET'},
                  status_forcelist={500, 502, 503, 504})
    session.mount('https://', HTTPAdapter(max_retries=retry))
    return session


def check(response):
    if response.status_code >= 400:
        raise SystemExit(f'Pangram returned {response.status_code}: {response.text[:500]}')
    return response.json()


def select(speeches, args):
    rows = [s for s in speeches if s['upload_batch'] in set(map(str, args.years))]
    if args.exclude_office_holders:
        rows = [s for s in rows if not s['is_office_holder']]
    if args.ids:
        rows = [s for s in rows if s['speech_id'] in set(args.ids)]
    return rows[:args.limit] if args.limit else rows


def submit(session, state_dir, todo, model, max_units):
    for group in chunk(todo, max_units):
        body = {'items': [{'id': s['speech_id'], 'text': s['text']} for s in group], 'model': model}
        record = {'submitted_at': now(), 'model': model, 'speech_ids': [s['speech_id'] for s in group],
                  'estimated_units': sum(units(s['words']) for s in group)}
        try:
            response = session.post(f'{BASE_URL}/bulk', json=body, timeout=120)
        except requests.RequestException as exc:
            # The job may exist without our knowing its ID; record it so nothing is resent.
            append_jsonl(state_dir / 'jobs.jsonl', [{**record, 'bulk_id': None, 'error': str(exc)}])
            raise SystemExit(f'Submission outcome unknown ({exc}). Check the Pangram dashboard before '
                             'removing the bulk_id=null line from jobs.jsonl.')
        data = check(response)
        append_jsonl(state_dir / 'jobs.jsonl', [{**record, 'bulk_id': data['bulk_id'], 'response': data}])
        print(f"Submitted {data['bulk_id']}: {len(group)} speeches, ~{record['estimated_units']} units")


def collect(session, state_dir, job, poll_seconds, sleep):
    bulk_id = job['bulk_id']
    raw = state_dir / 'raw' / bulk_id
    raw.mkdir(parents=True, exist_ok=True)
    while True:
        status = check(session.get(f'{BASE_URL}/bulk/{bulk_id}', timeout=60))
        if status['status'] in TERMINAL:
            break
        print(f"{bulk_id}: {status['status']} ({status.get('succeeded', 0)}/{status.get('total_items')})")
        sleep(poll_seconds)
    (raw / 'status.json').write_text(json.dumps(status, indent=2) + '\n')

    rows, offset, fetched_at = {}, 0, now()
    while offset < status['total_items']:
        page = check(session.get(f'{BASE_URL}/bulk/{bulk_id}/results',
                                 params={'offset': offset, 'limit': API_UNIT_LIMIT}, timeout=120))
        (raw / f'results-{offset:05d}.json').write_text(json.dumps(page, ensure_ascii=False) + '\n')
        for item in page.get('failed_items', []) + page.get('items', []):
            result = item.get('result') or None
            success = bool(result and result.get('stage') == 'STAGE_SUCCESS')
            if success or item.get('id') not in rows:
                rows[item.get('id')] = {
                    'speech_id': item.get('id'), 'bulk_id': bulk_id, 'task_id': item.get('task_id'),
                    'model': job['model'], 'fetched_at': fetched_at,
                    'status': 'success' if success else 'failed', 'error': item.get('error'), 'result': result}
        offset += page.get('limit') or API_UNIT_LIMIT
    append_jsonl(state_dir / 'results.jsonl', rows.values())
    ok = sum(r['status'] == 'success' for r in rows.values())
    print(f'{bulk_id}: {status["status"]}, saved {ok} results and {len(rows) - ok} failures')


def write_csv(path, speeches):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['tag', 'text'])
        writer.writerows([s['speech_id'], s['text']] for s in speeches)


def run(args, session=None, sleep=time.sleep):
    speeches = read_jsonl(args.export_dir / 'speeches.jsonl')
    if not speeches:
        raise SystemExit(f'No speeches.jsonl in {args.export_dir}; run export_pangram_speeches.py first.')
    state_dir = args.export_dir / 'pangram'
    state_dir.mkdir(parents=True, exist_ok=True)
    jobs = read_jsonl(state_dir / 'jobs.jsonl')
    collected = {r['bulk_id'] for r in read_jsonl(state_dir / 'results.jsonl')}
    sent = {sid for job in jobs for sid in job['speech_ids']}
    sent |= {r['speech_id'] for r in read_jsonl(state_dir / 'results.jsonl') if r['status'] == 'success'}
    pending = [j for j in jobs if j['bulk_id'] and j['bulk_id'] not in collected]
    unknown = [j for j in jobs if not j['bulk_id']]
    todo = [s for s in select(speeches, args) if s['speech_id'] not in sent]

    total_units = sum(units(s['words']) for s in todo)
    print(f'Selected {len(todo)} unsent speeches, {sum(s["words"] for s in todo):,} words, '
          f'{total_units:,} units, ~${total_units * USD_PER_UNIT:,.2f} in '
          f'{len(chunk(todo, args.max_units))} request(s). Pending jobs: {len(pending)}.')
    if unknown:
        print(f'{len(unknown)} submission(s) have an unknown outcome; see jobs.jsonl.')
    if args.write_csv:
        write_csv(args.write_csv, todo)
        print(f'Wrote {len(todo)} speeches to {args.write_csv} for the Pangram dashboard. '
              'Nothing is recorded, so upload it once.')
        return
    if not pending and not (args.submit and todo):
        if todo:
            print('Dry run: add --submit to send these speeches.')
        return

    if session is None:
        load_dotenv()
        key = os.getenv('PANGRAM_API_KEY')
        if not key:
            raise SystemExit('Set PANGRAM_API_KEY in the environment or .env.')
        session = make_session(key)
    for job in pending:
        collect(session, state_dir, job, args.poll_seconds, sleep)
    if args.submit and todo:
        models = check(session.get(f'{BASE_URL}/models', timeout=60)).get('models', [])
        if args.model not in models:
            raise SystemExit(f'Model {args.model!r} is not available to this key: {models}')
        submit(session, state_dir, todo, args.model, args.max_units)
        done = {r['bulk_id'] for r in read_jsonl(state_dir / 'results.jsonl')}
        for job in read_jsonl(state_dir / 'jobs.jsonl'):
            if job['bulk_id'] and job['bulk_id'] not in done:
                collect(session, state_dir, job, args.poll_seconds, sleep)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--years', nargs='+', type=int, default=[2020, 2025])
    parser.add_argument('--exclude-office-holders', action='store_true')
    parser.add_argument('--ids', nargs='+', help='Only these speech_ids')
    parser.add_argument('--limit', type=int, help='Only the first N selected speeches')
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--submit', action='store_true', help='Spend credits on unsent speeches')
    action.add_argument('--write-csv', type=Path, help='Write unsent speeches as a dashboard upload instead')
    parser.add_argument('--model', default='pangram-4')
    parser.add_argument('--max-units', type=int, default=900,
                        help=f'Units per request; Pangram allows {API_UNIT_LIMIT} and may count words differently')
    parser.add_argument('--poll-seconds', type=float, default=15)
    parser.add_argument('--export-dir', type=Path, default=DEFAULT_OUT)
    return parser.parse_args(argv)


if __name__ == '__main__':
    run(parse_args())
