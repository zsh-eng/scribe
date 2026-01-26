'use client'

import { useState, useEffect, use } from 'react'
import Link from 'next/link'
import type { Section, Speaker } from '@/types'

// Map abbreviations to full names
const QUESTION_TYPE_LABELS: Record<string, string> = {
    'OA': 'Oral Answer to Oral Question',
    'WA': 'Written Answer',
    'WANA': 'Written Answer to Oral Question not answered by end of Question Time',
    'OS': 'Oral Statement',
    'BP': 'Bill',
}

interface QuestionDetail extends Section {
    ministryName?: string
}

export default function QuestionDetailPage({
    params,
}: {
    params: Promise<{ id: string }>
}) {
    const { id } = use(params)
    const [question, setQuestion] = useState<QuestionDetail | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        async function fetchQuestion() {
            try {
                const res = await fetch(`/api/questions/${id}`)
                if (!res.ok) throw new Error('Question not found')
                const data = await res.json()
                setQuestion(data)
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Failed to load question')
            } finally {
                setLoading(false)
            }
        }
        fetchQuestion()
    }, [id])

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent"></div>
            </div>
        )
    }

    if (error || !question) {
        return (
            <div className="py-12 text-center">
                <p className="text-red-500">{error || 'Question not found'}</p>
                <Link href="/" className="mt-4 text-blue-500 hover:underline">
                    ← Back to Home
                </Link>
            </div>
        )
    }

    const typeLabel = QUESTION_TYPE_LABELS[question.sectionType] || question.sectionType
    const speakers = Array.isArray(question.speakers) ? question.speakers : []

    return (
        <div className="mx-auto max-w-4xl">
            <Link href="/" className="mb-6 inline-flex items-center text-sm text-blue-600 hover:underline dark:text-blue-400">
                ← Back to Questions
            </Link>

            <article className="rounded-lg border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900">
                {/* Header */}
                <header className="mb-6">
                    <div className="mb-3 flex flex-wrap items-center gap-2">
                        <span className="rounded bg-blue-100 px-3 py-1 text-sm font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                            {typeLabel}
                        </span>
                        {question.ministry && (
                            <span className="rounded bg-green-100 px-3 py-1 text-sm font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
                                {question.ministryName || question.ministry}
                            </span>
                        )}
                        <span className="text-sm text-zinc-500 dark:text-zinc-400">
                            {new Date(question.sessionDate).toLocaleDateString('en-SG', {
                                weekday: 'long',
                                year: 'numeric',
                                month: 'long',
                                day: 'numeric',
                            })}
                        </span>
                    </div>
                    <h1 className="text-2xl font-bold text-zinc-900 dark:text-white">
                        {question.sectionTitle}
                    </h1>
                </header>

                {/* Speakers */}
                {speakers.length > 0 && (
                    <section className="mb-6">
                        <h2 className="mb-2 text-sm font-semibold uppercase text-zinc-500 dark:text-zinc-400">
                            Speakers
                        </h2>
                        <div className="flex flex-wrap gap-2">
                            {speakers.map((speaker, i) => {
                                const s = speaker as Speaker
                                return (
                                    <Link
                                        key={i}
                                        href={`/members/${s.memberId}`}
                                        className="rounded-full bg-zinc-100 px-3 py-1 text-sm text-zinc-700 transition-colors hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
                                    >
                                        {s.name}
                                        {s.designation && (
                                            <span className="ml-1 text-zinc-500">({s.designation})</span>
                                        )}
                                    </Link>
                                )
                            })}
                        </div>
                    </section>
                )}

                {/* Summary placeholder */}
                <section className="mb-6 rounded-lg bg-amber-50 p-4 dark:bg-amber-900/20">
                    <h2 className="mb-2 text-sm font-semibold uppercase text-amber-700 dark:text-amber-400">
                        Summary
                    </h2>
                    <p className="text-sm italic text-amber-600 dark:text-amber-300">
                        Summary will be added in a future update.
                    </p>
                </section>

                {/* Full Content */}
                <section>
                    <h2 className="mb-3 text-sm font-semibold uppercase text-zinc-500 dark:text-zinc-400">
                        Full Transcript
                    </h2>
                    <div
                        className="prose prose-zinc max-w-none dark:prose-invert prose-p:my-2 prose-p:leading-relaxed"
                        dangerouslySetInnerHTML={{ __html: question.contentHtml }}
                    />
                </section>
            </article>
        </div>
    )
}
