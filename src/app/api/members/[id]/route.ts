// src/app/api/members/[id]/route.ts
import { NextRequest, NextResponse } from 'next/server'
import { query } from '@/lib/db'

export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ id: string }> }
) {
    const { id } = await params

    try {
        // Get member info with summary
        const memberResult = await query(
            `SELECT m.id, m.name, ms.summary
       FROM members m
       LEFT JOIN member_summaries ms ON m.id = ms.member_id
       WHERE m.id = $1`,
            [id]
        )

        if (memberResult.rows.length === 0) {
            return NextResponse.json({ error: 'Member not found' }, { status: 404 })
        }

        const member = memberResult.rows[0]

        // Get sections this member spoke in
        const sectionsResult = await query(
            `SELECT 
        s.id,
        s.section_type as "sectionType",
        s.section_title as "sectionTitle",
        s.content_plain as "contentPlain",
        m.acronym as ministry,
        sess.date as "sessionDate",
        ss.designation,
        ss.constituency
       FROM section_speakers ss
       JOIN sections s ON ss.section_id = s.id
       JOIN sessions sess ON s.session_id = sess.id
       LEFT JOIN ministries m ON s.ministry_id = m.id
       WHERE ss.member_id = $1
       ORDER BY sess.date DESC, s.section_order ASC
       LIMIT 100`,
            [id]
        )

        return NextResponse.json({
            ...member,
            sections: sectionsResult.rows
        })
    } catch (error) {
        console.error('Database error:', error)
        return NextResponse.json(
            { error: 'Failed to fetch member' },
            { status: 500 }
        )
    }
}
