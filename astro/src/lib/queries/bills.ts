import db from './connection';
import type { Speaker, Bill, BillSection } from './types';

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
