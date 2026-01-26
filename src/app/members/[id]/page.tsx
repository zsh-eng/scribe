'use client'

import { useState, useEffect, use } from 'react'
import SectionCard from '@/components/SectionCard'
import type { Section } from '@/types'

interface MemberDetail {
    id: string
    name: string
    summary: string | null
    sections: Section[]
}

export default function MemberDetailPage({
    params,
}: {
    params: Promise<{ id: string }>
}) {
    const { id } = use(params)
    const [member, setMember] = useState<MemberDetail | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        async function fetchMember() {
            try {
                const res = await fetch(`/api/members/${id}`)
                if (!res.ok) throw new Error('Member not found')
                const data = await res.json()
                setMember(data)
            } catch (err) {
                setError(err instanceof Error ? err.message : 'Failed to load member')
            } finally {
                setLoading(false)
            }
        }
        fetchMember()
    }, [id])

    if (loading) {
        return (
            <div className="flex items-center justify-center py-12">
                <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent"></div>
            </div>
        )
    }

    if (error || !member) {
        return (
            <div className="py-12 text-center">
                <p className="text-red-500">{error || 'Member not found'}</p>
            </div>
        )
    }

    return (
        <div>
            <section className="mb-8">
                <h1 className="mb-2 text-3xl font-bold text-zinc-900 dark:text-white">
                    {member.name}
                </h1>
                {member.summary && (
                    <p className="text-lg text-zinc-600 dark:text-zinc-400">
                        {member.summary}
                    </p>
                )}
            </section>

            <section>
                <h2 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
                    Parliamentary Appearances ({member.sections.length})
                </h2>
                {member.sections.length === 0 ? (
                    <p className="py-8 text-center text-zinc-500 dark:text-zinc-400">
                        No recorded appearances
                    </p>
                ) : (
                    <div className="grid gap-4 md:grid-cols-2">
                        {member.sections.map((section) => (
                            <SectionCard key={section.id} section={section} showSpeakers={false} />
                        ))}
                    </div>
                )}
            </section>
        </div>
    )
}
