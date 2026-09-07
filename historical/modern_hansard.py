"""Archive structured Hansard reports without the live site's section filters.

The caller retains response bytes. This transform retains every source row and all
response fields in the audit. It does not write a database or call a provider.
"""
from copy import deepcopy
from datetime import datetime

from bs4 import BeautifulSoup

from legacy_hansard import clean_fragment, resolve_speakers, text
from parliament_sitting import MP, ParliamentSitting, ALL_VALID_TYPES
from util import parse_mp_name


def _source_strings(value):
    """Retain text from every string field, including supplementary report lists."""
    if isinstance(value, str):
        yield text(BeautifulSoup(value, 'html.parser'))
    elif isinstance(value, dict):
        for item in value.values():
            yield from _source_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _source_strings(item)


def parse_modern(date, data):
    """Return one archive section per takesSectionVOList entry, in source order."""
    datetime.strptime(date, '%d-%m-%Y')
    if not isinstance(data, dict) or not isinstance(data.get('takesSectionVOList'), list):
        raise ValueError('Expected structured Hansard report with takesSectionVOList')
    raw_metadata = data.get('metadata') or {}
    if not isinstance(raw_metadata, dict):
        raise ValueError('Expected Hansard metadata object')
    if raw_metadata.get('sittingDate') != date:
        raise ValueError(f"Requested {date}, received {raw_metadata.get('sittingDate')}")
    warnings = []
    sitting = ParliamentSitting(date)
    metadata = {'format': 'new'}
    for source, target in [('sittingNO', 'sitting_no'), ('parlimentNO', 'parliament'),
                           ('sessionNO', 'session_no'), ('volumeNO', 'volume_no')]:
        value = raw_metadata.get(source)
        try:
            metadata[target] = int(value)
        except (ValueError, TypeError):
            metadata[target] = None
            warnings.append(f'Unknown metadata {target}: {value!r}')
    sitting.set_metadata(metadata)
    audit = sitting.parse_audit = {
        'format': 'modern-structured', 'warnings': warnings, 'topics': [],
        'raw_section_count': len(data['takesSectionVOList']),
        'unresolved_attendance': [], 'unresolved_speakers': [], 'unknown_section_types': [],
        'source_response': deepcopy(data),
        'retained_source_text': ' '.join(_source_strings(data)),
    }
    attendance = data.get('attendanceList')
    if not isinstance(attendance, list):
        warnings.append('Missing or invalid attendanceList; raw value retained in source_response')
        attendance = []
    audit['raw_attendance_count'] = len(attendance)
    for index, row in enumerate(attendance):
        name = row.get('mpName') if isinstance(row, dict) else None
        present = row.get('attendance') if isinstance(row, dict) else None
        try:
            if not isinstance(name, str) or not name.strip() or not isinstance(present, bool):
                raise ValueError('Missing name or non-boolean attendance')
            member = MP(*parse_mp_name(name))
            if not member.name.strip():
                raise ValueError('Empty parsed name')
        except (ValueError, TypeError, AttributeError) as error:
            audit['unresolved_attendance'].append({'index': index, 'row': deepcopy(row), 'reason': str(error)})
            continue
        (sitting.present_members if present else sitting.absent_members).append(member)
    if audit['unresolved_attendance']:
        warnings.append(f"Unresolved attendance rows: {len(audit['unresolved_attendance'])}")
    members = sitting.present_members + sitting.absent_members
    for index, row in enumerate(data['takesSectionVOList']):
        source_id = f'modern:{date}:takesSectionVOList:{index}'
        raw = row if isinstance(row, dict) else {}
        if not isinstance(row, dict):
            warnings.append(f'Invalid section row {index}; raw value retained')
        title = raw.get('title') or 'Untitled source section'
        if not isinstance(title, str):
            title = str(title)
            warnings.append(f'Non-string title in section {index}')
        kind = raw.get('sectionType')
        category = 'other'
        if kind in ('OA', 'WA', 'WANA'):
            category = 'question'
        elif kind in ('BI', 'BP'):
            category = 'bill'
        elif kind in ('OS', 'WS'):
            category = ('clarification' if 'clarification' in title.casefold() else
                        'adjournment_motion' if raw.get('reportType') == 'Matter Raised On Adjournment Motion' else 'motion')
        if not isinstance(kind, str) or kind not in ALL_VALID_TYPES:
            audit['unknown_section_types'].append({'index': index, 'value': deepcopy(kind)})
            kind = kind if isinstance(kind, str) else None
        html = raw.get('content')
        if not isinstance(html, str):
            warnings.append(f'Missing or non-string content in section {index}; row retained')
            html = ''
        body = clean_fragment(html)
        speakers, unresolved = resolve_speakers(body, members)
        sitting.sections.append({
            'title': title, 'section_type': kind, 'category': category,
            'content_html': str(body), 'content_plain': text(body), 'speakers': speakers,
            'source_ids': [source_id],
            'source_url': (f"https://sprs.parl.gov.sg/search/#/sprs3topic?reportid={raw['sectionId']}"
                           if raw.get('sectionId') is not None else
                           f'https://sprs.parl.gov.sg/search/#/fullreport?sittingdate={date}'),
            'official_section_id': raw.get('sectionId'),
            'order': index, 'historical': True,
        })
        audit['topics'].append({'title': title, 'type': kind, 'source_id': source_id})
        audit['unresolved_speakers'].extend(unresolved)
    audit['unresolved_speakers'] = sorted(set(audit['unresolved_speakers']))
    audit['retained_section_count'] = len(sitting.sections)
    if audit['unknown_section_types']:
        warnings.append(f"Unknown section types: {len(audit['unknown_section_types'])}")
    for key in ('writtenAnswersVOList', 'writtenAnsNAVOList', 'annexureList', 'vernacularList'):
        if data.get(key):
            warnings.append(f'{key} retained in source_response; not segmented as takes sections')
    if not sitting.sections:
        warnings.append('Report has no takes sections; full source response retained')
    return sitting
