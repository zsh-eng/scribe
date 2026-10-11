"""Estimate the Pangram cost of scanning prepared speeches across whole years of Hansard.

Counts speaker turns in motions (including the Address debate, Budget and Committee of Supply),
adjournment motions and bill second-reading debates, split and filtered as in
export_pangram_speeches.py. Question time, written answers and the Chair are left out. Nothing is
sent to Pangram; cost uses the bulk rate and 100-word units from run_pangram_bulk.py.
"""
import argparse
import sqlite3
from collections import defaultdict
from pathlib import Path

from db_sqlite import DB_PATH
from export_pangram_speeches import OFFICE, PRESIDING, debate_type, split_turns
from run_pangram_bulk import USD_PER_UNIT, units
from util import extract_name_from_speaker_text

GROUPS = {
    'bills': 'Bill debates',
    'budget': 'Budget and Committee of Supply',
    'other_motion': 'Other motions and statements',
    'address': "President's Address debate",
    'adjournment': 'Adjournment motions',
}


def estimate(conn, years, min_words):
    """Totals keyed by (year, debate type, 'office' or 'mp'), plus sittings per year."""
    members = dict(conn.execute('SELECT name, id FROM members'))
    marks = ','.join('?' * len(years))
    year_args = [str(y) for y in years]
    designations = defaultdict(dict)
    for sitting_id, member_id, designation in conn.execute(
            f'''SELECT a.sitting_id, a.member_id, a.designation FROM sitting_attendance a
                JOIN sittings s ON s.id = a.sitting_id WHERE substr(s.date, 1, 4) IN ({marks})''', year_args):
        designations[sitting_id][member_id] = designation or ''
    sections = conn.execute(
        f'''SELECT x.category, x.section_type, x.section_title, x.content_html, s.id, s.date
            FROM sections x JOIN sittings s ON s.id = x.sitting_id
            WHERE (x.category IN ('motion', 'adjournment_motion') OR x.section_type = 'BP')
              AND substr(s.date, 1, 4) IN ({marks})''', year_args)
    totals = defaultdict(lambda: {'speeches': 0, 'words': 0, 'units': 0})
    for category, section_type, title, content_html, sitting_id, date in sections:
        kind = debate_type(category, section_type, title)
        for turn in split_turns(content_html):
            if PRESIDING.match(turn.label) or turn.label.startswith('The President'):
                continue
            words = len(turn.text.split())
            if words < min_words:
                continue
            member_id = members.get(extract_name_from_speaker_text(turn.label))
            office = turn.label.startswith('The ') or bool(OFFICE.search(designations[sitting_id].get(member_id, '')))
            row = totals[(date[:4], kind, 'office' if office else 'mp')]
            row['speeches'] += 1
            row['words'] += words
            row['units'] += units(words)
    sittings = dict(conn.execute(
        f'SELECT substr(date, 1, 4), COUNT(*) FROM sittings WHERE substr(date, 1, 4) IN ({marks}) GROUP BY 1', year_args))
    return totals, sittings


def report(totals, sittings, years, min_words):
    usd = lambda u: f'${u * USD_PER_UNIT:,.0f}'
    span = f'{years[0]}-{years[-1]}' if len(years) > 1 else str(years[0])
    lines = [f'Prepared speeches of {min_words}+ words, {span}, at ${USD_PER_UNIT:.2f} per 100-word unit',
             f'{"Year":<6}{"Sittings":>9}{"Speeches":>10}{"Words":>12}{"All speakers":>14}{"Outside office":>16}']
    grand = defaultdict(int)
    for year in map(str, years):
        rows = [v for k, v in totals.items() if k[0] == year]
        mp = [v for k, v in totals.items() if k[0] == year and k[2] == 'mp']
        n, w, u = (sum(r[f] for r in rows) for f in ('speeches', 'words', 'units'))
        um = sum(r['units'] for r in mp)
        for key, value in (('n', n), ('w', w), ('u', u), ('um', um)):
            grand[key] += value
        lines.append(f'{year:<6}{sittings.get(year, 0):>9}{n:>10,}{w:>12,}{usd(u):>14}{usd(um):>16}')
    lines.append(f'{"Total":<15}{grand["n"]:>10,}{grand["w"]:>12,}{usd(grand["u"]):>14}{usd(grand["um"]):>16}')
    lines += ['', 'By debate type, speakers outside office']
    for kind, label in GROUPS.items():
        rows = [v for k, v in totals.items() if k[1] == kind and k[2] == 'mp']
        n, w, u = (sum(r[f] for r in rows) for f in ('speeches', 'words', 'units'))
        lines.append(f'{label:<32}{n:>7,} speeches{w:>12,} words{usd(u):>8}')
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--years', nargs='+', type=int, default=list(range(2020, 2027)))
    parser.add_argument('--min-words', type=int, default=500)
    parser.add_argument('--db', default=DB_PATH)
    args = parser.parse_args()
    conn = sqlite3.connect(f'file:{Path(args.db).resolve()}?mode=ro', uri=True)
    try:
        totals, sittings = estimate(conn, sorted(args.years), args.min_words)
    finally:
        conn.close()
    print(report(totals, sittings, sorted(args.years), args.min_words))


if __name__ == '__main__':
    main()
