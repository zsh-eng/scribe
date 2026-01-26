import Link from 'next/link'
import type { Section } from '@/types'

// Map abbreviations to full names
const QUESTION_TYPE_LABELS: Record<string, string> = {
    'OA': 'Oral Answer to Oral Question',
    'WA': 'Written Answer',
    'WANA': 'Written Answer to Oral Question not answered by end of Question Time',
    'OS': 'Oral Statement',
    'BP': 'Bill',
}

interface QuestionCardProps {
    question: Section
    showSpeakers?: boolean
    showContent?: boolean
}

export default function QuestionCard({
    question,
    showSpeakers = true,
    showContent = false
}: QuestionCardProps) {
    const speakerNames = Array.isArray(question.speakers)
        ? question.speakers.map((s) => (typeof s === 'string' ? s : s.name))
        : []

    const typeLabel = QUESTION_TYPE_LABELS[question.sectionType] || question.sectionType

    return (
        <Link
            href={`/questions/${question.id}`}
            className="block rounded-lg border border-zinc-200 bg-white p-4 shadow-sm transition-all hover:border-blue-300 hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-blue-700"
        >
            <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                    {typeLabel}
                </span>
                {question.ministry && (
                    <span className="rounded bg-green-100 px-2 py-0.5 text-xs font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">
                        {question.ministry}
                    </span>
                )}
                <span className="text-xs text-zinc-500 dark:text-zinc-400">
                    {new Date(question.sessionDate).toLocaleDateString('en-SG', {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                    })}
                </span>
            </div>
            <h3 className="mb-2 font-semibold text-zinc-900 dark:text-white">
                {question.sectionTitle}
            </h3>
            {showContent && (
                <p className="mb-3 line-clamp-3 text-sm text-zinc-600 dark:text-zinc-400">
                    {question.contentPlain.slice(0, 250)}...
                </p>
            )}
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
        </Link>
    )
}
