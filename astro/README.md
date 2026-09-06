# Astro Frontend

The Second Reading frontend is built with [Astro](https://astro.build/) and styled with Tailwind CSS. It is mostly static, with islands used for paginated content and client-side search.

## Prerequisites

The SQLite database (`data/parliament.db`) must be generated first using the Python scripts in `/python`.

## Development

```sh
cd astro
bun install
bun run build   # required for Pagefind search index
bun run dev
```

Open [http://localhost:4321](http://localhost:4321) to view the app.

## Search Indexing (Pagefind)

Pagefind requires a production build to create the search index before it can be used in dev mode. Run `bun run build` at least once before `bun run dev`.

## Queries and deployment

Build-time SQL lives in `src/lib/queries/`, re-exported through `src/lib/db.ts`.
Query result types are separate from the UI helpers in `src/lib/types.ts`.

Use the [publication workflow](../docs/operations.md#reruns-and-recovery) from the repository
root so successful deployments update the publication marker. `bun run deploy` is the
low-level Wrangler command and does not update that marker.
