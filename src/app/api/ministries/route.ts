// src/app/api/ministries/route.ts
import { NextResponse } from 'next/server'
import { query } from '@/lib/db'

export async function GET() {
    try {
        const result = await query(`
      SELECT 
        m.id,
        m.name,
        m.acronym,
        COUNT(s.id) as "sectionCount"
      FROM ministries m
      LEFT JOIN sections s ON m.id = s.ministry_id
      GROUP BY m.id, m.name, m.acronym
      ORDER BY m.name ASC
    `)
        return NextResponse.json(result.rows)
    } catch (error) {
        console.error('Database error:', error)
        return NextResponse.json(
            { error: 'Failed to fetch ministries' },
            { status: 500 }
        )
    }
}
