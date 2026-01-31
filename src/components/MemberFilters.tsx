'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { useState, useCallback } from 'react'
import SearchBar from '@/components/SearchBar'

export default function MemberFilters({
    constituencies,
    initialSearch = '',
    initialConstituency = '',
    initialSort = 'name'
}: {
    constituencies: string[]
    initialSearch?: string
    initialConstituency?: string
    initialSort?: string
}) {
    const router = useRouter()
    const searchParams = useSearchParams()
    const [searchQuery, setSearchQuery] = useState(initialSearch)
    const [selectedConstituency, setSelectedConstituency] = useState(initialConstituency)
    const [sortBy, setSortBy] = useState(initialSort)

    const [prevParams, setPrevParams] = useState(searchParams.toString())
    if (searchParams.toString() !== prevParams) {
        setPrevParams(searchParams.toString())
        setSearchQuery(searchParams.get('search') || '')
        setSelectedConstituency(searchParams.get('constituency') || '')
        setSortBy(searchParams.get('sort') || 'name')
    }

    const updateFilters = useCallback((query: string, constituency: string, sort: string) => {
        const params = new URLSearchParams(searchParams.toString())

        const currentQuery = searchParams.get('search') || ''
        const currentConstituency = searchParams.get('constituency') || ''
        const currentSort = searchParams.get('sort') || 'name'

        // Only reset to page 1 if a filter has actually changed
        if (query !== currentQuery || constituency !== currentConstituency || sort !== currentSort) {
            params.delete('page')
        }

        if (query) params.set('search', query)
        else params.delete('search')

        if (constituency) params.set('constituency', constituency)
        else params.delete('constituency')

        if (sort !== 'name') params.set('sort', sort)
        else params.delete('sort')

        router.push(`/members?${params.toString()}`)
    }, [router, searchParams])

    const handleSearch = (query: string) => {
        setSearchQuery(query)
        updateFilters(query, selectedConstituency, sortBy)
    }

    return (
        <div className="flex flex-col gap-4 sm:flex-row">
            <div className="flex-1">
                <SearchBar
                    placeholder="Search MP profiles..."
                    onSearch={handleSearch}
                    defaultValue={searchQuery}
                />
            </div>
            <div className="flex w-full gap-2 sm:w-auto">
                <select
                    value={selectedConstituency}
                    onChange={(e) => {
                        setSelectedConstituency(e.target.value)
                        updateFilters(searchQuery, e.target.value, sortBy)
                    }}
                    className="w-full rounded-lg border border-zinc-300 bg-white px-4 py-3 text-sm text-zinc-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 sm:w-48"
                >
                    <option value="">All Constituencies</option>
                    {constituencies.map((c) => (
                        <option key={c} value={c}>
                            {c}
                        </option>
                    ))}
                </select>
                <select
                    value={sortBy}
                    onChange={(e) => {
                        setSortBy(e.target.value)
                        updateFilters(searchQuery, selectedConstituency, e.target.value)
                    }}
                    className="w-full rounded-lg border border-zinc-300 bg-white px-4 py-3 text-sm text-zinc-900 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 sm:w-48"
                >
                    <option value="name">Name (A-Z)</option>
                    <option value="involvements">Most Active</option>
                </select>
            </div>
        </div>
    )
}
