"""Pure ministry classification rules for parsed Hansard sections."""

# Maps ministerial designations to ministry acronyms.
# Includes "Minister for X", "Minister of State for X", and
# "Parliamentary Secretary for X" variants so that all designation
# forms (including "Senior Minister of State for X") are matched.
_MINISTRY_TOPICS = {
    "Culture, Community and Youth": "MCCY",
    "Defence": "MINDEF",
    "Digital Development and Information": "MDDI",
    "Education": "MOE",
    "Finance": "MOF",
    "Foreign Affairs": "MFA",
    "Health": "MOH",
    "Home Affairs": "MHA",
    "Law": "MINLAW",
    "Manpower": "MOM",
    "National Development": "MND",
    "Social and Family Development": "MSF",
    "Sustainability and the Environment": "MSE",
    "Trade and Industry": "MTI",
    "Transport": "MOT",
}

DESIGNATION_TO_MINISTRY = {
    "Prime Minister": "PMO",
    "Minister, Prime Minister's Office": "PMO",
    "Minister of State, Prime Minister's Office": "PMO",
}
for _topic, _acronym in _MINISTRY_TOPICS.items():
    DESIGNATION_TO_MINISTRY[f"Minister for {_topic}"] = _acronym
    DESIGNATION_TO_MINISTRY[f"Minister of State for {_topic}"] = _acronym
    DESIGNATION_TO_MINISTRY[f"Parliamentary Secretary for {_topic}"] = _acronym


FULL_NAME_TO_MINISTRY = {
    "Prime Minister's Office": "PMO",
    "Ministry of Culture, Community and Youth": "MCCY",
    "Ministry of Defence": "MINDEF",
    "Ministry of Digital Development and Information": "MDDI",
    "Ministry of Education": "MOE",
    "Ministry of Finance": "MOF",
    "Ministry of Foreign Affairs": "MFA",
    "Ministry of Health": "MOH",
    "Ministry of Home Affairs": "MHA",
    "Ministry of Law": "MINLAW",
    "Ministry of Manpower": "MOM",
    "Ministry of National Development": "MND",
    "Ministry of Social and Family Development": "MSF",
    "Ministry of Sustainability and the Environment": "MSE",
    "Ministry of Trade and Industry": "MTI",
    "Ministry of Transport": "MOT",
}

def detect_ministry_from_designation(designation):
    """Extract ministry acronym from a ministerial designation.

    Handles variants like "Minister of State for Education",
    "Senior Minister of State for Health", "Parliamentary Secretary for Transport", etc.
    """
    if not designation:
        return None
    designation_lower = designation.lower()
    for keyword, acronym in DESIGNATION_TO_MINISTRY.items():
        if keyword.lower() in designation_lower:
            return acronym
    return None


def detect_ministry_from_content(content_plain):
    """Detect ministry from question preamble content."""
    if not content_plain:
        return None

    preamble = content_plain[:1000]

    # Check specific ministry designations first, PMO last so that
    # "Prime Minister and Minister for Finance" matches MOF not PMO
    pmo_match = False
    for designation, acronym in DESIGNATION_TO_MINISTRY.items():
        if designation in preamble:
            if acronym == "PMO":
                pmo_match = True
            else:
                return acronym

    if pmo_match:
        return "PMO"

    return None

def detect_ministry_from_speakers(speakers):
    """Detect ministry from speaker appointments."""
    for speaker in speakers:
        designation = getattr(speaker, "appointment", None)
        if designation and "minister" in designation.lower():
            ministry = detect_ministry_from_designation(designation)
            if ministry:
                return ministry
    return None

def detect_ministry_from_title(title):
    """Detect ministry from section title."""
    for name, acronym in FULL_NAME_TO_MINISTRY.items():
        if name in title:
            return acronym
    return None

def detect_ministry(section):
    """Detect ministry for a section using content and speaker info."""
    # Try content-based detection first (more accurate)
    ministry = detect_ministry_from_content(section.get("content_plain", ""))
    if ministry:
        return ministry

    # Fallback to speaker designation
    return detect_ministry_from_speakers(section.get("speakers", []))
