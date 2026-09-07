"""Verify archive coverage and file integrity against the complete official inventory.

Writes audit/catalog files only when requested; never opens the application database.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import re

from bs4 import BeautifulSoup
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(path):
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def verify(data):
    inventory = read(data / 'inventory/inventory.json')
    expected = {row['date']: row for row in inventory['sittings'] if not row['present_in_active']}
    errors = []
    if not inventory.get('complete'):
        errors.append('Official inventory is incomplete')
    catalog = []
    counts = Counter()
    formats, categories, types = Counter(), Counter(), Counter()
    for date, entry in sorted(expected.items()):
        raw_path, output_path, state_path = [data / folder / f'{date}{suffix}' for folder,suffix in
                                            [('raw','.json.gz'),('normalized','.json.gz'),('state','.json')]]
        absent = [str(p.relative_to(data)) for p in [raw_path, output_path, state_path] if not p.exists()]
        if absent:
            errors.extend(f'Missing {p}' for p in absent)
            continue
        try:
            raw, output, state = read(raw_path), read(output_path), read(state_path)
        except Exception as error:
            errors.append(f'Unreadable {date}: {error}')
            continue
        digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        if state.get('raw_sha256') != digest:
            errors.append(f'Source checksum mismatch: {date}')
        if output.get('date') != date or state.get('date') != date:
            errors.append(f'Output date mismatch: {date}')
        if state.get('fetch_status') != 'ok':
            errors.append(f'Fetch not successful: {date}')
        if output.get('status') != state.get('transform_status'):
            errors.append(f'Transformation state mismatch: {date}')
        if output.get('institution') != entry['era'].replace('-', '_'):
            errors.append(f'Institution differs from official index: {date}')
        audit = output.get('audit', {})
        sections = output.get('sections', [])
        if raw.get('htmlFullContent'):
            if not (audit.get('retained_source_text') or output.get('full_text')):
                errors.append(f'No retained report text: {date}')
            if audit.get('retained_source_text'):
                source = BeautifulSoup(raw['htmlFullContent'], 'html.parser')
                for node in list(source.select('script, style')):
                    node.decompose()
                for node in list(source.select('font, .column')):
                    if re.fullmatch(r'(?:Column|Page):\s*\d+', ' '.join(node.get_text(' ', strip=True).split()), re.I):
                        node.decompose()
                source_text = ' '.join(source.get_text(' ', strip=True).split())
                if source_text != audit['retained_source_text']:
                    errors.append(f'Normalized full source text mismatch: {date}')
        else:
            if audit.get('source_response') != raw:
                errors.append(f'Structured source fields not fully retained: {date}')
            if len(sections) != len(raw.get('takesSectionVOList', [])):
                errors.append(f'Structured source section count mismatch: {date}')
        ids = [identifier for section in sections for identifier in section.get('source_ids', [])]
        if len(ids) != len(set(ids)):
            errors.append(f'Duplicate section source identity: {date}')
        if [s.get('order') for s in sections] != list(range(len(sections))):
            errors.append(f'Non-sequential section order: {date}')
        if audit.get('segmentation_status') in ('empty','unsegmented') and output.get('status') == 'parsed':
            errors.append(f'Unsegmented report marked parsed: {date}')
        counts[output.get('status','unknown')] += 1
        counts['sections'] += len(sections)
        counts['raw_bytes'] += raw_path.stat().st_size
        counts['normalized_bytes'] += output_path.stat().st_size
        formats[audit.get('format','unknown')] += 1
        for section in sections:
            categories[section.get('category') or 'unknown'] += 1
            types[section.get('section_type') or 'unclassified'] += 1
        catalog.append({'date': date, 'era': entry['era'], 'parliament': entry['parliament'],
                        'status': output.get('status'), 'format': audit.get('format'),
                        'sections': len(sections), 'raw_sha256': digest,
                        'normalized_sha256': hashlib.sha256(output_path.read_bytes()).hexdigest(),
                        'unresolved_speaker_labels': len(audit.get('unresolved_speakers', [])),
                        'warnings': len(audit.get('warnings', []))})
    actual = {p.name[:10] for p in (data/'raw').glob('*.json.gz')}
    if actual - expected.keys():
        errors.append(f'Raw reports outside target inventory: {sorted(actual - expected.keys())}')
    return {'complete': not errors and len(catalog) == len(expected),
            'scope': inventory['coverage'], 'target_sittings': len(expected),
            'verified_sittings': len(catalog), 'counts': dict(counts),
            'formats': dict(formats), 'categories': dict(categories), 'section_types': dict(types),
            'errors': errors,
            'limits': 'File coverage and source retention do not prove all topic boundaries, classifications, or speaker identities.'}, catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=ROOT/'data')
    parser.add_argument('--write',action='store_true')
    args = parser.parse_args()
    result, catalog = verify(args.data)
    if args.write:
        (args.data/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
        # A small tracked catalog can validate restored/downloaded archive files.
        (ROOT/'catalog.json').write_text(json.dumps({'schema_version':1,'sittings':catalog},indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
