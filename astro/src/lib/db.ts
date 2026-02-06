import Database from 'better-sqlite3';
import path from 'path';

// Connect to SQLite database
const dbPath = path.join(process.cwd(), '..', 'data', 'parliament.db');
const db = new Database(dbPath, { readonly: true });

// Enable WAL mode for better read performance
db.pragma('journal_mode = WAL');

// Types
export interface Session {
  id: string;
  date: string;
  sittingNo: number;
  parliament: number;
  sessionNo: number;
  volumeNo: number;
  format: string;
  url: string;
  sectionCount?: number;
}

export interface Member {
  id: string;
  name: string;
  summary?: string | null;
  sectionCount?: number;
  constituency?: string | null;
  designation?: string | null;
  attendanceTotal?: number;
  attendancePresent?: number;
}

export interface Ministry {
  id: string;
  name: string;
  acronym: string;
  sectionCount?: number;
}

export interface Speaker {
  memberId: string;
  name: string;
  constituency: string | null;
  designation: string | null;
}

export interface Section {
  id: string;
  sessionId: string;
  sessionDate?: string;
  sittingNo?: number;
  sectionType: string;
  sectionTitle: string;
  contentHtml?: string;
  contentPlain?: string;
  sectionOrder: number;
  ministry: string | null;
  ministryId: string | null;
  category: string | null;
  speakers?: Speaker[];
  sourceUrl?: string | null;
  summary?: string | null;
}

export interface Bill {
  id: string;
  title: string;
  ministryId: string | null;
  ministry?: string | null;
  firstReadingDate: string | null;
  firstReadingSessionId: string | null;
  hasSecondReading?: boolean;
  summary?: string | null;
}

export interface Attendee {
  id: string;
  name: string;
  present: boolean;
  constituency: string | null;
  designation: string | null;
}

// Query functions

export function getSessions(limit?: number, offset?: number): Session[] {
  const sql = `
    SELECT
      s.id,
      s.date,
      s.sitting_no as sittingNo,
      s.parliament,
      s.session_no as sessionNo,
      s.volume_no as volumeNo,
      s.format,
      s.url,
      COUNT(sec.id) as sectionCount
    FROM sessions s
    LEFT JOIN sections sec ON s.id = sec.session_id
    GROUP BY s.id
    ORDER BY s.date DESC
    ${limit ? `LIMIT ${limit}` : ''}
    ${offset ? `OFFSET ${offset}` : ''}
  `;
  return db.prepare(sql).all() as Session[];
}

export function getSessionCount(): number {
  const result = db.prepare('SELECT COUNT(*) as count FROM sessions').get() as { count: number };
  return result.count;
}

export function getSession(id: string): Session | undefined {
  const sql = `
    SELECT
      id,
      date,
      sitting_no as sittingNo,
      parliament,
      session_no as sessionNo,
      volume_no as volumeNo,
      format,
      url
    FROM sessions
    WHERE id = ?
  `;
  return db.prepare(sql).get(id) as Session | undefined;
}

export function getSessionSections(sessionId: string): Section[] {
  const sql = `
    SELECT
      sec.id,
      sec.session_id as sessionId,
      sec.section_type as sectionType,
      sec.section_title as sectionTitle,
      sec.content_html as contentHtml,
      sec.content_plain as contentPlain,
      sec.section_order as sectionOrder,
      sec.category,
      sec.source_url as sourceUrl,
      sec.summary,
      m.name as ministry,
      sec.ministry_id as ministryId,
      sec.bill_id as billId
    FROM sections sec
    LEFT JOIN ministries m ON sec.ministry_id = m.id
    WHERE sec.session_id = ?
    ORDER BY sec.section_order ASC
  `;
  const sections = db.prepare(sql).all(sessionId) as Section[];

  // Get speakers for each section
  const speakerSql = `
    SELECT
      ss.section_id as sectionId,
      ss.member_id as memberId,
      m.name,
      ss.constituency,
      ss.designation
    FROM section_speakers ss
    JOIN members m ON ss.member_id = m.id
    WHERE ss.section_id IN (${sections.map(() => '?').join(',')})
  `;

  if (sections.length > 0) {
    const speakers = db.prepare(speakerSql).all(...sections.map(s => s.id)) as (Speaker & { sectionId: string })[];
    const speakerMap = new Map<string, Speaker[]>();

    for (const speaker of speakers) {
      if (!speakerMap.has(speaker.sectionId)) {
        speakerMap.set(speaker.sectionId, []);
      }
      speakerMap.get(speaker.sectionId)!.push({
        memberId: speaker.memberId,
        name: speaker.name,
        constituency: speaker.constituency,
        designation: speaker.designation,
      });
    }

    for (const section of sections) {
      section.speakers = speakerMap.get(section.id) || [];
    }
  }

  return sections;
}

export function getSessionAttendees(sessionId: string): Attendee[] {
  const sql = `
    SELECT
      m.id,
      m.name,
      sa.present,
      sa.constituency,
      sa.designation
    FROM session_attendance sa
    JOIN members m ON sa.member_id = m.id
    WHERE sa.session_id = ?
    ORDER BY m.name ASC
  `;
  const results = db.prepare(sql).all(sessionId) as { id: string; name: string; present: number; constituency: string | null; designation: string | null }[];
  return results.map(r => ({
    ...r,
    present: r.present === 1,
  }));
}

export function getSessionBills(sessionId: string): { billId: string; billTitle: string; sectionTitle: string; ministry: string | null; ministryId: string | null; readingTypes: string[]; sectionOrder: number }[] {
  const sql = `
    SELECT
      sec.bill_id as billId,
      b.title as billTitle,
      sec.section_title as sectionTitle,
      m.name as ministry,
      sec.ministry_id as ministryId,
      sec.section_type as sectionType,
      sec.section_order as sectionOrder
    FROM sections sec
    LEFT JOIN ministries m ON sec.ministry_id = m.id
    LEFT JOIN bills b ON sec.bill_id = b.id
    WHERE sec.session_id = ? AND sec.bill_id IS NOT NULL
    ORDER BY sec.section_order ASC
  `;
  const results = db.prepare(sql).all(sessionId) as { billId: string; billTitle: string; sectionTitle: string; ministry: string | null; ministryId: string | null; sectionType: string; sectionOrder: number }[];

  // Group by bill and collect reading types
  const billMap = new Map<string, { billId: string; billTitle: string; sectionTitle: string; ministry: string | null; ministryId: string | null; readingTypes: string[]; sectionOrder: number }>();

  for (const row of results) {
    if (!billMap.has(row.billId)) {
      billMap.set(row.billId, {
        billId: row.billId,
        billTitle: row.billTitle,
        sectionTitle: row.sectionTitle,
        ministry: row.ministry,
        ministryId: row.ministryId,
        readingTypes: [],
        sectionOrder: row.sectionOrder,
      });
    }
    billMap.get(row.billId)!.readingTypes.push(row.sectionType);
  }

  return Array.from(billMap.values());
}

export function getMembers(limit?: number, offset?: number): Member[] {
  const sql = `
    SELECT
      m.id,
      m.name,
      ms.summary,
      COUNT(DISTINCT ss.section_id) as sectionCount
    FROM members m
    LEFT JOIN member_summaries ms ON m.id = ms.member_id
    LEFT JOIN section_speakers ss ON m.id = ss.member_id
    GROUP BY m.id
    ORDER BY m.name ASC
    ${limit ? `LIMIT ${limit}` : ''}
    ${offset ? `OFFSET ${offset}` : ''}
  `;
  return db.prepare(sql).all() as Member[];
}

export function getMemberCount(): number {
  const result = db.prepare('SELECT COUNT(*) as count FROM members').get() as { count: number };
  return result.count;
}

export function getMember(id: string): Member | undefined {
  const sql = `
    SELECT
      m.id,
      m.name,
      ms.summary,
      COUNT(DISTINCT ss.section_id) as sectionCount,
      (SELECT COUNT(*) FROM session_attendance WHERE member_id = m.id) as attendanceTotal,
      (SELECT COUNT(*) FROM session_attendance WHERE member_id = m.id AND present = 1) as attendancePresent,
      (
        SELECT sa.constituency FROM session_attendance sa
        JOIN sessions s ON sa.session_id = s.id
        WHERE sa.member_id = m.id
        ORDER BY s.date DESC
        LIMIT 1
      ) as constituency,
      (
        SELECT sa.designation FROM session_attendance sa
        JOIN sessions s ON sa.session_id = s.id
        WHERE sa.member_id = m.id
        ORDER BY s.date DESC
        LIMIT 1
      ) as designation
    FROM members m
    LEFT JOIN member_summaries ms ON m.id = ms.member_id
    LEFT JOIN section_speakers ss ON m.id = ss.member_id
    WHERE m.id = ?
    GROUP BY m.id
  `;
  return db.prepare(sql).get(id) as Member | undefined;
}

export function getBills(limit?: number, offset?: number): Bill[] {
  const sql = `
    SELECT
      b.id,
      b.title,
      b.ministry_id as ministryId,
      m.name as ministry,
      b.first_reading_date as firstReadingDate,
      b.first_reading_session_id as firstReadingSessionId,
      b.summary,
      EXISTS(
        SELECT 1 FROM sections sec
        WHERE sec.bill_id = b.id AND sec.section_type = 'BP'
      ) as hasSecondReading
    FROM bills b
    LEFT JOIN ministries m ON b.ministry_id = m.id
    ORDER BY b.first_reading_date DESC NULLS LAST
    ${limit ? `LIMIT ${limit}` : ''}
    ${offset ? `OFFSET ${offset}` : ''}
  `;
  const results = db.prepare(sql).all() as (Omit<Bill, 'hasSecondReading'> & { hasSecondReading: number })[];
  return results.map(r => ({ ...r, hasSecondReading: r.hasSecondReading === 1 }));
}

export function getBillCount(): number {
  const result = db.prepare('SELECT COUNT(*) as count FROM bills').get() as { count: number };
  return result.count;
}

export function getBill(id: string): Bill | undefined {
  const sql = `
    SELECT
      b.id,
      b.title,
      b.ministry_id as ministryId,
      m.name as ministry,
      b.first_reading_date as firstReadingDate,
      b.first_reading_session_id as firstReadingSessionId,
      b.summary,
      EXISTS(
        SELECT 1 FROM sections sec
        WHERE sec.bill_id = b.id AND sec.section_type = 'BP'
      ) as hasSecondReading
    FROM bills b
    LEFT JOIN ministries m ON b.ministry_id = m.id
    WHERE b.id = ?
  `;
  const result = db.prepare(sql).get(id) as (Omit<Bill, 'hasSecondReading'> & { hasSecondReading: number }) | undefined;
  if (!result) return undefined;
  return { ...result, hasSecondReading: result.hasSecondReading === 1 };
}

export function getMinistries(): Ministry[] {
  const sql = `
    SELECT
      m.id,
      m.name,
      m.acronym,
      COUNT(sec.id) as sectionCount
    FROM ministries m
    LEFT JOIN sections sec ON m.id = sec.ministry_id
    GROUP BY m.id
    ORDER BY m.name ASC
  `;
  return db.prepare(sql).all() as Ministry[];
}

export function getMinistry(id: string): Ministry | undefined {
  const sql = `
    SELECT
      m.id,
      m.name,
      m.acronym,
      COUNT(sec.id) as sectionCount
    FROM ministries m
    LEFT JOIN sections sec ON m.id = sec.ministry_id
    WHERE m.id = ?
    GROUP BY m.id
  `;
  return db.prepare(sql).get(id) as Ministry | undefined;
}

// Questions - sections that are questions (OA, WA, WANA) and not bill readings
export function getQuestions(limit?: number, offset?: number): Section[] {
  const sql = `
    SELECT
      sec.id,
      sec.session_id as sessionId,
      s.date as sessionDate,
      s.sitting_no as sittingNo,
      sec.section_type as sectionType,
      sec.section_title as sectionTitle,
      sec.content_plain as contentPlain,
      sec.section_order as sectionOrder,
      sec.category,
      sec.source_url as sourceUrl,
      sec.summary,
      m.name as ministry,
      sec.ministry_id as ministryId
    FROM sections sec
    JOIN sessions s ON sec.session_id = s.id
    LEFT JOIN ministries m ON sec.ministry_id = m.id
    WHERE sec.section_type IN ('OA', 'WA', 'WANA')
      AND sec.section_type NOT IN ('BI', 'BP')
    ORDER BY s.date DESC, sec.section_order ASC
    ${limit ? `LIMIT ${limit}` : ''}
    ${offset ? `OFFSET ${offset}` : ''}
  `;
  const sections = db.prepare(sql).all() as Section[];

  // Get speakers for each section
  if (sections.length > 0) {
    const speakerSql = `
      SELECT
        ss.section_id as sectionId,
        ss.member_id as memberId,
        m.name,
        ss.constituency,
        ss.designation
      FROM section_speakers ss
      JOIN members m ON ss.member_id = m.id
      WHERE ss.section_id IN (${sections.map(() => '?').join(',')})
    `;
    const speakers = db.prepare(speakerSql).all(...sections.map(s => s.id)) as (Speaker & { sectionId: string })[];
    const speakerMap = new Map<string, Speaker[]>();

    for (const speaker of speakers) {
      if (!speakerMap.has(speaker.sectionId)) {
        speakerMap.set(speaker.sectionId, []);
      }
      speakerMap.get(speaker.sectionId)!.push({
        memberId: speaker.memberId,
        name: speaker.name,
        constituency: speaker.constituency,
        designation: speaker.designation,
      });
    }

    for (const section of sections) {
      section.speakers = speakerMap.get(section.id) || [];
    }
  }

  return sections;
}

export function getQuestionCount(): number {
  const result = db.prepare(`
    SELECT COUNT(*) as count FROM sections
    WHERE section_type IN ('OA', 'WA', 'WANA')
      AND section_type NOT IN ('BI', 'BP')
  `).get() as { count: number };
  return result.count;
}

// Motions - sections categorized as motion or adjournment_motion
export function getMotions(limit?: number, offset?: number): Section[] {
  const sql = `
    SELECT
      sec.id,
      sec.session_id as sessionId,
      s.date as sessionDate,
      s.sitting_no as sittingNo,
      sec.section_type as sectionType,
      sec.section_title as sectionTitle,
      sec.content_plain as contentPlain,
      sec.section_order as sectionOrder,
      sec.category,
      sec.source_url as sourceUrl,
      sec.summary,
      m.name as ministry,
      sec.ministry_id as ministryId
    FROM sections sec
    JOIN sessions s ON sec.session_id = s.id
    LEFT JOIN ministries m ON sec.ministry_id = m.id
    WHERE sec.category IN ('motion', 'adjournment_motion')
    ORDER BY s.date DESC, sec.section_order ASC
    ${limit ? `LIMIT ${limit}` : ''}
    ${offset ? `OFFSET ${offset}` : ''}
  `;
  const sections = db.prepare(sql).all() as Section[];

  // Get speakers for each section
  if (sections.length > 0) {
    const speakerSql = `
      SELECT
        ss.section_id as sectionId,
        ss.member_id as memberId,
        m.name,
        ss.constituency,
        ss.designation
      FROM section_speakers ss
      JOIN members m ON ss.member_id = m.id
      WHERE ss.section_id IN (${sections.map(() => '?').join(',')})
    `;
    const speakers = db.prepare(speakerSql).all(...sections.map(s => s.id)) as (Speaker & { sectionId: string })[];
    const speakerMap = new Map<string, Speaker[]>();

    for (const speaker of speakers) {
      if (!speakerMap.has(speaker.sectionId)) {
        speakerMap.set(speaker.sectionId, []);
      }
      speakerMap.get(speaker.sectionId)!.push({
        memberId: speaker.memberId,
        name: speaker.name,
        constituency: speaker.constituency,
        designation: speaker.designation,
      });
    }

    for (const section of sections) {
      section.speakers = speakerMap.get(section.id) || [];
    }
  }

  return sections;
}

export function getMotionCount(): number {
  const result = db.prepare(`
    SELECT COUNT(*) as count FROM sections
    WHERE category IN ('motion', 'adjournment_motion')
  `).get() as { count: number };
  return result.count;
}

// Get a single section with full content
export function getSection(id: string): Section | undefined {
  const sql = `
    SELECT
      sec.id,
      sec.session_id as sessionId,
      s.date as sessionDate,
      s.sitting_no as sittingNo,
      s.url as sessionUrl,
      sec.section_type as sectionType,
      sec.section_title as sectionTitle,
      sec.content_html as contentHtml,
      sec.content_plain as contentPlain,
      sec.section_order as sectionOrder,
      sec.category,
      sec.source_url as sourceUrl,
      sec.summary,
      m.name as ministry,
      sec.ministry_id as ministryId
    FROM sections sec
    JOIN sessions s ON sec.session_id = s.id
    LEFT JOIN ministries m ON sec.ministry_id = m.id
    WHERE sec.id = ?
  `;
  const section = db.prepare(sql).get(id) as Section | undefined;

  if (section) {
    // Get speakers
    const speakerSql = `
      SELECT
        ss.member_id as memberId,
        m.name,
        ss.constituency,
        ss.designation
      FROM section_speakers ss
      JOIN members m ON ss.member_id = m.id
      WHERE ss.section_id = ?
    `;
    section.speakers = db.prepare(speakerSql).all(id) as Speaker[];
  }

  return section;
}

// Get all sections where a member is a speaker
export function getMemberSections(memberId: string): Section[] {
  const sql = `
    SELECT
      sec.id,
      sec.session_id as sessionId,
      s.date as sessionDate,
      s.sitting_no as sittingNo,
      sec.section_type as sectionType,
      sec.section_title as sectionTitle,
      sec.content_plain as contentPlain,
      sec.section_order as sectionOrder,
      sec.category,
      sec.source_url as sourceUrl,
      sec.summary,
      m.name as ministry,
      sec.ministry_id as ministryId,
      sec.bill_id as billId,
      b.title as billTitle
    FROM sections sec
    JOIN sessions s ON sec.session_id = s.id
    LEFT JOIN ministries m ON sec.ministry_id = m.id
    LEFT JOIN bills b ON sec.bill_id = b.id
    JOIN section_speakers ss ON sec.id = ss.section_id
    WHERE ss.member_id = ?
    ORDER BY s.date DESC, sec.section_order ASC
  `;
  const sections = db.prepare(sql).all(memberId) as Section[];

  // Get all speakers for these sections
  if (sections.length > 0) {
    const speakerSql = `
      SELECT
        ss.section_id as sectionId,
        ss.member_id as memberId,
        m.name,
        ss.constituency,
        ss.designation
      FROM section_speakers ss
      JOIN members m ON ss.member_id = m.id
      WHERE ss.section_id IN (${sections.map(() => '?').join(',')})
    `;
    const speakers = db.prepare(speakerSql).all(...sections.map(s => s.id)) as (Speaker & { sectionId: string })[];
    const speakerMap = new Map<string, Speaker[]>();

    for (const speaker of speakers) {
      if (!speakerMap.has(speaker.sectionId)) {
        speakerMap.set(speaker.sectionId, []);
      }
      speakerMap.get(speaker.sectionId)!.push({
        memberId: speaker.memberId,
        name: speaker.name,
        constituency: speaker.constituency,
        designation: speaker.designation,
      });
    }

    for (const section of sections) {
      section.speakers = speakerMap.get(section.id) || [];
    }
  }

  return sections;
}

// Get attendance history for a member
export interface AttendanceRecord {
  sessionId: string;
  date: string;
  sittingNo: number;
  present: boolean;
}

export function getMemberAttendance(memberId: string): AttendanceRecord[] {
  const sql = `
    SELECT
      sa.session_id as sessionId,
      s.date,
      s.sitting_no as sittingNo,
      sa.present
    FROM session_attendance sa
    JOIN sessions s ON sa.session_id = s.id
    WHERE sa.member_id = ?
    ORDER BY s.date DESC
  `;
  const results = db.prepare(sql).all(memberId) as { sessionId: string; date: string; sittingNo: number; present: number }[];
  return results.map(r => ({
    ...r,
    present: r.present === 1,
  }));
}

// Get all sections for a bill
export interface BillSection {
  id: string;
  sessionId: string;
  sessionDate: string;
  sittingNo: number;
  sectionType: string;
  sectionTitle: string;
  contentHtml: string;
  contentPlain: string;
  sourceUrl: string | null;
  speakers: Speaker[];
}

export function getBillSections(billId: string): BillSection[] {
  const sql = `
    SELECT
      sec.id,
      sec.session_id as sessionId,
      s.date as sessionDate,
      s.sitting_no as sittingNo,
      sec.section_type as sectionType,
      sec.section_title as sectionTitle,
      sec.content_html as contentHtml,
      sec.content_plain as contentPlain,
      sec.source_url as sourceUrl
    FROM sections sec
    JOIN sessions s ON sec.session_id = s.id
    WHERE sec.bill_id = ?
    ORDER BY s.date ASC, sec.section_order ASC
  `;
  const sections = db.prepare(sql).all(billId) as BillSection[];

  // Get speakers for each section
  if (sections.length > 0) {
    const speakerSql = `
      SELECT
        ss.section_id as sectionId,
        ss.member_id as memberId,
        m.name,
        ss.constituency,
        ss.designation
      FROM section_speakers ss
      JOIN members m ON ss.member_id = m.id
      WHERE ss.section_id IN (${sections.map(() => '?').join(',')})
    `;
    const speakers = db.prepare(speakerSql).all(...sections.map(s => s.id)) as (Speaker & { sectionId: string })[];
    const speakerMap = new Map<string, Speaker[]>();

    for (const speaker of speakers) {
      if (!speakerMap.has(speaker.sectionId)) {
        speakerMap.set(speaker.sectionId, []);
      }
      speakerMap.get(speaker.sectionId)!.push({
        memberId: speaker.memberId,
        name: speaker.name,
        constituency: speaker.constituency,
        designation: speaker.designation,
      });
    }

    for (const section of sections) {
      section.speakers = speakerMap.get(section.id) || [];
    }
  }

  return sections;
}

// Get all sections for a ministry
export function getMinistrySections(ministryId: string): Section[] {
  const sql = `
    SELECT
      sec.id,
      sec.session_id as sessionId,
      s.date as sessionDate,
      s.sitting_no as sittingNo,
      sec.section_type as sectionType,
      sec.section_title as sectionTitle,
      sec.content_plain as contentPlain,
      sec.section_order as sectionOrder,
      sec.category,
      sec.source_url as sourceUrl,
      sec.summary,
      m.name as ministry,
      sec.ministry_id as ministryId,
      sec.bill_id as billId
    FROM sections sec
    JOIN sessions s ON sec.session_id = s.id
    LEFT JOIN ministries m ON sec.ministry_id = m.id
    WHERE sec.ministry_id = ?
    ORDER BY s.date DESC, sec.section_order ASC
  `;
  const sections = db.prepare(sql).all(ministryId) as Section[];

  // Get speakers for each section
  if (sections.length > 0) {
    const speakerSql = `
      SELECT
        ss.section_id as sectionId,
        ss.member_id as memberId,
        m.name,
        ss.constituency,
        ss.designation
      FROM section_speakers ss
      JOIN members m ON ss.member_id = m.id
      WHERE ss.section_id IN (${sections.map(() => '?').join(',')})
    `;
    const speakers = db.prepare(speakerSql).all(...sections.map(s => s.id)) as (Speaker & { sectionId: string })[];
    const speakerMap = new Map<string, Speaker[]>();

    for (const speaker of speakers) {
      if (!speakerMap.has(speaker.sectionId)) {
        speakerMap.set(speaker.sectionId, []);
      }
      speakerMap.get(speaker.sectionId)!.push({
        memberId: speaker.memberId,
        name: speaker.name,
        constituency: speaker.constituency,
        designation: speaker.designation,
      });
    }

    for (const section of sections) {
      section.speakers = speakerMap.get(section.id) || [];
    }
  }

  return sections;
}

// Get all bills for a ministry
export function getMinistryBills(ministryId: string): Bill[] {
  const sql = `
    SELECT
      b.id,
      b.title,
      b.ministry_id as ministryId,
      m.name as ministry,
      b.first_reading_date as firstReadingDate,
      b.first_reading_session_id as firstReadingSessionId,
      b.summary,
      EXISTS(
        SELECT 1 FROM sections sec
        WHERE sec.bill_id = b.id AND sec.section_type = 'BP'
      ) as hasSecondReading
    FROM bills b
    LEFT JOIN ministries m ON b.ministry_id = m.id
    WHERE b.ministry_id = ?
    ORDER BY b.first_reading_date DESC NULLS LAST
  `;
  const results = db.prepare(sql).all(ministryId) as (Omit<Bill, 'hasSecondReading'> & { hasSecondReading: number })[];
  return results.map(r => ({ ...r, hasSecondReading: r.hasSecondReading === 1 }));
}

// Get members with extended info (constituency, designation from latest attendance)
export function getMembersWithInfo(limit?: number, offset?: number): Member[] {
  const sql = `
    SELECT
      m.id,
      m.name,
      ms.summary,
      COUNT(DISTINCT ss.section_id) as sectionCount,
      (SELECT COUNT(*) FROM session_attendance WHERE member_id = m.id) as attendanceTotal,
      (SELECT COUNT(*) FROM session_attendance WHERE member_id = m.id AND present = 1) as attendancePresent,
      (
        SELECT sa.constituency FROM session_attendance sa
        JOIN sessions s ON sa.session_id = s.id
        WHERE sa.member_id = m.id
        ORDER BY s.date DESC
        LIMIT 1
      ) as constituency,
      (
        SELECT sa.designation FROM session_attendance sa
        JOIN sessions s ON sa.session_id = s.id
        WHERE sa.member_id = m.id
        ORDER BY s.date DESC
        LIMIT 1
      ) as designation
    FROM members m
    LEFT JOIN member_summaries ms ON m.id = ms.member_id
    LEFT JOIN section_speakers ss ON m.id = ss.member_id
    GROUP BY m.id
    ORDER BY m.name ASC
    ${limit ? `LIMIT ${limit}` : ''}
    ${offset ? `OFFSET ${offset}` : ''}
  `;
  return db.prepare(sql).all() as Member[];
}

// Get all sections (for static path generation)
export function getAllSections(): { id: string; sectionTitle: string }[] {
  const sql = `SELECT id, section_title as sectionTitle FROM sections`;
  return db.prepare(sql).all() as { id: string; sectionTitle: string }[];
}

// Stats for home page
export function getStats(): { sessionCount: number; memberCount: number; billCount: number; sectionCount: number } {
  const sessionCount = (db.prepare('SELECT COUNT(*) as count FROM sessions').get() as { count: number }).count;
  const memberCount = (db.prepare('SELECT COUNT(*) as count FROM members').get() as { count: number }).count;
  const billCount = (db.prepare('SELECT COUNT(*) as count FROM bills').get() as { count: number }).count;
  const sectionCount = (db.prepare('SELECT COUNT(*) as count FROM sections').get() as { count: number }).count;

  return { sessionCount, memberCount, billCount, sectionCount };
}

// Get the most recent session for masthead info
export function getLatestSession(): Session | undefined {
  const sql = `
    SELECT
      id,
      date,
      sitting_no as sittingNo,
      parliament,
      session_no as sessionNo,
      volume_no as volumeNo,
      format,
      url
    FROM sessions
    ORDER BY date DESC
    LIMIT 1
  `;
  return db.prepare(sql).get() as Session | undefined;
}

// Get count of sittings in current year
export function getSittingsThisYear(): number {
  const currentYear = new Date().getFullYear();
  const result = db.prepare(`
    SELECT COUNT(*) as count FROM sessions
    WHERE strftime('%Y', date) = ?
  `).get(String(currentYear)) as { count: number };
  return result.count;
}

// Get recent bills that have had readings (for ticker/featured)
export interface RecentBillReading {
  billId: string;
  billTitle: string;
  sectionType: string;
  sessionDate: string;
  ministry: string | null;
}

export function getRecentBillReadings(limit: number = 5): RecentBillReading[] {
  const sql = `
    SELECT
      billId,
      billTitle,
      sectionType,
      sessionDate,
      ministry
    FROM (
      SELECT
        b.id as billId,
        b.title as billTitle,
        sec.section_type as sectionType,
        s.date as sessionDate,
        m.name as ministry,
        ROW_NUMBER() OVER (
          PARTITION BY b.id
          ORDER BY s.date DESC, sec.section_order DESC
        ) as rowNumber
      FROM sections sec
      JOIN sessions s ON sec.session_id = s.id
      JOIN bills b ON sec.bill_id = b.id
      LEFT JOIN ministries m ON b.ministry_id = m.id
      WHERE sec.bill_id IS NOT NULL
    )
    WHERE rowNumber = 1
    ORDER BY sessionDate DESC
    LIMIT ?
  `;
  return db.prepare(sql).all(limit) as RecentBillReading[];
}

// Get latest question with asker info
export interface LatestQuestion {
  id: string;
  sectionTitle: string;
  sessionDate: string;
  askerName: string | null;
  askerId: string | null;
  ministry: string | null;
}

export function getLatestQuestion(): LatestQuestion | undefined {
  const sql = `
    SELECT
      sec.id,
      sec.section_title as sectionTitle,
      s.date as sessionDate,
      m.name as ministry
    FROM sections sec
    JOIN sessions s ON sec.session_id = s.id
    LEFT JOIN ministries m ON sec.ministry_id = m.id
    WHERE sec.section_type IN ('OA', 'WA', 'WANA')
    ORDER BY s.date DESC, sec.section_order ASC
    LIMIT 1
  `;
  const question = db.prepare(sql).get() as { id: string; sectionTitle: string; sessionDate: string; ministry: string | null } | undefined;

  if (!question) return undefined;

  // Get first speaker (usually the asker)
  const speakerSql = `
    SELECT
      ss.member_id as askerId,
      m.name as askerName
    FROM section_speakers ss
    JOIN members m ON ss.member_id = m.id
    WHERE ss.section_id = ?
    LIMIT 1
  `;
  const speaker = db.prepare(speakerSql).get(question.id) as { askerId: string; askerName: string } | undefined;

  return {
    ...question,
    askerName: speaker?.askerName || null,
    askerId: speaker?.askerId || null,
  };
}

// Get bill readings from the most recent sitting
export function getBillReadingsFromLastSitting(): RecentBillReading[] {
  const sql = `
    SELECT DISTINCT
      b.id as billId,
      b.title as billTitle,
      sec.section_type as sectionType,
      s.date as sessionDate,
      m.name as ministry
    FROM sections sec
    JOIN sessions s ON sec.session_id = s.id
    JOIN bills b ON sec.bill_id = b.id
    LEFT JOIN ministries m ON b.ministry_id = m.id
    WHERE sec.bill_id IS NOT NULL
      AND s.date = (SELECT MAX(date) FROM sessions)
    ORDER BY sec.section_order ASC
  `;
  return db.prepare(sql).all() as RecentBillReading[];
}

// Get recent motions for ticker
export interface RecentMotion {
  id: string;
  sectionTitle: string;
  sessionDate: string;
}

export function getRecentMotions(limit: number = 3): RecentMotion[] {
  const sql = `
    SELECT
      sec.id,
      sec.section_title as sectionTitle,
      s.date as sessionDate
    FROM sections sec
    JOIN sessions s ON sec.session_id = s.id
    WHERE sec.category IN ('motion', 'adjournment_motion')
    ORDER BY s.date DESC, sec.section_order ASC
    LIMIT ?
  `;
  return db.prepare(sql).all(limit) as RecentMotion[];
}

export default db;
