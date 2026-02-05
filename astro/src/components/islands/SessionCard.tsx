import type { ListItem } from "../../lib/types";
import { formatSessionDate, getOrdinal } from "../../lib/types";

interface Props {
  item: ListItem;
}

export default function SessionCard({ item }: Props) {
  return (
    <a
      href={`/sessions/${item.id}`}
      class="group grid grid-cols-[160px_1fr_auto] items-center gap-6 py-4 border-b border-border transition-colors hover:bg-warm cursor-pointer px-2"
      data-pagefind-meta={`id:${item.id}`}
    >
      <div class="font-display text-base text-ink">
        {formatSessionDate(item.date)}
      </div>
      <div class="font-sans text-sm text-ink-muted">
        {getOrdinal(item.parliament || 0)} Parliament &middot;{" "}
        {getOrdinal(item.sessionNo || 0)} Session &middot;{" "}
        {getOrdinal(item.sittingNo || 0)} Sitting
      </div>
      <div class="font-sans text-xs text-ink-soft">
        {item.sectionCount !== undefined && `${item.sectionCount} items`}
      </div>
    </a>
  );
}
