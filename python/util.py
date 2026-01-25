import re

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

SALUTATIONS = [
    "Assoc Prof Dr",
    "Assoc Prof",
    "Prof",
    "Dr",
    "Mrs",
    "Miss",
    "Ms",
    "Mr",
]

def parse_mp_name(mp_name_str: str) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Parse an MP name string from the hansard report JSON.
    
    Returns:
        Tuple of (name, constituency, appointment) where:
        - name: Name without salutation
        - constituency: Constituency name, or "Nominated Member"/"Non-Constituency Member"
        - appointment: Ministerial or parliamentary appointment if applicable
    """
    text = mp_name_str.strip()
    
    # Speaker format: "Mr SPEAKER (Mr Seah Kian Peng (Marine Parade-Braddell Heights))."
    salutation_pattern = '|'.join(re.escape(s) for s in SALUTATIONS)
    speaker_match = re.match(rf'^(?:{salutation_pattern})\s+SPEAKER\s*\((.+)\)\s*\.?\s*$', text)
    if speaker_match:
        inner = speaker_match.group(1)
        name, constituency, _ = parse_mp_name(inner)
        return (name, constituency, "Speaker")
    
    # Remove trailing period and whitespace
    text = re.sub(r'\.\s*$', '', text)
    
    # Remove salutation
    name_without_salutation = text
    for salutation in SALUTATIONS:
        pattern = f'^{re.escape(salutation)}\\s+'
        if re.match(pattern, text, re.IGNORECASE):
            name_without_salutation = re.sub(pattern, '', text, count=1, flags=re.IGNORECASE)
            break
    
    # Pattern: Name (Constituency or Member Type), Appointment (if applicable)
    main_pattern = re.match(r'^(.+?)\s*\(([^)]+)\)(?:\s*,\s*(.+))?$', name_without_salutation)
    
    if main_pattern:
        name = main_pattern.group(1).strip()
        constituency = main_pattern.group(2).strip()
        appointment = main_pattern.group(3).strip() if main_pattern.group(3) else None
        return (name, constituency, appointment)
    
    # Fallback: couldn't parse, just return the name as-is
    return (name_without_salutation, None, None)


def extract_name_from_speaker_text(speaker_text: str) -> Optional[str]:
    """
    Extract the MP name from a speaker text found in HTML <strong> tags.
    
    Handles various formats:
    - "Ms Jessica Tan Soon Neo" -> "Jessica Tan Soon Neo"
    - "Ms Jessica Tan Soon Neo (East Coast)" -> "Jessica Tan Soon Neo"
    - "The Senior Minister of State for National Development (Ms Sun Xueling) (for the Minister...)" -> "Sun Xueling"
    - "Mr Speaker" -> "Speaker" (special case)
    - "Mr Alvin Tan" -> "Alvin Tan"
    
    Returns:
        The extracted name without salutation, or None if parsing fails.
    """
    text = speaker_text.strip()
    
    # Handle empty or very short text
    if not text or len(text) < 2:
        return None
    
    # Special case: "Mr Speaker" or just "Speaker"
    if re.match(r'^(Mr\s+)?Speaker$', text, re.IGNORECASE):
        return "Speaker"
    
    salutation_pattern = '|'.join(re.escape(s) for s in SALUTATIONS)
    
    # Pattern 1: Role format - "The ... (Salutation Name) (for ...)"
    # e.g. "The Senior Minister of State for National Development (Ms Sun Xueling) (for the Minister...)"
    role_pattern = re.match(
        rf'^The\s+.+?\s*\(({salutation_pattern})\s+([^)]+)\)(?:\s*\(for\s+.+\))?$',
        text
    )
    if role_pattern:
        return role_pattern.group(2).strip()
    
    # Pattern 2: Simple role format - "The ... (Salutation Name):"
    # e.g. "The Minister for Manpower (Dr Tan See Leng):"
    simple_role_pattern = re.match(
        rf'^The\s+.+?\s*\(({salutation_pattern})\s+([^)]+)\)\s*:?$',
        text
    )
    if simple_role_pattern:
        return simple_role_pattern.group(2).strip()
    
    # Pattern 3: Standard format with salutation - "Salutation Name" or "Salutation Name (Constituency)"
    # Use parse_mp_name for this
    name, constituency, appointment = parse_mp_name(text)
    if name and name != text:  # Successfully parsed
        return name
    
    # Fallback: just remove salutation if present
    for salutation in SALUTATIONS:
        pattern = f'^{re.escape(salutation)}\\s+'
        if re.match(pattern, text, re.IGNORECASE):
            return re.sub(pattern, '', text, count=1, flags=re.IGNORECASE).strip()
    
    return None


def clean_html_for_display(html_content: str) -> str:
    # Keep speakers' names in bold
    if not html_content:
        return ""
    
    # Replace common HTML entities
    clean = html_content.replace('&nbsp;', ' ')
    clean = clean.replace('â€™', "'")
    clean = clean.replace('â€"', '—')
    clean = clean.replace('&amp;', '&')
    clean = clean.replace('&#39;', "'")
    clean = clean.replace('&quot;', '"')
    
    # Keep <p>, <strong>, <br> tags for formatting
    # Remove other tags
    soup = BeautifulSoup(clean, 'html.parser')
    
    # Convert to formatted text preserving structure
    # This keeps speaker names bold
    return str(soup)

def strip_all_html(html: str) -> str:
    if not html:
        return ""
    
    clean = re.sub(r'<[^>]+>', '', html)
    clean = clean.replace('&nbsp;', ' ')
    clean = clean.replace('â€™', "'")
    clean = clean.replace('â€"', '—')
    clean = clean.replace('&amp;', '&')
    clean = clean.replace('&#39;', "'")
    clean = clean.replace('&quot;', '"')
    clean = re.sub(r'\s+', ' ', clean)
    
    return clean.strip()