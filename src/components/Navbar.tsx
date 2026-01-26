'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

export default function Navbar() {
    const pathname = usePathname()

    const navLinks = [
        { href: '/', label: 'Questions' },
        { href: '/members', label: 'Members' },
        { href: '/ministries', label: 'Ministries' },
    ]

    return (
        <nav className="sticky top-0 z-50 border-b border-zinc-200 bg-white/80 backdrop-blur-sm dark:border-zinc-800 dark:bg-zinc-950/80">
            <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
                <Link href="/" className="text-xl font-bold text-zinc-900 dark:text-white">
                    🇸🇬 Parliament
                </Link>
                <div className="flex gap-6">
                    {navLinks.map((link) => (
                        <Link
                            key={link.href}
                            href={link.href}
                            className={`text-sm font-medium transition-colors ${pathname === link.href
                                ? 'text-blue-600 dark:text-blue-400'
                                : 'text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white'
                                }`}
                        >
                            {link.label}
                        </Link>
                    ))}
                </div>
            </div>
        </nav>
    )
}
