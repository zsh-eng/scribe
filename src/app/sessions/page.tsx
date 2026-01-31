import Link from 'next/link'
import { query } from '@/lib/db'
import SessionFilters from '@/components/SessionFilters'
import ServerPagination from '@/components/ServerPagination'

interface Session {
    id: string
    date: string
    sittingNo: number
    parliament: number
    sessionNo: number
    volumeNo: number
    format: string
    url: string
    questionCount: number
}

// Helper to format ordinal numbers (1st, 2nd, 3rd, etc.)
function getOrdinal(n: number): string {
    const s = ['th', 'st', 'nd', 'rd']
    const v = n % 100
    return n + (s[(v - 20) % 10] || s[v] || s[0])
}

export default async function SessionsPage({
    searchParams,
}: {
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
    const params = await searchParams
    const startDate = typeof params.startDate === 'string' ? params.startDate : ''
    const endDate = typeof params.endDate === 'string' ? params.endDate : ''
    const pageNum = typeof params.page === 'string' ? parseInt(params.page) : 1
    const limit = 20
    const offset = (pageNum - 1) * limit

    // Fetch data directly from DB
    const sqlParams: (string | number)[] = []
    let paramCount = 1
    let whereClause = '1=1'

    if (startDate) {
        whereClause += ` AND s.date >= $${paramCount}`
        sqlParams.push(startDate)
        paramCount++
    }

    if (endDate) {
        whereClause += ` AND s.date <= $${paramCount}`
        sqlParams.push(endDate)
        paramCount++
    }

    // Get total count
    const countSql = `SELECT COUNT(*) as total FROM sessions s WHERE ${whereClause}`
    const countResult = await query(countSql, sqlParams)
    const totalCount = parseInt(countResult.rows[0].total)
    const totalPages = Math.ceil(totalCount / limit)

    // Get data
    const dataSql = `
        SELECT 
            s.id,
            s.date,
            s.sitting_no as "sittingNo",
            s.parliament,
            s.session_no as "sessionNo",
            s.volume_no as "volumeNo",
            s.format,
            s.url,
            COUNT(sec.id) as "questionCount"
        FROM sessions s
        LEFT JOIN sections sec ON s.id = sec.session_id
        WHERE ${whereClause}
        GROUP BY s.id
        ORDER BY s.date DESC
        LIMIT $${paramCount} OFFSET $${paramCount + 1}
    `
    const dataResult = await query(dataSql, [...sqlParams, limit, offset])
    const sessions: Session[] = dataResult.rows

    return (
        <div>
            <h1 className="mb-2 text-3xl font-bold text-zinc-900">
                Parliament Sittings
            </h1>
            <p className="mb-6 text-zinc-600">
                Browse parliamentary sittings and their readings.
            </p>

            <SessionFilters
                initialStartDate={startDate}
                initialEndDate={endDate}
            />

            <div className="grid gap-4">
                {sessions.length === 0 ? (
                    <p className="py-8 text-center text-zinc-500">
                        No sessions found for the selected date range
                    </p>
                ) : (
                    <>
                        {sessions.map((session) => (
                            <Link
                                key={session.id}
                                href={`/sessions/${session.id}`}
                                className="block rounded-lg border border-zinc-200 bg-white p-5 shadow-sm transition-all hover:border-blue-300 hover:shadow-md"
                            >
                                <div className="mb-2 flex flex-wrap items-center gap-3">
                                    <span className="text-lg font-semibold text-zinc-900">
                                        {new Date(session.date).toLocaleDateString('en-SG', {
                                            weekday: 'long',
                                            year: 'numeric',
                                            month: 'long',
                                            day: 'numeric',
                                        })}
                                    </span>
                                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700">
                                        {session.questionCount} sections
                                    </span>
                                </div>
                                <div className="mb-2 text-sm text-zinc-500">
                                    {getOrdinal(session.parliament)} Parliament, {getOrdinal(session.sessionNo)} Session, {getOrdinal(session.sittingNo)} Sitting
                                </div>
                            </Link>
                        ))}

                        {/* Pagination Controls */}
                        <ServerPagination
                            currentPage={pageNum}
                            totalPages={totalPages}
                            baseUrl="/sessions"
                        />
                    </>
                )}
            </div>
        </div>
    )
}
