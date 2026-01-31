import Link from 'next/link'
import MemberCard from '@/components/MemberCard'
import MemberFilters from '@/components/MemberFilters'
import { query } from '@/lib/db'
import ServerPagination from '@/components/ServerPagination'
import type { Member } from '@/types'

export default async function MembersPage({
    searchParams,
}: {
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
    const params = await searchParams
    const search = typeof params.search === 'string' ? params.search : ''
    const constituency = typeof params.constituency === 'string' ? params.constituency : ''
    const sort = typeof params.sort === 'string' ? params.sort : 'name'
    const pageNum = typeof params.page === 'string' ? parseInt(params.page) : 1
    const limit = 20
    const offset = (pageNum - 1) * limit

    // Fetch available constituencies for filters
    const constResult = await query('SELECT DISTINCT constituency FROM member_list_view WHERE constituency IS NOT NULL ORDER BY constituency')
    const constituencies = constResult.rows.map(r => r.constituency)

    // Build query for members
    const sqlParams: (string | number)[] = []
    let paramCount = 1
    let whereClause = '1=1'

    if (search) {
        whereClause += ` AND (
            mv.name ILIKE $${paramCount} OR 
            mv.constituency ILIKE $${paramCount} OR 
            mv.designation ILIKE $${paramCount}
        )`
        sqlParams.push(`%${search}%`)
        paramCount++
    }

    if (constituency) {
        whereClause += ` AND mv.constituency = $${paramCount}`
        sqlParams.push(constituency)
        paramCount++
    }

    // Determine sort order
    let orderBy = 'mv.name ASC'
    if (sort === 'involvements') {
        orderBy = 'mv.section_count DESC, mv.name ASC'
    }

    const sql = `
      SELECT 
        mv.id,
        mv.name,
        mv.summary,
        mv.section_count as "sectionCount",
        mv.constituency,
        mv.designation,
        COUNT(*) OVER() as "totalCount"
      FROM member_list_view mv
      WHERE ${whereClause}
      ORDER BY ${orderBy}
      LIMIT $${paramCount} OFFSET $${paramCount + 1}
    `

    const dataResult = await query(sql, [...sqlParams, limit, offset])
    const totalCount = dataResult.rows.length > 0 ? parseInt(dataResult.rows[0].totalCount) : 0
    const totalPages = Math.ceil(totalCount / limit)
    const members: Member[] = dataResult.rows.map(({ totalCount, ...rest }) => ({
        ...rest,
        sectionCount: parseInt(rest.sectionCount)
    }))

    return (
        <div>
            <section className="mb-8">
                <h1 className="mb-2 text-3xl font-bold text-zinc-900">
                    Members of Parliament
                </h1>
                <p className="mb-4 text-zinc-600">
                    Browse profiles of Members of Parliament.
                </p>
                <MemberFilters
                    constituencies={constituencies}
                    initialSearch={search}
                    initialConstituency={constituency}
                    initialSort={sort}
                />
            </section>

            {members.length === 0 ? (
                <p className="py-12 text-center text-zinc-500">
                    No members found
                </p>
            ) : (
                <>
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {members.map((member) => (
                            <MemberCard key={member.id} member={member} />
                        ))}
                    </div>

                    {/* Pagination Controls */}
                    <ServerPagination
                        currentPage={pageNum}
                        totalPages={totalPages}
                        baseUrl="/members"
                    />
                </>
            )}
        </div>
    )
}
