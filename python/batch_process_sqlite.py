"""
Batch processor for ingesting Hansard data into SQLite.
Synchronous version - no async/await, no network DB latency.
"""

import logging
import sys
from datetime import datetime, timedelta

from db_sqlite import (
    get_connection,
    find_existing_section,
    add_section_speaker,
    add_sitting_attendance,
    close_connection,
    create_or_update_sitting,
    create_section,
    find_ministry_by_acronym,
    create_bill,
    find_bill_for_second_reading,
    find_or_create_member,
    get_bill_count,
    get_member_count,
    get_section_count,
    get_sitting_count,
    init_db,
)
from hansard_api import HansardAPI
from parliament_sitting import BILL_TYPES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

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


def process_speaker(section_id, speaker):
    """Process a single speaker for a section."""
    member_id = find_or_create_member(speaker.name)
    add_section_speaker(
        section_id=section_id,
        member_id=member_id,
        constituency=getattr(speaker, "constituency", None),
        designation=getattr(speaker, "appointment", None),
    )


def process_section(sitting_id, idx, section, date_str, existing=None):
    """Process a single section and its speakers."""
    if existing is not None and existing['summary'] and existing['content_plain'] != section['content_plain']:
        logger.warning("Transcript changed for %s; retaining existing summary for explicit review", existing['id'])
    # Adjournment motions are raised by individual MPs on any topic;
    # the answering minister is incidental, so skip ministry tagging.
    if section.get("category") == "adjournment_motion":
        ministry_id = None
        ministry_acronym = None
    elif section.get("category") == "motion":
        ministry_acronym = detect_ministry_from_title(section.get("title", ""))
        if not ministry_acronym:
            ministry_acronym = detect_ministry_from_content(section.get("content_plain", ""))
        ministry_id = (
            find_ministry_by_acronym(ministry_acronym) if ministry_acronym else None
        )
    else:
        ministry_acronym = detect_ministry(section)
        ministry_id = (
            find_ministry_by_acronym(ministry_acronym) if ministry_acronym else None
        )

    bill_id = existing['bill_id'] if existing is not None else None
    section_type = section["section_type"]

    # Handle bill sections
    if existing is None and section_type == "BI":
        bill_id = create_bill(
            title=section["title"],
            ministry_id=ministry_id,
            first_reading_date=date_str,
            first_reading_sitting_id=sitting_id,
        )
    elif existing is None and section_type == "BP":
        bill_id = find_bill_for_second_reading(
            title=section["title"],
            ministry_id=ministry_id,
            reading_date=date_str,
        )

    # Create section
    section_id = create_section(
        sitting_id=sitting_id,
        ministry_id=ministry_id,
        bill_id=bill_id,
        category=section.get("category", "other"),
        section_type=section_type,
        title=section["title"],
        content_html=section["content_html"],
        content_plain=section["content_plain"],
        section_order=section["order"],
        source_url=section.get("source_url"),
        existing=existing,
        source_ids=section.get("source_ids", []),
    )

    # Process speakers
    for speaker in section["speakers"]:
        process_speaker(section_id, speaker)

    return section_id


def process_attendance(sitting_id, mp, present):
    """Process attendance for a single MP."""
    member_id = find_or_create_member(mp.name)
    add_sitting_attendance(
        sitting_id=sitting_id,
        member_id=member_id,
        present=present,
        constituency=mp.constituency,
        designation=mp.appointment,
    )


def ingest_sitting(date_str: str, source_file=None) -> str | None:
    """
    Fetch and ingest a single sitting into SQLite.
    Returns sitting ID if successful, None otherwise.
    """
    logger.info(f"Processing sitting for {date_str}...")

    # Fetch from Hansard API
    api = HansardAPI()
    try:
        parliament_sitting = api.read_source(date_str, source_file) if source_file else api.fetch_by_date(date_str)
    finally:
        api.session.close()

    if not parliament_sitting:
        logger.info(f"No data found for {date_str}")
        return None

    sections = parliament_sitting.get_sections()
    metadata = parliament_sitting.get_metadata()

    if not sections:
        logger.info(f"No sections found for {date_str}")
        return None

    # Create sitting URL
    sitting_url = f"https://sprs.parl.gov.sg/search/#/fullreport?sittingdate={date_str}"

    conn = get_connection()
    with conn:
        # Create/Update Sitting
        sitting_id = create_or_update_sitting(
            date_str=metadata.get("date"),
            sitting_no=metadata.get("sitting_no"),
            parliament=metadata.get("parliament"),
            session_no=metadata.get("session_no"),
            volume_no=metadata.get("volume_no"),
            format_type=metadata.get("format"),
            url=sitting_url,
        )
        logger.info(f"   Sitting ID: {sitting_id}")

        prior_ids = {row[0] for row in conn.execute('SELECT id FROM sections WHERE sitting_id = ?', (sitting_id,))}
        conn.execute('DELETE FROM sitting_attendance WHERE sitting_id = ?', (sitting_id,))

        # Process attendance
        attendance_count = 0
        for mp in parliament_sitting.present_members:
            process_attendance(sitting_id, mp, True)
            attendance_count += 1

        for mp in parliament_sitting.absent_members:
            process_attendance(sitting_id, mp, False)
            attendance_count += 1

        logger.info(f"   Saved attendance for {attendance_count} members")

        # Process sections — ensure BI (first readings) are processed before BP (second readings)
        # so that bills exist before second reading sections try to find them (same-day case)
        def section_sort_key(item):
            idx, section = item
            st = section.get("section_type", "")
            if st == "BI":
                return (0, idx)  # BI first
            elif st == "BP":
                return (2, idx)  # BP last
            return (1, idx)      # everything else in between

        sorted_sections = sorted(enumerate(sections), key=section_sort_key)
        # Resolve against the old mapping before any source IDs are replaced.
        existing_sections = {idx: find_existing_section(sitting_id, section)
                             for idx, section in sorted_sections}

        logger.info(f"   Processing {len(sections)} sections...")
        section_ids = []

        for idx, section in sorted_sections:
            section_id = process_section(sitting_id, idx, section, metadata.get("date"), existing_sections[idx])
            if section_id in section_ids:
                raise ValueError("Source sections now split an existing group; review before reimporting")
            section_ids.append(section_id)

            # Log progress every 10 sections
            if (idx + 1) % 10 == 0:
                logger.info(f"     Processed {idx + 1}/{len(sections)} sections")

        if prior_ids - set(section_ids):
            raise ValueError("Existing sections are absent from the import; review source changes before reimporting")

        logger.info(f"   Processed {len(section_ids)} sections for {date_str}")
        return sitting_id


def batch_process(start_date_str: str, end_date_str: str):
    """
    Process all sittings in a date range.
    """
    start_date = datetime.strptime(start_date_str, "%d-%m-%Y")
    end_date = datetime.strptime(end_date_str, "%d-%m-%Y")
    if start_date > end_date:
        raise ValueError("Start date must be on or before end date")
    init_db()

    # Generate all dates in range
    dates = []
    curr = start_date
    while curr <= end_date:
        dates.append(curr.strftime("%d-%m-%Y"))
        curr += timedelta(days=1)

    logger.info(
        f"Checking date range: {start_date_str} to {end_date_str} ({len(dates)} days)"
    )

    ingested_sittings = []

    try:
        for date_str in dates:
            sitting_id = ingest_sitting(date_str)
            if sitting_id:
                ingested_sittings.append(sitting_id)
    except Exception:
        close_connection()
        raise

    # Print summary
    logger.info("\n" + "=" * 50)
    logger.info("Batch processing complete!")
    logger.info(f"Sittings ingested: {len(ingested_sittings)}")
    logger.info(f"\nDatabase stats:")
    logger.info(f"  Total sittings: {get_sitting_count()}")
    logger.info(f"  Total members: {get_member_count()}")
    logger.info(f"  Total sections: {get_section_count()}")
    logger.info(f"  Total bills: {get_bill_count()}")

    close_connection()


def show_stats():
    """Show current database statistics."""
    init_db()
    print(f"\nDatabase stats:")
    print(f"  Sittings: {get_sitting_count()}")
    print(f"  Members: {get_member_count()}")
    print(f"  Sections: {get_section_count()}")
    print(f"  Bills: {get_bill_count()}")
    close_connection()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('start_date', nargs='?')
    parser.add_argument('end_date', nargs='?')
    parser.add_argument('--stats', action='store_true')
    parser.add_argument('--source-file', help='Replay a saved Hansard JSON response for one date')
    args = parser.parse_args()
    if args.stats:
        show_stats()
    elif not args.start_date:
        parser.error('start_date is required')
    elif args.source_file:
        if args.end_date:
            parser.error('--source-file accepts one date only')
        init_db()
        try:
            ingest_sitting(args.start_date, args.source_file)
        finally:
            close_connection()
    else:
        batch_process(args.start_date, args.end_date or args.start_date)
