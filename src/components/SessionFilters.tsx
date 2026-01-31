'use client'

import { useRouter, useSearchParams } from 'next/navigation'
import { useState } from 'react'

// Session filters component
export default function SessionFilters({
    initialStartDate = '',
    initialEndDate = ''
}: {
    initialStartDate?: string
    initialEndDate?: string
}) {
    const router = useRouter()
    const searchParams = useSearchParams()
    const [startDate, setStartDate] = useState(initialStartDate)
    const [endDate, setEndDate] = useState(initialEndDate)

    const [prevParams, setPrevParams] = useState(searchParams.toString())
    if (searchParams.toString() !== prevParams) {
        setPrevParams(searchParams.toString())
        setStartDate(searchParams.get('startDate') || '')
        setEndDate(searchParams.get('endDate') || '')
    }

    const updateFilters = (newStart: string, newEnd: string) => {
        const params = new URLSearchParams(searchParams.toString())
        if (newStart) params.set('startDate', newStart)
        else params.delete('startDate')

        if (newEnd) params.set('endDate', newEnd)
        else params.delete('endDate')

        // Reset to page 1 on filter change
        params.delete('page')

        router.push(`/sessions?${params.toString()}`)
    }

    return (
        <div className="mb-6 flex flex-col gap-4 rounded-lg border border-zinc-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center">
            <div className="flex flex-1 items-center gap-2">
                <label htmlFor="startDate" className="min-w-[40px] text-sm font-medium text-zinc-700">
                    From
                </label>
                <input
                    type="date"
                    id="startDate"
                    value={startDate}
                    onChange={(e) => {
                        setStartDate(e.target.value)
                        updateFilters(e.target.value, endDate)
                    }}
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
                    onChange={(e) => {
                        setEndDate(e.target.value)
                        updateFilters(startDate, e.target.value)
                    }}
                    className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                />
            </div>
            {(startDate || endDate) && (
                <button
                    onClick={() => {
                        setStartDate('')
                        setEndDate('')
                        updateFilters('', '')
                    }}
                    className="text-sm text-blue-600 hover:underline"
                >
                    Clear filters
                </button>
            )}
        </div>
    )
}
