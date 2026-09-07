"""Build a separate sitting-date inventory from the official public search index.

No imports from the active pipeline. The active database is opened read-only.
Run: python3 historical/inventory.py [--refresh]
"""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
from urllib.request import Request, urlopen

BASE_URL = 'https://sprs.parl.gov.sg/search/'
ROOT = Path(__file__).resolve().parent


def query_payload(upper):
    return dict(keyword='', dateRange='custom', fromday='1', frommonth='1',
                fromyear='1955', today=str(upper.day), tomonth=str(upper.month),
                toyear=str(upper.year), reportContent='with all the words',
                parliamentNo='', selectedSort='date_dt desc', startIndex='0',
                endIndex='19', titleChecked='false', footNoteChecked='false')


def fetch_page(upper, cache, refresh=False):
    target = cache / f'{upper.isoformat()}.json'
    payload = query_payload(upper)
    if target.exists() and not refresh:
        saved = json.loads(target.read_text())
        if saved['request'] != payload:
            raise ValueError(f'Cache request mismatch: {target}')
        return saved['response']
    request = Request(BASE_URL + 'searchResult', data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json'})
    for attempt in range(4):
        try:
            with urlopen(request, timeout=60) as response:
                raw = response.read()
            rows = json.loads(raw)
            if not isinstance(rows, list):
                raise ValueError('Expected search result list')
            break
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)
    saved = dict(source_url=request.full_url, request=payload, response=rows,
                 retrieved_at=datetime.now(timezone.utc).isoformat(),
                 response_sha256=hashlib.sha256(raw).hexdigest())
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(saved, ensure_ascii=False) + '\n')
    temporary.replace(target)
    return rows


def parse_date(value):
    return datetime.strptime(value, '%d-%m-%Y').date()


def build_inventory(output, database, upper, refresh=False):
    cache = output / 'pages'
    cache.mkdir(parents=True, exist_ok=True)
    initial_upper = upper
    found = {}
    page_count = 0
    previous_total = None
    while upper >= date(1955, 1, 1):
        rows = fetch_page(upper, cache, refresh)
        page_count += 1
        if not rows:
            break
        total = int(rows[0]['maxResult'])
        if any(int(row['maxResult']) != total for row in rows) or total < len(rows):
            raise ValueError(f'Inconsistent search count: {upper}')
        if previous_total is not None and total >= previous_total:
            raise ValueError(f'Search count did not decrease: {upper}')
        previous_total = total
        dates = [parse_date(row['sittingDate']) for row in rows]
        if dates != sorted(dates, reverse=True) or max(dates) > upper:
            raise ValueError(f'Search is not in descending date order: {upper}')
        for row, sitting_date in zip(rows, dates):
            parliament = int(row['parlNo'])
            era = 'legislative-assembly' if parliament == 0 else 'parliament'
            item = dict(date=sitting_date.isoformat(), era=era,
                        parliament=parliament, era_id=f'{era}-{parliament}',
                        report_version=row.get('reportVersion'),
                        evidence_page=f'pages/{upper.isoformat()}.json')
            previous = found.setdefault(item['date'], item)
            if previous['era_id'] != item['era_id']:
                raise ValueError(f'Conflicting legislature for {sitting_date}')
        if total == len(rows):
            break
        upper = min(dates) - timedelta(days=1)
        if page_count % 100 == 0:
            print(f'{page_count} pages; {len(found)} dates; next {upper}', flush=True)
            write_inventory(output, database, initial_upper, found, page_count, False)
    return write_inventory(output, database, initial_upper, found, page_count, True)


def write_inventory(output, database, initial_upper, found, page_count, complete):
    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        active = {row[0] for row in db.execute('SELECT date FROM sittings')}
    sittings = sorted(found.values(), key=lambda row: row['date'])
    for row in sittings:
        row['present_in_active'] = row['date'] in active
    missing = [row['date'] for row in sittings if not row['present_in_active']]
    summary = dict(total=len(sittings), missing=len(missing), present=len(sittings)-len(missing),
                   first_date=sittings[0]['date'] if sittings else None,
                   last_date=sittings[-1]['date'] if sittings else None,
                   by_era=dict(Counter(row['era_id'] for row in sittings)),
                   active_dates_absent_from_index=sorted(active - set(found)))
    result = dict(source=BASE_URL+'searchResult', generated_at=datetime.now(timezone.utc).isoformat(),
                  through_date=initial_upper.isoformat(), complete=complete,
                  coverage='All sitting dates returned by the official search index since 1955; not a claim about records absent from that index.',
                  page_count=page_count, summary=summary, sittings=sittings)
    temporary = output/'inventory.tmp'
    temporary.write_text(json.dumps(result, indent=2)+'\n')
    temporary.replace(output/'inventory.json')
    (output/'missing_dates.txt').write_text(''.join(day+'\n' for day in missing))
    if complete:
        print(json.dumps(summary, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'data'/'inventory')
    parser.add_argument('--active-db', type=Path, default=ROOT.parent/'data'/'parliament.db')
    parser.add_argument('--through', type=date.fromisoformat, default=date.today())
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    build_inventory(args.output, args.active_db, args.through, args.refresh)


if __name__ == '__main__':
    main()
