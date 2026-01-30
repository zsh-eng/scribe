import QuestionCard from '@/components/QuestionCard'
import QuestionFilters from '@/components/QuestionFilters'
import { query } from '@/lib/db'
import type { Section, Speaker } from '@/types'

export default async function MotionsPage({
    searchParams,
}: {
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
    const params = await searchParams
    const search = typeof params.search === 'string' ? params.search : ''
    const limit = 50

    let sql = `
        SELECT 
            s.id,
            s.session_id as "sessionId",
            s.section_type as "sectionType",
            s.section_title as "sectionTitle",
            s.category,
            LEFT(s.content_plain, 300) as "contentSnippet",
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
        WHERE s.category IN ('motion', 'adjournment_motion')
    `

    const sqlParams: (string | number)[] = []
    let paramCount = 1

    if (search) {
        sql += ` AND (
            to_tsvector('english', s.content_plain) @@ plainto_tsquery('english', $${paramCount}) OR 
            s.section_title ILIKE $${paramCount + 1}
        )`
        sqlParams.push(search, `%${search}%`)
        paramCount += 2
    }

    sql += ` GROUP BY s.id, s.session_id, s.section_type, s.section_title, 
             s.category, s.section_order, m.acronym, m.id, sess.date, sess.sitting_no
             ORDER BY sess.date DESC, s.section_order ASC 
             LIMIT $${paramCount}`
    sqlParams.push(limit)

    const result = await query(sql, sqlParams)
    const motions: Section[] = result.rows.map(row => ({
        ...row,
        speakers: row.speakers as Speaker[]
    }))

    return (
        <div>
            <header className="mb-8">
                <h1 className="mb-2 text-3xl font-bold text-zinc-900">
                    Motions
                </h1>
                <p className="text-zinc-600">
                    Browse and search parliamentary motions, including adjournment motions and ministerial statements.
                </p>
            </header>

            <QuestionFilters
                initialSearch={search}
                placeholder="Search motions..."
            />

            <section>
                <h2 className="mb-4 text-xl font-semibold text-zinc-900">
                    {search ? `Search Results for "${search}"` : 'Recent Motions'}
                </h2>

                {motions.length === 0 ? (
                    <p className="py-12 text-center text-zinc-500">
                        {search ? `No motions found matching "${search}"` : 'No motions found'}
                    </p>
                ) : (
                    <div className="grid gap-4 md:grid-cols-2">
                        {motions.map((motion) => (
                            <QuestionCard key={motion.id} question={motion} showContent={false} />
                        ))}
                    </div>
                )}
            </section>
        </div>
    )
}
