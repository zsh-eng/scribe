// src/app/api/sessions/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'

export async function GET(request: NextRequest) {
    const searchParams = request.nextUrl.searchParams
    const limit = parseInt(searchParams.get('limit') || '50')
    const startDate = searchParams.get('startDate')
    const endDate = searchParams.get('endDate')

    try {
        let sql = `
      SELECT 
        s.id,
        s.date,
        s.sitting_no as "sittingNo",
        s.parliament,
        s.session_no as "sessionNo",
        s.volume_no as "volumeNo",
        s.format,
        s.url,
        s.summary,
        COUNT(sec.id) as "questionCount"
      FROM sessions s
      LEFT JOIN sections sec ON s.id = sec.session_id
      WHERE 1=1
    `
        const params: (string | number)[] = []
        let paramCount = 1

        if (startDate) {
            sql += ` AND s.date >= $${paramCount}`
            params.push(startDate)
            paramCount++
        }

        if (endDate) {
            sql += ` AND s.date <= $${paramCount}`
            params.push(endDate)
            paramCount++
        }

        sql += `
      GROUP BY s.id
      ORDER BY s.date DESC
      LIMIT $${paramCount}
    `
        params.push(limit)

        const result = await query(sql, params)
        return NextResponse.json(result.rows)
    } catch (error) {
        console.error('Database error:', error)
        return NextResponse.json(
            { error: 'Failed to fetch sessions' },
            { status: 500 }
        )
    }
}
