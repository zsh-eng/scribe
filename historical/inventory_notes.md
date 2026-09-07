# Historical sitting-date inventory

Run `python3 historical/inventory.py`. This reads the official public search index and opens `data/parliament.db` with SQLite `mode=ro`. It does not call the active ingestion code. Results are under `historical/data/inventory/`.

## Source and request contract

The official client at <https://sprs.parl.gov.sg/search/> loads `main.6c50b646860a7eb9.js`. Its search service sends a JSON POST to `/searchResult`. The search model has `fromday`, `frommonth`, `fromyear`, `today`, `tomonth`, `toyear`, `dateRange`, `parliamentNo`, `selectedSort`, `startIndex`, and `endIndex`. Module `646.d45e02a2b7cb000c.js` supplies these values to the service. Both modules were read on 8 September 2026.

The client also sends `{}` to `/getDisplayData`. Its `parlVOList` lists Legislative Assembly (1955 to 1965), with `parlNO: 0`, and Parliaments 1 through 15. This is the official search grouping. `legislative-assembly-0` does **not** mean that the Assembly had a term numbered zero. Historical report metadata can have Assembly term numbers that overlap Parliament numbers. Keep the `era` field when using that metadata.

The inventory always uses an explicit custom range from 1 January 1955 to the requested upper date. It does not rely on a default date range. The endpoint returns 20 topic rows even when a larger `endIndex` is requested. The inventory does not use topic counts as sitting counts.

## Enumeration

Each request selects all content, no member or legislature filter, and descending date order. The code records every date in the response, then sets the next upper date to one day before the oldest date in that response. It checks the returned date order and upper bound. It also checks that each page has one consistent `maxResult` value and that this count decreases between requests. Thus, a sitting with more than 20 topics requires only one request. No calendar day is guessed to be a sitting. The walk ends when the page contains every remaining result (`maxResult == len(response)`) or when the response is empty. The empty range before the first indexed sitting returned HTTP 500 during verification, so the final result count provides the termination proof. A fetch or parse failure stops the run. Every 100 pages, the code writes a partial inventory with `complete: false`. Only a completed walk writes `complete: true`.

Each `pages/YYYY-MM-DD.json` stores the URL, request, response, retrieval time, and SHA-256 of the response bytes. These files let a stopped run resume without fetching completed pages. Use `--refresh` to fetch the same range again. Use a separate `--output` path to preserve a previous snapshot.

`inventory.json` contains `complete`, `through_date`, `page_count`, `summary`, and `sittings`. Each sitting has an ISO `date`, `era`, `parliament` (the official search group), `era_id`, `report_version`, `evidence_page`, and `present_in_active`. `missing_dates.txt` has one missing ISO date per line, in date order. The active comparison is by date; it does not claim that existing sitting content is complete.

Completeness means all sitting dates in the official search index for the stated range. It does not prove that the index contains every physical historical report or every sitting before 1955. Source downloads and report parsing require separate checks.

## Verified inventory on 8 September 2026

The completed walk used 1,021 search pages and found 1,753 sitting dates from 22 April 1955 to 5 August 2026. Of these, 331 were present in the active database and 1,422 were missing. Every active sitting date was found in the index. Legislative Assembly accounts for 277 dates. `inventory.json` gives the per-Parliament counts.

The last page, `pages/1955-04-25.json`, returned four topics, all dated 22 April 1955, with `maxResult: "4"`. Thus, that page contains every remaining search result. The full cached walk was replayed with date-order, date-bound, result-count, and legislature-consistency checks. Temporary-database fixtures checked missing-date output, era separation, and rejection of inconsistent result counts.
