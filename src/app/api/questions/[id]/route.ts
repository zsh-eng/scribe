// src/app/api/questions/[id]/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params

  try {
    const result = await query(
      `SELECT 
              s.id,
              s.session_id as "sessionId",
              s.section_type as "sectionType",
              s.section_title as "sectionTitle",
              s.content_html as "contentHtml",
              s.content_plain as "contentPlain",
              s.section_order as "sectionOrder",
              s.source_url as "sourceUrl",
              m.id as "ministryId",
              m.acronym as ministry,
              m.name as "ministryName",
              sess.date as "sessionDate",
              sess.sitting_no as "sittingNo",
              COALESCE(
                json_agg(
                  json_build_object(
                    'memberId', mem.id,
                    'name', mem.name,
                    'constituency', ss.constituency,
                    'designation', ss.designation
                  ) ORDER BY mem.name
                ) FILTER (WHERE mem.id IS NOT NULL),
                '[]'
              ) as speakers
            FROM sections s
            JOIN sessions sess ON s.session_id = sess.id
            LEFT JOIN ministries m ON s.ministry_id = m.id
            LEFT JOIN section_speakers ss ON s.id = ss.section_id
            LEFT JOIN members mem ON ss.member_id = mem.id
            WHERE s.id = $1
            GROUP BY s.id, s.session_id, s.section_type, s.section_title, s.content_html,
                     s.content_plain, s.section_order, s.source_url, m.id, m.acronym, m.name, sess.date, sess.sitting_no`,
      [id]
    )

    if (result.rows.length === 0) {
      return NextResponse.json({ error: 'Question not found' }, { status: 404 })
    }

    return NextResponse.json(result.rows[0])
  } catch (error) {
    console.error('Database error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch question' },
      { status: 500 }
    )
  }
}
