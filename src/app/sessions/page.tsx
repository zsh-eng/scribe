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
    summary: string | null
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

    useEffect(() => {
        async function fetchSessions() {
            setLoading(true)
            try {
                const params = new URLSearchParams()
                if (startDate) params.set('startDate', startDate)
                if (endDate) params.set('endDate', endDate)

                const res = await fetch(`/api/sessions?${params.toString()}`)
                const data = await res.json()
                setSessions(data)
            } catch (error) {
                console.error('Failed to fetch sessions:', error)
            } finally {
                setLoading(false)
            }
        }
        fetchSessions()
    }, [startDate, endDate])

    return (
        <div>
            <h1 className="mb-6 text-3xl font-bold text-zinc-900 dark:text-white">
                Parliament Sessions
            </h1>

            {/* Date Range Filter */}
            <div className="mb-6 flex flex-wrap items-center gap-4 rounded-lg border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
                <div className="flex items-center gap-2">
                    <label htmlFor="startDate" className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                        From
                    </label>
                    <input
                        type="date"
                        id="startDate"
                        value={startDate}
                        onChange={(e) => setStartDate(e.target.value)}
                        className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-white"
                    />
                </div>
                <div className="flex items-center gap-2">
                    <label htmlFor="endDate" className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                        To
                    </label>
                    <input
                        type="date"
                        id="endDate"
                        value={endDate}
                        onChange={(e) => setEndDate(e.target.value)}
                        className="rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-zinc-700 dark:bg-zinc-800 dark:text-white"
                    />
                </div>
                {(startDate || endDate) && (
                    <button
                        onClick={() => {
                            setStartDate('')
                            setEndDate('')
                        }}
                        className="text-sm text-blue-600 hover:underline dark:text-blue-400"
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
                        <p className="py-8 text-center text-zinc-500 dark:text-zinc-400">
                            No sessions found for the selected date range
                        </p>
                    ) : (
                        sessions.map((session) => (
                            <Link
                                key={session.id}
                                href={`/sessions/${session.id}`}
                                className="block rounded-lg border border-zinc-200 bg-white p-5 shadow-sm transition-all hover:border-blue-300 hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-blue-700"
                            >
                                <div className="mb-2 flex flex-wrap items-center gap-3">
                                    <span className="text-lg font-semibold text-zinc-900 dark:text-white">
                                        {new Date(session.date).toLocaleDateString('en-SG', {
                                            weekday: 'long',
                                            year: 'numeric',
                                            month: 'long',
                                            day: 'numeric',
                                        })}
                                    </span>
                                    <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                                        {session.questionCount} questions
                                    </span>
                                </div>
                                <div className="mb-2 text-sm text-zinc-500 dark:text-zinc-400">
                                    {getOrdinal(session.parliament)} Parliament, {getOrdinal(session.sessionNo)} Session, {getOrdinal(session.sittingNo)} Sitting
                                </div>
                                {session.summary && (
                                    <p className="line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">
                                        {session.summary}
                                    </p>
                                )}
                            </Link>
                        ))
                    )}
                </div>
            )}
        </div>
    )
}
