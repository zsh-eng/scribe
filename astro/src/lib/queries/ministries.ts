import db from './connection';
import type { Ministry, Speaker, Section, Bill, MinistryParliamentStats } from './types';
import { getLatestParliament } from './sittings';

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

export function getMinistryParliamentStats(ministryId: string): MinistryParliamentStats[] {
  const sql = `
    SELECT
      sit.parliament,
      COUNT(DISTINCT sec.id) as involvements,
      COUNT(DISTINCT CASE WHEN sec.section_type = 'OA' THEN sec.id END) as oralQuestions,
      COUNT(DISTINCT CASE WHEN sec.section_type = 'WA' THEN sec.id END) as writtenQuestions,
      COUNT(DISTINCT CASE WHEN sec.section_type = 'WANA' THEN sec.id END) as unansweredQuestions,
      COUNT(DISTINCT CASE WHEN sec.category IN ('motion', 'adjournment_motion', 'statement') THEN sec.id END) as motions,
      COUNT(DISTINCT CASE WHEN sec.section_type IN ('BI', 'BP') THEN sec.bill_id END) as bills
    FROM sections sec
    JOIN sittings sit ON sec.sitting_id = sit.id
    LEFT JOIN bills b ON sec.bill_id = b.id
    WHERE COALESCE(b.ministry_id, sec.ministry_id) = ?
    GROUP BY sit.parliament
    ORDER BY sit.parliament DESC
  `;
  return db.prepare(sql).all(ministryId) as MinistryParliamentStats[];
}

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
