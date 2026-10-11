"""Build the internal verification page for the Pangram AI-detection pipeline.

Covers the President's Address pilot, the wider export of prepared speeches, dashboard imports and
the portrait pipeline. Code excerpts are copied from the source files with their line numbers, every
expected output comes from running that check from the repository root, and the findings are
computed from the results at build time, so the page cannot drift from the code or the data.
Needs the results folders, the photos folder and the database; nothing is sent to Pangram.
"""
import argparse
import ast
import html
import json
import re
import sqlite3
import subprocess
from datetime import date, datetime
from pathlib import Path

from build_pangram_explorer import photo_uri
from db_sqlite import DB_PATH
from export_pangram_speeches import DEFAULT_OUT, PREPARED_OUT, ROOT
from run_pangram_bulk import USD_PER_UNIT, read_jsonl

PY = ROOT / 'python'
TEMPLATE = PY / 'pangram_verification.html'
EXPORT = PY / 'export_pangram_speeches.py'
BULK = PY / 'run_pangram_bulk.py'
PHOTOS = PY / 'fetch_mp_photos.py'
BUILD = PY / 'build_pangram_explorer.py'
EXPLORER = PY / 'pangram_explorer.html'
IMPORTER = PY / 'import_pangram_dashboard.py'
PHOTO_DIR = DEFAULT_OUT.parent / 'photos'
# Check commands run from the repository root.
D = DEFAULT_OUT.relative_to(ROOT).as_posix()
P = PREPARED_OUT.relative_to(ROOT).as_posix()
PH = PHOTO_DIR.relative_to(ROOT).as_posix()
E = html.escape


def long_date(d):
    return f'{d.day}&nbsp;{d:%B %Y}'


def func(path, name):
    """Exact source of a top-level function with its line range."""
    tree = ast.parse(path.read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    src = path.read_text(encoding='utf-8').splitlines()[node.lineno - 1:node.end_lineno]
    return '\n'.join(src), node.lineno, node.end_lineno


def span(path, start_text, end_text):
    """Lines from the first line containing start_text to the next containing end_text."""
    src = path.read_text(encoding='utf-8').splitlines()
    a = next(i for i, line in enumerate(src) if start_text in line)
    b = next(i for i in range(a, len(src)) if end_text in src[i])
    return '\n'.join(src[a:b + 1]), a + 1, b + 1


def run(cmd):
    p = subprocess.run(['bash', '-c', cmd], cwd=ROOT, capture_output=True, text=True)
    out = (p.stdout + p.stderr).rstrip()
    if p.returncode:
        raise SystemExit(f'Check failed ({p.returncode}): {cmd}\n{out}')
    return out


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True)


def code(excerpt, lang, path):
    src, a, b = excerpt
    return (f'<figure class="code"><figcaption><span>{E(path.relative_to(ROOT).as_posix())}</span><span>lines {a}–{b}</span>'
            f'</figcaption><pre><code class="language-{lang}">{E(src)}</code></pre></figure>')


def check(title, needs, body, cmd, expected=None, lang='bash'):
    out = run(cmd) if expected is None else expected
    tag = {'folder': 'Results folder', 'repo': 'Repo checkout', 'db': 'Repo + database'}[needs]
    return (f'<div class="check"><div class="check-head"><b>Check</b><span class="what">{E(title)}</span>'
            f'<span class="needs n-{needs}">{tag}</span></div>'
            + (f'<p>{body}</p>' if body else '') +
            f'<div class="cmd"><button type="button" class="copy">Copy</button>'
            f'<pre><code class="language-{lang}">{E(cmd)}</code></pre></div>'
            f'<div class="expect"><span>Expected output</span><pre>{E(out)}</pre></div></div>')


def read_jobs(export_dir):
    """Submitted jobs, the batch of every speech and the speeches with a saved result."""
    state = export_dir / 'pangram'
    rows = lambda path: [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    batch = {s['speech_id']: s['upload_batch'] for s in rows(export_dir / 'speeches.jsonl')}
    saved = {r['speech_id'] for r in rows(state / 'results.jsonl') if r['status'] == 'success'}
    return rows(state / 'jobs.jsonl'), batch, saved


def jobs_table(jobs, batch):
    rows = []
    for job in jobs:
        sent = datetime.fromisoformat(job['submitted_at'])
        bulk = f'<code>{E(job["bulk_id"][:12])}…</code>' if job['bulk_id'] else 'unknown outcome'
        batches = ' + '.join(sorted({batch.get(i, '?') for i in job['speech_ids']}))
        rows.append(f'<tr><td>{sent:%H:%M:%S}</td><td>{bulk}</td><td>{batches}</td>'
                    f'<td class="r">{len(job["speech_ids"])}</td><td class="r">{job["estimated_units"]:,}</td></tr>')
    days = sorted({datetime.fromisoformat(j['submitted_at']).date() for j in jobs})
    when = long_date(days[0]) if len(days) == 1 else f'{long_date(days[0])} to {long_date(days[-1])}'
    units = sum(j['estimated_units'] for j in jobs)
    speeches = sum(len(j['speech_ids']) for j in jobs)
    return f'''<div class="tablewrap"><table>
<caption>Jobs sent on {when} (UTC), from <code>pangram/jobs.jsonl</code></caption>
<thead><tr><th>Time</th><th>Bulk job</th><th>Batch</th><th class="r">Speeches</th><th class="r">Units</th></tr></thead>
<tbody>{''.join(rows)}</tbody>
<tfoot><tr><td colspan="3">Total, at ${USD_PER_UNIT:.2f} per unit: ${units * USD_PER_UNIT:,.2f}</td><td class="r">{speeches}</td><td class="r">{units:,}</td></tr></tfoot>
</table></div>'''


def manifest_note(export_dir):
    recorded = json.loads((export_dir / 'manifest.json').read_text())['git_commit'] or 'unknown'
    head = git('rev-parse', 'HEAD').stdout.strip()
    if recorded == head:
        return f'The manifest records commit <code>{recorded[:7]}</code>, the commit checked out now.'
    existed = git('cat-file', '-e', f'{recorded}:{EXPORT.relative_to(ROOT).as_posix()}').returncode == 0
    why = ('which is older than the code shown here' if existed
           else 'because the export ran before the script was first committed')
    return (f'The manifest records commit <code>{recorded[:7]}</code>, {why}. Re-running the export at the current commit '
            'reproduces every file byte for byte, which is the stronger guarantee.')


def contact_sheet():
    """Every accepted portrait with its article, licence and author, for a check by eye."""
    credits = json.loads((PHOTO_DIR / 'credits.json').read_text())
    cards, missing = [], []
    for credit in sorted(credits.values(), key=lambda c: c['name']):
        path = PHOTO_DIR / (credit.get('file') or '')
        if not credit.get('file') or not path.exists():
            missing.append(credit['name'])
            continue
        cards.append(f'<figure><img src="{photo_uri(path, 96)}" alt="" loading="lazy"><b>{E(credit["name"])}</b>'
                     f'<span>{E(credit.get("article") or "")}</span>'
                     f'<span>{E(credit.get("license") or "")} · {E(credit.get("author") or "Unknown")}</span></figure>')
    return (f'<div class="sheet">{"".join(cards)}</div><p>{len(missing)} searched members have no free portrait and get a '
            f'monogram: {E(", ".join(missing))}.</p>')


def high_share(result):
    """Share of characters in AI-generated windows rated High and at least 75 words long, as in the explorer."""
    ai = sum(w['end_index'] - w['start_index'] for w in result['windows']
             if w['label'] != 'Human Written' and w['confidence'] == 'High' and w['word_count'] >= 75)
    return ai / len(result['text'])


def scanned_rows(export_dir):
    speeches = {s['speech_id']: s for s in read_jsonl(export_dir / 'speeches.jsonl')}
    results = {}
    for r in read_jsonl(export_dir / 'pangram' / 'results.jsonl'):
        if r['status'] == 'success':
            results[r['speech_id']] = r['result']  # later lines win, as in the build
    return speeches, [(speeches[i], r) for i, r in results.items() if i in speeches]


def findings():
    """Headline figures recomputed from the results at build time, never typed in."""
    pct = lambda v: f'{v:.1%}'
    table, notes = [], []
    for label, export_dir in (("President's Address", DEFAULT_OUT), ('Prepared speeches', PREPARED_OUT)):
        if not (export_dir / 'pangram' / 'results.jsonl').exists():
            continue
        speeches, rows = scanned_rows(export_dir)
        for year in sorted({s['upload_batch'] for s, _ in rows}):
            got = [(s, r) for s, r in rows if s['upload_batch'] == year]
            total = sum(1 for s in speeches.values() if s['upload_batch'] == year)
            words = sum(s['words'] for s, _ in got)
            every = sum(s['words'] * r['fraction_ai'] for s, r in got) / words
            high = sum(s['words'] * high_share(r) for s, r in got) / words
            speakers = {s['member_id'] or s['speaker_label'] for s, _ in got}
            flagged = {s['member_id'] or s['speaker_label'] for s, r in got if high_share(r) > 0}
            debates = len({s['section_id'] for s, _ in got})
            table.append(f'<tr><td>{E(label)} {year}</td><td class="r">{len(got)} of {total}</td><td class="r">{debates}</td>'
                         f'<td class="r">{words:,}</td><td class="r">{pct(every)}</td><td class="r">{pct(high)}</td>'
                         f'<td class="r">{len(flagged)} of {len(speakers)}</td></tr>')
            if len(got) < total:
                notes.append(f'{label} {year} is a sample of {len(got)} of {total} speeches from {debates} '
                             f'debate{"s" if debates > 1 else ""}, so it shows the pipeline works rather than a result.')
        if export_dir == DEFAULT_OUT:
            mps = {}
            for s, r in rows:
                if s['member_id'] and not s['is_office_holder']:
                    mps.setdefault(s['member_id'], {}).setdefault(s['upload_batch'], []).append(high_share(r) > 0)
            both = [v for v in mps.values() if {'2020', '2025'} <= set(v)]
            if both:
                notes.append(f'{len(both)} MPs outside office spoke in both Address debates: '
                             f'{sum(any(v["2020"]) for v in both)} had a high-confidence passage in 2020 and '
                             f'{sum(any(v["2025"]) for v in both)} in 2025.')
    return f'''<p>Shares are of words, weighting each speech by its length. High confidence counts AI-generated passages rated High and
at least 75 words long; a speaker is flagged with at least one such passage.</p>
<div class="tablewrap"><table>
<thead><tr><th>Dataset</th><th class="r">Speeches scanned</th><th class="r">Debates</th><th class="r">Words</th>
<th class="r">All passages</th><th class="r">High confidence</th><th class="r">Speakers flagged</th></tr></thead>
<tbody>{''.join(table)}</tbody></table></div>
<ul>{''.join(f'<li>{E(n)}</li>' for n in notes)}</ul>'''


def build_steps(export_dir, jobs, batch):
    steps = []

    steps.append(('select', 'Select the debates', 'export_pangram_speeches.py · collect()', f'''
<p>The export opens the local Second Reading database read-only. It keeps sections in the <code>motion</code> category whose title,
lower-cased and stripped of apostrophes, is one of three names Hansard has used for the Address debate. 2020 has seven such
sections over five sitting days, because Hansard split two days in two; 2025 has five.</p>
{code(span(EXPORT, 'DEBATE_TITLES = ', 'DEBATE_TITLES = '), 'python', EXPORT)}
{code(span(EXPORT, "    sections = conn.execute(", "normalise_title(sec['section_title']) not in DEBATE_TITLES"), 'python', EXPORT)}
{check('Speeches per debate section', 'folder', 'Counts every exported 2020 and 2025 speech by sitting date and section.',
f"""python3 - <<'EOF'
import collections, json
rows = [json.loads(l) for l in open('{D}/speeches.jsonl')]
c = collections.Counter((s['date'], s['section_id'][:8]) for s in rows if s['upload_batch'] in ('2020', '2025'))
for (date, section), n in sorted(c.items()):
    print(date, section, n)
EOF""")}'''))

    steps.append(('split', 'Split each debate into speaker turns', 'export_pangram_speeches.py · split_turns()', f'''
<p>Hansard prints a debate as one block of paragraphs. A new turn starts only where a paragraph opens with a bold name followed
by a colon, so notices such as “[Deputy Speaker in the Chair]” stay inside the speech they interrupt. Hansard prints Mandarin,
Malay and Tamil passages in English translation; those are removed from the “(In Malay)” marker until “(In English)”, and the
number of words removed is kept with each speech.</p>
{code(span(EXPORT, 'SPEAKER_PARA = ', 'SWITCH_TO_VERNACULAR = '), 'python', EXPORT)}
{code(func(EXPORT, 'split_turns'), 'python', EXPORT)}
{check('Unit tests for the export and the bulk runner', 'repo', 'Uses fixed sample HTML and a fake Pangram server, so it needs no database, key or network.',
"(cd python && uv run python -m unittest tests.test_pangram_export tests.test_pangram_bulk 2>&1 | tail -3)")}
{check('Translation removed per year', 'folder', 'Open a few of these speeches on Second Reading and confirm the removed passages were translations.',
f"""python3 - <<'EOF'
import json
rows = [json.loads(l) for l in open('{D}/speeches.jsonl')]
for y in ('2020', '2025'):
    hit = [s for s in rows if s['upload_batch'] == y and s['translated_words_removed']]
    print(y, len(hit), 'speeches had translation removed,', sum(s['translated_words_removed'] for s in hit), 'words in total')
EOF""")}'''))

    steps.append(('label', 'Drop the Chair and label every speech', 'export_pangram_speeches.py · collect()', f'''
<p>Turns by the Speaker, a Deputy Speaker or the Chairman are dropped, as is the President's own Address. Speeches under 500
words are dropped because detection is less reliable on short text. Each remaining speech is matched to a member, then given the
constituency and designation printed in that day's attendance list. Two labels come from those fields:</p>
<ul>
<li><b>Office holder</b>: the designation contains “Minister”, “Parliamentary Secretary” or “Attorney-General”.</li>
<li><b>New MP</b>: the member's first recorded attendance falls on or after the first sitting of that Parliament.</li>
</ul>
{code(span(EXPORT, "        for turn in split_turns(sec['content_html']):", "'first_parliament': bool("), 'python', EXPORT)}
<div class="anatomy" aria-label="Parts of a speech ID">
<div class="id"><span>pa</span><span>2025-09-25</span><span>52f98c09</span><span>t032</span></div>
<div class="parts"><span>President's Address</span><span>sitting date</span><span>Hansard section</span><span>turn in section</span></div>
</div>
{check('What was excluded', 'folder', 'Counts cover every exported year, including 2023. An empty last line means every speaker label matched a member.',
f"""python3 - <<'EOF'
import json
m = json.load(open('{D}/manifest.json'))
print(m['parameters'])
print(m['excluded_turns'])
print(m['unmatched_speaker_labels'])
EOF""")}
<p class="gap"><b>Known gap</b> Attendance records start in January 2016, so an MP who served only before 2016 and later returned counts
as new. Gerald Giam appears to be one: he is labelled new in 2020 but looks to have been an NCMP from 2011 to 2015.</p>'''))

    reexport = f"""OUT=$(mktemp -d)
(cd python && uv run export_pangram_speeches.py --years 2020 2023 2025 --min-words 500 --out-dir "$OUT" > /dev/null)
python3 - "$OUT" <<'EOF'
import json, sys
new = json.load(open(sys.argv[1] + '/manifest.json'))['files']
old = json.load(open('{D}/manifest.json'))['files']
for name, digest in old.items():
    print(name, 'match' if new[name] == digest else 'DIFFERENT')
EOF"""
    reexported = run(reexport)
    steps.append(('export', 'Write the export and its manifest', 'export_pangram_speeches.py · write_outputs()', f'''
<p>The export writes <code>speeches.jsonl</code> (the exact text sent, with every label above), <code>members.csv</code>, one
<code>pangram_upload_&lt;year&gt;.csv</code> per year for the dashboard, and <code>manifest.json</code> with the settings, counts and a
SHA-256 hash of every file. {manifest_note(export_dir)}</p>
{code(func(EXPORT, 'sha256'), 'python', EXPORT)}
{code(span(EXPORT, "        'files': {p.name: sha256(p)", "        'files': {p.name: sha256(p)"), 'python', EXPORT)}
{check('Re-run the export and compare hashes', 'db', 'Writes into a temporary folder and leaves the team files untouched.', reexport, reexported)}'''))

    steps.append(('send', 'Send speeches to Pangram', 'run_pangram_bulk.py', f'''
<p>The runner is a dry run unless it gets <code>--submit</code>: it prints how many speeches, words and 100-word units it would
send and what that costs at the bulk rate, then stops. Pangram allows 1,000 units per request; the runner packs speeches into
requests of at most 900 in case Pangram counts words differently. Every submission is appended to <code>jobs.jsonl</code> before
anything else happens, and a speech listed there is never sent again.</p>
{code(func(BULK, 'units'), 'python', BULK)}
{code(func(BULK, 'chunk'), 'python', BULK)}
{code(func(BULK, 'make_session'), 'python', BULK)}
<p>If a submission fails in transit, Pangram may still have created the job. The runner records it with no job ID and stops, so the
same speeches are never billed twice:</p>
{code(span(BULK, '        try:', "removing the bulk_id=null line from jobs.jsonl.')"), 'python', BULK)}
{jobs_table(jobs, batch)}
{check('Nothing left to send for 2020 and 2025', 'repo', 'A dry run makes no network calls and needs no key.',
"(cd python && uv run run_pangram_bulk.py --years 2020 2025)")}
{check('What 2023 would cost', 'repo', 'The same dry run for the debate that has not been scanned, with and without office holders.',
"(cd python && uv run run_pangram_bulk.py --years 2023 && uv run run_pangram_bulk.py --years 2023 --exclude-office-holders)")}
{check('What whole years would cost', 'db', 'Counts speeches of 500 or more words in every motion, adjournment motion and bill debate, split and '
'filtered as in the export. Question time, written answers and the Chair are left out, and nothing is sent.',
"(cd python && uv run estimate_pangram_cost.py)")}'''))

    verify = f"""python3 - <<'EOF'
import json
speeches = {{s['speech_id']: s for s in map(json.loads, open('{D}/speeches.jsonl'))}}
results = {{}}
for r in map(json.loads, open('{D}/pangram/results.jsonl')):
    if r['status'] == 'success':
        results[r['speech_id']] = r['result']  # later lines win, as in the build

def high_confidence(r):
    ai = sum(w['end_index'] - w['start_index'] for w in r['windows']
             if w['label'] != 'Human Written' and w['confidence'] == 'High' and w['word_count'] >= 75)
    return ai / len(r['text'])

for year in ('2020', '2025'):
    rows = [(s, results[i]) for i, s in speeches.items() if s['upload_batch'] == year and i in results]
    words = sum(s['words'] for s, _ in rows)
    every = sum(s['words'] * r['fraction_ai'] for s, r in rows) / words
    high = sum(s['words'] * high_confidence(r) for s, r in rows) / words
    print(f'{{year}}: {{len(rows)}} speeches, {{words:,}} words, all passages {{every:.1%}}, high confidence {{high:.1%}}')
EOF"""
    textcheck = f"""python3 - <<'EOF'
import json
sent = {{s['speech_id']: s['text'] for s in map(json.loads, open('{D}/speeches.jsonl'))}}
rows = [json.loads(l) for l in open('{D}/pangram/results.jsonl')]
same = sum(sent[r['speech_id']].replace('\\n\\n', '\\n').replace('\\u200b', '') == r['result']['text'] for r in rows)
print(same, 'of', len(rows), 'returned texts equal ours after collapsing blank lines and removing zero-width spaces')
EOF"""
    steps.append(('results', 'Read Pangram’s results', 'pangram/results.jsonl', f'''
<p>Each result splits a speech into windows, each labelled “AI-Generated” or “Human Written” with a confidence of Low, Medium or
High, a score, a word count and character offsets. <code>fraction_ai</code> is the share of the speech's characters in AI-generated
windows. Pangram 4 labelled nothing as AI-assisted. The page derives three figures from these fields:</p>
<ul>
<li><b>Speech share</b>: <code>fraction_ai</code> as Pangram returns it.</li>
<li><b>High-confidence share</b>: characters in AI-generated windows rated High and at least 75 words long, divided by the speech's characters. The essay leads with this.</li>
<li><b>Group share</b>: speech shares weighted by each speech's word count.</li>
</ul>
{code(span(EXPLORER, '  const STRICT = (g)', '  const STRICT = (g)'), 'javascript', EXPLORER)}
{code(span(EXPLORER, '  const share = (s) =>', '  };'), 'javascript', EXPLORER)}
{check('Recompute the headline figures from the raw files', 'folder', 'Independent of the page: reads only the export and Pangram’s results.', verify)}
<p>Pangram does not return text exactly as sent. It collapses blank lines to single line breaks, and in one 2025 speech it dropped a
zero-width space. Window offsets point into Pangram's returned text, so the build and the reader always use that text, never ours.</p>
{check('Returned text matches what was sent', 'folder', None, textcheck)}'''))

    reprepared = f"""OUT=$(mktemp -d)
(cd python && uv run export_pangram_speeches.py --scope prepared --years 2021 2026 --through 09-10 --min-words 500 --out-dir "$OUT" > /dev/null)
python3 - "$OUT" <<'EOF'
import json, sys
new = json.load(open(sys.argv[1] + '/manifest.json'))['files']
old = json.load(open('{P}/manifest.json'))['files']
for name, digest in old.items():
    print(name, 'match' if new.get(name) == digest else 'DIFFERENT')
EOF"""
    steps.append(('prepared', 'Widen the export to prepared speeches', 'export_pangram_speeches.py --scope prepared', f'''
<p>The second dataset applies the same splitting and labels to every motion, adjournment motion and bill second-reading debate,
including the Budget debate and Committee of Supply. Question time, written answers, clarifications and bill introductions are
left out. Each speech gets a <code>debate_type</code>, and its ID starts with that type, so an Address speech has the same ID in
either export. <code>--through 09-10</code> keeps 1 January to 10 September in every year, the last sitting in the database, so
2021 (before ChatGPT) and 2026 cover the same part of the parliamentary year.</p>
{code(func(EXPORT, 'debate_type'), 'python', EXPORT)}
{code(span(EXPORT, "    where = (", "        params = [through, *params]"), 'python', EXPORT)}
{check('What the wider export holds', 'folder', 'Speeches and words per year and per debate type, for all speakers and for MPs outside office.',
f"""python3 - <<'EOF'
import json
m = json.load(open('{P}/manifest.json'))
print(m['parameters'])
for year, v in m['by_year'].items():
    print(year, v['speeches'], 'speeches', v['words'], 'words;', v['non_office_holder_speeches'], 'outside office,', v['non_office_holder_words'], 'words')
for kind, v in m['by_debate_type'].items():
    print(kind, v['speeches'], 'speeches,', v['non_office_holder_speeches'], 'outside office')
EOF""")}
{check('Re-run the wider export and compare hashes', 'db', 'Writes into a temporary folder and leaves the team files untouched.', reprepared)}'''))

    steps.append(('dashboard', 'Scan on the dashboard and import the reports', 'run_pangram_bulk.py --write-csv · import_pangram_dashboard.py', f'''
<p>The wider dataset is scanned on the Pangram dashboard rather than through the API. <code>run_pangram_bulk.py --write-csv</code>
writes the selection the API runner would send as a <code>tag,text</code> upload, leaving out any speech that already has a result.
Reports are saved from the dashboard history and imported. The importer keeps a report only when the text Pangram scanned is exactly
the text we exported, renames the dashboard's window fields to the API's (“Human” becomes “Human Written”, and
<code>ai_likelihood</code> is also stored as <code>ai_assistance_score</code>) and appends to the same <code>results.jsonl</code>,
so everything downstream treats both sources alike. Downloaded files are kept unchanged in <code>pangram/raw/dashboard/</code>.</p>
{code(span(BULK, "    sent = {sid for job in jobs", "    sent |= {r['speech_id']"), 'python', BULK)}
{code(func(IMPORTER, 'normalise'), 'python', IMPORTER)}
{code(span(IMPORTER, "            speech_id = report.get('file_name')", "print(f'Skipped {speech_id}"), 'python', IMPORTER)}
{check('Importer tests', 'repo', 'Uses a fake download, so it needs no account or network.',
"(cd python && uv run python -m unittest tests.test_pangram_dashboard 2>&1 | tail -3)")}
{check('Upload files hold only unscanned MPs outside office', 'folder', 'Each line should end with two zeros.',
f"""python3 - <<'EOF'
import csv, glob, json
csv.field_size_limit(10**8)
speeches = {{s['speech_id']: s for s in map(json.loads, open('{P}/speeches.jsonl'))}}
scanned = {{r['speech_id'] for r in map(json.loads, open('{P}/pangram/results.jsonl')) if r['status'] == 'success'}}
for path in sorted(glob.glob('{P}/dashboard_upload_*.csv')):
    tags = [row['tag'] for row in csv.DictReader(open(path, newline='', encoding='utf-8'))]
    print(path.rsplit('/', 1)[1] + ':', len(tags), 'rows,', sum(speeches[t]['words'] for t in tags), 'words; office holders',
          sum(speeches[t]['is_office_holder'] for t in tags), '; already scanned', sum(t in scanned for t in tags))
EOF""")}
{check('Imported reports', 'folder', 'Dashboard results by year, whether each returned text equals ours after the normalisation seen with the API, and the window labels after renaming.',
f"""python3 - <<'EOF'
import collections, json
sent = {{s['speech_id']: s for s in map(json.loads, open('{P}/speeches.jsonl'))}}
rows = [r for r in map(json.loads, open('{P}/pangram/results.jsonl')) if r.get('source') == 'dashboard' and r['status'] == 'success']
print(dict(collections.Counter(sent[r['speech_id']]['upload_batch'] for r in rows)))
same = sum(sent[r['speech_id']]['text'].replace('\\n\\n', '\\n').replace('\\u200b', '') == r['result']['text'] for r in rows)
print(same, 'of', len(rows), 'returned texts equal ours')
print(dict(collections.Counter(w['label'] for r in rows for w in r['result']['windows'])))
EOF""")}'''))

    steps.append(('photos', 'Find openly licensed portraits', 'fetch_mp_photos.py', f'''
<p>For each MP who spoke, the script searches English Wikipedia for “<i>name</i> Singapore politician”. It accepts an article when
the title shares the MP's name and the description mentions Singapore, then takes the lead image only if Wikipedia marks it as
freely licensed. Author, licence and file page come from Wikimedia Commons and are stored in <code>credits.json</code>. Official
portraits from parliament.gov.sg are not used: its terms forbid reproducing images without written permission.</p>
{code(func(PHOTOS, 'find_article'), 'python', PHOTOS)}
{code(span(PHOTOS, "        if match and match[1]:", "record.update(info, file=path.name, source_file=match[1])"), 'python', PHOTOS)}
<p>The explorer build shrinks each portrait to 176 pixels, embeds it in the page and lists its author and licence in the page's
credits. MPs without a portrait get a monogram.</p>
{code(func(BUILD, 'photo_uri'), 'python', BUILD)}
{check('Portraits and licences', 'folder', 'Matching was automatic, so every face still needs a check by eye: see the contact sheet below.',
f"""python3 - <<'EOF'
import collections, json
c = json.load(open('{PH}/credits.json'))
print(len(c), 'MPs searched,', sum(1 for r in c.values() if r['file']), 'with a free portrait')
print(collections.Counter(r['license'] for r in c.values() if r['file']).most_common())
EOF""")}
{check('Every portrait has a credit, and every credit a file', 'folder', 'All three lists should be empty.',
f"""python3 - <<'EOF'
import json, pathlib
d = pathlib.Path('{PH}')
c = json.load(open(d / 'credits.json'))
files = {{p.name for p in d.glob('*.jpg')}}
credited = {{r['file'] for r in c.values() if r['file']}}
print('files without a credit:', sorted(files - credited))
print('credits without a file:', sorted(credited - files))
print('credits missing author, licence or page:', [r['name'] for r in c.values() if r['file'] and not (r.get('author') and r.get('license') and r.get('page'))])
EOF""")}
{check('Portraits embedded in the explorer', 'folder', 'Every embedded portrait should have one credit line, so the last two numbers match.',
f"""python3 - <<'EOF'
import json
page = open('{D}/who-wrote-the-address.html', encoding='utf-8').read()
data = json.loads(page.split('const DATA = ', 1)[1].split(';\\n', 1)[0])
photos = [m for m in data['members'] if m['photo']]
print(len(data['members']), 'members in the page,', len(photos), 'with a portrait,', len(data['credits']), 'credit lines')
EOF""")}
<h3 class="sub">Contact sheet</h3>
<p>Every portrait the search accepted, with the Wikipedia article it came from. Check that each face is the MP named and that the
article is about them.</p>
{contact_sheet()}'''))

    steps.append(('build', 'Build the explorer page', 'build_pangram_explorer.py', f'''
<p>The build joins the export, Pangram's results, attendance on the debate days and the portraits into one data object, then
writes it into <code>pangram_explorer.html</code> to make a single self-contained file. Party is not stored in the database, so it
comes from a rule: three seats are Workers' Party, every other seat is PAP, and the four NCMPs are matched by name. Only
AI-generated windows are kept, as compact rows of start, end, confidence, score, words and a humanizer flag.</p>
{code(func(BUILD, 'party_of'), 'python', BUILD)}
{code(span(BUILD, "        segs = [[w['start_index']", "for w in res['windows'] if w['label'] != 'Human Written']"), 'python', BUILD)}
{check('Rebuild the page', 'db', 'Embeds the Timeless fonts if they are in ~/Downloads, otherwise falls back to system fonts. The opening figures should equal the high-confidence shares printed by the recompute check in step 6, and the all-passages shares after switching to All passages.',
"(cd python && uv run build_pangram_explorer.py)")}'''))

    steps.append(('share', 'Share with the team', 'rsync to Google Drive', f'''
<p>The results folder is git-ignored because it links named MPs to scores. It reaches the team through the shared Drive folder.
<code>who-wrote-the-address-v1.html</code> is the first version of the page, kept for comparison. Beside it are
<code>prepared_speeches/</code>, <code>photos/</code> and a snapshot of the database as <code>parliament.db</code>.</p>
{check('Sync and confirm the copy', 'repo', 'Run on the machine that holds the results. Replace &lt;account&gt; with the Google account in the Drive path.',
f'''DRIVE="$HOME/Library/CloudStorage/GoogleDrive-<account>/My Drive/Projects/Second Reading/AI speech detection"
for folder in presidents_address prepared_speeches photos; do
  rsync -a --exclude .DS_Store "data/ai_detection/$folder/" "$DRIVE/$folder/"
done
cmp {D}/who-wrote-the-address.html "$DRIVE/presidents_address/who-wrote-the-address.html" && echo synced''', expected='synced')}'''))

    return steps, reexported


def header(jobs, saved, reexported):
    tests = run('cd python && uv run python -m unittest discover -s tests')
    ran = int(re.search(r'Ran (\d+) tests?', tests).group(1))
    sent = {i for j in jobs if j['bulk_id'] for i in j['speech_ids']}
    billed = [j for j in jobs if j['bulk_id']]
    units = sum(j['estimated_units'] for j in billed)
    files = reexported.splitlines()
    matched = sum(line.endswith(' match') for line in files)
    confirmed = [
        (f'{len(sent & saved)} / {len(sent)}', 'speeches scanned, results saved'),
        (f'{matched} / {len(files)}', 'export files reproduce from the database'),
        (f'{ran} / {ran}', 'Python tests pass'),
        (f'${units * USD_PER_UNIT:,.2f}', f'{units:,} units billed in {len(billed)} jobs'),
    ]
    commit = git('rev-parse', '--short', 'HEAD').stdout.strip()
    branch = git('rev-parse', '--abbrev-ref', 'HEAD').stdout.strip()
    dirty = git('status', '--porcelain', '--', 'python').stdout.strip()
    code_note = (f'Code at commit <code>{commit}</code> on the <code>{E(branch)}</code> branch'
                 + ('; files under <code>python/</code> had uncommitted changes when this page was built.' if dirty else '.'))
    conn = sqlite3.connect(f'file:{Path(DB_PATH).resolve()}?mode=ro', uri=True)
    try:
        latest = conn.execute('SELECT MAX(date) FROM sittings').fetchone()[0]
    finally:
        conn.close()
    return {
        '<!--DATE-->': long_date(date.today()),
        '<!--CODE-->': code_note,
        '<!--CONFIRMED-->': ''.join(f'<div><b>{E(v)}</b><span>{E(t)}</span></div>' for v, t in confirmed),
        '<!--DB-->': f'with sittings up to {long_date(date.fromisoformat(latest))}',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT / 'pipeline-verification.html')
    args = parser.parse_args()

    jobs, batch, saved = read_jobs(DEFAULT_OUT)
    steps, reexported = build_steps(DEFAULT_OUT, jobs, batch)
    parts = header(jobs, saved, reexported)
    parts['<!--FINDINGS-->'] = findings()
    parts['<!--NAV-->'] = ''.join(f'<li><a href="#{k}"><span class="n">{i}</span>{E(t)}</a></li>'
                                  for i, (k, t, _, _) in enumerate(steps, 1))
    outputs = {
        'select': 'debate sections', 'split': 'speaker turns', 'label': 'speeches.jsonl', 'export': 'manifest.json · upload CSVs',
        'send': 'jobs.jsonl · raw/', 'results': 'results.jsonl', 'prepared': 'prepared_speeches/',
        'dashboard': 'upload CSVs · results.jsonl', 'photos': 'credits.json · photos/', 'build': 'who-wrote-the-address.html',
        'share': 'Drive folder'}
    parts['<!--PIPELINE-->'] = ''.join(f'<li><a href="#{k}"><span class="n">{i}</span><b>{E(t)}</b><span class="o">{E(outputs[k])}</span></a></li>'
                                       for i, (k, t, _, _) in enumerate(steps, 1))
    parts['<!--STEPS-->'] = ''.join(f'<section class="step" id="{k}"><header><span class="eyebrow">Step {i}</span><h2>{E(t)}</h2>'
                                    f'<span class="src">{E(src)}</span></header>{inner}</section>'
                                    for i, (k, t, src, inner) in enumerate(steps, 1))
    page = TEMPLATE.read_text(encoding='utf-8')
    for marker, value in parts.items():
        page = page.replace(marker, value)
    args.out.write_text(page, encoding='utf-8')
    print(f'Wrote {args.out} ({len(page) // 1024} KB)')


if __name__ == '__main__':
    main()
