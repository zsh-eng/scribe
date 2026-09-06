import db from './connection';
import type { Sitting, Speaker, Section, Attendee } from './types';

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

export function getParliaments(): number[] {
  const rows = db.prepare('SELECT DISTINCT parliament FROM sittings ORDER BY parliament DESC').all() as { parliament: number }[];
  return rows.map(r => r.parliament);
}

export function getLatestParliament(): number {
  const result = db.prepare('SELECT MAX(parliament) as parliament FROM sittings').get() as { parliament: number };
  return result.parliament;
}
