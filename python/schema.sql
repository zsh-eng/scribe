-- SQLite Schema for Parliament Summarizer
-- Mirrors the PostgreSQL/Supabase structure but SQLite-compatible

-- Enable foreign key support
PRAGMA foreign_keys = ON;

-- Sittings table (Parliament sitting dates)
CREATE TABLE IF NOT EXISTS sittings (
    id TEXT PRIMARY KEY,
    date TEXT UNIQUE NOT NULL,  -- ISO format: YYYY-MM-DD
    sitting_no INTEGER,
    parliament INTEGER,
    session_no INTEGER,
    volume_no INTEGER,
    format TEXT CHECK (format IN ('new', 'old')),
    url TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sittings_date ON sittings(date);

-- Members table (MP identities - time-invariant)
CREATE TABLE IF NOT EXISTS members (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Member summaries (AI-generated profiles)
CREATE TABLE IF NOT EXISTS member_summaries (
    member_id TEXT PRIMARY KEY REFERENCES members(id) ON DELETE CASCADE,
    summary TEXT,
    last_updated TEXT DEFAULT (datetime('now'))
);

-- Ministries table (pre-seeded reference data)
CREATE TABLE IF NOT EXISTS ministries (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    acronym TEXT UNIQUE,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Bills table (tracks bills across readings)
CREATE TABLE IF NOT EXISTS bills (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    ministry_id TEXT REFERENCES ministries(id),
    first_reading_date TEXT,  -- ISO format: YYYY-MM-DD
    first_reading_sitting_id TEXT REFERENCES sittings(id),
    summary TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_bills_title ON bills(title);

-- Sections table (main content: questions, bills, motions)
CREATE TABLE IF NOT EXISTS sections (
    id TEXT PRIMARY KEY,
    sitting_id TEXT NOT NULL REFERENCES sittings(id) ON DELETE CASCADE,
    ministry_id TEXT REFERENCES ministries(id),
    bill_id TEXT REFERENCES bills(id),
    category TEXT CHECK (category IN ('question', 'bill', 'motion', 'clarification', 'adjournment_motion', 'other')),
    section_type TEXT CHECK (section_type IN ('OA', 'WA', 'WANA', 'BI', 'BP', 'OS', 'WS')),
    section_title TEXT,
    content_html TEXT,
    content_plain TEXT,
    section_order INTEGER,
    source_url TEXT,
    summary TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_sections_sitting ON sections(sitting_id);
CREATE INDEX IF NOT EXISTS idx_sections_ministry ON sections(ministry_id);
CREATE INDEX IF NOT EXISTS idx_sections_category ON sections(category);
CREATE INDEX IF NOT EXISTS idx_sections_type ON sections(section_type);

-- Source identity is separate from public IDs, including merged Hansard sections.
CREATE TABLE IF NOT EXISTS section_sources (
    sitting_id TEXT NOT NULL REFERENCES sittings(id) ON DELETE CASCADE,
    source_id TEXT NOT NULL,
    section_id TEXT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    PRIMARY KEY (sitting_id, source_id)
);
CREATE INDEX IF NOT EXISTS idx_section_sources_section ON section_sources(section_id);

-- LLM attempt history is provenance, not an automatic regeneration queue.
-- Existing summary text without a matching successful attempt has unknown provenance.
CREATE TABLE IF NOT EXISTS summary_attempts (
    id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('section', 'bill', 'member')),
    entity_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    prompt_key TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'failed', 'blocked')),
    summary_hash TEXT,
    input_chars INTEGER NOT NULL,
    error TEXT,
    usage_json TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_summary_attempts_entity ON summary_attempts(entity_type, entity_id, id);

-- Section speakers (junction: sections <-> members with time snapshot)
CREATE TABLE IF NOT EXISTS section_speakers (
    section_id TEXT NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    constituency TEXT,
    designation TEXT,
    PRIMARY KEY (section_id, member_id)
);

CREATE INDEX IF NOT EXISTS idx_section_speakers_section ON section_speakers(section_id);
CREATE INDEX IF NOT EXISTS idx_section_speakers_member ON section_speakers(member_id);

-- Sitting attendance (who attended each sitting)
CREATE TABLE IF NOT EXISTS sitting_attendance (
    sitting_id TEXT NOT NULL REFERENCES sittings(id) ON DELETE CASCADE,
    member_id TEXT NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    present INTEGER NOT NULL DEFAULT 1,  -- 1 = present, 0 = absent
    constituency TEXT,
    designation TEXT,
    PRIMARY KEY (sitting_id, member_id)
);

CREATE INDEX IF NOT EXISTS idx_sitting_attendance_sitting ON sitting_attendance(sitting_id);
CREATE INDEX IF NOT EXISTS idx_sitting_attendance_member ON sitting_attendance(member_id);

-- Pre-seed ministries
INSERT OR IGNORE INTO ministries (id, name, acronym) VALUES
    ('01', 'Prime Minister''s Office', 'PMO'),
    ('02', 'Ministry of Culture, Community and Youth', 'MCCY'),
    ('03', 'Ministry of Defence', 'MINDEF'),
    ('04', 'Ministry of Digital Development and Information', 'MDDI'),
    ('05', 'Ministry of Education', 'MOE'),
    ('06', 'Ministry of Finance', 'MOF'),
    ('07', 'Ministry of Foreign Affairs', 'MFA'),
    ('08', 'Ministry of Health', 'MOH'),
    ('09', 'Ministry of Home Affairs', 'MHA'),
    ('10', 'Ministry of Law', 'MINLAW'),
    ('11', 'Ministry of Manpower', 'MOM'),
    ('12', 'Ministry of National Development', 'MND'),
    ('13', 'Ministry of Social and Family Development', 'MSF'),
    ('14', 'Ministry of Sustainability and the Environment', 'MSE'),
    ('15', 'Ministry of Trade and Industry', 'MTI'),
    ('16', 'Ministry of Transport', 'MOT')

-- FTS virtual table for full-text search on sections (optional, for search feature)
-- CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
--     section_title,
--     content_plain,
--     content=sections,
--     content_rowid=rowid
-- );
