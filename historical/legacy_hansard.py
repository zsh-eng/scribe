"""Conservative adapters for semantic and flat historical Hansard HTML.

Keep whole topics (including procedural ones) and expose unresolved identities for review.
No provider calls, database writes, or modern ministry guesses belong here.
"""
from collections import Counter
from datetime import datetime
import hashlib
import logging
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment, Tag

from parliament_sitting import MP, ParliamentSitting
from util import parse_mp_name, extract_name_from_speaker_text

logger = logging.getLogger(__name__)


def text(node):
    return ' '.join(node.get_text(' ', strip=True).split())


def clean_fragment(html):
    soup = BeautifulSoup(html, 'html.parser')
    for node in soup.find_all(string=lambda s: isinstance(s, Comment)):
        node.extract()
    for node in list(soup.select('script, style')):
        node.decompose()
    for node in list(soup.select('font, .column')):
        if re.fullmatch(r'(?:Column|Page):\s*\d+', text(node), re.I):
            node.decompose()
    for node in soup.find_all(True):
        for attr in list(node.attrs):
            if attr.lower().startswith('on'):
                del node[attr]
        for attr in ('href', 'src'):
            if node.get(attr):
                url = urljoin('https://sprs.parl.gov.sg/search/', node[attr])
                if url.startswith(('http://', 'https://')):
                    node[attr] = url
                else:
                    del node[attr]
    return soup


def metadata(soup, date, warnings=None):
    warnings = warnings if warnings is not None else []
    labels = {'Parliament No:': 'parliament', 'Session No:': 'session_no',
              'Volume No:': 'volume_no', 'Sitting No:': 'sitting_no', 'Sitting Date:': 'date'}
    values = {}
    for row in soup.find_all('tr'):
        cells = row.find_all('td', recursive=False)
        if len(cells) == 2 and text(cells[0]) in labels:
            values[labels[text(cells[0])]] = text(cells[1])
    for name, key in [('Parl_No', 'parliament'), ('Sess_No', 'session_no'),
                      ('Vol_No', 'volume_no'), ('Sit_No', 'sitting_no'), ('Sit_Date', 'date')]:
        tag = soup.find('meta', attrs={'name': name})
        if tag:
            value = tag.get('content', '')
            if key == 'date':
                try:
                    value = datetime.strptime(value, '%Y-%m-%d' if '-' in value else '%Y%m%d').strftime('%d-%m-%Y')
                except ValueError:
                    warnings.append(f'Unrecognised metadata date: {value}')
                    continue
            if key in values and values[key] != value:
                warnings.append(f'Conflicting metadata {key}: {values[key]!r} / {value!r}')
                continue
            values[key] = value
    if values.get('date'):
        raw_date = values['date']
        parsed_date = None
        for pattern in ('%d-%m-%Y', '%Y-%m-%d', '%Y%m%d'):
            try:
                parsed_date = datetime.strptime(raw_date, pattern).strftime('%d-%m-%Y')
                break
            except ValueError:
                pass
        if parsed_date is None:
            warnings.append(f'Unrecognised source date: {raw_date!r}; requested date retained')
        values['date'] = parsed_date or date
    if values.get('date') and values['date'] != date:
        raise ValueError(f"Requested {date}, received {values['date']}")
    values['date'] = date
    for key in set(labels.values()) - {'date'}:
        raw = values.get(key)
        try:
            values[key] = int(raw)
        except (ValueError, TypeError):
            warnings.append(f'Unknown metadata {key}: {raw!r}')
            values[key] = None
    return values


def heading(node):
    if not isinstance(node, Tag) or node.name != 'div' or node.get('align', '').lower() != 'center':
        return None
    value = text(node)
    if not value or value.startswith('[') or node.find('i'):
        return None
    if value in ('PRESENT:', 'ABSENT:') or node.find(['b', 'h4']):
        return value
    return None


def flat_blocks(soup):
    """Group adjacent centred title lines; keep every intervening body node in order."""
    if not soup.body:
        raise ValueError('Legacy HTML has no body')
    blocks = []
    current = None
    started = False
    column = None
    for node in soup.body.children:
        if isinstance(node, Tag):
            marker = re.fullmatch(r'(?:Column|Page):\s*(\d+)', text(node), re.I)
            if marker:
                column = marker.group(1)
        title = heading(node)
        if title == 'PRESENT:':
            started = True
        if not started:
            continue  # metadata and report masthead precede the explicit roster
        html = '' if isinstance(node, Comment) else str(node)
        meaningful = bool(text(clean_fragment(html)))
        if title:
            if (current and not current['has_body'] and current['title'] not in ('PRESENT:', 'ABSENT:')
                    and (not re.match(r'^(?:oral answers?|written answers?|bills introduced)\b', current['title'], re.I)
                         or current['title'].endswith(' NOT'))):
                current['title'] += ' ' + title
                current['html'] += html
                continue
            current = {'title': title, 'html': html, 'has_body': False, 'anchor': None, 'column': column}
            blocks.append(current)
        elif current:
            current['html'] += html
            current['has_body'] |= meaningful
    if not blocks:
        raise ValueError('Unrecognised flat legacy layout: no PRESENT roster')
    return blocks


def semantic_blocks(soup):
    blocks = []
    group = ''
    for node in soup.body.children:
        if not isinstance(node, Tag):
            continue
        if 'topicgroup' in node.get('class', []):
            group = text(node)
        elif 'hansardContent' in node.get('class', []):
            title = node.select_one('h1.topictitle1')
            if title is None:
                if not blocks:
                    raise ValueError('Legacy continuation has no preceding topic')
                blocks[-1]['html'] += str(node)
                continue
            body = node.select_one('.hansardBaseBody')
            blocks.append({'title': text(title), 'html': str(node), 'group': group,
                           'anchor': body.get('id') if body else None})
    return blocks


def roster(soup, blocks, semantic, warnings=None):
    warnings = warnings if warnings is not None else []
    rows = {'present': [], 'absent': []}
    if semantic:
        attendance = next((b for b in blocks if b['title'].lower() == 'attendance'), None)
        if not attendance:
            warnings.append('No structured attendance topic')
            return {'present': [], 'absent': []}
        part = BeautifulSoup(attendance['html'], 'html.parser')
        for header in part.find_all('h2'):
            key = text(header).lower().rstrip(':')
            if key in rows:
                listing = header.find_next_sibling('ul')
                if listing:
                    rows[key] = [text(li) for li in listing.find_all('li', recursive=False)]
    else:
        for block in blocks:
            if block['title'] in ('PRESENT:', 'ABSENT:'):
                # Original source wraps names across newlines: only BR is a record boundary.
                raw = clean_fragment(block['html'])
                for br in raw.find_all('br'):
                    br.replace_with('\x1e')
                rows[block['title'].lower().rstrip(':')] = [
                    ' '.join(line.split()) for line in raw.get_text().split('\x1e')
                    if line.strip() and line.strip() not in ('PRESENT:', 'ABSENT:')]
    result = {}
    for key, names in rows.items():
        members = []
        for name in names:
            details = parse_mp_name(name)
            if details[1] is None and details[2] != 'Speaker':
                warnings.append(f'Unresolved attendance entry: {name}')
                continue
            members.append(MP(*details))
        result[key] = members
    if not result['present']:
        warnings.append('No resolved present members')
    all_names = [m.name for ms in result.values() for m in ms]
    if len(all_names) != len(set(all_names)):
        warnings.append('Duplicate or conflicting attendance entries')
    return result


def section_kind(title, body, group):
    """Only label types supported by explicit headings or introductory wording."""
    title_lower = title.lower()
    intro = text(body)[:1200].lower()
    if 'bill' in title_lower and re.search(r'\bread (?:a |the )?first time\b', intro):
        return 'BI', 'bill'
    if 'bill' in title_lower and re.search(r'(?:read a second time|second reading)', intro):
        return 'BP', 'bill'
    if body.select_one('.hcQuestion') or re.search(r'\basked (?:the|whether)\b', intro):
        if 'not answered' in group.lower() or 'not answered' in title_lower:
            return 'WANA', 'question'
        if 'written answer' in group.lower():
            return 'WA', 'question'
        if 'oral answer' in group.lower():
            return 'OA', 'question'
    if '(motion)' in intro or 'i beg to move' in intro or 'statement by the minister' in intro:
        return 'OS', 'motion'
    return None, 'other'


def resolve_speakers(body, members):
    candidates = body.select('.hcMember') or body.find_all(['b', 'strong'])
    resolved, unresolved = {}, set()
    for node in candidates:
        label = text(node).rstrip(':')
        if len(label) > 250 or not re.match(r'^(?:The |Deputy |Minister |Mr |Mrs |Ms |Miss |Dr |Mdm |Encik |Assoc|Prof|BG |RAdm |Er |Speaker)', label):
            continue
        role_name = re.search(r'\((?:Mr|Mrs|Ms|Dr|Mdm|Encik) ([^)]+)\)', label)
        name = role_name.group(1) if role_name and 'Minister' in label else extract_name_from_speaker_text(label)
        if name:
            name = name.rstrip(' ,:')
        if not name:
            continue
        exact = [m for m in members if m.name.casefold() == name.casefold()]
        if not exact:
            # A surname/short name must be a whole-token subsequence and unique in this roster.
            exact = [m for m in members if re.search(r'(?<!\w)' + re.escape(name.casefold()) + r'(?!\w)', m.name.casefold())]
        if name == 'Speaker':
            exact = [m for m in members if m.appointment == 'Speaker']
        if len(exact) == 1:
            if exact[0].appointment != 'Speaker':
                resolved[exact[0].name] = exact[0]
        else:
            unresolved.add(label)
    return list(resolved.values()), sorted(unresolved)


def word_blocks(html):
    """Split original bytes at explicit markers before HTML error recovery changes nesting."""
    markers = list(re.finditer(r'<![ \t]*(?P<comment>--\s*)?(?P<kind>SECTION_NAME|TITLE_NAME):(?P<title>[\s\S]*?)(?(comment)-->|>)', html, re.I))
    blocks = []
    group = ''
    if markers and text(clean_fragment(html[:markers[0].start()])):
        blocks.append({'title': 'Report preamble', 'html': html[:markers[0].start()], 'anchor': None})
    for index, marker in enumerate(markers):
        title = text(BeautifulSoup(marker.group('title'), 'html.parser'))
        if marker.group('kind').upper() == 'SECTION_NAME':
            group = title
        end = markers[index + 1].start() if index + 1 < len(markers) else len(html)
        fragment = html[marker.end():end]
        if text(clean_fragment(fragment)):
            column_marker = re.search(r'<!--END_COL_TITLE:[\s\S]*?:::(\d+)\s*-->', fragment, re.I)
            blocks.append({'title': title or 'Untitled source section', 'html': fragment,
                           'anchor': None, 'group': group, 'source_offset': marker.start(),
                           'column': column_marker.group(1) if column_marker else None})
    return blocks


def institution(soup, date):
    """Use report wording for the old legislature; do not assign a modern parliament."""
    intro = re.split(r'\b(?:PRESENT|ATTENDANCE)\s*:', text(soup)[:12000].upper(), maxsplit=1)[0]
    if 'LEGISLATIVE ASSEMBLY' in intro:
        return {'name': 'Legislative Assembly', 'evidence': 'report masthead'}
    if 'LEGISLATIVE COUNCIL' in intro:
        return {'name': 'Legislative Council', 'evidence': 'report masthead'}
    if datetime.strptime(date, '%d-%m-%Y') >= datetime(1965, 8, 9):
        return {'name': 'Parliament of Singapore', 'evidence': 'sitting date on or after independence'}
    return {'name': None, 'evidence': 'pre-independence report; institution unresolved'}


def parse_legacy(date, html):
    soup = BeautifulSoup(html, 'html.parser')
    warnings = []
    info = metadata(soup, date, warnings)
    semantic = bool(soup.select('.hansardContent'))
    word = bool(re.search(r'<![ \t]*(?:--\s*)?SECTION_NAME:', html, re.I))
    layout = 'word-export' if word else 'semantic' if semantic else 'flat'
    try:
        blocks = word_blocks(html) if word else semantic_blocks(soup) if semantic else flat_blocks(soup)
    except ValueError as exc:
        warnings.append(str(exc))
        layout = 'unsegmented'
        blocks = [{'title': 'Unsegmented report', 'html': html, 'anchor': None}]
    attendance_blocks = blocks
    if word:
        attendance_blocks = []
        for block in blocks:
            if block['title'].upper() != 'ATTENDANCE':
                continue
            raw = clean_fragment(block['html'])
            for br in raw.find_all('br'):
                br.replace_with('\x1e')
            raw_text = raw.get_text()
            parts = re.split(r'\b(PRESENT|ABSENT):', raw_text)
            for index in range(1, len(parts), 2):
                # BR, not whitespace, is the name boundary in these reports.
                from html import escape
                entries = '<br>'.join(escape(line.strip()) for line in parts[index + 1].split('\x1e'))
                attendance_blocks.append({'title': parts[index] + ':', 'html': entries})
    members = roster(soup, attendance_blocks, semantic and not word, warnings)
    sitting = ParliamentSitting(date)
    sitting.set_metadata({**info, 'format': 'old'})
    sitting.metadata['institution'] = institution(soup, date)
    sitting.present_members, sitting.absent_members = members['present'], members['absent']
    sitting.parse_audit = {'format': layout, 'topics': [], 'group_headings': [],
                           'unresolved_speakers': [], 'warnings': warnings,
                           'retained_source_text': text(clean_fragment(html)),
                           'segmentation_status': 'unsegmented' if layout == 'unsegmented' else 'segmented' if blocks else 'empty'}
    seen = Counter()
    group = ''
    for block in blocks:
        title = block['title']
        body = clean_fragment(block['html'])
        # Standalone group labels carry no transcript and apply to following topics.
        if not word and not semantic and re.match(r'^(?:oral answers?|written answers?|bills introduced)\b', title, re.I):
            group = title
            sitting.parse_audit['group_headings'].append(title)
            if text(body) == title:
                continue
            warnings.append(f'Content retained under group heading: {title}')
        kind, category = section_kind(title, body, block.get('group', group))
        if title.lower() in ('attendance', 'present:', 'absent:'):
            kind, category = None, 'attendance'
        speakers, unresolved = resolve_speakers(body, sitting.present_members + sitting.absent_members)
        anchor = block['anchor']
        # Text corrections preserve IDs. Column markers distinguish repeated flat titles without using mutable transcript text.
        identity_text = title.casefold() + ':' + (block.get('column') or '')
        identity = anchor or hashlib.sha256(identity_text.encode()).hexdigest()[:24]
        seen[identity] += 1
        if seen[identity] > 1:
            warnings.append(f'Repeated topic identity uses occurrence suffix: {title}')
            identity += f':occurrence-{seen[identity]}'
        source_id = f'legacy:{date}:{identity}'
        url = f'https://sprs.parl.gov.sg/search/#/report?sittingdate={date}'
        sitting.sections.append({'title': title, 'section_type': kind, 'category': category,
                                 'content_html': str(body), 'content_plain': text(body),
                                 'speakers': speakers, 'source_ids': [source_id], 'source_url': url,
                                 'order': len(sitting.sections), 'historical': True})
        sitting.parse_audit['topics'].append({'title': title, 'type': kind, 'source_id': source_id})
        sitting.parse_audit['unresolved_speakers'].extend(unresolved)
    sitting.parse_audit['unresolved_speakers'] = sorted(set(sitting.parse_audit['unresolved_speakers']))
    if not sitting.sections:
        warnings.append('Report has no segmented topics; full source text retained')
    source_tokens = Counter(sitting.parse_audit['retained_source_text'].split())
    section_tokens = Counter(' '.join(s['content_plain'] for s in sitting.sections).split())
    residual = source_tokens - section_tokens
    sitting.parse_audit['text_coverage'] = {
        'source_tokens': sum(source_tokens.values()),
        'section_tokens': sum(section_tokens.values()),
        'tokens_outside_sections': sum(residual.values()),
        'outside_sections_token_counts': dict(sorted(residual.items())),
        'note': 'Token multiset comparison; source text includes masthead and attendance. This is not an order or semantic completeness proof.',
    }
    logger.info('Legacy %s: %s topics retained, %s unclassified', date, len(sitting.sections),
                sum(s['section_type'] is None for s in sitting.sections))
    if sitting.parse_audit['unresolved_speakers']:
        logger.warning('Legacy %s: unresolved speakers: %s', date, sitting.parse_audit['unresolved_speakers'])
    return sitting


if __name__ == '__main__':
    import argparse
    import gzip
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description='Inspect a saved historical report without database writes or API calls')
    parser.add_argument('date', help='DD-MM-YYYY')
    parser.add_argument('source', type=Path, help='Saved API JSON (optionally .gz)')
    args = parser.parse_args()
    raw = args.source.read_bytes()
    if args.source.suffix == '.gz':
        raw = gzip.decompress(raw)
    sitting = parse_legacy(args.date, json.loads(raw)['htmlFullContent'])
    print(json.dumps({'metadata': sitting.metadata,
                      'present': len(sitting.present_members), 'absent': len(sitting.absent_members),
                      'source_sha256': hashlib.sha256(raw).hexdigest(), **sitting.parse_audit}, indent=2))
