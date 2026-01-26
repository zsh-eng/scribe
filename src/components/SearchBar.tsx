'use client'

import { useState, useEffect } from 'react'

interface SearchBarProps {
    placeholder?: string
    onSearch: (query: string) => void
    debounceMs?: number
}

export default function SearchBar({
    placeholder = 'Search...',
    onSearch,
    debounceMs = 300,
}: SearchBarProps) {
    const [query, setQuery] = useState('')

    useEffect(() => {
        const timer = setTimeout(() => {
            onSearch(query)
        }, debounceMs)

        return () => clearTimeout(timer)
    }, [query, debounceMs, onSearch])

    return (
        <div className="relative w-full max-w-xl">
            <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={placeholder}
                className="w-full rounded-lg border border-zinc-300 bg-white px-4 py-3 pl-10 text-sm placeholder-zinc-400 shadow-sm transition-colors focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/20 dark:border-zinc-700 dark:bg-zinc-900 dark:text-white dark:placeholder-zinc-500"
            />
            <svg
                className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-zinc-400"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
            >
                <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
            </svg>
        </div>
    )
}
