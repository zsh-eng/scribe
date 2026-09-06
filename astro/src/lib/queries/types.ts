// Database query result shapes. UI-only types live in ../types.ts.

export interface Sitting {
  id: string;
  date: string;
  sittingNo: number;
  parliament: number;
  sessionNo: number;
  volumeNo: number;
  format: string;
  url: string;
  sectionCount?: number;
}

export interface Member {
  id: string;
  name: string;
  summary?: string | null;
  sectionCount?: number;
  constituency?: string | null;
  designation?: string | null;
  attendanceTotal?: number;
  attendancePresent?: number;
}

export interface Ministry {
  id: string;
  name: string;
  acronym: string;
  sectionCount?: number;
}

export interface Speaker {
  memberId: string;
  name: string;
  constituency: string | null;
  designation: string | null;
}

export interface Section {
  id: string;
  sittingId: string;
  sittingDate?: string;
  sittingNo?: number;
  sectionType: string;
  sectionTitle: string;
  contentHtml?: string;
  contentPlain?: string;
  sectionOrder: number;
  ministry: string | null;
  ministryId: string | null;
  category: string | null;
  speakers?: Speaker[];
  sourceUrl?: string | null;
  summary?: string | null;
}

export interface Bill {
  id: string;
  title: string;
  ministryId: string | null;
  ministry?: string | null;
  firstReadingDate: string | null;
  firstReadingSittingId: string | null;
  hasSecondReading?: boolean;
  summary?: string | null;
}

export interface Attendee {
  id: string;
  name: string;
  present: boolean;
  constituency: string | null;
  designation: string | null;
}

export interface AttendanceRecord {
  sittingId: string;
  date: string;
  sittingNo: number;
  present: boolean;
}

export interface CurrentParliamentStats {
  involvements: number;
  questions: number;
  motions: number;
  bills: number;
  attendancePresent: number;
  attendanceTotal: number;
}

export interface ParliamentStats {
  parliament: number;
  involvements: number;
  oralQuestions: number;
  writtenQuestions: number;
  unansweredQuestions: number;
  motions: number;
  bills: number;
  attendancePresent: number;
  attendanceTotal: number;
}

export interface MemberMinistryStats {
  ministryId: string;
  ministryName: string;
  total: number;
  oralQuestions: number;
  writtenQuestions: number;
  unansweredQuestions: number;
  motions: number;
  bills: number;
}

export interface BillSection {
  id: string;
  sittingId: string;
  sittingDate: string;
  sittingNo: number;
  sectionType: string;
  sectionTitle: string;
  contentHtml: string;
  contentPlain: string;
  sourceUrl: string | null;
  speakers: Speaker[];
}

export interface MinistryParliamentStats {
  parliament: number;
  involvements: number;
  oralQuestions: number;
  writtenQuestions: number;
  unansweredQuestions: number;
  motions: number;
  bills: number;
}

export interface RecentBillReading {
  billId: string;
  billTitle: string;
  sectionType: string;
  sittingDate: string;
  ministry: string | null;
}

export interface LatestQuestion {
  id: string;
  sectionTitle: string;
  sittingDate: string;
  askerName: string | null;
  askerId: string | null;
  ministry: string | null;
}

export interface RecentMotion {
  id: string;
  sectionTitle: string;
  sittingDate: string;
}
