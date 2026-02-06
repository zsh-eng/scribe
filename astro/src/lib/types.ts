// Shared types for PaginatedList and card components

export interface Speaker {
  memberId: string;
  name: string;
  constituency: string | null;
  designation: string | null;
}

// Unified item type for paginated lists
export interface ListItem {
  id: string;
  title?: string;
  date?: string;
  type?: string;
  category?: string;
  ministry?: string;
  speakers?: string[];
  snippet?: string;
  // Session-specific fields
  parliament?: number;
  sessionNo?: number;
  sittingNo?: number;
  sectionCount?: number;
  // Bill-specific fields
  firstReadingDate?: string;
  hasSecondReading?: boolean;
}

// Type badge configuration
export const typeBadgeConfig: Record<string, { label: string; color: TagColor }> = {
  OA: { label: "Oral Answer", color: "blue" },
  WA: { label: "Written Answer", color: "purple" },
  WANA: { label: "No Answer", color: "muted" },
  BI: { label: "1st Reading", color: "green" },
  BP: { label: "2nd Reading", color: "green" },
};

export const categoryLabels: Record<string, string> = {
  motion: "Motion",
  adjournment_motion: "Adjournment Motion",
  clarification: "Clarification",
  statement: "Statement",
};

export type TagColor = "accent" | "muted" | "blue" | "green" | "amber" | "purple" | "indigo";

export const tagColorClasses: Record<TagColor, string> = {
  accent: "bg-border-light text-accent",
  muted: "bg-border-light text-ink-muted",
  blue: "bg-wp-blue-bg text-wp-blue",
  green: "bg-status-passed-bg text-status-passed",
  amber: "bg-status-reading-bg text-status-reading",
  purple: "bg-purple-50 text-purple-700",
  indigo: "bg-indigo-50 text-indigo-700",
};

// Date formatters
export function formatDate(dateStr: string | undefined | null): string {
  if (!dateStr) return "";
  return new Date(dateStr).toLocaleDateString("en-SG", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatSessionDate(dateStr: string | undefined | null): string {
  if (!dateStr) return "";
  return new Date(dateStr).toLocaleDateString("en-SG", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

export function getOrdinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

// Get bill status based on reading data
export function getBillStatus(item: ListItem): { label: string; color: TagColor } {
  if (item.hasSecondReading) return { label: "2nd Reading", color: "accent" };
  return { label: "1st Reading", color: "muted" };
}
