import type { ListItem } from "../../lib/types";

export interface SearchResult {
  data(): Promise<{ meta?: { id?: string } }>;
}
export interface SearchIndex {
  search(
    query: string,
    options: { filters: Record<string, string> },
  ): Promise<{ results: SearchResult[] }>;
}
export interface ListRequest {
  query: string;
  from: string;
  to: string;
  page: number;
}
export interface ListView {
  items: ListItem[];
  total: number;
  page: number;
}
export function clampPage(page: number, total: number, size: number): number {
  return Math.min(
    Number.isSafeInteger(page) && page > 0 ? page : 1,
    Math.max(1, Math.ceil(total / size)),
  );
}

// Each search owns its fragment promises. A visible page waits for a pending prefetch.
export function createListLoader(options: {
  initialItems: ListItem[];
  total: number;
  size: number;
  type: string;
  fetchData(): Promise<ListItem[]>;
  loadIndex(): Promise<SearchIndex | null>;
}) {
  let dataPromise: Promise<ListItem[]> | undefined;
  let search:
    | {
        query: string;
        results: Promise<SearchResult[]>;
        fragments: Map<number, Promise<string | undefined>>;
      }
    | undefined;
  const data = () =>
    (dataPromise ??= options.fetchData().catch((error) => {
      dataPromise = undefined;
      throw error;
    }));
  return async (request: ListRequest): Promise<ListView> => {
    const query = request.query.trim();
    const searching = query.length > 2;
    const dates = Boolean(request.from || request.to);
    const filterDates = (items: ListItem[]) =>
      dates
        ? items.filter(
            (item) =>
              item.date &&
              (!request.from || item.date >= request.from) &&
              (!request.to || item.date <= request.to),
          )
        : items;
    const slice = (items: ListItem[]): ListView => {
      const page = clampPage(request.page, items.length, options.size);
      return {
        items: items.slice((page - 1) * options.size, page * options.size),
        total: items.length,
        page,
      };
    };
    if (
      !searching &&
      !dates &&
      clampPage(request.page, options.total, options.size) === 1
    ) {
      return { items: options.initialItems, total: options.total, page: 1 };
    }
    const items = await data();
    if (!searching) return slice(filterDates(items));
    const index = await options.loadIndex();
    if (!index) {
      return slice(
        filterDates(
          items.filter((item) =>
            [item.title, item.ministry, item.snippet, ...(item.speakers || [])]
              .filter(Boolean)
              .join(" ")
              .toLowerCase()
              .includes(query.toLowerCase()),
          ),
        ),
      );
    }
    if (!search || search.query !== query) {
      const session = {
        query,
        results: index
          .search(query, { filters: { type: options.type } })
          .then((result) => result.results),
        fragments: new Map<number, Promise<string | undefined>>(),
      };
      search = session;
      session.results.catch(() => {
        if (search === session) search = undefined;
      });
    }
    const session = search;
    const results = await session.results;
    const fragment = (position: number) => {
      let pending = session.fragments.get(position);
      if (!pending) {
        pending = results[position]
          .data()
          .then((result) => result.meta?.id)
          .catch((error) => {
            session.fragments.delete(position);
            throw error;
          });
        session.fragments.set(position, pending);
      }
      return pending;
    };
    const byId = new Map(items.map((item) => [item.id, item]));
    const resolve = async (start: number, end: number) =>
      (
        await Promise.all(
          Array.from({ length: end - start }, (_, offset) =>
            fragment(start + offset),
          ),
        )
      ).flatMap((id) => (id && byId.has(id) ? [byId.get(id)!] : []));
    if (dates) return slice(filterDates(await resolve(0, results.length)));
    const page = clampPage(request.page, results.length, options.size);
    const end = Math.min(page * options.size, results.length);
    const visible = await resolve((page - 1) * options.size, end);
    void resolve(
      end,
      Math.min((page + 2) * options.size, results.length),
    ).catch(() => {});
    return { items: visible, total: results.length, page };
  };
}
