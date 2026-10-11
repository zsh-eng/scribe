"""Download openly licensed portraits of MPs from Wikipedia/Wikimedia Commons.

For each member who spoke in the exported debates, searches English Wikipedia for a
Singaporean politician of that name and takes the article's lead image only when it is
freely licensed (pilicense=free). Saves a 320px thumbnail per member plus credits.json with
the file page, author and licence needed for attribution. Members without a match get no
file; the explorer draws a monogram for them.
"""
import argparse
import html
import json
import re
import time
from pathlib import Path

import requests

from export_pangram_speeches import DEFAULT_OUT
from run_pangram_bulk import read_jsonl

WIKI = 'https://en.wikipedia.org/w/api.php'
COMMONS = 'https://commons.wikimedia.org/w/api.php'
HEADERS = {'User-Agent': 'SecondReadingResearch/0.1 (https://secondreading.app; internal analysis)'}
POLITICIAN = re.compile(r'singapor', re.I)


def tokens(name):
    return {t for t in re.findall(r'[a-z]+', name.lower()) if len(t) > 1}


def find_article(session, name):
    """Return (title, image file name) for the best free-image article match, or None."""
    params = {'action': 'query', 'format': 'json', 'generator': 'search', 'gsrsearch': f'{name} Singapore politician',
              'gsrlimit': 5, 'prop': 'description|pageimages', 'piprop': 'name', 'pilicense': 'free'}
    pages = session.get(WIKI, params=params, timeout=30).json().get('query', {}).get('pages', {})
    want = tokens(name)
    for page in sorted(pages.values(), key=lambda p: p.get('index', 99)):
        title_tokens = tokens(page['title'])
        if len(want & title_tokens) < min(2, len(title_tokens)) or not POLITICIAN.search(page.get('description', '')):
            continue
        return page['title'], page.get('pageimage')
    return None


def image_info(session, file_name):
    params = {'action': 'query', 'format': 'json', 'titles': f'File:{file_name}', 'prop': 'imageinfo',
              'iiprop': 'url|extmetadata', 'iiurlwidth': 320}
    pages = session.get(COMMONS, params=params, timeout=30).json().get('query', {}).get('pages', {})
    info = next(iter(pages.values()), {}).get('imageinfo', [{}])[0]
    meta = info.get('extmetadata', {})
    plain = lambda key: re.sub(r'<[^>]+>', '', html.unescape(meta.get(key, {}).get('value', ''))).strip()
    return {'thumb': info.get('thumburl'), 'page': info.get('descriptionurl'), 'author': plain('Artist'),
            'license': plain('LicenseShortName'), 'license_url': plain('LicenseUrl')}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--export-dir', type=Path, default=DEFAULT_OUT)
    parser.add_argument('--out-dir', type=Path, default=DEFAULT_OUT.parent / 'photos')
    parser.add_argument('--years', nargs='+', default=['2020', '2025'])
    args = parser.parse_args()

    members = {}
    for s in read_jsonl(args.export_dir / 'speeches.jsonl'):
        if s['member_id'] and s['upload_batch'] in args.years:
            members[s['member_id']] = s['member_name']
    args.out_dir.mkdir(parents=True, exist_ok=True)
    credits_path = args.out_dir / 'credits.json'
    credits = json.loads(credits_path.read_text()) if credits_path.exists() else {}
    session = requests.Session()
    session.headers.update(HEADERS)

    for member_id, name in sorted(members.items(), key=lambda kv: kv[1]):
        if member_id in credits:
            continue
        match = find_article(session, name)
        record = {'name': name, 'article': match[0] if match else None, 'file': None}
        if match and match[1]:
            info = image_info(session, match[1])
            if info['thumb'] and info['license']:
                path = args.out_dir / f'{member_id}.jpg'
                path.write_bytes(session.get(info['thumb'], timeout=60).content)
                record.update(info, file=path.name, source_file=match[1])
        credits[member_id] = record
        print(f"{'photo' if record['file'] else ('article' if match else 'none '):7s} {name} -> {record['article']}")
        time.sleep(0.2)
    credits_path.write_text(json.dumps(credits, indent=2, ensure_ascii=False) + '\n')
    found = sum(1 for c in credits.values() if c['file'])
    print(f'{found} of {len(credits)} members have a freely licensed photo in {args.out_dir}')


if __name__ == '__main__':
    main()
