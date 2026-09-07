# Product triage fixes — 8 September 2026

This follow-up resolves 16 of the 19 entries in the separate Second Reading product description. The original triage describes source commit `c7312ef`. Fix work started from `47915d7`.

Two GPT-6 Astra agents, with low reasoning effort, worked in isolated worktrees. No more than two workers were active. The coordinator reviewed changes, ran combined checks, and managed integration. Historical archive work was outside this scope.

## Fixed bugs

| IDs | Result | Implementation commit |
| --- | --- | --- |
| B-02–B-08 | Search and date-filtered pages survive reload. Failed data, index queries, and fragments report an error and can retry. Clear cancels pending input. Old requests cannot replace newer results. Visible pages wait for pending prefetches. Invalid page numbers are clamped. Search has a label and live status. | `d1326d4` |
| B-01 | The mobile menu button exposes its controlled menu and current expanded state. | `e80ba99` |
| B-11 | Duplicate ticker links are removed from keyboard navigation. Focus and reduced motion show a static, scrollable original row. | `e80ba99` |
| B-12 | Budget URLs restore the selected year and sector. | `e80ba99` |
| B-13 | Mobile MP and ministry period tabs support arrow keys, Home, and End. | `e80ba99` |
| B-14 | MP search reapplies the selected sort whenever the match set changes. | `e80ba99` |
| B-15 | MP and ministry search failures show feedback and Retry search. New input invalidates older requests immediately. | `65fa528` |
| B-09 | Bill reading sections display available plain text when HTML is absent. HTML retains precedence. | `e05a1d8` |
| B-18 | Statements without a dedicated category receive the detail URL already used by their sitting cards. The detail uses the correct oral/written label and a separate search type. Question lists and totals retain their existing scope. | `e05a1d8` |
| B-19 | Transcript enhancement retains meaningful text before, between, and after element blocks. | `e05a1d8` |

`de5b33c` restores global DOM descriptors after mounted list tests so tests can run together. `5fd452c` fixes two type-check findings from central review.

## UX choices in the fixes

- Main lists hide stale cards on failure and show an explicit Retry action. Profile searches retain previous cards with a message that identifies them as previous results and offers Retry search.
- Invalid page URLs move to the nearest valid page. Successful loading writes the corrected page into the URL.
- Period tabs select and focus the next tab on arrow-key input, with wrapping at either end.
- Ticker focus stops animation, hides the duplicate row, and permits horizontal scrolling. Pointer links in the normal animated duplicate remain usable.
- The statement repair preserves existing URLs under `/questions/`. It does not introduce a new Statements list or change question counts.

## Decisions still required

| ID | Decision | Suggested direction for review |
| --- | --- | --- |
| B-10 | Should Home call a BP record “Passed” or use “2nd Reading”, as the detail does? | Use the common stage label unless a separate verified status establishes passage. Confirm the intended source interpretation first. |
| B-16 | How should keyboard and touch users inspect detailed chart values and expand sectors? | Choose an equivalent data table, direct keyboard chart controls, or both. This affects layout and interaction. |
| B-17 | What should ministry totals count: sections, distinct bills, or another defined unit? | Define one counting rule, or explicitly label each different scope, before changing totals. |

## Validation

- The unchanged baseline had 6 passing tests. The combined suite has 39 passing tests and 182 assertions, including controlled request failures and races, production script handlers, synthetic SQLite routes, and rendered transcript output.
- The fixture production build generated and indexed 124 pages.
- A full build against the current publication database generated and indexed 19,953 pages in 136.94 seconds. The final type annotation and null guard were then verified with the fixture build and combined tests.
- The full type check remains red: 117 existing errors, down from 227 at baseline. Comparison by file, error code, and message found no new diagnostics after normalizing worktree paths. This change does not resolve the wider type-check backlog.
- Browser checks passed for indexed search page restoration, date-filtered page restoration, invalid-page correction, failed JSON request and Retry recovery, mobile menu state, MP tab arrow keys, focused ticker animation, both plain-text bill reading slots, and statement detail text and search type.
- B-09 and B-18 were reproduced with synthetic records. The current publication database had no matching affected records. B-19 was verified with mixed-text fixtures; occurrence in published content was not established.
- Accessible attributes and keyboard behavior were checked. Physical screen-reader output and physical touch chart interaction were not tested.

## Suggested review order

1. `astro/src/components/islands/list-loader.ts`, then `PaginatedList.tsx` and `astro/tests/list-state.test.tsx`: request caching, page bounds, stale-request checks, and retry behavior.
2. `astro/src/pages/members/[slug].astro` and `astro/src/pages/ministries/[slug].astro`, then `profile-search.test.ts`: tab keys and profile error recovery.
3. `Navbar.astro`, `BudgetTreemapGraph.astro`, `members/index.astro`, `index.astro`, and `global.css`, then `reader-controls.test.ts` and `ticker.test.ts`: menu, URL state, sorting, and ticker behavior.
4. `TranscriptDialogue.astro`, bill detail, `lib/queries/sections.ts`, and question detail, then `reading.test.ts`: text preservation and additive statement routes.
