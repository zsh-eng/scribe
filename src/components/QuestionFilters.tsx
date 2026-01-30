'use client'

import { useRouter, useSearchParams, usePathname } from 'next/navigation'
import SearchBar from '@/components/SearchBar'

export default function QuestionFilters({
    initialSearch = '',
    placeholder = 'Search questions...'
}: {
    initialSearch?: string
    placeholder?: string
}) {
    const router = useRouter()
    const pathname = usePathname()
    const searchParams = useSearchParams()

    const handleSearch = (query: string) => {
        const params = new URLSearchParams(searchParams.toString())
        if (query) params.set('search', query)
        else params.delete('search')

        router.push(`${pathname}?${params.toString()}`)
    }

    return (
        <div className="mb-6">
            <SearchBar
                placeholder={placeholder}
                onSearch={handleSearch}
                defaultValue={initialSearch}
            />
        </div>
    )
}
