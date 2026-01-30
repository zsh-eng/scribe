import re

from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Set
from util import parse_mp_name, extract_name_from_speaker_text, clean_html_for_display, strip_all_html, extract_name_from_br_text

# OA: Oral Answer to Oral Question
# WANA: Written Answer to Oral Question not answered by end of Question Time
# WA: Written Answer
# OS: Oral Statement (Ministerial Statements, etc.)
# WS: Written Statement
# BP: Second Reading of Bill
# BI: First Reading of Bill 
QUESTION_SECTION_TYPES = {'OA', 'WA', 'WANA'}
BILL_TYPES = {'BI', 'BP'}
STATEMENT_TYPES = {'OS', 'WS'}

ALL_VALID_TYPES = QUESTION_SECTION_TYPES | BILL_TYPES | STATEMENT_TYPES

# Minimum content length to filter out procedural/short sections
# This excludes things like "Motion to extend sitting" or "Adjournment of debate"
MIN_CONTENT_LENGTH = 500

# Keywords that indicate procedural content (not substantive)
PROCEDURAL_KEYWORDS = [
    'motion to adjourn',
    'adjournment of debate',
    'time extension',
    'leave of absence',
    'papers presented',
    'papers laid',
    'permission to members',
]

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
        # Pattern for format: <strong style="...">Name</strong> or <strong>Name</strong>
        pattern_strong = r'<strong[^>]*>\s*(.+?)\s*</strong>'
        # Pattern for old format: <b>Name</b>
        pattern_bold = r'<b[^>]*>\s*(.+?)\s*</b>'
        
        for pattern in [pattern_strong, pattern_bold]:
            matches = re.finditer(pattern, html_content, re.IGNORECASE)
            for match in matches:
                speaker = match.group(1).strip()
                # Remove nested tags if any (e.g. <span> inside strong)
                speaker = re.sub(r'<[^>]+>', '', speaker)
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
        Processes questions (OA, WA, WANA), bills (BI, BP), and statements (OS, WS).
        Filters out procedural/short content for statements.
        """
        for idx, section in enumerate(raw_sections):
            section_type = section.get('sectionType')
            if section_type not in ALL_VALID_TYPES:
                continue
            
            title = section.get('title', 'Untitled')
            # Determine category early for logic checks
            report_type = section.get('reportType', '')
            
            if 'clarification' in title.lower():
                category = 'clarification'
            elif report_type == 'Matter Raised On Adjournment Motion':
                category = 'adjournment_motion'
            elif section_type in QUESTION_SECTION_TYPES:
                category = 'question'
            elif section_type in BILL_TYPES:
                category = 'bill'
            elif section_type in STATEMENT_TYPES:
                category = 'motion' # Renamed from statement to motion
            else:
                category = 'other'

            content_html = section.get('content', '')
            if not content_html:
                continue
            
            # Clean content
            content_display = clean_html_for_display(content_html)
            content_plain = strip_all_html(content_html)
            
            # For statements (OS, WS), filter out procedural/short content
            if section_type in STATEMENT_TYPES:
                # Check minimum length (except if it's explicitly adjournment motion)
                is_adjournment = category == 'adjournment_motion'
                
                if not is_adjournment and len(content_plain) < MIN_CONTENT_LENGTH:
                    continue
                
                # Check for procedural keywords in title
                title_lower = title.lower()
                extended_keywords = PROCEDURAL_KEYWORDS + [
                    'administration of oaths',
                    'personal explanation',
                    'time limit',
                    'commencement of business',
                    'order of business',
                    'adjournment' # careful with adjournment *motion* vs adjournment of sitting
                ]
                
                # Exclude if meaningful
                if not is_adjournment and any(keyword in title_lower for keyword in extended_keywords):
                     continue
            
            # Extract and match speakers
            raw_speakers = self._extract_speakers_from_html(content_html)
            matched_speakers = []
            
            for speaker_text in raw_speakers:
                mp = self.match_speaker(speaker_text)
                if mp:
                    # Avoid duplicates and Speaker (who is not involved in PQs)
                    if mp in matched_speakers or mp.appointment == "Speaker":
                        continue
                        
                    # EXCLUSION: For Adjournment Motions, exclude Leader/Deputy Leader of the House
                    # because they only say "General/Procedural" lines like "I beg to move".
                    if category == 'adjournment_motion':
                        appt_lower = (mp.appointment or "").lower()
                        if "leader of the house" in appt_lower:
                            continue
                            
                    matched_speakers.append(mp)
            
            # Construct source URL
            section_id = section.get('sectionId')
            source_url = f"https://sprs.parl.gov.sg/search/sprs3topic?reportid={section_id}" if section_id else None
            
            # Determine category
            report_type = section.get('reportType', '')
            
            if 'clarification' in title.lower():
                category = 'clarification'
            elif report_type == 'Matter Raised On Adjournment Motion':
                category = 'adjournment_motion'
            elif section_type in QUESTION_SECTION_TYPES:
                category = 'question'
            elif section_type in BILL_TYPES:
                category = 'bill'
            elif section_type in STATEMENT_TYPES:
                category = 'motion' # Renamed from statement to motion
            else:
                category = 'other'
            
            # MERGING LOGIC: Check if we already have a section with this title
            existing_index = next((i for i, s in enumerate(self.sections) if s['title'] == title), None)
            
            if existing_index is not None:
                # Merge into existing section
                existing_section = self.sections[existing_index]
                existing_section['content_html'] += "<br><hr><br>" + content_display
                existing_section['content_plain'] += "\n\n" + content_plain
                
                # Merge speakers (avoid duplicates)
                current_speaker_names = {s.name for s in existing_section['speakers']}
                for mp in matched_speakers:
                    if mp.name not in current_speaker_names:
                        existing_section['speakers'].append(mp)
                        current_speaker_names.add(mp.name)
                        
                # Keep the original order/id/url (or update if needed, but keeping separate is complex)
                # We assume the first occurrence is the main one.
            else:
                # Add new section
                self.sections.append({
                    "section_type": section_type,
                    "category": category,
                    "title": title,
                    "speakers": matched_speakers,
                    "content_html": content_display,
                    "content_plain": content_plain,
                    "order": idx,
                    "source_url": source_url
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
