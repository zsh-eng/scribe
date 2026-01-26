// Types matching the current database schema

export interface Session {
    id: string
    date: string
    sittingNo: number
    parliament: number
    sessionNo: number
    volumeNo: number
    format: string
    url: string
    summary: string | null
}

export interface Member {
    id: string
    name: string
    summary?: string | null
    sectionCount?: number
}

export interface Ministry {
    id: string
    name: string
    acronym: string
    sectionCount?: number
}

export interface Speaker {
    memberId: string
    name: string
    constituency: string | null
    designation: string | null
}

export interface Section {
    id: string
    sessionId: string
    sessionDate: string
    sittingNo: number
    sectionType: string
    sectionTitle: string
    contentHtml: string
    contentPlain: string
    sectionOrder: number
    ministry: string | null
    ministryId: string | null
    speakers: Speaker[] | string[]
}

export interface FilterState {
    search: string
    ministry: string
    sectionType: string
}