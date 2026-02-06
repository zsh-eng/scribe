import type { ListItem } from "../../lib/types";
import { formatDate, getBillStatus } from "../../lib/types";
import { slugify } from "../../lib/slugify";
import Tag from "./Tag";

interface Props {
  item: ListItem;
}

export default function BillCard({ item }: Props) {
  const status = getBillStatus(item);

  return (
    <a
      href={`/bills/${slugify(item.title || "", item.id)}`}
      class="group block p-5 border-b border-border transition-colors hover:bg-warm cursor-pointer"
      data-pagefind-meta={`id:${item.id}`}
    >
      <div class="flex flex-wrap items-center gap-2 mb-2">
        <Tag color={status.color}>{status.label}</Tag>
        {item.firstReadingDate && (
          <span class="font-sans text-xs text-ink-muted">
            {formatDate(item.firstReadingDate)}
          </span>
        )}
      </div>

      <h3 class="font-display text-lg text-ink leading-snug mb-2 group-hover:text-accent transition-colors">
        {item.title}
      </h3>

      {item.ministry && (
        <div class="font-sans text-sm text-ink-muted">{item.ministry}</div>
      )}
    </a>
  );
}
