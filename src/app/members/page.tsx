'use client'

import { useState, useEffect, useCallback } from 'react'
import SearchBar from '@/components/SearchBar'
import MemberCard from '@/components/MemberCard'
import type { Member } from '@/types'

export default function MembersPage() {
    const [members, setMembers] = useState<Member[]>([])
    const [loading, setLoading] = useState(true)
    const [searchQuery, setSearchQuery] = useState('')

    const fetchMembers = useCallback(async (search: string) => {
        setLoading(true)
        try {
            const params = new URLSearchParams()
            if (search) params.set('search', search)

            const res = await fetch(`/api/members?${params}`)
            const data = await res.json()
            setMembers(data)
        } catch (error) {
            console.error('Failed to fetch members:', error)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        fetchMembers(searchQuery)
    }, [searchQuery, fetchMembers])

    const handleSearch = useCallback((query: string) => {
        setSearchQuery(query)
    }, [])

    return (
        <div>
            <section className="mb-8">
                <h1 className="mb-4 text-3xl font-bold text-zinc-900 dark:text-white">
                    Members of Parliament
                </h1>
                <SearchBar
                    placeholder="Search members by name..."
                    onSearch={handleSearch}
                />
            </section>

            {loading ? (
                <div className="flex items-center justify-center py-12">
                    <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent"></div>
                </div>
            ) : members.length === 0 ? (
                <p className="py-12 text-center text-zinc-500 dark:text-zinc-400">
                    No members found
                </p>
            ) : (
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {members.map((member) => (
                        <MemberCard key={member.id} member={member} />
                    ))}
                </div>
            )}
        </div>
    )
}
