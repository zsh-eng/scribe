# Project guidelines

- Use Bun inside `astro/` and uv inside `python/`.
- Read [architecture](docs/architecture.md) for module responsibilities and
  [operations](docs/operations.md) for pipeline and deployment commands.
- Keep ingestion atomic per sitting and preserve public IDs and curated corrections.
- Model/prompt changes are review signals; regenerate summaries only when explicitly requested.
- Budget releases require source reconciliation; preserve estimate/actual/revised labels.
- Bill introduction is first reading (`BI`); debate is second reading (`BP`). Status is
  derived from sections. The schema does not track passage or third-reading dates.
- Verify with temporary databases/fake providers and an Astro build as appropriate.
  Do not use production ingestion, paid generation or deployment as routine tests.
- After edits, suggest a review order for changed files, with relevant line numbers.
