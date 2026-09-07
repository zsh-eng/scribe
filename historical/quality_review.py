"""Read-only corpus review. Counts are not a claim of transcript correctness."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import re


def read(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def review(root):
    signatures = Counter()
    statuses = Counter()
    formats = Counter()
    cases = []
    pending = []
    warnings = Counter()
    totals = Counter()
    residual_cases = []
    empty_attendance = []
    unknown_titles = []
    institution_conflicts = []
    for path in sorted((root / 'raw').glob('*.json.gz')):
        date = path.name[:10]
        raw = read(path)
        html = raw.get('htmlFullContent') or ''
        signature = ('word-export' if re.search(r'<!--\s*SECTION_NAME:', html, re.I)
                     else 'semantic' if 'hansardContent' in html
                     else 'other-html' if html else 'structured-takes')
        signatures[signature] += 1
        output = root / 'normalized' / path.name
        if not output.exists():
            pending.append(date)
            continue
        normalized = read(output)
        statuses[normalized.get('status', 'unknown')] += 1
        audit = normalized.get('audit', {})
        formats[audit.get('format', 'missing')] += 1
        if not normalized.get('attendance', {}).get('present'):
            empty_attendance.append(date)
        if any(section.get('title') == 'Untitled source section' for section in normalized.get('sections', [])):
            unknown_titles.append(date)
        evidence_name = normalized.get('metadata', {}).get('institution', {}).get('name')
        if evidence_name in ('Legislative Assembly', 'Legislative Council') and date >= '1965-08-09':
            institution_conflicts.append({'date': date, 'inferred_name': evidence_name})
        sections = normalized.get('sections', [])
        totals['sections'] += len(sections)
        for section in sections:
            if section.get('section_type') is None:
                totals['null_type_sections'] += 1
                totals['null_type_' + section.get('category', 'unknown')] += 1
            if section.get('title') == 'Untitled source section':
                totals['untitled_sections'] += 1
        unresolved = audit.get('unresolved_speakers', [])
        if unresolved:
            totals['reports_with_unresolved_speakers'] += 1
            totals['unresolved_speaker_report_labels'] += len(unresolved)
        coverage = audit.get('text_coverage', {})
        source_tokens = coverage.get('source_tokens', 0)
        residual = coverage.get('tokens_outside_sections', 0)
        ratio = residual / source_tokens if source_tokens else None
        if residual:
            totals['reports_with_residual_tokens'] += 1
            totals['residual_tokens'] += residual
            residual_cases.append({'date': date, 'ratio': ratio, 'outside_tokens': residual, 'source_tokens': source_tokens})
        for warning in audit.get('warnings', []):
            warnings[warning.split(':', 1)[0]] += 1
        if normalized.get('status') != 'parsed' or (ratio is not None and ratio > .1) or len(normalized.get('sections', [])) < 2:
            cases.append({'date': date, 'signature': signature, 'status': normalized.get('status'),
                          'format': audit.get('format'), 'sections': len(normalized.get('sections', [])),
                          'source_tokens': source_tokens, 'outside_tokens': residual,
                          'outside_ratio': round(ratio, 4) if ratio is not None else None,
                          'error': normalized.get('error'), 'warnings': audit.get('warnings', [])[:5]})
    return {'totals': dict(totals), 'largest_residual_ratios': sorted(residual_cases, key=lambda row: row['ratio'], reverse=True)[:10],
            'raw_signatures': dict(signatures), 'normalized_statuses': dict(statuses),
            'normalized_formats': dict(formats), 'pending_dates': pending,
            'warning_counts': dict(warnings), 'review_cases': cases,
            'empty_present_attendance_dates': empty_attendance,
            'untitled_section_dates': unknown_titles,
            'institution_date_conflicts': institution_conflicts,
            'limits': 'A token multiset audit cannot prove order or topic boundaries. Pending outputs may still be in progress.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path(__file__).parent / 'data')
    args = parser.parse_args()
    print(json.dumps(review(args.data), indent=2))
