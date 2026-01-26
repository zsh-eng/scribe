// src/app/api/members/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'

export async function GET(request: NextRequest) {
    const searchParams = request.nextUrl.searchParams
    const search = searchParams.get('search') || ''
    const limit = parseInt(searchParams.get('limit') || '100')

    let sql = `
    SELECT 
      m.id,
      m.name,
      ms.summary,
      COUNT(DISTINCT ss.section_id) as "sectionCount"
    FROM members m
    LEFT JOIN member_summaries ms ON m.id = ms.member_id
    LEFT JOIN section_speakers ss ON m.id = ss.member_id
    WHERE 1=1
  `

    const params: (string | number)[] = []
    let paramCount = 1

    if (search) {
        sql += ` AND m.name ILIKE $${paramCount}`
        params.push(`%${search}%`)
        paramCount++
    }

    sql += ` GROUP BY m.id, m.name, ms.summary
           ORDER BY m.name ASC
           LIMIT $${paramCount}`
    params.push(limit)

    try {
        const result = await query(sql, params)
        return NextResponse.json(result.rows)
    } catch (error) {
        console.error('Database error:', error)
        return NextResponse.json(
            { error: 'Failed to fetch members' },
            { status: 500 }
        )
    }
}
