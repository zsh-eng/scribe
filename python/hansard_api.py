# python/hansard_api.py (UPDATED - Extract metadata from HTML)
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import re
from bs4 import BeautifulSoup
from parliament_session import ParliamentSession

class HansardAPI:
    BASE_URL = "https://sprs.parl.gov.sg/search/getHansardReport/"
    
    # OA: Oral Answers to Oral Questions
    # OS: Oral Statement
    # BP: Bill
    # WANA: Written Answers to Oral Questions not answered by end of Question Time
    # WA: Written Answer
    # WS: Written Statement
    # BI: 
    QUESTION_SECTION_TYPES = {'OA', 'WA', 'WANA'}
    
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
            parliament_session.set_attendance(data['attendanceList'])
            
            # Parse sections if available (new format)
            if data.get('takesSectionVOList'):
                parliament_session.set_sections(data['takesSectionVOList'])
            
            return parliament_session
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {date_str}: {e}")
            return None
    
    def detect_format(self, raw_data: Dict) -> str:
        if 'takesSectionVOList' in raw_data and raw_data['takesSectionVOList']:
            return 'new'
        elif 'htmlFullContent' in raw_data and raw_data['htmlFullContent']:
            return 'old'
        return 'unknown'
    
    def extract_metadata_from_html(self, html: str) -> Dict:
        # Extract metadata from old format HTML
        soup = BeautifulSoup(html, 'html.parser')
        
        metadata = {
            'date': None,
            'sitting_no': None,
            'parliament': None,
            'session_no': None,
            'volume_no': None
        }
        
        # Method 1: Look for meta tags
        parl_no = soup.find('meta', {'name': 'Parl_No'})
        sess_no = soup.find('meta', {'name': 'Sess_No'})
        vol_no = soup.find('meta', {'name': 'Vol_No'})
        sit_no = soup.find('meta', {'name': 'Sit_No'})
        sit_date = soup.find('meta', {'name': 'Sit_Date'})
        
        if parl_no:
            metadata['parliament'] = int(parl_no.get('content'))
        if sess_no:
            metadata['session_no'] = int(sess_no.get('content'))
        if vol_no:
            metadata['volume_no'] = int(vol_no.get('content'))
        if sit_no:
            metadata['sitting_no'] = int(sit_no.get('content'))
        if sit_date:
            # Format is YYYY-MM-DD, convert to DD-MM-YYYY
            date_str = sit_date.get('content')
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                metadata['date'] = dt.strftime('%d-%m-%Y')
            except:
                pass
        
        # Method 2: Look in table (backup method)
        if not metadata['parliament']:
            for row in soup.find_all('tr'):
                cells = row.find_all('td')
                if len(cells) == 2:
                    label = cells[0].get_text(strip=True)
                    value = cells[1].get_text(strip=True)
                    
                    if 'Parliament No' in label:
                        try:
                            metadata['parliament'] = int(value)
                        except:
                            pass
                    elif 'Session No' in label:
                        try:
                            metadata['session_no'] = int(value)
                        except:
                            pass
                    elif 'Volume No' in label:
                        try:
                            metadata['volume_no'] = int(value)
                        except:
                            pass
                    elif 'Sitting No' in label:
                        try:
                            metadata['sitting_no'] = int(value)
                        except:
                            pass
                    elif 'Sitting Date' in label:
                        # Format is DD-MM-YYYY
                        metadata['date'] = value
        
        return metadata
    
    def get_session_metadata(self, raw_data: Dict) -> Dict:
        format_type = self.detect_format(raw_data)
        
        if format_type == 'new':
            metadata = raw_data.get('metadata', {})
            return {
                'date': metadata.get('sittingDate'),
                'sitting_no': metadata.get('sittingNO'),
                'parliament': metadata.get('parlimentNO'),
                'session_no': metadata.get('sessionNO'),
                'volume_no': metadata.get('volumeNO'),
                'format': 'new'
            }
        else:  # old format
            html = raw_data.get('htmlFullContent', '')
            html_metadata = self.extract_metadata_from_html(html)
            
            return {
                'date': html_metadata.get('date'),
                'sitting_no': html_metadata.get('sitting_no'),
                'parliament': html_metadata.get('parliament'),
                'session_no': html_metadata.get('session_no'),
                'volume_no': html_metadata.get('volume_no'),
                'format': 'old'
            }
    
    def extract_speakers_from_html(self, html_content: str) -> Set[str]:
        # Speakers are in <strong> tags
        speakers = set()
        pattern = r'<strong>\s*(.+?)\s*</strong>'
        matches = re.finditer(pattern, html_content)
        
        for match in matches:
            speaker = match.group(1).strip()
            # Clean up common HTML entities
            speaker = speaker.replace('&nbsp;', ' ')
            speaker = re.sub(r'\s+', ' ', speaker)
            if speaker:
                speakers.add(speaker)
        
        return speakers
    
    def parse_sections_new_format(self, raw_data: Dict) -> List[Dict]:
        """Parse new format - Keep entire sections intact"""
        sections = []
        section_list = raw_data.get('takesSectionVOList', [])
        
        for idx, section in enumerate(section_list):
            section_type = section.get('sectionType')
            if section_type not in self.QUESTION_SECTION_TYPES:
                continue
            
            title = section.get('title', 'Untitled')
            content_html = section.get('content', '')
            if not content_html:
                continue
            
            speakers = self.extract_speakers_from_html(content_html)
            
            # Clean content for display (preserves speaker bold formatting)
            content_display = self.clean_html_for_display(content_html)
            
            # Plain text for AI processing
            content_plain = self.strip_all_html(content_html)
            
            sections.append({
                'section_type': section_type,
                'section_title': title,
                'content_html': content_display,  # For display with formatting
                'content_plain': content_plain,   # For AI/search
                'speakers': list(speakers),       # All speakers in this section
                'order': idx
            })
        
        return sections
    
    def parse_sections_old_format(self, raw_data: Dict) -> List[Dict]:
        """
        Parse old format - Extract question/answer sections
        This is much harder as old format doesn't have clear section boundaries
        """
        html = raw_data.get('htmlFullContent', '')
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        sections = []
        
        # In old format, look for section markers or group by topic
        # This is a basic implementation - may need refinement
        
        current_section_content = []
        current_speakers = set()
        
        for element in soup.find_all(['p', 'br', 'div']):
            text = element.get_text(strip=True)
            
            if not text or len(text) < 10:
                continue
            
            # Extract speaker if present
            speaker_match = re.search(r'^([A-Z][^:]+?):\s*', text)
            if speaker_match:
                speaker = speaker_match.group(1).strip()
                if any(title in speaker for title in ['Minister', 'Mr', 'Ms', 'Dr', 'Assoc', 'Prof']):
                    current_speakers.add(speaker)
            
            # Add to current section
            current_section_content.append(str(element))
            
            # Simple heuristic: break into sections every ~10 paragraphs
            # or when we see "Mr Speaker" (indicates topic change)
            if len(current_section_content) >= 10 or 'Mr Speaker' in text:
                if current_section_content and current_speakers:
                    html_content = ''.join(current_section_content)
                    
                    sections.append({
                        'section_type': 'DEBATE',
                        'section_title': 'Parliamentary Question',
                        'content_html': html_content,
                        'content_plain': self.strip_all_html(html_content),
                        'speakers': list(current_speakers),
                        'order': len(sections)
                    })
                    
                    current_section_content = []
                    current_speakers = set()
        
        # Don't forget last section
        if current_section_content and current_speakers:
            html_content = ''.join(current_section_content)
            sections.append({
                'section_type': 'DEBATE',
                'section_title': 'Parliamentary Question',
                'content_html': html_content,
                'content_plain': self.strip_all_html(html_content),
                'speakers': list(current_speakers),
                'order': len(sections)
            })
        
        return sections
    
    def parse_sections(self, raw_data: Dict) -> List[Dict]:
        """
        Main parser - returns complete sections with all speakers
        """
        format_type = self.detect_format(raw_data)
        
        if format_type == 'new':
            return self.parse_sections_new_format(raw_data)
        elif format_type == 'old':
            return self.parse_sections_old_format(raw_data)
        else:
            print("Warning: Unknown format")
            return []

# Test
if __name__ == '__main__':
    api = HansardAPI()
    
    # Test new format
    print("=" * 60)
    print("Testing NEW format (14-01-2026)")
    print("=" * 60)
    session_new = api.fetch_by_date('14-01-2026')
    
    if session_new:
        session_new.print_sections()
    
    # Test old format
    # print("\n" + "=" * 60)
    # print("Testing OLD format (15-10-2001)")
    # print("=" * 60)
    # data_old = api.fetch_by_date('15-10-2001')
    
    # if data_old:
    #     print(f"Format detected: {api.detect_format(data_old)}")
    #     metadata = api.get_session_metadata(data_old)
    #     print(f"\nMetadata:")
    #     for key, value in metadata.items():
    #         print(f"  {key}: {value}")
        
    #     sections = api.parse_sections(data_old)
    #     print(f"\nFound {len(sections)} sections\n")
        
    #     for idx, section in enumerate(sections[:2]):
    #         print(f"--- Section {idx+1} ---")
    #         print(f"Type: {section['section_type']}")
    #         print(f"Speakers ({len(section['speakers'])}): {', '.join(section['speakers'])}")
    #         print(f"Content: {section['content_plain'][:200]}...")
    #         print()