import Link from 'next/link'
import BillFilters from '@/components/BillFilters'
import { query } from '@/lib/db'

interface Bill {
    id: string
    title: string
    firstReadingDate: string | null
    firstReadingSessionId: string | null
    secondReadingDate: string | null
    secondReadingSessionId: string | null
    ministryId: string | null
    ministry: string | null
    ministryName: string | null
}

export default async function BillsPage({
    searchParams,
}: {
    searchParams: Promise<{ [key: string]: string | string[] | undefined }>
}) {
    const params = await searchParams
    const search = typeof params.search === 'string' ? params.search : ''
    const limit = 20

    // Get unified bills with their reading information


    const sqlParams: (string | number)[] = []
    let paramCount = 1

    // Use a subquery to calculate rank for each bill based on its best matching section
    let rankSelect = ''
    let rankOrderBy = ''

    if (search) {
        sqlParams.push(search)
        // Rank is either title match or max section match
        rankSelect = `, (
            SELECT MAX(ts_rank(to_tsvector('english', s_rank.content_plain), plainto_tsquery('english', $${paramCount})))
            FROM sections s_rank
            WHERE s_rank.bill_id = b.id
        ) as doc_rank`
        rankOrderBy = 'doc_rank DESC NULLS LAST,'
        paramCount++
    }

    // Get unified bills with their reading information
    let sql = `
        SELECT 
            b.id,
            b.title,
            b.first_reading_date as "firstReadingDate",
            b.first_reading_session_id as "firstReadingSessionId",
            m.id as "ministryId",
            m.acronym as ministry,
            m.name as "ministryName",
            -- Get second reading info from sections
            (SELECT MIN(sess.date) FROM sections s 
             JOIN sessions sess ON s.session_id = sess.id 
             WHERE s.bill_id = b.id AND s.section_type = 'BP') as "secondReadingDate",
            (SELECT s.session_id FROM sections s 
             JOIN sessions sess ON s.session_id = sess.id 
             WHERE s.bill_id = b.id AND s.section_type = 'BP' 
             ORDER BY sess.date LIMIT 1) as "secondReadingSessionId"
            ${rankSelect}
        FROM bills b
        LEFT JOIN ministries m ON b.ministry_id = m.id
        WHERE 1=1
    `

    if (search) {
        sql += ` AND (
            b.title ILIKE $${paramCount} OR
            EXISTS (
                SELECT 1 FROM sections s_search 
                WHERE s_search.bill_id = b.id 
                AND to_tsvector('english', s_search.content_plain) @@ plainto_tsquery('english', $${1}) -- reuse first param for query
            )
        )`
        sqlParams.push(`%${search}%`)
        paramCount++
    }

    sql += ` ORDER BY ${rankOrderBy} COALESCE(b.first_reading_date, 
                 (SELECT MIN(sess.date) FROM sections s 
                  JOIN sessions sess ON s.session_id = sess.id 
                  WHERE s.bill_id = b.id)) DESC NULLS LAST
                 LIMIT $${paramCount}`
    sqlParams.push(limit)

    const result = await query(sql, sqlParams)
    const bills: Bill[] = result.rows

    return (
        <div>
            <header className="mb-8">
                <h1 className="mb-2 text-3xl font-bold text-zinc-900">
                    Bills
                </h1>
                <p className="text-zinc-600">
                    Browse parliamentary bills and their readings.
                </p>
            </header>

            <BillFilters initialSearch={search} />

            <section>
                <h2 className="mb-4 text-xl font-semibold text-zinc-900">
                    {search ? `Search Results for "${search}"` : 'Recent Bills'}
                </h2>
                {bills.length === 0 ? (
                    <p className="py-12 text-center text-zinc-500">
                        {search ? 'No bills found matching your search' : 'No bills found'}
                    </p>
                ) : (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {bills.map((bill) => (
                            <Link key={bill.id} href={`/bills/${bill.id}`}>
                                <div className="group h-full cursor-pointer rounded-lg border border-zinc-200 bg-white p-4 transition-all hover:border-purple-300 hover:shadow-md">
                                    {/* Header */}
                                    <div className="mb-2 flex flex-wrap items-center gap-2">
                                        {bill.ministry && (
                                            <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                                                {bill.ministry}
                                            </span>
                                        )}
                                    </div>

                                    {/* Title */}
                                    <h3 className="mb-3 line-clamp-2 font-semibold text-zinc-900 group-hover:text-purple-600">
                                        {bill.title}
                                    </h3>

                                    {/* Reading Dates */}
                                    <div className="mt-auto space-y-1 text-xs text-zinc-500">
                                        {bill.firstReadingDate && (
                                            <div className="flex items-center gap-2">
                                                <span className="rounded bg-purple-100 px-1.5 py-0.5 text-purple-700">
                                                    1R
                                                </span>
                                                <span>
                                                    {new Date(bill.firstReadingDate).toLocaleDateString('en-SG', {
                                                        year: 'numeric',
                                                        month: 'short',
                                                        day: 'numeric',
                                                    })}
                                                </span>
                                            </div>
                                        )}
                                        {bill.secondReadingDate && (
                                            <div className="flex items-center gap-2">
                                                <span className="rounded bg-purple-100 px-1.5 py-0.5 text-purple-700">
                                                    2R
                                                </span>
                                                <span>
                                                    {new Date(bill.secondReadingDate).toLocaleDateString('en-SG', {
                                                        year: 'numeric',
                                                        month: 'short',
                                                        day: 'numeric',
                                                    })}
                                                </span>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </Link>
                        ))}
                    </div>
                )}
            </section>
        </div>
    )
}
