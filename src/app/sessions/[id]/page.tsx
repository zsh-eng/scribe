'use client'

import { useState, useEffect, use } from 'react'
import Link from 'next/link'
import QuestionCard from '@/components/QuestionCard'
import SearchBar from '@/components/SearchBar'
import PaginatedList from '@/components/PaginatedList'
import type { Section } from '@/types'

// Helper to format ordinal numbers (1st, 2nd, 3rd, etc.)
function getOrdinal(n: number): string {
    const s = ['th', 'st', 'nd', 'rd']
    const v = n % 100
    return n + (s[(v - 20) % 10] || s[v] || s[0])
}

interface Attendee {
    id: string
    name: string
    present: boolean
    constituency: string | null
    designation: string | null
}

interface SessionDetail {
    id: string
    date: string
    sittingNo: number
    parliament: number
    sessionNo: number
    volumeNo: number
    format: string
    url: string

    questions: Section[]
    statements: Section[]
    bills: Array<{
        billId: string
        sectionTitle: string
        ministry: string | null
        ministryId: string | null
        readingTypes: string[]
        sectionOrder: number
    }>
    attendees: Attendee[]
}



export default function SessionDetailPage({
    params,
}: {
    params: Promise<{ id: string }>
}) {
    const { id } = use(params)
    const [session, setSession] = useState<SessionDetail | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [showAttendance, setShowAttendance] = useState(false)
    const [searchQuery, setSearchQuery] = useState('')

    useEffect(() => {
        async function fetchSession() {
            try {
                const res = await fetch(`/api/sessions/${id}`)
                if (!res.ok) throw new Error('Session not found')
                const data = await res.json()
                setSession(data)
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Failed to load session')
            } finally {
                setLoading(false)
            }
        }
        fetchSession()
    }, [id])

    // Filter content based on search query
    const filteredBills = session?.bills.filter(bill =>
        bill.sectionTitle.toLowerCase().includes(searchQuery.toLowerCase())
    ) || []

    const filteredQuestions = session?.questions.filter(question =>
        question.sectionTitle.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (question.contentPlain && question.contentPlain.toLowerCase().includes(searchQuery.toLowerCase()))
    ) || []

    const filteredStatements = session?.statements.filter(statement =>
        statement.sectionTitle.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (statement.contentPlain && statement.contentPlain.toLowerCase().includes(searchQuery.toLowerCase()))
    ) || []

    const motions = filteredStatements.filter(s => s.category !== 'clarification')
    const clarifications = filteredStatements.filter(s => s.category === 'clarification')

    const oralAnswers = filteredQuestions.filter(q => q.sectionType === 'OA')
    const writtenAnswers = filteredQuestions.filter(q => ['WA', 'WANA'].includes(q.sectionType))

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent"></div>
            </div>
        )
    }

    if (error || !session) {
        return (
            <div className="py-12 text-center">
                <p className="text-red-500">{error || 'Session not found'}</p>
                <Link href="/sessions" className="mt-4 text-blue-500 hover:underline">
                    ← Back to Sittings
                </Link>
            </div>
        )
    }

    const presentMembers = session.attendees?.filter(a => a.present) || []
    const absentMembers = session.attendees?.filter(a => !a.present) || []

    return (
        <main className="container mx-auto px-4 py-8">
            <Link href="/sessions" className="mb-6 inline-flex items-center text-sm text-blue-600 hover:underline">
                ← Back to Sittings
            </Link>

            <header className="mb-8">
                <h1 className="mb-2 text-3xl font-bold text-zinc-900">
                    {new Date(session.date).toLocaleDateString('en-SG', {
                        weekday: 'long',
                        year: 'numeric',
                        month: 'long',
                        day: 'numeric',
                    })}
                </h1>
                <div className="flex flex-wrap gap-3 text-sm text-zinc-600">
                    <span>{getOrdinal(session.parliament)} Parliament</span>
                    <span>•</span>
                    <span>{getOrdinal(session.sessionNo)} Session</span>
                    <span>•</span>
                    <span>{getOrdinal(session.sittingNo)} Sitting</span>
                    {session.url && (
                        <>
                            <span>•</span>
                            <a
                                href={session.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-600 hover:underline"
                            >
                                Full report from Hansard ↗
                            </a>
                        </>
                    )}
                </div>
            </header>


            <div className="mb-8">
                <SearchBar
                    placeholder="Search session proceedings..."
                    onSearch={setSearchQuery}
                    defaultValue={searchQuery}
                />
            </div>

            {/* Attendance */}
            {session.attendees && session.attendees.length > 0 && (
                <section className="mb-8">
                    <button
                        onClick={() => setShowAttendance(!showAttendance)}
                        className="mb-4 flex items-center gap-2 text-xl font-semibold text-zinc-900"
                    >
                        <span>Members ({presentMembers.length} present, {absentMembers.length} absent)</span>
                        <svg
                            className={`h-5 w-5 transition-transform ${showAttendance ? 'rotate-180' : ''}`}
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                        >
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                        </svg>
                    </button>

                    {showAttendance && (
                        <div className="rounded-lg border border-zinc-200 bg-white p-5">
                            {/* Present */}
                            <div className="mb-4">
                                <h3 className="mb-2 text-sm font-semibold uppercase text-green-600">
                                    Present ({presentMembers.length})
                                </h3>
                                <div className="flex flex-wrap gap-2">
                                    {presentMembers.map((member) => (
                                        <Link
                                            key={member.id}
                                            href={`/members/${member.id}`}
                                            className="rounded-full bg-green-50 px-3 py-1 text-sm text-green-700 transition-colors hover:bg-green-100"
                                        >
                                            {member.name}
                                            {member.designation && (
                                                <span className="ml-1 text-green-500">
                                                    ({member.designation})
                                                </span>
                                            )}
                                        </Link>
                                    ))}
                                </div>
                            </div>

                            {/* Absent */}
                            {absentMembers.length > 0 && (
                                <div>
                                    <h3 className="mb-2 text-sm font-semibold uppercase text-zinc-500">
                                        Absent ({absentMembers.length})
                                    </h3>
                                    <div className="flex flex-wrap gap-2">
                                        {absentMembers.map((member) => (
                                            <Link
                                                key={member.id}
                                                href={`/members/${member.id}`}
                                                className="rounded-full bg-zinc-100 px-3 py-1 text-sm text-zinc-500 transition-colors hover:bg-zinc-200"
                                            >
                                                {member.name}
                                            </Link>
                                        ))}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </section>
            )}

            {/* Motions */}
            {motions.length > 0 && (
                <section className="mb-8">
                    <h2 className="mb-4 text-xl font-semibold text-zinc-900">
                        Motions ({motions.length})
                    </h2>
                    <PaginatedList
                        items={motions}
                        itemsPerPage={10}
                        emptyMessage="No motions in this session"
                        renderItem={(statement) => (
                            <QuestionCard key={statement.id} question={statement} showDate={false} />
                        )}
                    />
                </section>
            )}

            {/* Bills */}
            {filteredBills.length > 0 && (
                <section className="mb-8">
                    <h2 className="mb-4 text-xl font-semibold text-zinc-900">
                        Bills ({filteredBills.length})
                    </h2>
                    <PaginatedList
                        items={filteredBills}
                        itemsPerPage={10}
                        emptyMessage="No bills in this session"
                        renderItem={(bill) => (
                            <Link key={bill.billId} href={`/bills/${bill.billId}`}>
                                <div className="group h-full cursor-pointer rounded-lg border border-zinc-200 bg-white p-4 transition-all hover:border-purple-300 hover:shadow-md">
                                    <div className="mb-2 flex flex-wrap items-center gap-2">
                                        {bill.readingTypes?.includes('BI') && (
                                            <span className="rounded bg-purple-100 px-2 py-0.5 text-xs font-medium text-purple-700">
                                                1st Reading
                                            </span>
                                        )}
                                        {bill.readingTypes?.includes('BP') && (
                                            <span className="rounded bg-purple-100 px-2 py-0.5 text-xs font-medium text-purple-700">
                                                2nd Reading
                                            </span>
                                        )}
                                        {bill.ministry && (
                                            <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700">
                                                {bill.ministry}
                                            </span>
                                        )}
                                    </div>
                                    <h3 className="line-clamp-2 font-semibold text-zinc-900 group-hover:text-purple-600">
                                        {bill.sectionTitle}
                                    </h3>
                                </div>
                            </Link>
                        )}
                    />
                </section>
            )}

            {/* Oral Answers */}
            <section className="mb-8">
                <h2 className="mb-4 text-xl font-semibold text-zinc-900">
                    Oral Answers ({oralAnswers.length})
                </h2>
                <PaginatedList
                    items={oralAnswers}
                    itemsPerPage={10}
                    emptyMessage={searchQuery ? 'No results found matching your search' : 'No oral answers in this session'}
                    renderItem={(question) => (
                        <QuestionCard key={question.id} question={question} showDate={false} />
                    )}
                />
            </section>

            {/* Written Answers */}
            <section className="mb-8">
                <h2 className="mb-4 text-xl font-semibold text-zinc-900">
                    Written Answers ({writtenAnswers.length})
                </h2>
                <PaginatedList
                    items={writtenAnswers}
                    itemsPerPage={10}
                    emptyMessage={searchQuery ? 'No results found matching your search' : 'No written answers in this session'}
                    renderItem={(question) => (
                        <QuestionCard key={question.id} question={question} showDate={false} />
                    )}
                />
            </section>

            {/* Clarifications */}
            {clarifications.length > 0 && (
                <section className="mb-8">
                    <h2 className="mb-4 text-xl font-semibold text-zinc-900">
                        Clarifications ({clarifications.length})
                    </h2>
                    <PaginatedList
                        items={clarifications}
                        itemsPerPage={10}
                        emptyMessage="No clarifications in this session"
                        renderItem={(statement) => (
                            <QuestionCard key={statement.id} question={statement} showDate={false} />
                        )}
                    />
                </section>
            )}
        </main>
    )
}
