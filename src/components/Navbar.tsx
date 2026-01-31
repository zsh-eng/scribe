'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState, useCallback } from 'react'

// Map routes to their API endpoints for prefetching
const prefetchMap: Record<string, string> = {
    '/sessions': '/api/sessions?page=1&limit=20',
    '/motions': '/api/sections?limit=50',
    '/questions': '/api/sections?limit=50',
    '/bills': '/api/bills?limit=50',
    '/members': '/api/members?page=1&limit=20',
    '/ministries': '/api/ministries',
}

export default function Navbar() {
    const pathname = usePathname()
    const [isMenuOpen, setIsMenuOpen] = useState(false)

    const navLinks = [
        { href: '/', label: 'Home' },
        { href: '/sessions', label: 'Sittings' },
        { href: '/motions', label: 'Motions' },
        { href: '/bills', label: 'Bills' },
        { href: '/questions', label: 'Questions' },
        { href: '/members', label: 'MPs' },
        { href: '/ministries', label: 'Ministries' },
    ]

    // Prefetch API data on hover to warm the cache
    const handlePrefetch = useCallback((href: string) => {
        const apiUrl = prefetchMap[href]
        if (apiUrl) {
            // Use fetch with low priority to prefetch without blocking
            fetch(apiUrl, { priority: 'low' as RequestPriority }).catch(() => { })
        }
    }, [])

    return (
        <nav className="sticky top-0 z-50 border-b border-zinc-200 bg-white/80 backdrop-blur-sm">
            <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
                <Link href="/" className="text-xl font-bold text-zinc-900">
                    📜 Scribe
                </Link>

                {/* Desktop Navigation */}
                <div className="hidden items-center gap-6 md:flex">
                    {navLinks.map((link) => (
                        <Link
                            key={link.href}
                            href={link.href}
                            onMouseEnter={() => handlePrefetch(link.href)}
                            className={`text-sm font-medium transition-colors ${pathname === link.href
                                ? 'text-blue-600'
                                : 'text-zinc-600 hover:text-zinc-900'
                                }`}
                        >
                            {link.label}
                        </Link>
                    ))}
                </div>

                {/* Mobile Menu Button */}
                <button
                    onClick={() => setIsMenuOpen(!isMenuOpen)}
                    className="rounded-md p-2 text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 md:hidden"
                    aria-label="Toggle menu"
                >
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="h-6 w-6"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                    >
                        {isMenuOpen ? (
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        ) : (
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                        )}
                    </svg>
                </button>
            </div>

            {/* Mobile Navigation Dropdown */}
            {isMenuOpen && (
                <div className="border-t border-zinc-100 bg-white px-4 py-4 md:hidden">
                    <div className="flex flex-col gap-4">
                        {navLinks.map((link) => (
                            <Link
                                key={link.href}
                                href={link.href}
                                onClick={() => setIsMenuOpen(false)}
                                onMouseEnter={() => handlePrefetch(link.href)}
                                className={`text-base font-medium transition-colors ${pathname === link.href
                                    ? 'text-blue-600'
                                    : 'text-zinc-600 hover:text-zinc-900'
                                    }`}
                            >
                                {link.label}
                            </Link>
                        ))}
                    </div>
                </div>
            )}
        </nav>
    )
}
