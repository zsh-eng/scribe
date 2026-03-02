import Database from 'better-sqlite3';
import path from 'path';

// Connect to SQLite database
const dbPath = path.join(process.cwd(), '..', 'data', 'parliament.db');
const db = new Database(dbPath, { readonly: true });

// Enable WAL mode for better read performance
db.pragma('journal_mode = WAL');

// Types
export interface Sitting {
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
  sittingId: string;
  sittingDate?: string;
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
  firstReadingSittingId: string | null;
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

export function getSittings(limit?: number, offset?: number): Sitting[] {
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
    FROM sittings s
    LEFT JOIN sections sec ON s.id = sec.sitting_id
    GROUP BY s.id
    ORDER BY s.date DESC
    ${limit ? `LIMIT ${limit}` : ''}
    ${offset ? `OFFSET ${offset}` : ''}
  `;
  return db.prepare(sql).all() as Sitting[];
}

export function getSittingCount(): number {
  const result = db.prepare('SELECT COUNT(*) as count FROM sittings').get() as { count: number };
  return result.count;
}

export function getSitting(id: string): Sitting | undefined {
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
    FROM sittings
    WHERE id = ?
  `;
  return db.prepare(sql).get(id) as Sitting | undefined;
}

export function getSittingSections(sittingId: string): Section[] {
  const sql = `
    SELECT
      sec.id,
      sec.sitting_id as sittingId,
      sec.section_type as sectionType,
      sec.section_title as sectionTitle,
      sec.content_html as contentHtml,
      sec.content_plain as contentPlain,
      sec.section_order as sectionOrder,
      sec.category,
      sec.source_url as sourceUrl,
      sec.summary,
      m.name as ministry,
      COALESCE(b.ministry_id, sec.ministry_id) as ministryId,
      sec.bill_id as billId
    FROM sections sec
    LEFT JOIN bills b ON sec.bill_id = b.id
    LEFT JOIN ministries m ON COALESCE(b.ministry_id, sec.ministry_id) = m.id
    WHERE sec.sitting_id = ?
    ORDER BY sec.section_order ASC
  `;
  const sections = db.prepare(sql).all(sittingId) as Section[];

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

export function getSittingAttendees(sittingId: string): Attendee[] {
  const sql = `
    SELECT
      m.id,
      m.name,
      sa.present,
      sa.constituency,
      sa.designation
    FROM sitting_attendance sa
    JOIN members m ON sa.member_id = m.id
    WHERE sa.sitting_id = ?
    ORDER BY m.name ASC
  `;
  const results = db.prepare(sql).all(sittingId) as { id: string; name: string; present: number; constituency: string | null; designation: string | null }[];
  return results.map(r => ({
    ...r,
    present: r.present === 1,
  }));
}

export function getSittingBills(sittingId: string): { billId: string; billTitle: string; sectionTitle: string; ministry: string | null; ministryId: string | null; readingTypes: string[]; sectionOrder: number }[] {
  const sql = `
    SELECT
      sec.bill_id as billId,
      b.title as billTitle,
      sec.section_title as sectionTitle,
      m.name as ministry,
      COALESCE(b.ministry_id, sec.ministry_id) as ministryId,
      sec.section_type as sectionType,
      sec.section_order as sectionOrder
    FROM sections sec
    LEFT JOIN bills b ON sec.bill_id = b.id
    LEFT JOIN ministries m ON COALESCE(b.ministry_id, sec.ministry_id) = m.id
    WHERE sec.sitting_id = ? AND sec.bill_id IS NOT NULL
    ORDER BY sec.section_order ASC
  `;
  const results = db.prepare(sql).all(sittingId) as { billId: string; billTitle: string; sectionTitle: string; ministry: string | null; ministryId: string | null; sectionType: string; sectionOrder: number }[];

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
  const latestParl = getLatestParliament();
  const sql = `
    SELECT
      m.id,
      m.name,
      ms.summary,
      COUNT(DISTINCT ss.section_id) as sectionCount
    FROM members m
    LEFT JOIN member_summaries ms ON m.id = ms.member_id
    LEFT JOIN section_speakers ss ON m.id = ss.member_id
    WHERE m.id IN (
      SELECT DISTINCT sa.member_id FROM sitting_attendance sa
      JOIN sittings s ON sa.sitting_id = s.id
      WHERE s.parliament = ?
    )
    GROUP BY m.id
    ORDER BY m.name ASC
    ${limit ? `LIMIT ${limit}` : ''}
    ${offset ? `OFFSET ${offset}` : ''}
  `;
  return db.prepare(sql).all(latestParl) as Member[];
}

export function getMemberCount(): number {
  const latestParl = getLatestParliament();
  const result = db.prepare(`
    SELECT COUNT(DISTINCT sa.member_id) as count
    FROM sitting_attendance sa
    JOIN sittings s ON sa.sitting_id = s.id
    WHERE s.parliament = ?
  `).get(latestParl) as { count: number };
  return result.count;
}

export function getMember(id: string): Member | undefined {
  const sql = `
    SELECT
      m.id,
      m.name,
      ms.summary,
      COUNT(DISTINCT ss.section_id) as sectionCount,
      (SELECT COUNT(*) FROM sitting_attendance WHERE member_id = m.id) as attendanceTotal,
      (SELECT COUNT(*) FROM sitting_attendance WHERE member_id = m.id AND present = 1) as attendancePresent,
      (
        SELECT sa.constituency FROM sitting_attendance sa
        JOIN sittings s ON sa.sitting_id = s.id
        WHERE sa.member_id = m.id
        ORDER BY s.date DESC
        LIMIT 1
      ) as constituency,
      (
        SELECT sa.designation FROM sitting_attendance sa
        JOIN sittings s ON sa.sitting_id = s.id
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
      b.first_reading_sitting_id as firstReadingSittingId,
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
      b.first_reading_sitting_id as firstReadingSittingId,
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
  const latestParl = getLatestParliament();
  const sql = `
    SELECT
      m.id,
      m.name,
      m.acronym,
      (
        SELECT COUNT(*) FROM sections sec
        JOIN sittings sit ON sec.sitting_id = sit.id
        WHERE sec.ministry_id = m.id AND sit.parliament = ?
      ) as sectionCount
    FROM ministries m
    ORDER BY m.name ASC
  `;
  return db.prepare(sql).all(latestParl) as Ministry[];
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
      sec.sitting_id as sittingId,
      s.date as sittingDate,
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
    JOIN sittings s ON sec.sitting_id = s.id
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
      sec.sitting_id as sittingId,
      s.date as sittingDate,
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
    JOIN sittings s ON sec.sitting_id = s.id
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

// Clarifications - sections categorized as clarification
export function getClarifications(limit?: number, offset?: number): Section[] {
  const sql = `
    SELECT
      sec.id,
      sec.sitting_id as sittingId,
      s.date as sittingDate,
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
    JOIN sittings s ON sec.sitting_id = s.id
    LEFT JOIN ministries m ON sec.ministry_id = m.id
    WHERE sec.category = 'clarification'
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

export function getClarificationCount(): number {
  const result = db.prepare(`
    SELECT COUNT(*) as count FROM sections
    WHERE category = 'clarification'
  `).get() as { count: number };
  return result.count;
}

// Get a single section with full content
export function getSection(id: string): Section | undefined {
  const sql = `
    SELECT
      sec.id,
      sec.sitting_id as sittingId,
      s.date as sittingDate,
      s.sitting_no as sittingNo,
      s.url as sittingUrl,
      sec.section_type as sectionType,
      sec.section_title as sectionTitle,
      sec.content_html as contentHtml,
      sec.content_plain as contentPlain,
      sec.section_order as sectionOrder,
      sec.category,
      sec.source_url as sourceUrl,
      sec.summary,
      m.name as ministry,
      COALESCE(b.ministry_id, sec.ministry_id) as ministryId
    FROM sections sec
    JOIN sittings s ON sec.sitting_id = s.id
    LEFT JOIN bills b ON sec.bill_id = b.id
    LEFT JOIN ministries m ON COALESCE(b.ministry_id, sec.ministry_id) = m.id
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
      sec.sitting_id as sittingId,
      s.date as sittingDate,
      s.sitting_no as sittingNo,
      sec.section_type as sectionType,
      sec.section_title as sectionTitle,
      sec.content_plain as contentPlain,
      sec.section_order as sectionOrder,
      sec.category,
      sec.source_url as sourceUrl,
      sec.summary,
      m.name as ministry,
      COALESCE(b.ministry_id, sec.ministry_id) as ministryId,
      sec.bill_id as billId,
      b.title as billTitle
    FROM sections sec
    JOIN sittings s ON sec.sitting_id = s.id
    LEFT JOIN bills b ON sec.bill_id = b.id
    LEFT JOIN ministries m ON COALESCE(b.ministry_id, sec.ministry_id) = m.id
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
  sittingId: string;
  date: string;
  sittingNo: number;
  present: boolean;
}

export function getMemberAttendance(memberId: string): AttendanceRecord[] {
  const sql = `
    SELECT
      sa.sitting_id as sittingId,
      s.date,
      s.sitting_no as sittingNo,
      sa.present
    FROM sitting_attendance sa
    JOIN sittings s ON sa.sitting_id = s.id
    WHERE sa.member_id = ?
    ORDER BY s.date DESC
  `;
  const results = db.prepare(sql).all(memberId) as { sittingId: string; date: string; sittingNo: number; present: number }[];
  return results.map(r => ({
    ...r,
    present: r.present === 1,
  }));
}

// Get current parliament stats for a member (returns null if not in current parliament)
export interface CurrentParliamentStats {
  involvements: number;
  questions: number;
  motions: number;
  bills: number;
  attendancePresent: number;
  attendanceTotal: number;
}

export function getMemberCurrentParliamentStats(memberId: string): CurrentParliamentStats | null {
  const latestParl = getLatestParliament();

  // Check if member is in the current parliament
  const inCurrentParl = db.prepare(`
    SELECT 1 FROM sitting_attendance sa
    JOIN sittings s ON sa.sitting_id = s.id
    WHERE sa.member_id = ? AND s.parliament = ?
    LIMIT 1
  `).get(memberId, latestParl);

  if (!inCurrentParl) return null;

  const involvements = (db.prepare(`
    SELECT COUNT(DISTINCT ss.section_id) as count
    FROM section_speakers ss
    JOIN sections sec ON ss.section_id = sec.id
    JOIN sittings sit ON sec.sitting_id = sit.id
    WHERE ss.member_id = ? AND sit.parliament = ?
  `).get(memberId, latestParl) as { count: number }).count;

  const questions = (db.prepare(`
    SELECT COUNT(DISTINCT ss.section_id) as count
    FROM section_speakers ss
    JOIN sections sec ON ss.section_id = sec.id
    JOIN sittings sit ON sec.sitting_id = sit.id
    WHERE ss.member_id = ? AND sit.parliament = ?
      AND sec.section_type IN ('OA', 'WA', 'WANA')
  `).get(memberId, latestParl) as { count: number }).count;

  const motions = (db.prepare(`
    SELECT COUNT(DISTINCT ss.section_id) as count
    FROM section_speakers ss
    JOIN sections sec ON ss.section_id = sec.id
    JOIN sittings sit ON sec.sitting_id = sit.id
    WHERE ss.member_id = ? AND sit.parliament = ?
      AND sec.category IN ('motion', 'adjournment_motion', 'statement')
  `).get(memberId, latestParl) as { count: number }).count;

  const bills = (db.prepare(`
    SELECT COUNT(DISTINCT ss.section_id) as count
    FROM section_speakers ss
    JOIN sections sec ON ss.section_id = sec.id
    JOIN sittings sit ON sec.sitting_id = sit.id
    WHERE ss.member_id = ? AND sit.parliament = ?
      AND sec.section_type IN ('BI', 'BP')
  `).get(memberId, latestParl) as { count: number }).count;

  const attendanceTotal = (db.prepare(`
    SELECT COUNT(*) as count FROM sitting_attendance sa
    JOIN sittings s ON sa.sitting_id = s.id
    WHERE sa.member_id = ? AND s.parliament = ?
  `).get(memberId, latestParl) as { count: number }).count;

  const attendancePresent = (db.prepare(`
    SELECT COUNT(*) as count FROM sitting_attendance sa
    JOIN sittings s ON sa.sitting_id = s.id
    WHERE sa.member_id = ? AND s.parliament = ? AND sa.present = 1
  `).get(memberId, latestParl) as { count: number }).count;

  return { involvements, questions, motions, bills, attendancePresent, attendanceTotal };
}

// Get all sections for a bill
export interface BillSection {
  id: string;
  sittingId: string;
  sittingDate: string;
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
      sec.sitting_id as sittingId,
      s.date as sittingDate,
      s.sitting_no as sittingNo,
      sec.section_type as sectionType,
      sec.section_title as sectionTitle,
      sec.content_html as contentHtml,
      sec.content_plain as contentPlain,
      sec.source_url as sourceUrl
    FROM sections sec
    JOIN sittings s ON sec.sitting_id = s.id
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
      sec.sitting_id as sittingId,
      s.date as sittingDate,
      s.sitting_no as sittingNo,
      sec.section_type as sectionType,
      sec.section_title as sectionTitle,
      sec.content_plain as contentPlain,
      sec.section_order as sectionOrder,
      sec.category,
      sec.source_url as sourceUrl,
      sec.summary,
      m.name as ministry,
      COALESCE(b.ministry_id, sec.ministry_id) as ministryId,
      sec.bill_id as billId
    FROM sections sec
    JOIN sittings s ON sec.sitting_id = s.id
    LEFT JOIN bills b ON sec.bill_id = b.id
    LEFT JOIN ministries m ON COALESCE(b.ministry_id, sec.ministry_id) = m.id
    WHERE COALESCE(b.ministry_id, sec.ministry_id) = ?
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
      b.first_reading_sitting_id as firstReadingSittingId,
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
// Scoped to latest parliament only — stats are also parliament-scoped
export function getMembersWithInfo(limit?: number, offset?: number): Member[] {
  const latestParl = getLatestParliament();
  const sql = `
    SELECT
      m.id,
      m.name,
      ms.summary,
      (
        SELECT COUNT(DISTINCT ss2.section_id) FROM section_speakers ss2
        JOIN sections sec ON ss2.section_id = sec.id
        JOIN sittings sit ON sec.sitting_id = sit.id
        WHERE ss2.member_id = m.id AND sit.parliament = ?
      ) as sectionCount,
      (
        SELECT COUNT(*) FROM sitting_attendance sa2
        JOIN sittings s2 ON sa2.sitting_id = s2.id
        WHERE sa2.member_id = m.id AND s2.parliament = ?
      ) as attendanceTotal,
      (
        SELECT COUNT(*) FROM sitting_attendance sa3
        JOIN sittings s3 ON sa3.sitting_id = s3.id
        WHERE sa3.member_id = m.id AND sa3.present = 1 AND s3.parliament = ?
      ) as attendancePresent,
      (
        SELECT sa.constituency FROM sitting_attendance sa
        JOIN sittings s ON sa.sitting_id = s.id
        WHERE sa.member_id = m.id
        ORDER BY s.date DESC
        LIMIT 1
      ) as constituency,
      (
        SELECT sa.designation FROM sitting_attendance sa
        JOIN sittings s ON sa.sitting_id = s.id
        WHERE sa.member_id = m.id
        ORDER BY s.date DESC
        LIMIT 1
      ) as designation
    FROM members m
    LEFT JOIN member_summaries ms ON m.id = ms.member_id
    WHERE m.id IN (
      SELECT DISTINCT sa.member_id FROM sitting_attendance sa
      JOIN sittings s ON sa.sitting_id = s.id
      WHERE s.parliament = ?
    )
    GROUP BY m.id
    ORDER BY m.name ASC
    ${limit ? `LIMIT ${limit}` : ''}
    ${offset ? `OFFSET ${offset}` : ''}
  `;
  return db.prepare(sql).all(latestParl, latestParl, latestParl, latestParl) as Member[];
}

// Get all sections (for static path generation)
export function getAllSections(): { id: string; sectionTitle: string }[] {
  const sql = `SELECT id, section_title as sectionTitle FROM sections`;
  return db.prepare(sql).all() as { id: string; sectionTitle: string }[];
}

// Get ALL members with info (unscoped, for static path generation)
export function getAllMembersWithInfo(): Member[] {
  const sql = `
    SELECT
      m.id,
      m.name,
      ms.summary,
      COUNT(DISTINCT ss.section_id) as sectionCount,
      (SELECT COUNT(*) FROM sitting_attendance WHERE member_id = m.id) as attendanceTotal,
      (SELECT COUNT(*) FROM sitting_attendance WHERE member_id = m.id AND present = 1) as attendancePresent,
      (
        SELECT sa.constituency FROM sitting_attendance sa
        JOIN sittings s ON sa.sitting_id = s.id
        WHERE sa.member_id = m.id
        ORDER BY s.date DESC
        LIMIT 1
      ) as constituency,
      (
        SELECT sa.designation FROM sitting_attendance sa
        JOIN sittings s ON sa.sitting_id = s.id
        WHERE sa.member_id = m.id
        ORDER BY s.date DESC
        LIMIT 1
      ) as designation
    FROM members m
    LEFT JOIN member_summaries ms ON m.id = ms.member_id
    LEFT JOIN section_speakers ss ON m.id = ss.member_id
    GROUP BY m.id
    ORDER BY m.name ASC
  `;
  return db.prepare(sql).all() as Member[];
}

// Get ALL ministries (unscoped, for static path generation)
export function getAllMinistries(): Ministry[] {
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

// Get latest parliament number
export function getLatestParliament(): number {
  const result = db.prepare('SELECT MAX(parliament) as parliament FROM sittings').get() as { parliament: number };
  return result.parliament;
}

// Stats for home page (all scoped to latest parliament)
export function getStats(): {
  sittingCount: number; memberCount: number; billCount: number;
  sectionCount: number; questionCount: number; motionCount: number;
} {
  const latestParl = getLatestParliament();
  const sittingCount = (db.prepare('SELECT COUNT(*) as count FROM sittings WHERE parliament = ?').get(latestParl) as { count: number }).count;
  const memberCount = getMemberCount();
  const billCount = (db.prepare(`
    SELECT COUNT(*) as count FROM bills b
    JOIN sittings s ON b.first_reading_sitting_id = s.id
    WHERE s.parliament = ?
  `).get(latestParl) as { count: number }).count;
  const sectionCount = (db.prepare(`
    SELECT COUNT(*) as count FROM sections sec
    JOIN sittings s ON sec.sitting_id = s.id
    WHERE s.parliament = ?
  `).get(latestParl) as { count: number }).count;
  const questionCount = (db.prepare(`
    SELECT COUNT(*) as count FROM sections sec
    JOIN sittings s ON sec.sitting_id = s.id
    WHERE sec.section_type IN ('OA', 'WA', 'WANA')
      AND sec.section_type NOT IN ('BI', 'BP')
      AND s.parliament = ?
  `).get(latestParl) as { count: number }).count;
  const motionCount = (db.prepare(`
    SELECT COUNT(*) as count FROM sections sec
    JOIN sittings s ON sec.sitting_id = s.id
    WHERE sec.category IN ('motion', 'adjournment_motion')
      AND s.parliament = ?
  `).get(latestParl) as { count: number }).count;

  return { sittingCount, memberCount, billCount, sectionCount, questionCount, motionCount };
}

// Get the most recent sitting for masthead info
export function getLatestSitting(): Sitting | undefined {
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
    FROM sittings
    ORDER BY date DESC
    LIMIT 1
  `;
  return db.prepare(sql).get() as Sitting | undefined;
}

// Get count of sittings in current year (scoped to latest parliament)
export function getSittingsThisYear(): number {
  const latestParl = getLatestParliament();
  const currentYear = new Date().getFullYear();
  const result = db.prepare(`
    SELECT COUNT(*) as count FROM sittings
    WHERE strftime('%Y', date) = ? AND parliament = ?
  `).get(String(currentYear), latestParl) as { count: number };
  return result.count;
}

// Get recent bills that have had readings (for ticker/featured)
export interface RecentBillReading {
  billId: string;
  billTitle: string;
  sectionType: string;
  sittingDate: string;
  ministry: string | null;
}

export function getRecentBillReadings(limit: number = 5): RecentBillReading[] {
  const sql = `
    SELECT
      billId,
      billTitle,
      sectionType,
      sittingDate,
      ministry
    FROM (
      SELECT
        b.id as billId,
        b.title as billTitle,
        sec.section_type as sectionType,
        s.date as sittingDate,
        m.name as ministry,
        ROW_NUMBER() OVER (
          PARTITION BY b.id
          ORDER BY s.date DESC, sec.section_order DESC
        ) as rowNumber
      FROM sections sec
      JOIN sittings s ON sec.sitting_id = s.id
      JOIN bills b ON sec.bill_id = b.id
      LEFT JOIN ministries m ON b.ministry_id = m.id
      WHERE sec.bill_id IS NOT NULL
    )
    WHERE rowNumber = 1
    ORDER BY sittingDate DESC
    LIMIT ?
  `;
  return db.prepare(sql).all(limit) as RecentBillReading[];
}

// Get latest question with asker info
export interface LatestQuestion {
  id: string;
  sectionTitle: string;
  sittingDate: string;
  askerName: string | null;
  askerId: string | null;
  ministry: string | null;
}

export function getLatestQuestion(): LatestQuestion | undefined {
  const sql = `
    SELECT
      sec.id,
      sec.section_title as sectionTitle,
      s.date as sittingDate,
      m.name as ministry
    FROM sections sec
    JOIN sittings s ON sec.sitting_id = s.id
    LEFT JOIN ministries m ON sec.ministry_id = m.id
    WHERE sec.section_type IN ('OA', 'WA', 'WANA')
    ORDER BY s.date DESC, sec.section_order ASC
    LIMIT 1
  `;
  const question = db.prepare(sql).get() as { id: string; sectionTitle: string; sittingDate: string; ministry: string | null } | undefined;

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
      s.date as sittingDate,
      m.name as ministry
    FROM sections sec
    JOIN sittings s ON sec.sitting_id = s.id
    JOIN bills b ON sec.bill_id = b.id
    LEFT JOIN ministries m ON b.ministry_id = m.id
    WHERE sec.bill_id IS NOT NULL
      AND s.date = (SELECT MAX(date) FROM sittings)
    ORDER BY sec.section_order ASC
  `;
  return db.prepare(sql).all() as RecentBillReading[];
}

// Get recent motions for ticker
export interface RecentMotion {
  id: string;
  sectionTitle: string;
  sittingDate: string;
}

export function getRecentMotions(limit: number = 3): RecentMotion[] {
  const sql = `
    SELECT
      sec.id,
      sec.section_title as sectionTitle,
      s.date as sittingDate
    FROM sections sec
    JOIN sittings s ON sec.sitting_id = s.id
    WHERE sec.category IN ('motion', 'adjournment_motion')
    ORDER BY s.date DESC, sec.section_order ASC
    LIMIT ?
  `;
  return db.prepare(sql).all(limit) as RecentMotion[];
}

export default db;
