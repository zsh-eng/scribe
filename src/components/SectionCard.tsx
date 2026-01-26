import Link from 'next/link'
import type { Section } from '@/types'

interface SectionCardProps {
    section: Section
    showSpeakers?: boolean
}

export default function SectionCard({ section, showSpeakers = true }: SectionCardProps) {
    const speakerNames = Array.isArray(section.speakers)
        ? section.speakers.map((s) => (typeof s === 'string' ? s : s.name))
        : []

    return (
        <div className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900">
            <div className="mb-2 flex items-center gap-2">
                <span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                    {section.sectionType}
                </span>
                {section.ministry && (
                    <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
                        {section.ministry}
                    </span>
                )}
                <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {new Date(section.sessionDate).toLocaleDateString('en-SG', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                    })}
                </span>
            </div>
            <h3 className="mb-2 font-semibold text-zinc-900 dark:text-white">
                {section.sectionTitle}
            </h3>
            <p className="mb-3 line-clamp-3 text-sm text-zinc-600 dark:text-zinc-400">
                {section.contentPlain.slice(0, 250)}...
            </p>
            {showSpeakers && speakerNames.length > 0 && (
                <div className="flex flex-wrap gap-1">
                    {speakerNames.slice(0, 3).map((name, i) => (
                        <span
                            key={i}
                            className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400"
                        >
                            {name}
                        </span>
                    ))}
                    {speakerNames.length > 3 && (
                        <span className="text-xs text-zinc-500">+{speakerNames.length - 3} more</span>
                    )}
                </div>
            )}
        </div>
    )
}
