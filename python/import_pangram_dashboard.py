"""Import Pangram dashboard reports into the same results.jsonl as the bulk API.

Reads JSONL files of reports saved from the dashboard history, one line per report with its HTTP
status, fetch time and the report JSON. Each report is joined to speeches.jsonl by its file name,
which is the speech_id tag from the upload CSV, and is
imported only if the text Pangram scanned is exactly the text we exported. Window fields are
renamed to the bulk API's ("Human" becomes "Human Written"; ai_likelihood is also stored as
ai_assistance_score) and every other field is kept. Each downloaded file is copied unchanged to
pangram/raw/dashboard/, and reports already imported are skipped, so a file can be imported twice.
"""
import argparse
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from export_pangram_speeches import PREPARED_OUT
from run_pangram_bulk import append_jsonl, read_jsonl

LABELS = {'Human': 'Human Written'}


def normalise(payload):
    """The dashboard's result with windows in the bulk API's shape."""
    windows = []
    for w in payload.get('windows') or []:
        w = {**w, 'label': LABELS.get(w.get('label'), w.get('label'))}
        if 'ai_assistance_score' not in w and 'ai_likelihood' in w:
            w['ai_assistance_score'] = w['ai_likelihood']
        windows.append(w)
    return {**payload, 'windows': windows}


def import_reports(paths, export_dir):
    speeches = {s['speech_id']: s for s in read_jsonl(export_dir / 'speeches.jsonl')}
    if not speeches:
        raise SystemExit(f'No speeches.jsonl in {export_dir}; run export_pangram_speeches.py first.')
    state = export_dir / 'pangram'
    raw = state / 'raw' / 'dashboard'
    raw.mkdir(parents=True, exist_ok=True)
    existing = read_jsonl(state / 'results.jsonl')
    imported = {r['report_uuid'] for r in existing if r.get('report_uuid')}
    scanned = {r['speech_id'] for r in existing if r['status'] == 'success'}

    counts, rows = Counter(), []
    for path in paths:
        data = path.read_bytes()
        copy = raw / f'{hashlib.sha256(data).hexdigest()[:12]}-{path.name}'
        if not copy.exists():
            shutil.copy2(path, copy)
        for record in read_jsonl(path):
            report = record.get('json')
            if record.get('status') != 200 or not isinstance(report, dict):
                counts['not_fetched'] += 1
                continue
            if report.get('uuid') in imported:
                counts['already_imported'] += 1
                continue
            speech_id = report.get('file_name') or record.get('label')
            speech = speeches.get(speech_id)
            if speech is None:
                counts['not_in_export'] += 1
                continue
            if report.get('prompt') != speech['text']:
                counts['text_differs'] += 1
                print(f'Skipped {speech_id}: Pangram scanned different text from the export')
                continue
            payload = report.get('response_payload') or {}
            success = payload.get('stage') == 'STAGE_SUCCESS'
            if success and speech_id in scanned:
                counts['rescanned'] += 1
            rows.append({
                'speech_id': speech_id, 'source': 'dashboard', 'bulk_id': None, 'report_uuid': report['uuid'],
                'task_id': payload.get('task_id'), 'model': f"dashboard-{payload.get('version')}",
                'scanned_at': report.get('timestamp'), 'fetched_at': record.get('fetchedAt'),
                'imported_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'raw_file': copy.name,
                'status': 'success' if success else 'failed', 'error': None if success else payload.get('stage'),
                'result': normalise(payload) if success else None,
            })
            imported.add(report['uuid'])
            if success:
                scanned.add(speech_id)
            counts['imported' if success else 'failed'] += 1
    append_jsonl(state / 'results.jsonl', rows)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('files', nargs='+', type=Path, help='pangram-history-reports-*.jsonl downloads')
    parser.add_argument('--export-dir', type=Path, default=PREPARED_OUT)
    args = parser.parse_args()
    counts = import_reports(args.files, args.export_dir)
    print(', '.join(f'{k.replace("_", " ")}: {v}' for k, v in counts.items()) or 'Nothing to import')
    if counts['rescanned']:
        print('Rescanned speeches now have more than one result; the build uses the latest.')


if __name__ == '__main__':
    main()
