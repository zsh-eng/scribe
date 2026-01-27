import re

from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Set
from util import parse_mp_name, extract_name_from_speaker_text, clean_html_for_display, strip_all_html, extract_name_from_br_text

# OA: Oral Answer to Oral Question
# WANA: Written Answer to Oral Question not answered by end of Question Time
# WA: Written Answer
# OS: Oral Statement
# BP: Bill
# WS: Written Statement
# BI: Bill 
QUESTION_SECTION_TYPES = {'OA', 'WA', 'WANA'}


class MP:
    def __init__(self, name: str, constituency: str, appointment: str = None):
        self.name = name
        self.constituency = constituency
        self.appointment = appointment
    
    def get_details(self):
        return (self.name, self.constituency, self.appointment)

    def __repr__(self):
        return f"MP ({self.name}, {self.constituency}, {self.appointment})"


class ParliamentSession:
    metadata: dict
    present_members: List[MP]
    absent_members: List[MP]
    sections: List[Dict]

    def __init__(self, date: str):
        self.metadata = {"date": date, "sitting_no": None, "parliament": None, "session_no": None, "volume_no": None}
        self.present_members = []
        self.absent_members = []
        self.sections = []
        self._mp_name_index: Dict[str, MP] = {}  # Cache for name lookups

    def set_metadata(self, metadata: Dict):
        self.metadata["sitting_no"] = metadata["sitting_no"]
        self.metadata["parliament"] = metadata["parliament"]
        self.metadata["session_no"] = metadata["session_no"]
        self.metadata["volume_no"] = metadata["volume_no"]

    def set_attendance(self, attendanceList: List[Dict]):
        present = filter(lambda x: x['attendance'], attendanceList)
        absent = filter(lambda x: not x['attendance'], attendanceList)
        self.present_members = list(map(lambda x: MP(*parse_mp_name(x['mpName'])), present))
        self.absent_members = list(map(lambda x: MP(*parse_mp_name(x['mpName'])), absent))
        
        # Build name index for fast lookups
        self._build_name_index()
    
    def _build_name_index(self):
        """Build an index mapping name variations to MP objects."""
        self._mp_name_index = {}
        
        all_members = self.present_members + self.absent_members
        for mp in all_members:
            # Index by full name (lowercase for case-insensitive matching)
            self._mp_name_index[mp.name.lower()] = mp
            
            # Also index by last name for partial matching
            name_parts = mp.name.split()
            if len(name_parts) > 1:
                # Last name
                self._mp_name_index[name_parts[-1].lower()] = mp
                # First + Last name
                if len(name_parts) > 2:
                    self._mp_name_index[f"{name_parts[0]} {name_parts[-1]}".lower()] = mp

    def match_speaker(self, speaker_text: str) -> Optional[MP]:
        """
        Match a speaker text from HTML to a known MP.
        """
        name = extract_name_from_speaker_text(speaker_text)
        if not name:
            return None
        
        # Special case: Speaker
        if name == "Speaker":
            # Find the MP with appointment="Speaker"
            for mp in self.present_members:
                if mp.appointment == "Speaker":
                    return mp
            return None
        
        name_lower = name.lower()
        
        # Try exact match first
        if name_lower in self._mp_name_index:
            return self._mp_name_index[name_lower]
        
        # Try substring matching - check if the extracted name is contained in any MP name
        for mp_name_lower, mp in self._mp_name_index.items():
            # Check if extracted name contains the MP name or vice versa
            if name_lower in mp.name.lower() or mp.name.lower() in name_lower:
                return mp
        
        # No match found - could be external speaker or parsing issue
        return None

    def set_attendance_from_html(self, html_content: str):
        """Parse attendance from 'PRESENT:' and 'ABSENT:' sections in HTML."""
        
        # Split by <br> tags (case insensitive)
        lines = re.split(r'<(?:br|BR)\s*/?>', html_content)
        
        current_list = None  # None, 'present', 'absent'
        present_mps = []
        absent_mps = []
        
        for line in lines:
            text = strip_all_html(line).strip()
            # Clean up weird whitespace
            text = re.sub(r'\s+', ' ', text)
            
            if not text:
                continue
            
            # Detect section headers
            if 'PRESENT:' in text:
                current_list = 'present'
                continue
            elif 'ABSENT:' in text:
                current_list = 'absent'
                continue
            elif 'PERMISSION TO MEMBERS TO BE ABSENT' in text:
                # End of attendance list usually
                break
                
            # If we are in a list, try to parse MP details
            if current_list:
                # Filter out obvious non-MP lines
                if len(text) < 5 or text.startswith('Column:'):
                    continue
                    
                mp_details = extract_name_from_br_text(text)
                if mp_details:
                    name, constituency, appointment = mp_details
                    # Sanity check: name should shouldn't constitute a sentence
                    if len(name.split()) > 10:
                        continue
                        
                    mp = MP(name, constituency, appointment)
                    
                    if current_list == 'present':
                        present_mps.append(mp)
                    else:
                        absent_mps.append(mp)
        
        self.present_members = present_mps
        self.absent_members = absent_mps
        self._build_name_index()

    def _extract_speakers_from_html(self, html_content: str) -> Set[str]:
        """Extract speaker text from <strong> or <b> tags in HTML."""
        speakers = set()
        # Pattern for new format: <strong>Name</strong>
        pattern_strong = r'<strong>\s*(.+?)\s*</strong>'
        # Pattern for old format: <b>Name</b>
        pattern_bold = r'<b>\s*(.+?)\s*</b>'
        
        for pattern in [pattern_strong, pattern_bold]:
            matches = re.finditer(pattern, html_content)
            for match in matches:
                speaker = match.group(1).strip()
                speaker = speaker.replace('&nbsp;', ' ')
                speaker = re.sub(r'\s+', ' ', speaker)
                # Remove trailing colon often found in old format e.g. "<b>Name:</b>"
                speaker = re.sub(r':$', '', speaker)
                
                if speaker and len(speaker) > 1:
                    speakers.add(speaker)
        
        return speakers

    def set_sections(self, raw_sections: List[Dict]):
        """
        Parse raw section data and store as Section objects with matched speakers.
        """
        for idx, section in enumerate(raw_sections):
            section_type = section.get('sectionType')
            if section_type not in QUESTION_SECTION_TYPES:
                continue
            
            title = section.get('title', 'Untitled')
            content_html = section.get('content', '')
            if not content_html:
                continue
            
            # Extract and match speakers
            raw_speakers = self._extract_speakers_from_html(content_html)
            matched_speakers = []
            
            for speaker_text in raw_speakers:
                mp = self.match_speaker(speaker_text)
                if mp:
                    # Avoid duplicates and Speaker (who is not involved in PQs)
                    if mp not in matched_speakers and mp.appointment != "Speaker":
                        matched_speakers.append(mp)
            
            # Clean content
            content_display = clean_html_for_display(content_html)
            content_plain = strip_all_html(content_html)
            
            self.sections.append({
                "section_type": section_type,
                "title": title,
                "speakers": matched_speakers,
                "content_html": content_display,
                "content_plain": content_plain,
                "order": idx
            })

    def get_sections(self):
        return self.sections
    
    def get_metadata(self):
        return self.metadata
    
    def print_attendance(self):
        print("Attendance for session on", self.date)
        print("Present Members:")
        for mp in self.present_members:
            print(mp.get_details())
        print("Absent Members:")
        for mp in self.absent_members:
            print(mp.get_details())

    def print_sections(self):
        print(f"\nSections for session on {self.metadata['date']}:")
        print(f"Total: {len(self.sections)} question sections\n")
        for section in self.sections:
            print(f"--- {section['section_type']}: {section['title'][:60]}... ---")
            print(f"Speakers ({len(section['speakers'])}):")
            for speaker in section['speakers']:
                print(f"  - {speaker.name} ({speaker.constituency})")
            print()
