"""Count normalized archive records and estimate static output without a build.

Run with Python's standard library. JSON output states completeness and separates
exact source counts, HTML bounds under stated assumptions, and search estimates.
"""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_json(path):
    payload = path.read_bytes()
    return json.loads(gzip.decompress(payload) if path.suffix == '.gz' else payload)


def project(inventory, normalized, dist):
    rows = read_json(inventory)['sittings']
    dates = sorted({r['date'] for r in rows if not r.get('present_in_active', False)})
    active = len({r['date'] for r in rows if r.get('present_in_active', False)})
    counts, types, categories, statuses = Counter(), Counter(), Counter(), Counter()
    names, missing = set(), []
    for date in dates:
        path = normalized / f'{date}.json.gz'
        if not path.exists():
            missing.append(date)
            continue
        record = read_json(path)
        counts['normalized_sittings'] += 1
        statuses[record.get('status', 'unknown')] += 1
        for roster in record.get('attendance', {}).values():
            for member in roster:
                if member.get('name'):
                    names.add(member['name'])
        for section in record.get('sections', []):
            counts['retained_topics'] += 1
            kind, category = section.get('section_type'), section.get('category')
            types[kind or 'unclassified'] += 1
            categories[category or 'unclassified'] += 1
            question = kind in ('OA', 'WA', 'WANA')
            motion = category in ('motion', 'adjournment_motion')
            clarification = category == 'clarification'
            bill = kind in ('BI', 'BP') or category == 'bill'
            counts['question_routes'] += question
            counts['motion_routes'] += motion
            counts['clarification_routes'] += clarification
            counts['bill_sections'] += bill
            counts['topics_without_current_detail_route'] += not (question or motion or clarification or bill)
            for member in section.get('speakers', []):
                if member.get('name'):
                    names.add(member['name'])
    files = [p for p in dist.rglob('*') if p.is_file()]
    html = sum(p.suffix == '.html' for p in files)
    pagefind = sum('pagefind' == p.relative_to(dist).parts[0] for p in files)
    other = len(files) - html - pagefind
    sitting_count = counts['normalized_sittings']
    detail = sum(counts[key] for key in ('question_routes', 'motion_routes', 'clarification_routes'))
    lower = sitting_count + detail
    upper = lower + counts['bill_sections'] + len(names)
    all_topics = sitting_count + counts['retained_topics']
    def scenario(low, high):
        ratio = pagefind / html if html else None
        return {
            'additional_html_lower': low, 'additional_html_upper': high,
            'combined_html_lower': html + low, 'combined_html_upper': html + high,
            'combined_assets_without_new_search_lower': len(files) + low,
            'combined_assets_without_new_search_upper': len(files) + high,
            'combined_assets_at_current_search_ratio_lower': round(len(files) + low * (1 + ratio)) if ratio is not None else None,
            'combined_assets_at_current_search_ratio_upper': round(len(files) + high * (1 + ratio)) if ratio is not None else None,
        }
    return {
        'inventory': {'indexed_dates': len({r['date'] for r in rows}), 'active_dates': active,
                      'additional_dates': len(dates), 'additional_vs_active_ratio': len(dates) / active if active else None,
                      'total_vs_active_ratio': (active + len(dates)) / active if active else None},
        'complete': not missing, 'missing_normalized_dates': missing,
        'counts': dict(counts), 'section_types': dict(types), 'categories': dict(categories),
        'statuses': dict(statuses), 'distinct_parsed_member_names': len(names),
        'existing_build': {'html': html, 'pagefind': pagefind, 'other': other, 'assets': len(files)},
        'current_route_scenario': scenario(lower, upper),
        'all_retained_topic_scenario': scenario(all_topics, all_topics + len(names)),
        'assumptions': [
            'Current route bounds add one sitting page and all eligible question, motion, clarification routes.',
            'Current route lower adds no bill/member pages; upper adds one per bill section and distinct parsed member name.',
            'Bill identity and member overlap are unresolved. These are design bounds, not exact generated route counts.',
            'Both scenarios add zero ministry routes and retain fixed pages and other assets; a ministry design change requires recounting.',
            'All-topic scenario gives every retained topic its own page, plus sitting pages and optionally member pages; no extra bill-group pages.',
            'New Pagefind file counts have no measured upper bound here. Search-ratio outputs are estimates, not capacity guarantees.',
            'Assets without new search retain the existing Pagefind files but add no archive search files.',
            'needs_review records can contain unsegmented source text; retained topic totals do not assert complete semantic segmentation.',
            'Counts are provisional until complete is true; rerun after transformation finishes.',
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path, default=ROOT / 'data/inventory/inventory.json')
    parser.add_argument('--normalized', type=Path, default=ROOT / 'data/normalized')
    parser.add_argument('--dist', type=Path, default=ROOT.parent / 'astro/dist')
    args = parser.parse_args()
    print(json.dumps(project(args.inventory, args.normalized, args.dist), indent=2))


if __name__ == '__main__':
    main()
