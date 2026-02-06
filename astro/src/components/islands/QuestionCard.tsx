import type { ListItem, TagColor } from "../../lib/types";
import { formatDate, typeBadgeConfig, categoryLabels } from "../../lib/types";
import { slugify } from "../../lib/slugify";
import Tag from "./Tag";

interface Props {
  item: ListItem;
}

export default function QuestionCard({ item }: Props) {
  // Determine badge config - category takes precedence
  let badgeConfig: { label: string; color: TagColor };
  if (item.category && categoryLabels[item.category]) {
    badgeConfig = { label: categoryLabels[item.category], color: "indigo" };
  } else if (item.type && typeBadgeConfig[item.type]) {
    badgeConfig = typeBadgeConfig[item.type];
  } else {
    badgeConfig = { label: item.type || "", color: "muted" };
  }

  return (
    <a
      href={`/questions/${slugify(item.title || "", item.id)}`}
      class="group block p-5 border-b border-border transition-colors hover:bg-warm cursor-pointer"
      data-pagefind-meta={`id:${item.id}`}
    >
      <div class="flex flex-wrap items-center gap-2 mb-2">
        <Tag color={badgeConfig.color}>{badgeConfig.label}</Tag>
        {item.ministry && <Tag color="green">{item.ministry}</Tag>}
        {item.date && (
          <span class="font-sans text-xs text-ink-muted">{formatDate(item.date)}</span>
        )}
      </div>

      <h3 class="font-display text-lg text-ink leading-snug mb-2 group-hover:text-accent transition-colors line-clamp-2">
        {item.title}
      </h3>

      {item.speakers && item.speakers.length > 0 && (
        <div class="flex flex-wrap gap-2 mb-2">
          {item.speakers.slice(0, 3).map((speaker) => (
            <span key={speaker} class="font-sans text-xs text-accent">
              {speaker}
            </span>
          ))}
          {item.speakers.length > 3 && (
            <span class="font-sans text-xs text-ink-muted">
              +{item.speakers.length - 3} more
            </span>
          )}
        </div>
      )}

      {item.snippet && (
        <p class="font-body text-sm text-ink-soft leading-relaxed line-clamp-1">
          {item.snippet}
        </p>
      )}
    </a>
  );
}
