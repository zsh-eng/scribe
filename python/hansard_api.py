"""Fetch Hansard responses, retain source snapshots, and parse offline replays."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from parliament_sitting import ParliamentSitting


class HansardAPI:
    BASE_URL = "https://sprs.parl.gov.sg/search/getHansardReport/"

    def __init__(self):
        self.session = requests.Session()
        # This POST endpoint is a read-only report lookup.
        retry = Retry(total=2, backoff_factor=0.5, allowed_methods={'POST'},
                      status_forcelist=(429, 500, 502, 503, 504),
                      respect_retry_after_header=False)
        self.session.mount('https://', HTTPAdapter(max_retries=retry))

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
