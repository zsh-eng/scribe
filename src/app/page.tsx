'use client'

import { useState, useEffect, useCallback } from 'react'
import SearchBar from '@/components/SearchBar'
import QuestionCard from '@/components/QuestionCard'
import type { Section } from '@/types'

export default function Home() {
  const [questions, setQuestions] = useState<Section[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')

  const fetchQuestions = useCallback(async (search: string) => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (search) params.set('search', search)
      params.set('limit', '20')

      const res = await fetch(`/api/sections?${params}`)
      const data = await res.json()
      setQuestions(data)
    } catch (error) {
      console.error('Failed to fetch questions:', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchQuestions(searchQuery)
  }, [searchQuery, fetchQuestions])

  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query)
  }, [])

  return (
    <div>
      <section className="mb-12 text-center">
        <h1 className="mb-4 text-4xl font-bold text-zinc-900 dark:text-white">
          🇸🇬 Parliament Summarizer
        </h1>
        <p className="mb-8 text-lg text-zinc-600 dark:text-zinc-400">
          Search and browse Singapore Parliament questions
        </p>
        <div className="flex justify-center">
          <SearchBar
            placeholder="Search questions by title..."
            onSearch={handleSearch}
          />
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-xl font-semibold text-zinc-900 dark:text-white">
          {searchQuery ? `Search Results for "${searchQuery}"` : 'Recent Questions'}
        </h2>
        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-blue-500 border-t-transparent"></div>
          </div>
        ) : questions.length === 0 ? (
          <p className="py-12 text-center text-zinc-500 dark:text-zinc-400">
            No questions found
          </p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {questions.map((question) => (
              <QuestionCard key={question.id} question={question} showContent={false} />
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
