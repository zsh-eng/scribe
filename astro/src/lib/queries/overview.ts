import db from './connection';
import type { Sitting, RecentBillReading, LatestQuestion, RecentMotion } from './types';
import { getLatestParliament } from './sittings';
import { getMemberCount } from './members';

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

export function getSittingsThisYear(): number {
  const latestParl = getLatestParliament();
  const currentYear = new Date().getFullYear();
  const result = db.prepare(`
    SELECT COUNT(*) as count FROM sittings
    WHERE strftime('%Y', date) = ? AND parliament = ?
  `).get(String(currentYear), latestParl) as { count: number };
  return result.count;
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
