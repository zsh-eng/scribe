'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'

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

export default function SessionsPage() {
    const [sessions, setSessions] = useState<Session[]>([])
    const [loading, setLoading] = useState(true)
    const [startDate, setStartDate] = useState('')
    const [endDate, setEndDate] = useState('')
    const [page, setPage] = useState(1)
    const [totalPages, setTotalPages] = useState(1)

    useEffect(() => {
        // Reset to page 1 when filters change
        setPage(1)
    }, [startDate, endDate])

    useEffect(() => {
        async function fetchSessions() {
            setLoading(true)
            try {
                const params = new URLSearchParams()
                params.set('page', page.toString())
                params.set('limit', '20')
                if (startDate) params.set('startDate', startDate)
                if (endDate) params.set('endDate', endDate)

                const res = await fetch(`/api/sessions?${params.toString()}`)
                const data = await res.json()
                setSessions(data.sessions)
                setTotalPages(data.totalPages)
            } catch (error) {
                console.error('Failed to fetch sessions:', error)
            } finally {
                setLoading(false)
            }
        }
        fetchSessions()
    }, [startDate, endDate, page])

    return (
        <div>
            <h1 className="mb-2 text-3xl font-bold text-zinc-900">
                Parliament Sessions
            </h1>
            <p className="mb-6 text-zinc-600">
                Browse parliamentary sessions and their readings. (Placeholder)
            </p>

            {/* Date Range Filter */}
            <div className="mb-6 flex flex-col gap-4 rounded-lg border border-zinc-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center">
                <div className="flex flex-1 items-center gap-2">
                    <label htmlFor="startDate" className="min-w-[40px] text-sm font-medium text-zinc-700">
                        From
                    </label>
                    <input
                        type="date"
                        id="startDate"
                        value={startDate}
                        onChange={(e) => setStartDate(e.target.value)}
                        className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                </div>
                <div className="flex flex-1 items-center gap-2">
                    <label htmlFor="endDate" className="min-w-[40px] text-sm font-medium text-zinc-700">
                        To
                    </label>
                    <input
                        type="date"
                        id="endDate"
                        value={endDate}
                        onChange={(e) => setEndDate(e.target.value)}
                        className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                </div>
                {(startDate || endDate) && (
                    <button
                        onClick={() => {
                            setStartDate('')
                            setEndDate('')
                        }}
                        className="text-sm text-blue-600 hover:underline"
                    >
                        Clear filters
                    </button>
                )}
            </div>

            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent"></div>
                </div>
            ) : (
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
                            {totalPages > 1 && (
                                <div className="mt-8 flex justify-center gap-2">
                                    <button
                                        onClick={() => setPage((p) => Math.max(1, p - 1))}
                                        disabled={page === 1}
                                        className="rounded border border-zinc-300 px-3 py-1 text-sm disabled:opacity-50"
                                    >
                                        Previous
                                    </button>
                                    <span className="flex items-center text-sm text-zinc-600">
                                        Page {page} of {totalPages}
                                    </span>
                                    <button
                                        onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                                        disabled={page === totalPages}
                                        className="rounded border border-zinc-300 px-3 py-1 text-sm disabled:opacity-50"
                                    >
                                        Next
                                    </button>
                                </div>
                            )}
                        </>
                    )}
                </div>
            )}
        </div>
    )
}
