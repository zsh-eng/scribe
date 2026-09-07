"""Fetch and transform historical sittings outside the application database and build.

Each date has independent raw, normalized, and state files. Re-running fetch resumes
missing reports. Re-running transform uses saved bytes and makes no network requests.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
import logging
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'python'))
from bs4 import BeautifulSoup
import requests
from modern_hansard import parse_modern
from legacy_hansard import parse_legacy

URL = 'https://sprs.parl.gov.sg/search/getHansardReport'
DATA = ROOT / 'data'
logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')


def atomic(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def write_json(path, data):
    payload = (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
    atomic(path, gzip.compress(payload, mtime=0) if path.suffix == '.gz' else payload)


def read_json(path):
    payload = path.read_bytes()
    return json.loads(gzip.decompress(payload) if path.suffix == '.gz' else payload)


def paths(date):
    return (DATA / 'raw' / f'{date}.json.gz', DATA / 'normalized' / f'{date}.json.gz',
            DATA / 'state' / f'{date}.json')


def fetch(date):
    raw, _, state_path = paths(date)
    if raw.exists():
        return date, 'cached'
    request_date = datetime.strptime(date, '%Y-%m-%d').strftime('%d-%m-%Y')
    last = None
    for attempt in range(3):
        try:
            response = requests.post(URL, json={'sittingDate': request_date}, timeout=(15, 60))
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or not (data.get('htmlFullContent') or data.get('takesSectionVOList')):
                raise ValueError('Response has no report content')
            write_json(raw, data)
            write_json(state_path, {'date': date, 'fetch_status': 'ok', 'url': URL,
                                   'request': {'sittingDate': request_date},
                                   'fetched_at': datetime.now(timezone.utc).isoformat(),
                                   'raw_sha256': hashlib.sha256(raw.read_bytes()).hexdigest()})
            return date, 'fetched'
        except (requests.RequestException, ValueError) as error:
            last = f'{type(error).__name__}: {error}'
            time.sleep(1 + attempt)
    write_json(state_path, {'date': date, 'fetch_status': 'failed', 'error': last})
    return date, 'failed'


def institution(date):
    return 'legislative_assembly' if date < '1965-08-09' else 'parliament'


def transform(date):
    raw, output, state_path = paths(date)
    if not raw.exists():
        return date, 'missing_raw'
    data = read_json(raw)
    state = read_json(state_path) if state_path.exists() else {'date': date, 'fetch_status': 'ok'}
    request_date = datetime.strptime(date, '%Y-%m-%d').strftime('%d-%m-%Y')
    try:
        if data.get('htmlFullContent'):
            sitting = parse_legacy(request_date, data['htmlFullContent'])
        else:
            sitting = parse_modern(request_date, data)
        audit = getattr(sitting, 'parse_audit', {})
        sections = []
        for section in sitting.sections:
            sections.append({**section, 'speakers': [vars(mp) for mp in section['speakers']]})
        status = 'needs_review' if audit.get('segmentation_status') in ('unsegmented', 'empty') else 'parsed'
        era = institution(date)
        identified = sitting.metadata.get('institution')
        if isinstance(identified, dict):
            era = {'Legislative Assembly': 'legislative_assembly', 'Legislative Council': 'legislative_council',
                   'Parliament of Singapore': 'parliament'}.get(identified.get('name'), 'unknown')
        record = {'schema_version': 1, 'date': date, 'institution': era,
                  'metadata': sitting.metadata, 'status': status,
                  'source': {'url': URL, 'request': {'sittingDate': request_date},
                             'raw_file': f'raw/{date}.json.gz',
                             'raw_sha256': hashlib.sha256(raw.read_bytes()).hexdigest()},
                  'attendance': {'present': [vars(mp) for mp in sitting.present_members],
                                 'absent': [vars(mp) for mp in sitting.absent_members]},
                  'sections': sections, 'audit': audit}
        state.update(transform_status=status, sections=len(sections),
                     unclassified=sum(s['section_type'] is None for s in sections))
        state.pop('transform_error', None)
    except Exception as error:
        # Still provide searchable source text when a layout cannot yet be segmented.
        html = data.get('htmlFullContent') or '\n'.join(s.get('content') or '' for s in data.get('takesSectionVOList', []))
        record = {'schema_version': 1, 'date': date, 'institution': institution(date),
                  'status': 'needs_review', 'source': {'raw_file': f'raw/{date}.json.gz'},
                  'sections': [], 'full_text': BeautifulSoup(html, 'html.parser').get_text(' ', strip=True),
                  'error': f'{type(error).__name__}: {error}'}
        state.update(transform_status='needs_review', transform_error=record['error'], sections=0)
    write_json(output, record)
    write_json(state_path, state)
    return date, record['status']


def inventory_dates(path):
    inventory = read_json(path)
    return sorted({row['date'] for row in inventory['sittings'] if not row.get('present_in_active', False)})


def summarize(dates):
    from collections import Counter
    statuses, kinds = Counter(), Counter()
    totals = Counter()
    members = set()
    with (DATA / 'index.jsonl').open('w') as index:
        for date in dates:
            raw, output, state_path = paths(date)
            state = read_json(state_path) if state_path.exists() else {'date': date, 'fetch_status': 'not_attempted'}
            index.write(json.dumps(state, sort_keys=True) + '\n')
            statuses[state.get('transform_status', state['fetch_status'])] += 1
            if output.exists():
                record = read_json(output)
                for section in record.get('sections', []):
                    kinds[section.get('section_type') or 'unclassified'] += 1
                    totals['text_characters'] += len(section.get('content_plain', ''))
                    for member in section.get('speakers', []):
                        members.add(member['name'])
                totals['sections'] += len(record.get('sections', []))
                totals['fallback_text_characters'] += len(record.get('full_text', ''))
    summary = {'target_sittings': len(dates), 'statuses': dict(statuses), 'section_types': dict(kinds),
               'speaker_names': len(members), **dict(totals)}
    write_json(DATA / 'summary.json', summary)
    print(json.dumps(summary, indent=2), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['fetch', 'transform', 'summary'])
    parser.add_argument('--inventory', type=Path, default=DATA / 'inventory' / 'inventory.json')
    parser.add_argument('--date', action='append', help='Restrict to ISO date; repeatable')
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    DATA.mkdir(exist_ok=True)
    dates = args.date or inventory_dates(args.inventory)
    if args.action != 'summary':
        worker = fetch if args.action == 'fetch' else transform
        executor_type = ProcessPoolExecutor if args.action == 'transform' else ThreadPoolExecutor
        with executor_type(max_workers=args.workers) as executor:
            futures = {executor.submit(worker, date): date for date in dates}
            for number, future in enumerate(as_completed(futures), 1):
                date, status = future.result()
                print(f'{number}/{len(dates)} {date} {status}', flush=True)
    summarize(dates)


if __name__ == '__main__':
    main()
