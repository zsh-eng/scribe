import { useState, useEffect, useCallback, useRef } from "preact/hooks";
import type { ListItem } from "../../lib/types";
import QuestionCard from "./QuestionCard";
import BillCard from "./BillCard";
import SittingCard from "./SittingCard";

interface DataResponse {
  items: ListItem[];
  total: number;
}

interface PagefindResult {
  id: string;
  data: () => Promise<{
    meta?: { id?: string };
    url: string;
    excerpt: string;
  }>;
}

interface PagefindSearch {
  results: PagefindResult[];
}

interface Pagefind {
  search: (
    query: string,
    options?: { filters?: Record<string, string> },
  ) => Promise<PagefindSearch>;
}

interface Props {
  contentType: "question" | "bill" | "motion" | "sitting" | "clarification";
  dataUrl: string;
  totalCount: number;
  pageSize?: number;
  placeholder?: string;
  showSearch?: boolean;
  initialItems: ListItem[];
}

// Filter items by date range using lexicographic comparison on YYYY-MM-DD strings
function filterByDateRange(
  items: ListItem[],
  from: string,
  to: string,
): ListItem[] {
  if (!from && !to) return items;
  return items.filter((item) => {
    if (!item.date) return false;
    if (from && item.date < from) return false;
    if (to && item.date > to) return false;
    return true;
  });
}

// Number of extra pages to prefetch ahead of the current page
const PREFETCH_PAGES = 2;

export default function PaginatedList({
  contentType,
  dataUrl,
  totalCount,
  pageSize = 20,
  placeholder = "Search...",
  showSearch = true,
  initialItems,
}: Props) {
  const STAGGER_LIMIT = 12;
  const [items, setItems] = useState<ListItem[]>(initialItems);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  // In search mode without date filter: holds only the current page's items
  // In search mode with date filter: holds ALL matched+filtered items (for client-side pagination)
  const [searchResults, setSearchResults] = useState<ListItem[]>([]);
  const [searchTotalCount, setSearchTotalCount] = useState(0);
  const [isSearchMode, setIsSearchMode] = useState(false);
  const [allData, setAllData] = useState<ListItem[] | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [filteredResults, setFilteredResults] = useState<ListItem[]>([]);
  // Whether search results include date filtering (affects pagination strategy)
  const [searchHasDateFilter, setSearchHasDateFilter] = useState(false);

  const pagefindRef = useRef<Pagefind | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const searchSeqRef = useRef(0);
  // Store raw pagefind results for lazy fragment fetching
  const pagefindResultsRef = useRef<PagefindResult[]>([]);
  // Cache of resolved pagefind result index -> meta.id
  const resolvedIdsRef = useRef<Map<number, string>>(new Map());
  // Tracks fragment indices currently being resolved to avoid duplicate fetches
  const resolvingIndicesRef = useRef<Set<number>>(new Set());

  const hasDateFilter = dateFrom !== "" || dateTo !== "";
  const isDateFilterMode = hasDateFilter && !isSearchMode;

  // Calculate pagination values
  const totalPages = Math.ceil(totalCount / pageSize);
  const searchTotalPages = searchHasDateFilter
    ? Math.ceil(searchResults.length / pageSize)
    : Math.ceil(searchTotalCount / pageSize);
  const filteredTotalPages = Math.ceil(filteredResults.length / pageSize);
  const currentTotalPages = isSearchMode
    ? searchTotalPages
    : isDateFilterMode
      ? filteredTotalPages
      : totalPages;
  const currentTotalCount = isSearchMode
    ? (searchHasDateFilter ? searchResults.length : searchTotalCount)
    : isDateFilterMode
      ? filteredResults.length
      : totalCount;

  // Get current page items
  // In lazy search mode (no date filter): searchResults IS the current page's items
  // In date-filtered search mode: searchResults holds all items, slice for current page
  const currentItems = isSearchMode
    ? (searchHasDateFilter
      ? searchResults.slice((page - 1) * pageSize, page * pageSize)
      : searchResults)
    : isDateFilterMode
      ? filteredResults.slice((page - 1) * pageSize, page * pageSize)
      : items;

  // Status text
  const start = currentTotalCount === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, currentTotalCount);
  const dateRangeLabel = hasDateFilter
    ? ` (${dateFrom || "start"}\u2009\u2013\u2009${dateTo || "present"})`
    : "";
  const statusText = isSearchMode
    ? currentTotalCount === 0
      ? "No results found"
      : `Found ${currentTotalCount} results (${start}-${end})${dateRangeLabel}`
    : isDateFilterMode
      ? currentTotalCount === 0
        ? `No items found${dateRangeLabel}`
        : `${currentTotalCount} items${dateRangeLabel} (${start}-${end})`
      : `Showing ${start}-${end} of ${currentTotalCount}`;

  // Load Pagefind
  const loadPagefind = useCallback(async (): Promise<Pagefind | null> => {
    if (pagefindRef.current) return pagefindRef.current;
    try {
      const base = (import.meta as any).env?.BASE_URL || "/";
      const pagefindPath = `${base}pagefind/pagefind.js`.replace(/\/+/g, "/");
      pagefindRef.current = (await import(
        /* @vite-ignore */ pagefindPath
      )) as Pagefind;
      return pagefindRef.current;
    } catch {
      console.warn("Pagefind not available - search will be disabled.");
      return null;
    }
  }, []);

  // Fetch all JSON data
  const fetchAllData = useCallback(async (): Promise<ListItem[]> => {
    if (allData) return allData;
    try {
      const response = await fetch(dataUrl);
      const data: DataResponse = await response.json();
      setAllData(data.items);
      return data.items;
    } catch (e) {
      console.error("Failed to fetch JSON data:", e);
      return [];
    }
  }, [dataUrl, allData]);

  // Resolve a set of pagefind result indices and cache index -> id mappings.
  const resolveFragmentIndices = useCallback(
    async (indices: number[], seq: number): Promise<void> => {
      const pfResults = pagefindResultsRef.current;
      const pending: number[] = [];

      for (const idx of indices) {
        if (
          idx >= 0 &&
          idx < pfResults.length &&
          !resolvedIdsRef.current.has(idx) &&
          !resolvingIndicesRef.current.has(idx)
        ) {
          pending.push(idx);
          resolvingIndicesRef.current.add(idx);
        }
      }

      if (!pending.length) return;

      try {
        const resolved = await Promise.all(
          pending.map(async (idx) => {
            try {
              const resultData = await pfResults[idx].data();
              return { idx, id: resultData.meta?.id };
            } catch {
              return { idx, id: undefined };
            }
          }),
        );

        // Ignore stale async work from a previous search/query.
        if (
          seq !== searchSeqRef.current ||
          pagefindResultsRef.current !== pfResults
        ) {
          return;
        }

        for (const { idx, id } of resolved) {
          if (id) {
            resolvedIdsRef.current.set(idx, id);
          }
        }
      } finally {
        for (const idx of pending) {
          resolvingIndicesRef.current.delete(idx);
        }
      }
    },
    [],
  );

  // Resolve and return ListItems for the requested page.
  // Prefetches additional pages in the background without blocking UI update.
  const resolveSearchPage = useCallback(
    async (
      pageNum: number,
      data: ListItem[],
      seq: number,
    ): Promise<ListItem[] | null> => {
      const pfResults = pagefindResultsRef.current;
      if (!pfResults.length) return [];

      const dataById = new Map(data.map((item) => [item.id, item]));

      // Determine the window of indices to resolve (current page + prefetch buffer)
      const startIdx = (pageNum - 1) * pageSize;
      const pageEndIdx = Math.min(pageNum * pageSize, pfResults.length);

      // Resolve current page first so we can render quickly.
      const unresolvedCurrentPage: number[] = [];
      for (let i = startIdx; i < pageEndIdx; i++) {
        if (!resolvedIdsRef.current.has(i)) {
          unresolvedCurrentPage.push(i);
        }
      }

      await resolveFragmentIndices(unresolvedCurrentPage, seq);
      if (seq !== searchSeqRef.current) return null;

      // Build ListItems for the current page only
      const pageItems: ListItem[] = [];
      for (let i = startIdx; i < pageEndIdx; i++) {
        const id = resolvedIdsRef.current.get(i);
        if (id) {
          const item = dataById.get(id);
          if (item) pageItems.push(item);
        }
      }

      // Prefetch subsequent pages in the background.
      const prefetchEndIdx = Math.min(
        (pageNum + PREFETCH_PAGES) * pageSize,
        pfResults.length,
      );
      if (pageEndIdx < prefetchEndIdx) {
        const prefetchIndices: number[] = [];
        for (let i = pageEndIdx; i < prefetchEndIdx; i++) {
          if (!resolvedIdsRef.current.has(i)) {
            prefetchIndices.push(i);
          }
        }
        if (prefetchIndices.length > 0) {
          void resolveFragmentIndices(prefetchIndices, seq);
        }
      }

      return pageItems;
    },
    [pageSize, resolveFragmentIndices],
  );

  // Update URL parameters
  const updateUrlParams = useCallback(
    (newPage: number, newQuery: string, from?: string, to?: string) => {
      const url = new URL(window.location.href);
      if (newQuery) {
        url.searchParams.set("q", newQuery);
      } else {
        url.searchParams.delete("q");
      }
      if (newPage > 1) {
        url.searchParams.set("page", String(newPage));
      } else {
        url.searchParams.delete("page");
      }
      // Use provided values, or fall back to current state
      const fromVal = from !== undefined ? from : dateFrom;
      const toVal = to !== undefined ? to : dateTo;
      if (fromVal) {
        url.searchParams.set("from", fromVal);
      } else {
        url.searchParams.delete("from");
      }
      if (toVal) {
        url.searchParams.set("to", toVal);
      } else {
        url.searchParams.delete("to");
      }
      window.history.replaceState({}, "", url.toString());
    },
    [dateFrom, dateTo],
  );

  // Apply date filter (no search query — browse + date filter mode)
  const applyDateFilter = useCallback(
    async (from: string, to: string) => {
      if (!from && !to) {
        // No date filter — return to browse mode
        setFilteredResults([]);
        setPage(1);
        setItems(initialItems);
        updateUrlParams(1, "", "", "");
        return;
      }

      setIsLoading(true);
      const data = await fetchAllData();
      const filtered = filterByDateRange(data, from, to);
      setFilteredResults(filtered);
      setPage(1);
      updateUrlParams(1, "", from, to);
      setIsLoading(false);
    },
    [fetchAllData, initialItems, updateUrlParams],
  );

  // Perform search
  const performSearch = useCallback(
    async (searchQuery: string, from?: string, to?: string) => {
      const searchSeq = (searchSeqRef.current += 1);
      const trimmedQuery = searchQuery.trim();
      const filterFrom = from !== undefined ? from : dateFrom;
      const filterTo = to !== undefined ? to : dateTo;

      if (!trimmedQuery || trimmedQuery.length <= 2) {
        setIsSearchMode(false);
        setSearchResults([]);
        setSearchTotalCount(0);
        setSearchHasDateFilter(false);
        pagefindResultsRef.current = [];
        resolvedIdsRef.current = new Map();
        resolvingIndicesRef.current.clear();
        setPage(1);
        setItems(initialItems);
        // If date filter active, apply it
        if (filterFrom || filterTo) {
          applyDateFilter(filterFrom, filterTo);
        } else {
          updateUrlParams(1, "", filterFrom, filterTo);
        }
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      const pf = await loadPagefind();
      const data = await fetchAllData();
      if (searchSeq !== searchSeqRef.current) return;

      if (!pf) {
        // Fallback: simple text matching
        const lowerQuery = searchQuery.toLowerCase();
        let matched = data.filter((item) => {
          const text = [
            item.title,
            item.ministry,
            item.snippet,
            ...(item.speakers || []),
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();
          return text.includes(lowerQuery);
        });

        matched = filterByDateRange(matched, filterFrom, filterTo);

        setIsSearchMode(true);
        setSearchHasDateFilter(true); // fallback always has all results
        setSearchResults(matched);
        setSearchTotalCount(matched.length);
        setPage(1);
        updateUrlParams(1, searchQuery, filterFrom, filterTo);
        if (searchSeq === searchSeqRef.current) {
          setIsLoading(false);
        }
        return;
      }

      // Use Pagefind for search
      const results = await pf.search(trimmedQuery, {
        filters: { type: contentType },
      });
      if (searchSeq !== searchSeqRef.current) return;

      const hasDateRange = !!(filterFrom || filterTo);

      if (hasDateRange) {
        // Date filter active: resolve ALL fragments in parallel so we can
        // filter by date and get an accurate count for client-side pagination.
        const allFragments = await Promise.all(
          results.results.map((r) => r.data()),
        );
        if (searchSeq !== searchSeqRef.current) return;

        const dataById = new Map(data.map((item) => [item.id, item]));
        let matched: ListItem[] = [];
        for (const fragment of allFragments) {
          if (fragment.meta?.id) {
            const item = dataById.get(fragment.meta.id);
            if (item) matched.push(item);
          }
        }

        matched = filterByDateRange(matched, filterFrom, filterTo);

        pagefindResultsRef.current = [];
        resolvedIdsRef.current = new Map();
        resolvingIndicesRef.current.clear();
        setIsSearchMode(true);
        setSearchHasDateFilter(true);
        setSearchResults(matched);
        setSearchTotalCount(matched.length);
        setPage(1);
        updateUrlParams(1, trimmedQuery, filterFrom, filterTo);
        if (searchSeq === searchSeqRef.current) {
          setIsLoading(false);
        }
      } else {
        // No date filter: use lazy page-based fragment fetching.
        // Store raw results and only resolve fragments for the first few pages.
        pagefindResultsRef.current = results.results;
        resolvedIdsRef.current = new Map();
        resolvingIndicesRef.current.clear();

        setIsSearchMode(true);
        setSearchHasDateFilter(false);
        setSearchTotalCount(results.results.length);
        setPage(1);

        // Resolve fragments for page 1 (+ prefetch buffer)
        const pageItems = await resolveSearchPage(1, data, searchSeq);
        if (pageItems === null) return; // superseded

        setSearchResults(pageItems);
        updateUrlParams(1, trimmedQuery, filterFrom, filterTo);
        if (searchSeq === searchSeqRef.current) {
          setIsLoading(false);
        }
      }
    },
    [
      contentType,
      dateFrom,
      dateTo,
      fetchAllData,
      initialItems,
      loadPagefind,
      resolveSearchPage,
      updateUrlParams,
      applyDateFilter,
    ],
  );

  // Load page data for browse mode
  const loadPage = useCallback(
    async (pageNum: number) => {
      if (pageNum === 1) {
        setItems(initialItems);
        return;
      }

      setIsLoading(true);
      const data = await fetchAllData();
      const start = (pageNum - 1) * pageSize;
      const pageItems = data.slice(start, start + pageSize);
      setItems(pageItems);
      setIsLoading(false);
    },
    [fetchAllData, initialItems, pageSize],
  );

  // Handle page change
  const handlePageChange = useCallback(
    async (newPage: number) => {
      if (newPage < 1 || newPage > currentTotalPages) return;
      setPage(newPage);
      if (isSearchMode && !searchHasDateFilter) {
        // Lazy search mode: resolve fragments for the new page
        setIsLoading(true);
        const data = await fetchAllData();
        const seq = searchSeqRef.current;
        const pageItems = await resolveSearchPage(newPage, data, seq);
        if (pageItems !== null) {
          setSearchResults(pageItems);
          setIsLoading(false);
        }
        updateUrlParams(newPage, query);
      } else if (isSearchMode || isDateFilterMode) {
        // Date-filtered search or date filter mode: client-side slice
        updateUrlParams(newPage, isSearchMode ? query : "");
      } else {
        await loadPage(newPage);
        updateUrlParams(newPage, "");
      }
    },
    [
      currentTotalPages,
      isSearchMode,
      searchHasDateFilter,
      isDateFilterMode,
      fetchAllData,
      resolveSearchPage,
      loadPage,
      query,
      updateUrlParams,
    ],
  );

  // Handle search input
  const handleSearchInput = useCallback(
    (e: Event) => {
      const value = (e.target as HTMLInputElement).value;
      setQuery(value);

      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }

      debounceRef.current = setTimeout(() => {
        performSearch(value);
      }, 150);
    },
    [performSearch],
  );

  // Handle clear search text (preserve date filters)
  const handleClear = useCallback(() => {
    setQuery("");
    performSearch("");
    inputRef.current?.focus();
  }, [performSearch]);

  // Handle date changes
  const handleDateFromChange = useCallback(
    (e: Event) => {
      const value = (e.target as HTMLInputElement).value;
      setDateFrom(value);
      if (query.trim().length > 2) {
        performSearch(query, value, dateTo);
      } else {
        applyDateFilter(value, dateTo);
      }
    },
    [query, dateTo, performSearch, applyDateFilter],
  );

  const handleDateToChange = useCallback(
    (e: Event) => {
      const value = (e.target as HTMLInputElement).value;
      setDateTo(value);
      if (query.trim().length > 2) {
        performSearch(query, dateFrom, value);
      } else {
        applyDateFilter(dateFrom, value);
      }
    },
    [query, dateFrom, performSearch, applyDateFilter],
  );

  // Clear date filters
  const handleClearDates = useCallback(() => {
    setDateFrom("");
    setDateTo("");
    if (query.trim().length > 2) {
      performSearch(query, "", "");
    } else {
      setFilteredResults([]);
      setPage(1);
      setItems(initialItems);
      updateUrlParams(1, "", "", "");
    }
  }, [query, performSearch, initialItems, updateUrlParams]);

  // Handle escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && query) {
        setQuery("");
        performSearch("");
      }
    },
    [performSearch, query],
  );

  // Initialize from URL params
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const initialQuery = urlParams.get("q");
    const initialPage = urlParams.get("page");
    const initialFrom = urlParams.get("from") || "";
    const initialTo = urlParams.get("to") || "";

    if (initialFrom) setDateFrom(initialFrom);
    if (initialTo) setDateTo(initialTo);

    if (initialQuery) {
      setQuery(initialQuery);
      performSearch(initialQuery, initialFrom, initialTo);
    } else if (initialFrom || initialTo) {
      applyDateFilter(initialFrom, initialTo);
    } else if (initialPage) {
      const pageNum = parseInt(initialPage, 10);
      if (Number.isFinite(pageNum) && pageNum > 1) {
        setPage(pageNum);
        loadPage(pageNum);
      }
    }
  }, [loadPage, performSearch, applyDateFilter]);

  // Handle popstate for back/forward navigation
  useEffect(() => {
    const handlePopState = () => {
      const urlParams = new URLSearchParams(window.location.search);
      const queryParam = urlParams.get("q");
      const pageParam = urlParams.get("page");
      const fromParam = urlParams.get("from") || "";
      const toParam = urlParams.get("to") || "";

      setDateFrom(fromParam);
      setDateTo(toParam);

      if (queryParam) {
        setQuery(queryParam);
        performSearch(queryParam, fromParam, toParam);
      } else if (fromParam || toParam) {
        setQuery("");
        setIsSearchMode(false);
        setSearchResults([]);
        setSearchTotalCount(0);
        setSearchHasDateFilter(false);
        pagefindResultsRef.current = [];
        resolvedIdsRef.current = new Map();
        resolvingIndicesRef.current.clear();
        applyDateFilter(fromParam, toParam);
      } else {
        setQuery("");
        setIsSearchMode(false);
        setSearchResults([]);
        setSearchTotalCount(0);
        setSearchHasDateFilter(false);
        pagefindResultsRef.current = [];
        resolvedIdsRef.current = new Map();
        resolvingIndicesRef.current.clear();
        setFilteredResults([]);
        const pageNum = pageParam ? parseInt(pageParam, 10) : 1;
        const validPage =
          Number.isFinite(pageNum) && pageNum >= 1 ? pageNum : 1;
        setPage(validPage);
        loadPage(validPage);
      }
    };

    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, [loadPage, performSearch, applyDateFilter]);

  // Preload pagefind on mount
  useEffect(() => {
    loadPagefind();
  }, [loadPagefind]);

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
      <p class="font-sans text-sm text-ink-muted mb-6">{statusText}</p>

      {/* Loading indicator */}
      {isLoading && (
        <div class="flex items-center justify-center py-8">
          <div class="animate-spin h-6 w-6 border-2 border-accent border-t-transparent rounded-full" />
        </div>
      )}

      {/* Item list */}
      {!isLoading && (
        <div class="flex flex-col border-t border-border -mx-6 sm:mx-0">
          {currentItems.length === 0 ? (
            <p class="py-12 text-center font-body text-ink-muted">
              {isSearchMode || isDateFilterMode
                ? "No results found"
                : "No items found"}
            </p>
          ) : (
            currentItems.map((item, i) => {
              const isStaggered =
                !isSearchMode &&
                !hasDateFilter &&
                page === 1 &&
                i < STAGGER_LIMIT;
              return (
                <div
                  key={item.id}
                  class={isStaggered ? "animate-fade-up" : undefined}
                  style={
                    isStaggered
                      ? `animation-delay: ${0.1 + i * 0.05}s`
                      : undefined
                  }
                >
                  {renderCard(item)}
                </div>
              );
            })
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
            disabled={page === 1}
            onClick={() => handlePageChange(page - 1)}
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
            disabled={page >= currentTotalPages}
            onClick={() => handlePageChange(page + 1)}
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
