import { useState, useEffect, useCallback, useRef } from "preact/hooks";
import { clampPage, createListLoader, type ListRequest } from "./list-loader";
import type { ListItem } from "../../lib/types";
import QuestionCard from "./QuestionCard";
import BillCard from "./BillCard";
import SittingCard from "./SittingCard";

interface Props {
  contentType: "question" | "bill" | "motion" | "sitting" | "clarification";
  dataUrl: string;
  totalCount: number;
  pageSize?: number;
  placeholder?: string;
  showSearch?: boolean;
  initialItems: ListItem[];
}

export default function PaginatedList({
  contentType,
  dataUrl,
  totalCount,
  pageSize = 20,
  placeholder = "Search...",
  showSearch = true,
  initialItems,
}: Props) {
  const [view, setView] = useState({
    items: initialItems,
    total: totalCount,
    page: 1,
  });
  const [pendingPage, setPendingPage] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sequence = useRef(0);
  const request = useRef<ListRequest>({ query: "", from: "", to: "", page: 1 });
  const loader = useRef<ReturnType<typeof createListLoader>>();
  if (!loader.current)
    loader.current = createListLoader({
      initialItems,
      total: totalCount,
      size: pageSize,
      type: contentType,
      fetchData: async () => {
        const response = await fetch(dataUrl);
        if (!response.ok) throw new Error("List request failed");
        const data = await response.json();
        if (!Array.isArray(data.items)) throw new Error("Invalid list data");
        return data.items;
      },
      loadIndex: async () => {
        try {
          const base = (import.meta as any).env?.BASE_URL || "/";
          const path = `${base}pagefind/pagefind.js`.replace(/\/+/g, "/");
          return await import(/* @vite-ignore */ path);
        } catch {
          return null;
        }
      },
    });
  const cancelPending = useCallback(() => {
    if (debounceRef.current !== null) clearTimeout(debounceRef.current);
    debounceRef.current = null;
    sequence.current += 1;
  }, []);
  const run = useCallback(
    async (next: ListRequest, showLoading = true) => {
      cancelPending();
      const seq = sequence.current;
      request.current = next;
      setPendingPage(next.page);
      // The unfiltered first page is already in the generated HTML.
      const usesInitialItems =
        next.page === 1 && !next.from && !next.to && next.query.trim().length < 3;
      setIsLoading(showLoading && !usesInitialItems);
      setError(false);
      try {
        const result = await loader.current!(next);
        if (seq !== sequence.current) return;
        request.current = { ...next, page: result.page };
        setView(result);
        const url = new URL(window.location.href);
        const values = {
          q: next.query.trim().length > 2 ? next.query.trim() : "",
          from: next.from,
          to: next.to,
          page: result.page > 1 ? String(result.page) : "",
        };
        for (const [key, value] of Object.entries(values)) {
          if (value) url.searchParams.set(key, value);
          else url.searchParams.delete(key);
        }
        window.history.replaceState({}, "", url.toString());
      } catch {
        if (seq === sequence.current) setError(true);
      } finally {
        if (seq === sequence.current) {
          setIsLoading(false);
          setPendingPage(null);
        }
      }
    },
    [cancelPending],
  );
  const change = (next: ListRequest) => {
    setQuery(next.query);
    setDateFrom(next.from);
    setDateTo(next.to);
    void run(next);
  };
  const handleSearchInput = (event: Event) => {
    const value = (event.target as HTMLInputElement).value;
    setQuery(value);
    cancelPending();
    const next = { ...request.current, query: value, page: 1 };
    request.current = next;
    debounceRef.current = setTimeout(() => {
      void run(next);
    }, 150);
  };
  const handleClear = () => {
    change({ ...request.current, query: "", page: 1 });
    inputRef.current?.focus();
  };
  const handleKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Escape" && query) handleClear();
  };
  const handleDateFromChange = (event: Event) =>
    change({
      ...request.current,
      from: (event.target as HTMLInputElement).value,
      page: 1,
    });
  const handleDateToChange = (event: Event) =>
    change({
      ...request.current,
      to: (event.target as HTMLInputElement).value,
      page: 1,
    });
  const handleClearDates = () =>
    change({ ...request.current, from: "", to: "", page: 1 });
  const handlePageChange = (page: number) => {
    // Keep the current rows and page label until the requested page is ready.
    void run({ ...request.current, page }, false);
  };
  const prefetchPage = (page: number) => {
    if (page < 1 || page > Math.ceil(view.total / pageSize)) return;
    // Share the loader's JSON and fragment promises with the eventual click.
    // A failed prefetch is silent; a click can retry and report any failure.
    void loader.current!({ ...request.current, page }).catch(() => {});
  };
  useEffect(() => {
    const restore = () => {
      const params = new URLSearchParams(window.location.search);
      change({
        query: params.get("q") || "",
        from: params.get("from") || "",
        to: params.get("to") || "",
        page: Number(params.get("page") || 1),
      });
    };
    restore();
    window.addEventListener("popstate", restore);
    return () => {
      cancelPending();
      window.removeEventListener("popstate", restore);
    };
  }, []);
  const page = view.page;
  const navigationPage = clampPage(pendingPage ?? page, view.total, pageSize);
  const currentItems = view.items;
  const currentTotalPages = Math.ceil(view.total / pageSize);
  const hasDateFilter = Boolean(dateFrom || dateTo);
  const isSearchMode = query.trim().length > 2;
  const isDateFilterMode = hasDateFilter && !isSearchMode;
  const start = view.total ? (page - 1) * pageSize + 1 : 0;
  const end = Math.min(page * pageSize, view.total);
  const dateRangeLabel = hasDateFilter
    ? ` (${dateFrom || "start"}\u2009\u2013\u2009${dateTo || "present"})`
    : "";
  const statusText = isLoading
    ? "Loading results…"
    : error
      ? "Could not load results. Try again."
      : isSearchMode
        ? view.total
          ? `Found ${view.total} results (${start}-${end})${dateRangeLabel}`
          : "No results found"
        : isDateFilterMode
          ? view.total === 0
            ? `No items found${dateRangeLabel}`
            : `${view.total} items${dateRangeLabel} (${start}-${end})`
          : `Showing ${start}-${end} of ${view.total}`;

  // Render card based on content type
  const renderCard = (item: ListItem) => {
    switch (contentType) {
      case "bill":
        return <BillCard item={item} />;
      case "sitting":
        return <SittingCard item={item} />;
      case "question":
      case "motion":
      case "clarification":
      default:
        return <QuestionCard item={item} />;
    }
  };

  return (
    <div class="paginated-list-wrapper">
      {/* Search input */}
      {showSearch && (
        <div class="mb-4">
          <div class="relative">
            <svg
              class="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink/40 pointer-events-none"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="1.5"
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <input
              ref={inputRef}
              type="text"
              aria-label={placeholder}
              class="w-full rounded-lg border border-border bg-surface px-4 py-2.5 pl-10 pr-10 font-ui text-sm text-ink placeholder:text-ink/40 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/20 transition-colors"
              placeholder={placeholder}
              autocomplete="off"
              spellcheck={false}
              value={query}
              onInput={handleSearchInput}
              onKeyDown={handleKeyDown}
            />
            {query && (
              <button
                type="button"
                class="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-ink/40 hover:text-ink transition-colors"
                aria-label="Clear search"
                onClick={handleClear}
              >
                <svg fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
              </button>
            )}
          </div>
        </div>
      )}

      {/* Date range filters */}
      <div class="mb-6 flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-2">
          <label
            class="text-xs font-ui uppercase tracking-wider text-ink-muted"
            for="date-from"
          >
            From
          </label>
          <input
            id="date-from"
            type="date"
            class="rounded-lg border border-border bg-surface px-3 py-1.5 font-ui text-sm text-ink focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/20 transition-colors"
            value={dateFrom}
            onInput={handleDateFromChange}
          />
        </div>
        <div class="flex items-center gap-2">
          <label
            class="text-xs font-ui uppercase tracking-wider text-ink-muted"
            for="date-to"
          >
            To
          </label>
          <input
            id="date-to"
            type="date"
            class="rounded-lg border border-border bg-surface px-3 py-1.5 font-ui text-sm text-ink focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/20 transition-colors"
            value={dateTo}
            onInput={handleDateToChange}
          />
        </div>
        {hasDateFilter && (
          <button
            type="button"
            class="border border-border bg-surface px-3 py-2 font-ui text-xs text-ink-muted hover:text-ink hover:border-accent/30 transition-colors"
            onClick={handleClearDates}
          >
            Clear dates
          </button>
        )}
      </div>

      {/* Status text */}
      <p
        role="status"
        aria-live="polite"
        class="font-sans text-sm text-ink-muted mb-6"
      >
        {statusText}
      </p>

      {/* Loading indicator */}
      {isLoading && (
        <div class="flex items-center justify-center py-8">
          <div class="animate-spin h-6 w-6 border-2 border-accent border-t-transparent rounded-full" />
        </div>
      )}

      {error && (
        <button
          type="button"
          class="rounded-lg border border-border bg-surface px-4 py-2 font-ui text-sm text-ink/70 hover:border-accent/30 hover:text-accent"
          onClick={() => run(request.current)}
        >
          Retry
        </button>
      )}

      {/* Item list */}
      {!isLoading && !error && (
        <div class="flex flex-col border-t border-border -mx-6 sm:mx-0">
          {currentItems.length === 0 ? (
            <p class="py-12 text-center font-body text-ink-muted">
              {isSearchMode || isDateFilterMode
                ? "No results found"
                : "No items found"}
            </p>
          ) : (
            currentItems.map((item) => (
              <div key={item.id}>{renderCard(item)}</div>
            ))
          )}
        </div>
      )}

      {/* Pagination controls */}
      {currentTotalPages > 1 && (
        <nav
          class="flex items-center justify-center gap-4 py-6"
          aria-label="Pagination"
        >
          <button
            class="flex items-center gap-1.5 rounded-lg border border-border bg-surface px-4 py-2 font-ui text-sm text-ink/70 transition-all hover:border-accent/30 hover:text-accent disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:border-border disabled:hover:text-ink/70"
            disabled={navigationPage === 1}
            onPointerEnter={() => prefetchPage(navigationPage - 1)}
            onFocus={() => prefetchPage(navigationPage - 1)}
            onClick={() => handlePageChange(navigationPage - 1)}
          >
            <svg
              class="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="1.5"
                d="M15 19l-7-7 7-7"
              />
            </svg>
            Previous
          </button>
          <span class="font-ui text-sm text-ink/50">
            Page <span class="font-medium text-ink">{page}</span> of{" "}
            <span class="font-medium text-ink">{currentTotalPages}</span>
          </span>
          <button
            class="flex items-center gap-1.5 rounded-lg border border-border bg-surface px-4 py-2 font-ui text-sm text-ink/70 transition-all hover:border-accent/30 hover:text-accent disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:border-border disabled:hover:text-ink/70"
            disabled={navigationPage >= currentTotalPages}
            onPointerEnter={() => prefetchPage(navigationPage + 1)}
            onFocus={() => prefetchPage(navigationPage + 1)}
            onClick={() => handlePageChange(navigationPage + 1)}
          >
            Next
            <svg
              class="h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="1.5"
                d="M9 5l7 7-7 7"
              />
            </svg>
          </button>
        </nav>
      )}
    </div>
  );
}
