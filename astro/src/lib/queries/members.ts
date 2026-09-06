import db from './connection';
import type { Member, Speaker, Section, AttendanceRecord, CurrentParliamentStats, ParliamentStats, MemberMinistryStats } from './types';
import { getLatestParliament } from './sittings';

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

export function getMemberParliamentStats(memberId: string): ParliamentStats[] {
  // Get all parliaments this member attended
  const parliaments = db.prepare(`
    SELECT DISTINCT s.parliament
    FROM sitting_attendance sa
    JOIN sittings s ON sa.sitting_id = s.id
    WHERE sa.member_id = ?
    ORDER BY s.parliament DESC
  `).all(memberId) as { parliament: number }[];

  return parliaments.map(({ parliament }) => {
    const involvements = (db.prepare(`
      SELECT COUNT(DISTINCT ss.section_id) as count
      FROM section_speakers ss
      JOIN sections sec ON ss.section_id = sec.id
      JOIN sittings sit ON sec.sitting_id = sit.id
      WHERE ss.member_id = ? AND sit.parliament = ?
    `).get(memberId, parliament) as { count: number }).count;

    const oralQuestions = (db.prepare(`
      SELECT COUNT(DISTINCT ss.section_id) as count
      FROM section_speakers ss
      JOIN sections sec ON ss.section_id = sec.id
      JOIN sittings sit ON sec.sitting_id = sit.id
      WHERE ss.member_id = ? AND sit.parliament = ?
        AND sec.section_type = 'OA'
    `).get(memberId, parliament) as { count: number }).count;

    const writtenQuestions = (db.prepare(`
      SELECT COUNT(DISTINCT ss.section_id) as count
      FROM section_speakers ss
      JOIN sections sec ON ss.section_id = sec.id
      JOIN sittings sit ON sec.sitting_id = sit.id
      WHERE ss.member_id = ? AND sit.parliament = ?
        AND sec.section_type = 'WA'
    `).get(memberId, parliament) as { count: number }).count;

    const unansweredQuestions = (db.prepare(`
      SELECT COUNT(DISTINCT ss.section_id) as count
      FROM section_speakers ss
      JOIN sections sec ON ss.section_id = sec.id
      JOIN sittings sit ON sec.sitting_id = sit.id
      WHERE ss.member_id = ? AND sit.parliament = ?
        AND sec.section_type = 'WANA'
    `).get(memberId, parliament) as { count: number }).count;

    const motions = (db.prepare(`
      SELECT COUNT(DISTINCT ss.section_id) as count
      FROM section_speakers ss
      JOIN sections sec ON ss.section_id = sec.id
      JOIN sittings sit ON sec.sitting_id = sit.id
      WHERE ss.member_id = ? AND sit.parliament = ?
        AND sec.category IN ('motion', 'adjournment_motion', 'statement')
    `).get(memberId, parliament) as { count: number }).count;

    const bills = (db.prepare(`
      SELECT COUNT(DISTINCT sec.bill_id) as count
      FROM section_speakers ss
      JOIN sections sec ON ss.section_id = sec.id
      JOIN sittings sit ON sec.sitting_id = sit.id
      WHERE ss.member_id = ? AND sit.parliament = ?
        AND sec.section_type IN ('BI', 'BP')
    `).get(memberId, parliament) as { count: number }).count;

    const attendanceTotal = (db.prepare(`
      SELECT COUNT(*) as count FROM sitting_attendance sa
      JOIN sittings s ON sa.sitting_id = s.id
      WHERE sa.member_id = ? AND s.parliament = ?
    `).get(memberId, parliament) as { count: number }).count;

    const attendancePresent = (db.prepare(`
      SELECT COUNT(*) as count FROM sitting_attendance sa
      JOIN sittings s ON sa.sitting_id = s.id
      WHERE sa.member_id = ? AND s.parliament = ? AND sa.present = 1
    `).get(memberId, parliament) as { count: number }).count;

    return { parliament, involvements, oralQuestions, writtenQuestions, unansweredQuestions, motions, bills, attendancePresent, attendanceTotal };
  });
}

export function getMemberMinistryStats(memberId: string): MemberMinistryStats[] {
  const sql = `
    SELECT
      m.id as ministryId,
      m.name as ministryName,
      COUNT(DISTINCT sec.id) as total,
      COUNT(DISTINCT CASE WHEN sec.section_type = 'OA' THEN sec.id END) as oralQuestions,
      COUNT(DISTINCT CASE WHEN sec.section_type = 'WA' THEN sec.id END) as writtenQuestions,
      COUNT(DISTINCT CASE WHEN sec.section_type = 'WANA' THEN sec.id END) as unansweredQuestions,
      COUNT(DISTINCT CASE WHEN sec.category IN ('motion', 'adjournment_motion', 'statement') THEN sec.id END) as motions,
      COUNT(DISTINCT CASE WHEN sec.section_type IN ('BI', 'BP') THEN sec.bill_id END) as bills
    FROM ministries m
    LEFT JOIN (
      SELECT sec.id, sec.section_type, sec.category, sec.bill_id, COALESCE(b.ministry_id, sec.ministry_id) as ministry_id
      FROM sections sec
      JOIN section_speakers ss ON sec.id = ss.section_id
      LEFT JOIN bills b ON sec.bill_id = b.id
      WHERE ss.member_id = ?
    ) sec ON sec.ministry_id = m.id
    GROUP BY m.id
    ORDER BY total DESC, m.name ASC
  `;
  return db.prepare(sql).all(memberId) as MemberMinistryStats[];
}

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

export function getMembersForParliament(parliament: number): Member[] {
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
        WHERE sa.member_id = m.id AND s.parliament = ?
        ORDER BY s.date DESC
        LIMIT 1
      ) as constituency,
      (
        SELECT sa.designation FROM sitting_attendance sa
        JOIN sittings s ON sa.sitting_id = s.id
        WHERE sa.member_id = m.id AND s.parliament = ?
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
  `;
  return db.prepare(sql).all(parliament, parliament, parliament, parliament, parliament, parliament) as Member[];
}

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
