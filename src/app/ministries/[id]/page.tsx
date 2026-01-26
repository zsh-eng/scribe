'use client'

import { useState, useEffect, use } from 'react'
import QuestionCard from '@/components/QuestionCard'
import type { Section } from '@/types'

interface MinistryDetail {
    id: string
    name: string
    acronym: string
    sections: Section[]
}

export default function MinistryDetailPage({
    params,
}: {
    params: Promise<{ id: string }>
}) {
    const { id } = use(params)
    const [ministry, setMinistry] = useState<MinistryDetail | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        async function fetchMinistry() {
            try {
                const res = await fetch(`/api/ministries/${id}`)
                if (!res.ok) throw new Error('Ministry not found')
                const data = await res.json()
                setMinistry(data)
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Failed to load ministry')
            } finally {
                setLoading(false)
            }
        }
        fetchMinistry()
    }, [id])

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent"></div>
            </div>
        )
    }

    if (error || !ministry) {
        return (
            <div className="py-12 text-center">
                <p className="text-red-500">{error || 'Ministry not found'}</p>
            </div>
        )
    }

    return (
        <div>
            <section className="mb-8">
                <div className="mb-2 flex items-center gap-2">
                    <span className="rounded bg-green-100 px-3 py-1 text-sm font-bold text-green-700 dark:bg-green-900/30 dark:text-green-400">
                        {ministry.acronym}
                    </span>
                </div>
                <h1 className="text-3xl font-bold text-zinc-900 dark:text-white">
                    {ministry.name}
                </h1>
            </section>

            <section>
                <h2 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                    Related Questions ({ministry.sections.length})
                </h2>
                {ministry.sections.length === 0 ? (
                    <p className="py-8 text-center text-zinc-500 dark:text-zinc-400">
                        No questions found for this ministry
                    </p>
                ) : (
                    <div className="grid gap-4 md:grid-cols-2">
                        {ministry.sections.map((section) => (
                            <QuestionCard key={section.id} question={section} />
                        ))}
                    </div>
                )}
            </section>
        </div>
    )
}
