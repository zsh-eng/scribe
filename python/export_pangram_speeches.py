"""Export President's Address or other prepared speeches for Pangram AI-detection bulk uploads.

The default scope is the President's Address debate. --scope prepared takes every motion,
adjournment motion and bill second-reading debate instead, with debate_type on each speech.
Reads the site database read-only and writes one directory of reproducible outputs:
speeches.jsonl (one speaker turn per line, with member mappings and text),
members.csv (per-member cohort view), pangram_upload_<year>.csv (tag,text) and
manifest.json (parameters, counts, billed words and output hashes).
"""
import argparse
import csv
import hashlib
import html
import json
import math
import re
import sqlite3
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from db_sqlite import DB_PATH
from util import extract_name_from_speaker_text

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / 'data' / 'ai_detection' / 'presidents_address'
PREPARED_OUT = ROOT / 'data' / 'ai_detection' / 'prepared_speeches'
DEBATE_TITLES = {'debate on presidents address', 'debate on the presidents address', 'presidents speech'}
SITE = 'https://secondreading.app'

SPEAKER_PARA = re.compile(r'^\s*<strong>(.*?)</strong>\s*(:?)(.*)$', re.S)
PRESIDING = re.compile(r'^(?:Mr|Mdm|Madam|Mrs|Ms)?\s*(?:Deputy\s+)?(?:Speaker|Chairman)\b|^The (?:Deputy )?Chairman\b', re.I)
VERNACULAR_MARK = re.compile(r'\(In (?:Mandarin|Malay|Tamil)\)', re.I)
ENGLISH_MARK = re.compile(r'^.*?\(In English\)\s*:?\s*', re.I | re.S)
SWITCH_TO_VERNACULAR = re.compile(r'\bin (?:Mandarin|Malay|Tamil),?\s*(?:please)?\s*[.?]\s*$', re.I)
OFFICE = re.compile(r'Minister|Parliamentary Secretary|Attorney-General', re.I)
# Committee of Supply heads are titled by ministry in some years.
BUDGET = re.compile(r'^(committee of supply|annual budget statement|debate on annual budget statement|'
                    r'supplementary estimates|estimates of expenditure|ministry of|prime ministers office)')
ID_PREFIX = {'address': 'pa', 'bills': 'bp', 'budget': 'bu', 'other_motion': 'mo', 'adjournment': 'am'}


@dataclass
class Turn:
    index: int
    label: str
    paragraphs: list = field(default_factory=list)
    translated_words_removed: int = 0

    @property
    def text(self):
        return '\n\n'.join(self.paragraphs)


def plain(fragment):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<.*?>', '', fragment))).strip()


def split_turns(content_html):
    """Split Hansard HTML into speaker turns, dropping translated vernacular passages.

    A paragraph opens a new turn only when a bold label is followed by a colon, so
    chair notices such as "[Deputy Speaker in the Chair]" do not cut a speech.
    Translation runs from an "(In Malay)" marker, or a closing "in Malay, please."
    request, until "(In English)" or the next speaker.
    """
    turns, current, translated, label_count = [], None, False, 0
    for para in re.findall(r'<p[^>]*>(.*?)</p>', content_html or '', re.S):
        match = SPEAKER_PARA.match(para)
        label = plain(match.group(1)).rstrip(':').strip() if match else ''
        if match and label and (match.group(2) or match.group(1).rstrip().endswith(':')):
            current = Turn(label_count, label)
            label_count += 1
            turns.append(current)
            translated = False
            para = match.group(3)
        elif match and not plain(match.group(3)):
            continue  # standalone bold notice or heading
        if current is None:
            continue
        text = plain(para)
        if not text:
            continue
        if ENGLISH_MARK.match(text) and re.search(r'\(In English\)', text, re.I):
            translated = False
            text = ENGLISH_MARK.sub('', text)
        elif VERNACULAR_MARK.search(text):
            translated = True
        if translated:
            current.translated_words_removed += len(re.sub(r'^.*?\(In \w+\)\s*:?', '', text).split())
            continue
        if SWITCH_TO_VERNACULAR.search(text):
            translated = True  # the request line is kept; what follows is translation
        if text:
            current.paragraphs.append(text)
    return turns


def slugify(text, section_id):
    """Mirror astro/src/lib/slugify.ts for site links."""
    slug = re.sub(r"[''’]", '', text.lower())
    slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')[:80].rstrip('-')
    return f'{slug}-{section_id[:8]}' if slug else section_id[:8]


def normalise_title(title):
    return re.sub(r'\s+', ' ', re.sub(r"[''’]", '', title or '').lower()).strip()


def debate_type(category, section_type, title):
    name = normalise_title(title)
    if section_type == 'BP':
        return 'bills'
    if category == 'adjournment_motion':
        return 'adjournment'
    if name in DEBATE_TITLES:
        return 'address'
    return 'budget' if BUDGET.match(name) else 'other_motion'


def git_commit():
    try:
        return subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True,
                              text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(conn, years, min_words, scope='address', through=None):
    members = {row['name']: row['id'] for row in conn.execute('SELECT id, name FROM members')}
    first_attended = dict(conn.execute(
        '''SELECT a.member_id, MIN(s.date) FROM sitting_attendance a
           JOIN sittings s ON s.id = a.sitting_id WHERE a.present = 1 GROUP BY a.member_id'''))
    parliament_open = dict(conn.execute('SELECT parliament, MIN(date) FROM sittings GROUP BY parliament'))
    where = ("x.category = 'motion'" if scope == 'address'
             else "(x.category IN ('motion', 'adjournment_motion') OR x.section_type = 'BP')")
    params = [str(y) for y in years]
    if through:  # same calendar window in every year, e.g. 09-10 for 1 January to 10 September
        where += ' AND substr(s.date, 6, 5) <= ?'
        params = [through, *params]
    sections = conn.execute(
        '''SELECT x.id, x.category, x.section_type, x.section_title, x.section_order, x.content_html,
                  s.id AS sitting_id, s.date, s.parliament, b.id AS bill_id, b.title AS bill_title
           FROM sections x JOIN sittings s ON s.id = x.sitting_id LEFT JOIN bills b ON b.id = x.bill_id
           WHERE {} AND substr(s.date, 1, 4) IN ({})
           ORDER BY s.date, x.section_order, x.id'''.format(where, ','.join('?' * len(years))),
        params).fetchall()

    speeches, excluded, unmatched = [], Counter(), Counter()
    for sec in sections:
        if scope == 'address' and normalise_title(sec['section_title']) not in DEBATE_TITLES:
            continue
        kind = debate_type(sec['category'], sec['section_type'], sec['section_title'])
        if kind == 'bills':
            url = f"{SITE}/bills/{slugify(sec['bill_title'], sec['bill_id'])}" if sec['bill_id'] else None
        else:
            url = f"{SITE}/motions/{slugify(sec['section_title'] or '', sec['id'])}"
        roles = {row['member_id']: row for row in conn.execute(
            '''SELECT member_id, constituency, designation FROM sitting_attendance
               WHERE sitting_id = ?''', (sec['sitting_id'],))}
        for turn in split_turns(sec['content_html']):
            words = len(turn.text.split())
            if PRESIDING.match(turn.label):
                excluded['presiding_officer'] += 1
                continue
            if turn.label.startswith('The President'):
                excluded['head_of_state_address'] += 1
                continue
            if words < min_words:
                excluded[f'under_{min_words}_words'] += 1
                continue
            name = extract_name_from_speaker_text(turn.label)
            member_id = members.get(name)
            if member_id is None:
                unmatched[turn.label] += 1
            role = roles.get(member_id) or {}
            designation = role['designation'] if role else None
            first = first_attended.get(member_id)
            opened = parliament_open.get(sec['parliament'])
            speeches.append({
                'speech_id': f"{ID_PREFIX[kind]}-{sec['date']}-{sec['id'][:8]}-t{turn.index:03d}",
                'upload_batch': sec['date'][:4],
                'date': sec['date'],
                'parliament': sec['parliament'],
                'section_id': sec['id'],
                'section_title': (sec['section_title'] or '').strip(),
                **({'debate_type': kind} if scope == 'prepared' else {}),
                'secondreading_url': url,
                'turn_index': turn.index,
                'speaker_label': turn.label,
                'member_id': member_id,
                'member_name': name,
                'constituency': role['constituency'] if role else None,
                'designation': designation or None,
                'is_office_holder': bool(turn.label.startswith('The ') or OFFICE.search(designation or '')),
                'first_attended': first,
                'first_parliament': bool(first and opened and first >= opened),
                'words': words,
                'billed_words': math.ceil(words / 100) * 100,
                'translated_words_removed': turn.translated_words_removed,
                'text_sha256': hashlib.sha256(turn.text.encode()).hexdigest(),
                'text': turn.text,
            })
    return speeches, excluded, unmatched


def summarise(speeches, years):
    by_year = {}
    for year in map(str, years):
        rows = [s for s in speeches if s['upload_batch'] == year]
        members = [s for s in rows if not s['is_office_holder']]
        by_year[year] = {
            'speeches': len(rows), 'words': sum(s['words'] for s in rows),
            'billed_words': sum(s['billed_words'] for s in rows),
            'non_office_holder_speeches': len(members),
            'non_office_holder_words': sum(s['words'] for s in members),
            'first_parliament_speakers': len({s['member_id'] for s in rows if s['first_parliament']}),
            'speakers': len({s['member_id'] or s['speaker_label'] for s in rows}),
            'speeches_with_translation_removed': sum(1 for s in rows if s['translated_words_removed']),
        }
    return by_year


def summarise_types(speeches):
    by_type = {}
    for kind in ID_PREFIX:
        rows = [s for s in speeches if s.get('debate_type') == kind]
        members = [s for s in rows if not s['is_office_holder']]
        by_type[kind] = {'speeches': len(rows), 'words': sum(s['words'] for s in rows),
                         'non_office_holder_speeches': len(members),
                         'non_office_holder_words': sum(s['words'] for s in members)}
    return by_type


def member_rows(speeches, years):
    grouped = defaultdict(lambda: defaultdict(list))
    for s in speeches:
        grouped[s['member_id'] or s['speaker_label']][s['upload_batch']].append(s)
    rows = []
    for key, per_year in grouped.items():
        latest = per_year[max(per_year)][-1]
        row = {'member_id': latest['member_id'], 'member_name': latest['member_name'],
               'first_attended': latest['first_attended'],
               'years_spoken': ' '.join(sorted(per_year))}
        for year in map(str, years):
            items = per_year.get(year, [])
            row[f'speeches_{year}'] = len(items)
            row[f'words_{year}'] = sum(s['words'] for s in items)
            row[f'office_holder_{year}'] = any(s['is_office_holder'] for s in items) if items else ''
            row[f'first_parliament_{year}'] = any(s['first_parliament'] for s in items) if items else ''
        rows.append(row)
    return sorted(rows, key=lambda r: (r['member_name'] or ''))


def write_outputs(out_dir, speeches, excluded, unmatched, years, args, conn):
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / 'speeches.jsonl', 'w', encoding='utf-8') as f:
        for s in speeches:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')

    members = member_rows(speeches, years)
    with open(out_dir / 'members.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(members[0]))
        writer.writeheader()
        writer.writerows(members)

    uploads = []
    for year in map(str, years):
        path = out_dir / f'pangram_upload_{year}.csv'
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['tag', 'text'])
            for s in speeches:
                if s['upload_batch'] == year:
                    writer.writerow([s['speech_id'], s['text']])
        uploads.append(path)

    spoke = defaultdict(set)
    for s in speeches:
        if s['member_id']:
            spoke[s['member_id']].add(s['upload_batch'])
    cohorts = {}
    if {'2020', '2025'} <= set(map(str, years)):
        cohorts['spoke_2020_and_2025'] = sum(1 for y in spoke.values() if {'2020', '2025'} <= y)
    if {'2020', '2023', '2025'} <= set(map(str, years)):
        cohorts['spoke_2020_2023_and_2025'] = sum(1 for y in spoke.values() if {'2020', '2023', '2025'} <= y)

    manifest = {
        'generated_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'git_commit': git_commit(),
        'database': str(Path(args.db).resolve()),
        'database_latest_sitting': conn.execute('SELECT MAX(date) FROM sittings').fetchone()[0],
        'parameters': {'scope': args.scope, 'years': years, 'through': args.through, 'min_words': args.min_words},
        'notes': [
            'One row per speaker turn; an MP may have several turns in one debate.',
            'Translated vernacular passages are removed; translated_words_removed records how much.',
            'first_parliament compares first recorded attendance with the opening of that Parliament; '
            'attendance records begin in January 2016.',
            'billed_words rounds each speech up to Pangram API 100-word units.',
        ],
        'by_year': summarise(speeches, years),
        **({'by_debate_type': summarise_types(speeches)} if args.scope == 'prepared' else {}),
        'cohorts': cohorts,
        'excluded_turns': dict(excluded),
        'unmatched_speaker_labels': dict(unmatched),
        'files': {p.name: sha256(p) for p in [out_dir / 'speeches.jsonl', out_dir / 'members.csv', *uploads]},
    }
    (out_dir / 'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    return manifest


def month_day(value):
    if not re.fullmatch(r'(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])', value):
        raise argparse.ArgumentTypeError('use MM-DD, e.g. 09-10')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--years', nargs='+', type=int, default=[2020, 2023, 2025])
    parser.add_argument('--min-words', type=int, default=150)
    parser.add_argument('--db', default=DB_PATH)
    parser.add_argument('--scope', choices=['address', 'prepared'], default='address')
    parser.add_argument('--through', type=month_day, help='Keep sittings up to this MM-DD in every year')
    parser.add_argument('--out-dir', type=Path, help='Defaults to presidents_address/ or prepared_speeches/ by scope')
    args = parser.parse_args()
    args.out_dir = args.out_dir or (DEFAULT_OUT if args.scope == 'address' else PREPARED_OUT)

    conn = sqlite3.connect(f'file:{Path(args.db).resolve()}?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        speeches, excluded, unmatched = collect(conn, args.years, args.min_words, args.scope, args.through)
        manifest = write_outputs(args.out_dir, speeches, excluded, unmatched, args.years, args, conn)
    finally:
        conn.close()
    keys = ('by_year', 'by_debate_type', 'cohorts', 'excluded_turns', 'unmatched_speaker_labels')
    print(json.dumps({k: manifest[k] for k in keys if k in manifest}, indent=2))
    print(f'Wrote {args.out_dir}')


if __name__ == '__main__':
    main()
