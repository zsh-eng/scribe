import db from './connection';
import type { Speaker, Section } from './types';

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

export function getAllSections(): { id: string; sectionTitle: string }[] {
  const sql = `SELECT id, section_title as sectionTitle FROM sections`;
  return db.prepare(sql).all() as { id: string; sectionTitle: string }[];
}

// Preserve sitting-card destinations for statements outside the dedicated lists.
// This query adds detail routes only; it does not change question totals or data.
export function getStatementDetailPaths(): { id: string; sectionTitle: string }[] {
  return db.prepare(`
    SELECT sec.id, sec.section_title as sectionTitle
    FROM sections sec
    JOIN sittings s ON sec.sitting_id = s.id
    WHERE sec.section_type IN ('OS', 'WS')
      AND COALESCE(sec.category, '') NOT IN ('motion', 'adjournment_motion', 'clarification')
  `).all() as { id: string; sectionTitle: string }[];
}
