"""Fetch Hansard responses, retain source snapshots, and parse offline replays."""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from parliament_sitting import ParliamentSitting


class HansardAPI:
    BASE_URL = "https://sprs.parl.gov.sg/search/getHansardReport/"
    SEARCH_URL = "https://sprs.parl.gov.sg/search/searchResult"

    def __init__(self):
        self.session = requests.Session()
        # This POST endpoint is a read-only report lookup.
        retry = Retry(total=2, backoff_factor=0.5, allowed_methods={'POST'},
                      status_forcelist=(429, 500, 502, 503, 504),
                      respect_retry_after_header=False)
        self.session.mount('https://', HTTPAdapter(max_retries=retry))

    def discover_dates(self, start_date_str, end_date_str):
        """Read distinct sitting dates from the index, then return oldest first.

        Use broad date windows because the service can return HTTP 500 for an
        empty narrow window. Each page moves the upper bound before its oldest
        date. Duplicate section hits for that date need no further pagination:
        the report endpoint returns the whole sitting.
        """
        start = datetime.strptime(start_date_str, '%d-%m-%Y').date()
        upper = datetime.strptime(end_date_str, '%d-%m-%Y').date()
        if start > upper:
            raise ValueError('Start date must be on or before end date')
        found = set()
        previous_total = None
        while upper >= start:
            payload = dict(keyword='', dateRange='custom', fromday='1', frommonth='1',
                           fromyear='1955', today=str(upper.day), tomonth=str(upper.month),
                           toyear=str(upper.year), reportContent='with all the words',
                           parliamentNo='', selectedSort='date_dt desc', startIndex='0',
                           endIndex='19', titleChecked='false', footNoteChecked='false')
            response = self.session.post(self.SEARCH_URL, json=payload, timeout=(10, 30))
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list):
                raise ValueError('Expected a Hansard search result list')
            if not rows:
                break
            try:
                total = int(rows[0]['maxResult'])
                dates = [datetime.strptime(row['sittingDate'], '%d-%m-%Y').date()
                         for row in rows]
                counts_match = all(int(row['maxResult']) == total for row in rows)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError('Malformed Hansard search result') from exc
            if not counts_match or total < len(rows):
                raise ValueError('Inconsistent Hansard search count')
            if dates != sorted(dates, reverse=True) or max(dates) > upper:
                raise ValueError('Hansard search dates are not descending within the window')
            if previous_total is not None and total >= previous_total:
                raise ValueError('Hansard search count did not decrease')
            found.update(day for day in dates if day >= start)
            if min(dates) <= start or total == len(rows):
                break
            previous_total = total
            upper = min(dates) - timedelta(days=1)
        return [day.strftime('%d-%m-%Y') for day in sorted(found)]

    def fetch_by_date(self, date_str: str) -> Optional[ParliamentSitting]:
        datetime.strptime(date_str, '%d-%m-%Y')
        response = self.session.post(self.BASE_URL, json={'sittingDate': date_str}, timeout=(10, 30))
        response.raise_for_status()
        data = response.json()
        self.save_source(date_str, data)
        return self.parse_response(date_str, data)

    def save_source(self, date_str, data):
        """Keep content-addressed snapshots; failed parsing remains reproducible."""
        default_db = Path(__file__).parent.parent / 'data' / 'parliament.db'
        db_path = Path(os.getenv('PARLIAMENT_DB_PATH', str(default_db)))
        root = Path(os.getenv('HANSARD_RAW_DIR', str(db_path.parent / 'raw' / 'hansard')))
        directory = root / datetime.strptime(date_str, '%d-%m-%Y').strftime('%Y-%m-%d')
        directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, sort_keys=True).encode()
        digest = hashlib.sha256(payload).hexdigest()
        target = directory / f'{digest}.json'
        try:
            with target.open('xb') as f:
                f.write(payload)
        except FileExistsError:
            return
        target.with_suffix('.meta.json').write_text(json.dumps({
            'source_url': f'{self.BASE_URL}?sittingDate={date_str}',
            'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'sha256': digest,
        }, indent=2) + '\n')

    def read_source(self, date_str, source_file):
        return self.parse_response(date_str, json.loads(Path(source_file).read_text()))

    def parse_response(self, date_str, data):
        if not isinstance(data, dict):
            raise ValueError('Expected a Hansard report object')
        if not data.get('takesSectionVOList'):
            if data.get('htmlFullContent'):
                raise ValueError('Unsupported legacy Hansard format')
            # Do not mistake an arbitrary error object for an empty report.
            if 'takesSectionVOList' not in data:
                raise ValueError('Hansard response is missing takesSectionVOList')
            return None
        metadata = self.get_sitting_metadata(data)
        if metadata['date'] != date_str:
            raise ValueError(f"Requested {date_str}, received {metadata['date']}")
        sitting = ParliamentSitting(date_str)
        sitting.set_metadata(metadata)
        sitting.set_attendance(data['attendanceList'])
        sitting.set_sections(data['takesSectionVOList'])
        return sitting

    def get_sitting_metadata(self, raw_data: Dict) -> Dict:
        metadata = raw_data.get('metadata', {})
        return {
            'date': metadata.get('sittingDate'),
            'sitting_no': metadata.get('sittingNO'),
            'parliament': metadata.get('parlimentNO'),
            'session_no': metadata.get('sessionNO'),
            'volume_no': metadata.get('volumeNO'),
            'format': 'new',
        }
