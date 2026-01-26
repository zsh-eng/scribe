// src/app/api/sections/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const search = searchParams.get('search') || ''
  const ministry = searchParams.get('ministry')
  const sectionType = searchParams.get('sectionType')
  const memberId = searchParams.get('memberId')
  const limit = parseInt(searchParams.get('limit') || '50')

  let sql = `
    SELECT 
      s.id,
      s.session_id as "sessionId",
      s.section_type as "sectionType",
      s.section_title as "sectionTitle",
      s.content_html as "contentHtml",
      s.content_plain as "contentPlain",
      s.section_order as "sectionOrder",
      m.acronym as ministry,
      m.id as "ministryId",
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
    WHERE 1=1
  `

  const params: (string | number)[] = []
  let paramCount = 1

  if (search) {
    sql += ` AND (
      to_tsvector('english', s.content_plain) @@ plainto_tsquery('english', $${paramCount}) OR 
      s.section_title ILIKE $${paramCount + 1}
    )`
    params.push(search, `%${search}%`)
    paramCount += 2
  }

  if (ministry && ministry !== 'all') {
    sql += ` AND m.acronym = $${paramCount}`
    params.push(ministry)
    paramCount++
  }

  if (sectionType && sectionType !== 'all') {
    sql += ` AND s.section_type = $${paramCount}`
    params.push(sectionType)
    paramCount++
  }

  if (memberId) {
    sql += ` AND ss.member_id = $${paramCount}`
    params.push(memberId)
    paramCount++
  }

  sql += ` GROUP BY s.id, s.session_id, s.section_type, s.section_title, s.content_html, 
           s.content_plain, s.section_order, m.acronym, m.id, sess.date, sess.sitting_no
           ORDER BY sess.date DESC, s.section_order ASC 
           LIMIT $${paramCount}`
  params.push(limit)

  try {
    const result = await query(sql, params)
    return NextResponse.json(result.rows)
  } catch (error) {
    console.error('Database error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch sections' },
      { status: 500 }
    )
  }
}
