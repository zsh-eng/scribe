"""Build the internal Pangram results explorer as one self-contained HTML file.

Joins speeches.jsonl with pangram/results.jsonl, adds speaking order from the database and
injects the data into pangram_explorer.html. Timeless fonts are embedded when their folder
is available (the licence allows embedding in a work but not redistributing the files, so
they are read from the local download rather than kept in the repository). Portraits come from
fetch_mp_photos.py and are embedded with their credits; the chamber view uses attendance.
"""
import argparse
import base64
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path

from db_sqlite import DB_PATH
from export_pangram_speeches import DEFAULT_OUT
from run_pangram_bulk import read_jsonl

TEMPLATE = Path(__file__).with_name('pangram_explorer.html')
DEFAULT_FONTS = Path.home() / 'Downloads' / 'Timeless-Type-Family-1.094'
FONTS = [
    ('Timeless Serif', 300, 'normal', 'Serif-Text/static/woff2/TimelessSerif-Light.woff2'),
    ('Timeless Serif', 300, 'italic', 'Serif-Text/static/woff2/TimelessSerif-LightItalic.woff2'),
    ('Timeless Serif Text', 400, 'normal', 'Serif-Text/static/woff2/TimelessSerif-TextRegular.woff2'),
    ('Timeless Sans Grotesk', 400, 'normal', 'Sans-Grotesk/static/woff2/TimelessSans-GroteskRegular.woff2'),
    ('Timeless Sans Grotesk', 500, 'normal', 'Sans-Grotesk/static/woff2/TimelessSans-GroteskMedium.woff2'),
]
CONFIDENCE = {'Low': 0, 'Medium': 1, 'High': 2}
DEFAULT_PHOTOS = DEFAULT_OUT.parent / 'photos'
# Seats held by opposition MPs in each Parliament; NCMPs are matched by name.
OPPOSITION_SEATS = {'Aljunied': 'WP', 'Sengkang': 'WP', 'Hougang': 'WP'}
NCMP_PARTY = {'Leong Mun Wai': 'PSP', 'Hazel Poa': 'PSP', 'Eileen Chong Pei Shan': 'WP', 'Low Wu Yang Andre': 'WP'}
OFFICE = re.compile(r'Minister|Parliamentary Secretary', re.I)


def party_of(name, constituency):
    if constituency == 'Nominated Member':
        return 'NMP'
    if constituency == 'Non-Constituency Member':
        return NCMP_PARTY.get(name, 'Opposition')
    return OPPOSITION_SEATS.get(constituency, 'PAP')


def photo_uri(path, size=176):
    """Return a small JPEG data URI, resized with macOS sips when available."""
    data = path.read_bytes()
    if shutil.which('sips'):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'p.jpg'
            subprocess.run(['sips', '-Z', str(size), '-s', 'format', 'jpeg', '-s', 'formatOptions', '74',
                            str(path), '--out', str(out)], capture_output=True, check=False)
            if out.exists():
                data = out.read_bytes()
    return 'data:image/jpeg;base64,' + base64.b64encode(data).decode()


def common_name(credit, fallback):
    article = (credit or {}).get('article')
    return re.sub(r'\s*\(.*?\)$', '', article) if article else fallback


def font_css(font_dir):
    rules = []
    for family, weight, style, rel in FONTS:
        path = font_dir / rel
        if not path.exists():
            print(f'Font not found, using fallback: {path}')
            continue
        data = base64.b64encode(path.read_bytes()).decode()
        rules.append(f"@font-face {{ font-family: '{family}'; font-weight: {weight}; font-style: {style}; "
                     f"font-display: swap; src: url(data:font/woff2;base64,{data}) format('woff2'); }}")
    return '\n'.join(rules)


def section_order(db_path, section_ids):
    conn = sqlite3.connect(f'file:{Path(db_path).resolve()}?mode=ro', uri=True)
    try:
        marks = ','.join('?' * len(section_ids))
        return dict(conn.execute(f'SELECT id, section_order FROM sections WHERE id IN ({marks})', list(section_ids)))
    finally:
        conn.close()


def attendance(db_path, dates):
    """Members present on any debate day, with their latest constituency and designation."""
    conn = sqlite3.connect(f'file:{Path(db_path).resolve()}?mode=ro', uri=True)
    try:
        marks = ','.join('?' * len(dates))
        rows = conn.execute(f'''SELECT a.member_id, m.name, a.constituency, a.designation, s.date
                                FROM sitting_attendance a JOIN sittings s ON s.id = a.sitting_id
                                JOIN members m ON m.id = a.member_id
                                WHERE a.present = 1 AND s.date IN ({marks}) ORDER BY s.date''', list(dates)).fetchall()
    finally:
        conn.close()
    latest = {}
    for member_id, name, constituency, designation, _ in rows:
        latest[member_id] = (name, constituency, designation)
    return latest


def build_data(export_dir, db_path, photo_dir):
    speeches = {s['speech_id']: s for s in read_jsonl(export_dir / 'speeches.jsonl')}
    results = {}
    for r in read_jsonl(export_dir / 'pangram' / 'results.jsonl'):
        if r['status'] == 'success':
            results[r['speech_id']] = r  # later lines win
    scanned = [speeches[sid] for sid in results if sid in speeches]
    if not scanned:
        raise SystemExit('No scanned speeches found; run run_pangram_bulk.py first.')
    years = sorted({s['upload_batch'] for s in scanned})
    dates = {y: sorted({s['date'] for s in scanned if s['upload_batch'] == y}) for y in years}
    present = {y: attendance(db_path, dates[y]) for y in years}

    credits_path = photo_dir / 'credits.json'
    credits = json.loads(credits_path.read_text()) if credits_path.exists() else {}
    names = {s['member_id']: s['member_name'] for s in scanned if s['member_id']}
    for y in years:
        names.update({mid: row[0] for mid, row in present[y].items()})
    member_ids = sorted(names)
    width = len(str(len(member_ids)))
    members, index, used_credits = [], {}, []
    for k, mid in enumerate(member_ids):
        index[mid] = k
        credit = credits.get(mid)
        photo = None
        if credit and credit.get('file') and (photo_dir / credit['file']).exists():
            photo = photo_uri(photo_dir / credit['file'])
            used_credits.append({'name': common_name(credit, names[mid]), 'author': credit.get('author') or 'Unknown',
                                 'license': credit.get('license'), 'url': credit.get('page')})
        members.append({'code': f'MP {k + 1:0{width}d}', 'name': common_name(credit, names[mid]),
                        'full': names[mid], 'photo': photo})

    chamber = {}
    for y in years:
        chamber[y] = [{'m': index[mid], 'party': party_of(name, con), 'con': con, 'desig': desig,
                       'office': bool(OFFICE.search(desig or ''))}
                      for mid, (name, con, desig) in sorted(present[y].items())]

    orders = section_order(db_path, {s['section_id'] for s in scanned})
    rows = []
    for s in sorted(scanned, key=lambda s: (s['date'], orders.get(s['section_id'], 0), s['turn_index'])):
        res = results[s['speech_id']]['result']
        segs = [[w['start_index'], w['end_index'], CONFIDENCE.get(w['confidence'], 0),
                 round(w['ai_assistance_score'], 3), w['word_count'], int(bool(w.get('is_humanized')))]
                for w in res['windows'] if w['label'] != 'Human Written']
        rows.append({
            'id': s['speech_id'], 'y': s['upload_batch'], 'date': s['date'], 'ord': len(rows),
            'm': index.get(s['member_id'], -1), 'label': s['speaker_label'],
            'role': 'off' if s['is_office_holder'] else ('new' if s['first_parliament'] else 'ret'),
            'party': party_of(s['member_name'], s['constituency']),
            'desig': s['designation'], 'con': s['constituency'], 'words': s['words'],
            'chars': len(res['text']), 'v': res['prediction_short'], 'fa': round(res['fraction_ai'], 4),
            'segs': sorted(segs), 'url': s['secondreading_url'], 'text': res['text'],
        })
    fetched = max(results[s['speech_id']]['fetched_at'] for s in scanned)
    versions = sorted({results[s['speech_id']]['result'].get('version') for s in scanned})
    models = sorted({results[s['speech_id']]['model'] for s in scanned})
    meta = {'scanned': fetched[:10], 'model': ', '.join(models), 'version': ', '.join(versions), 'dates': dates}
    used_credits.sort(key=lambda c: c['name'])
    return {'meta': meta, 'members': members, 'chamber': chamber, 'speeches': rows, 'credits': used_credits}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--export-dir', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--db', default=DB_PATH)
    parser.add_argument('--fonts', type=Path, default=DEFAULT_FONTS)
    parser.add_argument('--photos', type=Path, default=DEFAULT_PHOTOS)
    parser.add_argument('--out', type=Path, help='Defaults to <export-dir>/who-wrote-the-address.html')
    args = parser.parse_args()

    data = build_data(args.export_dir, args.db, args.photos)
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    page = TEMPLATE.read_text(encoding='utf-8')
    page = page.replace('/*__FONTS__*/', font_css(args.fonts)).replace('/*__DATA__*/null', payload)
    head = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n')
    out = args.out or args.export_dir / 'who-wrote-the-address.html'
    out.write_text(head + page + '\n</html>\n', encoding='utf-8')
    print(f'Wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {len(data["speeches"])} speeches)')


if __name__ == '__main__':
    main()
