"""
SQLite database module for Parliament Summarizer.
Synchronous operations using Python's built-in sqlite3.
Write helpers never commit; callers own the transaction.
"""
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

# Default database path (can be overridden via environment variable)
DEFAULT_DB_PATH = Path(__file__).parent.parent / 'data' / 'parliament.db'
DB_PATH = os.getenv('PARLIAMENT_DB_PATH', str(DEFAULT_DB_PATH))

# Global connection (reused for performance)
_conn = None


def get_connection() -> sqlite3.Connection:
    """Get or create a database connection."""
    global _conn
    if _conn is None:
        # Ensure directory exists
        db_path = Path(DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        _conn = sqlite3.connect(DB_PATH)
        _conn.row_factory = sqlite3.Row  # Enable dict-like access
        _conn.execute('PRAGMA foreign_keys = ON')
        _conn.execute('PRAGMA journal_mode = WAL')  # Better concurrent access
    return _conn


def close_connection():
    """Close the database connection."""
    global _conn
    if _conn:
        _conn.close()
        _conn = None


def init_db():
    """Initialize the database with schema."""
    conn = get_connection()
    schema_path = Path(__file__).parent / 'schema.sql'

    with open(schema_path, 'r') as f:
        schema = f.read()

    conn.executescript(schema)
    conn.commit()
    print(f"Database initialized at {DB_PATH}")


def generate_id() -> str:
    """Generate a UUID string for use as primary key."""
    return str(uuid.uuid4())


def parse_date(date_str: str) -> str:
    """Convert DD-MM-YYYY to YYYY-MM-DD (ISO format for SQLite)."""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, '%d-%m-%Y')
        return dt.strftime('%Y-%m-%d')
    except ValueError:
        # Already in ISO format or invalid
        return date_str


def find_or_create_member(name: str) -> str:
    """Find existing member or create new one. Returns member ID."""
    conn = get_connection()
    cursor = conn.cursor()

    name = name.strip()
    # Try to find existing
    cursor.execute('SELECT id FROM members WHERE name = ?', (name,))
    row = cursor.fetchone()

    if row:
        return row['id']

    # Create new
    member_id = generate_id()
    cursor.execute(
        'INSERT INTO members (id, name) VALUES (?, ?)',
        (member_id, name)
    )
    return member_id


def find_ministry_by_acronym(acronym: str) -> str:
    """Find ministry ID by acronym. Returns None if not found."""
    if not acronym:
        return None

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id FROM ministries WHERE acronym = ?', (acronym,))
    row = cursor.fetchone()
    return row['id'] if row else None


def create_bill(title: str, ministry_id: str = None,
                first_reading_date: str = None,
                first_reading_sitting_id: str = None) -> str:
    """Create a new bill record. Called for BI (first reading) sections.
    Each first reading is a unique bill, even if the title matches an existing bill."""
    conn = get_connection()
    cursor = conn.cursor()

    title = title.strip()
    existing = conn.execute(
        'SELECT id FROM bills WHERE title = ? AND first_reading_sitting_id = ?',
        (title, first_reading_sitting_id),
    ).fetchall()
    if len(existing) > 1:
        raise ValueError(f"Ambiguous first reading: {title}; reconcile existing bills first")
    if existing:
        return existing[0]['id']
    bill_id = generate_id()
    cursor.execute(
        '''INSERT INTO bills (id, title, ministry_id, first_reading_date, first_reading_sitting_id)
           VALUES (?, ?, ?, ?, ?)''',
        (bill_id, title, ministry_id, parse_date(first_reading_date), first_reading_sitting_id)
    )
    return bill_id


def find_bill_for_second_reading(title: str, ministry_id: str = None, reading_date: str = None) -> str:
    """Find the most recent bill with this title for a BP (second reading) section.
    Returns the bill with the latest first_reading_date, or creates one if none exists."""
    conn = get_connection()
    cursor = conn.cursor()

    title = title.strip()
    cursor.execute(
        '''SELECT id, first_reading_date FROM bills WHERE title = ?
           AND (first_reading_date IS NULL OR first_reading_date <= ?)
           ORDER BY first_reading_date DESC, id LIMIT 2''',
        (title, parse_date(reading_date) or '9999-12-31')
    )
    rows = cursor.fetchall()
    if len(rows) > 1 and rows[0]['first_reading_date'] == rows[1]['first_reading_date']:
        raise ValueError(f"Ambiguous bill reading: {title}; reconcile existing bills first")
    row = rows[0] if rows else None

    if row:
        bill_id = row['id']
        # Update ministry if not set
        if ministry_id:
            cursor.execute(
                'UPDATE bills SET ministry_id = ? WHERE id = ? AND ministry_id IS NULL',
                (ministry_id, bill_id)
            )
        return bill_id

    # No bill found — create one (BP without a preceding BI)
    bill_id = generate_id()
    cursor.execute(
        '''INSERT INTO bills (id, title, ministry_id)
           VALUES (?, ?, ?)''',
        (bill_id, title, ministry_id)
    )
    return bill_id


def create_or_update_sitting(date_str: str, sitting_no: int = None,
                              parliament: int = None, session_no: int = None,
                              volume_no: int = None, format_type: str = None,
                              url: str = None) -> str:
    """Create or update a sitting. Returns sitting ID."""
    conn = get_connection()
    cursor = conn.cursor()

    iso_date = parse_date(date_str)

    # Check if sitting exists
    cursor.execute('SELECT id FROM sittings WHERE date = ?', (iso_date,))
    row = cursor.fetchone()

    if row:
        sitting_id = row['id']
        # Update existing
        cursor.execute(
            '''UPDATE sittings SET sitting_no = ?, parliament = ?, session_no = ?,
               volume_no = ?, format = ?, url = ? WHERE id = ?''',
            (sitting_no, parliament, session_no, volume_no, format_type, url, sitting_id)
        )
    else:
        # Create new
        sitting_id = generate_id()
        cursor.execute(
            '''INSERT INTO sittings (id, date, sitting_no, parliament, session_no, volume_no, format, url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (sitting_id, iso_date, sitting_no, parliament, session_no, volume_no, format_type, url)
        )

    return sitting_id


def add_sitting_attendance(sitting_id: str, member_id: str, present: bool = True,
                           constituency: str = None, designation: str = None):
    """Add or update sitting attendance record."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        '''INSERT INTO sitting_attendance (sitting_id, member_id, present, constituency, designation)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (sitting_id, member_id) DO UPDATE SET
           present = excluded.present,
           constituency = excluded.constituency,
           designation = excluded.designation''',
        (sitting_id, member_id, 1 if present else 0, constituency, designation)
    )


def find_existing_section(sitting_id, section):
    """Match source IDs first; adopt legacy rows without changing public IDs.

    Multiple matches are a data reconciliation problem, never a dedupe decision.
    """
    conn = get_connection()
    candidates = set()
    for source_id in section.get('source_ids', []):
        rows = conn.execute(
            'SELECT section_id FROM section_sources WHERE sitting_id = ? AND source_id = ?',
            (sitting_id, source_id),
        ).fetchall()
        candidates.update(row[0] for row in rows)
        # Older rows only stored the first source URL of a merged section.
        rows = conn.execute(
            'SELECT id FROM sections WHERE sitting_id = ? AND source_url = ?',
            (sitting_id, f'https://sprs.parl.gov.sg/search/sprs3topic?reportid={source_id}'),
        ).fetchall()
        candidates.update(row[0] for row in rows)
    if not candidates:
        rows = conn.execute(
            """SELECT id FROM sections WHERE sitting_id = ?
               AND section_title = ? AND section_type = ?
               AND NOT EXISTS (SELECT 1 FROM section_sources WHERE section_id = sections.id)""",
            (sitting_id, section['title'], section['section_type']),
        ).fetchall()
        candidates.update(row[0] for row in rows)
    if len(candidates) > 1:
        raise ValueError(f"Ambiguous existing section: {section['title']}; reconcile before reimporting")
    if candidates:
        return conn.execute('SELECT * FROM sections WHERE id = ?', (candidates.pop(),)).fetchone()
    return None


def create_section(sitting_id: str, category: str, section_type: str,
                   title: str, content_html: str, content_plain: str,
                   section_order: int, source_url: str = None,
                   ministry_id: str = None, bill_id: str = None,
                   existing=None, source_ids=()) -> str:
    """Upsert transcript data within the caller's sitting transaction.

    Preserve curated titles, classifications, bill links and summaries on replay.
    Source corrections to those fields require explicit review.
    """
    conn = get_connection()
    section_id = existing['id'] if existing is not None else generate_id()
    if existing is not None:
        conn.execute(
            """UPDATE sections SET content_html = ?, content_plain = ?,
               section_order = ?, source_url = ? WHERE id = ?""",
            (content_html, content_plain, section_order, source_url, section_id),
        )
        conn.execute('DELETE FROM section_speakers WHERE section_id = ?', (section_id,))
        conn.execute('DELETE FROM section_sources WHERE section_id = ?', (section_id,))
    else:
        conn.execute(
            """INSERT INTO sections
               (id, sitting_id, ministry_id, bill_id, category, section_type,
                section_title, content_html, content_plain, section_order, source_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (section_id, sitting_id, ministry_id, bill_id, category, section_type,
             title, content_html, content_plain, section_order, source_url),
        )
    for source_id in set(source_ids):
        conn.execute(
            'INSERT INTO section_sources (sitting_id, source_id, section_id) VALUES (?, ?, ?)',
            (sitting_id, source_id, section_id),
        )
    return section_id


def add_section_speaker(section_id: str, member_id: str,
                        constituency: str = None, designation: str = None):
    """Add a speaker to a section."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        '''INSERT INTO section_speakers (section_id, member_id, constituency, designation)
           VALUES (?, ?, ?, ?)
           ON CONFLICT (section_id, member_id) DO NOTHING''',
        (section_id, member_id, constituency, designation)
    )


def get_sitting_count() -> int:
    """Get total number of sittings in database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM sittings')
    return cursor.fetchone()['count']


def get_member_count() -> int:
    """Get total number of members in database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM members')
    return cursor.fetchone()['count']


def get_section_count() -> int:
    """Get total number of sections in database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM sections')
    return cursor.fetchone()['count']


def get_bill_count() -> int:
    """Get total number of bills in database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM bills')
    return cursor.fetchone()['count']


if __name__ == '__main__':
    # Initialize database and show stats
    init_db()
    print(f"\nDatabase stats:")
    print(f"  Sittings: {get_sitting_count()}")
    print(f"  Members: {get_member_count()}")
    print(f"  Sections: {get_section_count()}")
    print(f"  Bills: {get_bill_count()}")
    close_connection()
