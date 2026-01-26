// src/app/api/ministries/[id]/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'

export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ id: string }> }
) {
    const { id } = await params

    try {
        // Get ministry info
        const ministryResult = await query(
            `SELECT id, name, acronym FROM ministries WHERE id = $1`,
            [id]
        )

        if (ministryResult.rows.length === 0) {
            return NextResponse.json({ error: 'Ministry not found' }, { status: 404 })
        }

        const ministry = ministryResult.rows[0]

        // Get sections under this ministry
        const sectionsResult = await query(
            `SELECT 
        s.id,
        s.section_type as "sectionType",
        s.section_title as "sectionTitle",
        s.content_plain as "contentPlain",
        sess.date as "sessionDate",
        ARRAY_AGG(DISTINCT mem.name ORDER BY mem.name) as speakers
       FROM sections s
       JOIN sessions sess ON s.session_id = sess.id
       LEFT JOIN section_speakers ss ON s.id = ss.section_id
       LEFT JOIN members mem ON ss.member_id = mem.id
       WHERE s.ministry_id = $1
       GROUP BY s.id, s.section_type, s.section_title, s.content_plain, sess.date, s.section_order
       ORDER BY sess.date DESC, s.section_order ASC
       LIMIT 100`,
            [id]
        )

        return NextResponse.json({
            ...ministry,
            sections: sectionsResult.rows
        })
    } catch (error) {
        console.error('Database error:', error)
        return NextResponse.json(
            { error: 'Failed to fetch ministry' },
            { status: 500 }
        )
    }
}
