import requests
from typing import Dict, Optional
from bs4 import BeautifulSoup
from parliament_session import ParliamentSession

class HansardAPI:
    BASE_URL = "https://sprs.parl.gov.sg/search/getHansardReport/"
    
    def __init__(self):
        self.session = requests.Session()
    
    def fetch_by_date(self, date_str: str) -> Optional[ParliamentSession]:
        # date_str format: 'DD-MM-YYYY' (e.g., '14-01-2026')
        url = f"{self.BASE_URL}?sittingDate={date_str}"
        
        try:
            response = self.session.post(url)
            response.raise_for_status()
            data = response.json()
            if not (data.get('takesSectionVOList') or data.get('htmlFullContent')):
                return None
            
            parliament_session = ParliamentSession(date_str)
            parliament_session.set_metadata(self.get_session_metadata(data))
            
            # Check format type
            if data.get('takesSectionVOList'):
                # New format
                parliament_session.set_attendance(data['attendanceList'])
                parliament_session.set_sections(data['takesSectionVOList'])
            
            
            return parliament_session
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {date_str}: {e}")
            return None
    
    def get_session_metadata(self, raw_data: Dict) -> Dict:
        if 'takesSectionVOList' in raw_data and raw_data['takesSectionVOList']:
            metadata = raw_data.get('metadata', {})
            return {
                'date': metadata.get('sittingDate'),
                'sitting_no': metadata.get('sittingNO'),
                'parliament': metadata.get('parlimentNO'),
                'session_no': metadata.get('sessionNO'),
                'volume_no': metadata.get('volumeNO'),
                'format': 'new'
            }
        else:
            raise ValueError("Unknown format")
    

if __name__ == '__main__':
    api = HansardAPI()
    
    # Test new format
    print("=" * 60)
    print("Testing NEW format (22-09-2025)")
    print("=" * 60)
    session_new = api.fetch_by_date('22-09-2025')
    
    if session_new:
        session_new.print_sections()
