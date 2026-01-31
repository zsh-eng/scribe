-- Create tables
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL UNIQUE,
    sitting_no INTEGER,
    parliament INTEGER,
    session_no INTEGER,
    volume_no INTEGER,
    format VARCHAR(10), -- 'new' or 'old'
    url TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Members table (Identity only, no time-variant fields)
CREATE TABLE members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Member Summaries (Aggregate view of member activity)
CREATE TABLE member_summaries (
    member_id UUID REFERENCES members(id) ON DELETE CASCADE PRIMARY KEY,
    summary TEXT, -- AI-generated profile/summary
    last_updated TIMESTAMP DEFAULT NOW()
);

-- Ministries (Fixed list)
CREATE TABLE ministries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    acronym VARCHAR(20),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Pre-seed Ministries
INSERT INTO ministries (name, acronym) VALUES
    ('Prime Minister''s Office', 'PMO'),
    ('Ministry of Culture, Community and Youth', 'MCCY'),
    ('Ministry of Defence', 'MINDEF'),
    ('Ministry of Digital Development and Information', 'MDDI'),
    ('Ministry of Education', 'MOE'),
    ('Ministry of Finance', 'MOF'),
    ('Ministry of Foreign Affairs', 'MFA'),
    ('Ministry of Health', 'MOH'),
    ('Ministry of Home Affairs', 'MHA'),
    ('Ministry of Law', 'MINLAW'),
    ('Ministry of Manpower', 'MOM'),
    ('Ministry of National Development', 'MND'),
    ('Ministry of Social and Family Development', 'MSF'),
    ('Ministry of Sustainability and the Environment', 'MSE'),
    ('Ministry of Trade and Industry', 'MTI'),
    ('Ministry of Transport', 'MOT'),
    ('Parliament of Singapore', 'PARL'); -- For Speaker, etc.

-- Bills table: groups BI and BP sections by title
CREATE TABLE bills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    ministry_id UUID REFERENCES ministries(id),
    first_reading_date DATE,
    first_reading_session_id UUID REFERENCES sessions(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Main table: one row per section (e.g., one parliamentary question or bill)
CREATE TABLE sections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    ministry_id UUID REFERENCES ministries(id), -- Nullable if not applicable
    bill_id UUID REFERENCES bills(id), -- Links bill sections to parent bill
    category VARCHAR(20) NOT NULL DEFAULT 'question', -- 'question' or 'bill'
    section_type VARCHAR(50) NOT NULL, -- 'OA', 'WA', 'WANA', 'BI', 'BP', etc.
    section_title TEXT,
    content_html TEXT NOT NULL,
    content_plain TEXT NOT NULL,
    section_order INTEGER NOT NULL,
    source_url TEXT, -- Link to original Hansard
    created_at TIMESTAMP DEFAULT NOW()
);

-- Junction table: links sections to members WITH time-variant data
CREATE TABLE section_speakers (
    section_id UUID REFERENCES sections(id) ON DELETE CASCADE,
    member_id UUID REFERENCES members(id) ON DELETE CASCADE,
    constituency VARCHAR(255), -- Snapshot at this time
    designation TEXT, -- Snapshot: 'Minister for Health', 'MP for Aljunied GRC', etc.
    PRIMARY KEY (section_id, member_id)
);

-- Session attendance: tracks which members attended each session
CREATE TABLE session_attendance (
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    member_id UUID REFERENCES members(id) ON DELETE CASCADE,
    present BOOLEAN NOT NULL DEFAULT true,
    constituency VARCHAR(255), -- Snapshot at this time
    designation TEXT, -- Snapshot at this time
    PRIMARY KEY (session_id, member_id)
);

-- Indexes
CREATE INDEX idx_sections_session ON sections(session_id);
CREATE INDEX idx_sections_ministry ON sections(ministry_id);
CREATE INDEX idx_sessions_date ON sessions(date);
CREATE INDEX idx_section_speakers_section ON section_speakers(section_id);
CREATE INDEX idx_section_speakers_member ON section_speakers(member_id);
CREATE INDEX idx_session_attendance_session ON session_attendance(session_id);
CREATE INDEX idx_session_attendance_member ON session_attendance(member_id);

-- Full-text search
CREATE INDEX idx_sections_content_plain_fts ON sections 
USING GIN(to_tsvector('english', content_plain));

-- RLS
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE members ENABLE ROW LEVEL SECURITY;
ALTER TABLE member_summaries ENABLE ROW LEVEL SECURITY;
ALTER TABLE ministries ENABLE ROW LEVEL SECURITY;
ALTER TABLE sections ENABLE ROW LEVEL SECURITY;
ALTER TABLE section_speakers ENABLE ROW LEVEL SECURITY;
ALTER TABLE session_attendance ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Enable read access for all users" ON sessions FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON members FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON member_summaries FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON ministries FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON sections FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON section_speakers FOR SELECT USING (true);
CREATE POLICY "Enable read access for all users" ON session_attendance FOR SELECT USING (true);

-- View: Sections with Speaker details
CREATE VIEW sections_with_speakers AS
SELECT 
    s.id,
    s.section_type,
    s.section_title,
    m_min.acronym as ministry,
    sess.date as session_date,
    ARRAY_AGG(
        CASE WHEN ss.designation IS NOT NULL 
        THEN m.name || ' (' || ss.designation || ')'
        ELSE m.name END
        ORDER BY m.name
    ) as speakers
FROM sections s
JOIN sessions sess ON s.session_id = sess.id
LEFT JOIN ministries m_min ON s.ministry_id = m_min.id
LEFT JOIN section_speakers ss ON s.id = ss.section_id
LEFT JOIN members m ON ss.member_id = m.id
GROUP BY s.id, sess.date, m_min.acronym
ORDER BY sess.date DESC, s.section_order ASC;

-- Materialized View: Member List View (Efficient aggregation for Member Directory)
-- Refreshed periodically to support search/filter on aggregated fields
CREATE MATERIALIZED VIEW member_list_view AS
WITH latestspeakerinfo AS (
    SELECT DISTINCT ON (ss.member_id) ss.member_id,
    ss.constituency AS speaker_constituency,
    ss.designation AS speaker_designation
    FROM section_speakers ss
    JOIN sections s ON ss.section_id = s.id
    JOIN sessions sess ON s.session_id = sess.id
    WHERE ss.constituency IS NOT NULL OR ss.designation IS NOT NULL
    ORDER BY ss.member_id, sess.date DESC
), latestattendanceinfo AS (
    SELECT DISTINCT ON (sa.member_id) sa.member_id,
    sa.constituency AS attendance_constituency,
    sa.designation AS attendance_designation
    FROM session_attendance sa
    JOIN sessions sess ON sa.session_id = sess.id
    WHERE sa.constituency IS NOT NULL OR sa.designation IS NOT NULL
    ORDER BY sa.member_id, sess.date DESC
), membersectioncounts AS (
    SELECT section_speakers.member_id,
    count(DISTINCT section_speakers.section_id) AS section_count
    FROM section_speakers
    GROUP BY section_speakers.member_id
)
SELECT m.id,
    m.name,
    ms.summary,
    COALESCE(msc.section_count, 0) AS section_count,
    COALESCE(lsi.speaker_constituency, lai.attendance_constituency) AS constituency,
    COALESCE(lsi.speaker_designation, lai.attendance_designation) AS designation
FROM members m
LEFT JOIN member_summaries ms ON m.id = ms.member_id
LEFT JOIN latestspeakerinfo lsi ON m.id = lsi.member_id
LEFT JOIN latestattendanceinfo lai ON m.id = lai.member_id
LEFT JOIN membersectioncounts msc ON m.id = msc.member_id;

-- Index for Member List View refreshing/concurrency
CREATE UNIQUE INDEX idx_member_list_view_id ON member_list_view(id);