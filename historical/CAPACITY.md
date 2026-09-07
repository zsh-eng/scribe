# Static archive capacity

Checked 2026-09-08. This is a read-only assessment of the live database and the existing build output. No build or deployment was run.

## Current source and output

The default build database is `data/parliament.db` (see `astro/src/lib/queries/connection.ts`). A caller can override this with `PARLIAMENT_DB_PATH`.

| Live database item | Count |
| --- | ---: |
| Sittings | 331 |
| Sections | 19,868 |
| Members | 199 |
| Bills | 443 |
| Ministries | 16 |

The sitting date range is **2016-01-15 through 2026-08-05**. This is the modern database, not a full historical archive.

Astro uses static output with `build.format: "file"`. The existing `astro/dist` files have modification times on 2026-09-06. Their counts are a build snapshot, not evidence of the remote deployment.

| HTML route group | Files |
| --- | ---: |
| Questions | 17,809 |
| Motions (including adjournment motions) | 998 |
| Clarifications | 147 |
| Bills | 443 |
| Sittings | 331 |
| Members | 199 |
| Ministries | 16 |
| Fixed pages | 10 |
| **Total HTML** | **19,953** |

Bill sections share bill pages; they do not each create a separate HTML file. The live database has 914 bill sections. List pagination uses five JSON endpoints, not one static HTML page for each list page.

| Other output | Files |
| --- | ---: |
| Pagefind fragments | 19,596 |
| Pagefind index shards | 926 |
| Pagefind filters | 3 |
| Pagefind runtime and other files | 10 |
| **All Pagefind files** | **20,535** |
| JavaScript/CSS under `_astro` | 12 |
| JSON data endpoints | 5 |
| Root non-HTML assets | 3 |
| **All output files, including HTML** | **40,508** |

The largest file is `data/questions.json`: 8,066,393 bytes, below 25 MiB. File count is the current constraint before individual file size.

## Applicable Cloudflare limits

The repository deploys **Workers Static Assets**: `astro/package.json` runs `wrangler deploy`, and `astro/wrangler.jsonc` sets `assets.directory` to `./dist`. There is no Pages deployment command in that script. The account's actual subscription was not checked.

Cloudflare currently allows **20,000 asset files per Worker version on Workers Free**, or **100,000 on Workers Paid**. Each asset can be at most **25 MiB**. Wrangler 4.34.0 or later is required for the larger file count; the repository declares `^4.71.0`. These are plan limits, not an HTML-page limit. A higher limit requires a separate request and is not guaranteed. [Workers limits](https://developers.cloudflare.com/workers/platform/limits/#static-assets)

For comparison, Pages also allows 20,000 files on Free and 100,000 on paid plans such as Pro, Business, and Enterprise. Its larger limit requires `PAGES_WRANGLER_MAJOR_VERSION=4` in project settings. These Pages plan names and settings do not determine this repository's Workers limit. [Pages limits](https://developers.cloudflare.com/pages/platform/limits/#files)

Static asset requests are free and unlimited, with no additional storage charge for Assets. Requests that execute Worker code use Workers billing. File-count capacity and request billing are separate. [Static Assets billing](https://developers.cloudflare.com/workers/static-assets/billing-and-limitations/)

The current 40,508-file snapshot already exceeds Workers Free. Workers Paid would leave **59,492 files** before its documented limit. Moving the same files from Workers to Pages does not increase the paid file-count ceiling.

## Full sitting inventory

The official inventory contains **1,753 indexed sitting dates**. Of these, **331** are already in the active database and **1,422** are additional dates. The additional archive is **4.296 times** the active sitting count; the combined inventory is **5.296 times** the active count. These exact sitting ratios must not be used as section or asset growth ratios.

`historical/capacity_projection.py` reads the inventory and normalized files, then counts the current route predicates. Run `python3 historical/capacity_projection.py` after transformation finishes. Its `complete` field must be true before treating source totals as final. It also reports every retained topic, including topics that have no current detail route.

## Historical projection and decision rule

For the current routes:

```text
HTML = questions + motions + clarifications + distinct bills
     + sittings + distinct members + distinct ministries + 10

assets = HTML + Pagefind files + other output files
```

Use route-eligible rows after parser validation and deduplication. Do not use raw report count as page count, or raw bill-section count as distinct bills. Add only new identities when combining the archive with the modern database. Unsupported historical section categories may need a route decision before this formula covers them.

The current output has about **2.0302 asset files per HTML page**. If this ratio stayed constant, 100,000 assets would correspond to about **49,256 HTML pages**. This is only a planning estimate: Pagefind fragments, language indexes, text length, and asset bundles can change. It is not a deployment guarantee.

### Completed archive counts

The projection script now reports `complete: true`: all **1,422** additional dates have normalized output, with **30,395 retained topics**. All records have status `parsed`; this status does **not** mean that every speaker identity, topic boundary, or classification is resolved.

| Archive topic group | Retained topics |
| --- | ---: |
| Questions eligible for current detail routes | 12,911 |
| Motions, including adjournment motions | 2,496 |
| Clarifications | 6 |
| Bill sections (not distinct bills) | 4,601 |
| Topics without a current detail route | 10,381 |
| **Total** | **30,395** |

The 10,381 topics without a current detail route include **2,393 attendance topics** and **7,988 other topics**. The archive has **1,333 distinct parsed member-name strings** across attendance and speakers. This is not a verified count of people; spelling variants and unresolved names remain possible.

### Publication scenarios

Both scenarios retain the existing 40,508 output files and add 1,422 sitting pages. They add no ministry pages, fixed pages, or new non-search bundles. These are design assumptions, not results from an archive build.

| Scenario | Additional HTML | Combined HTML | Combined assets before new archive search | Combined assets at current Pagefind ratio |
| --- | ---: | ---: | ---: | ---: |
| Current route categories | 16,835–22,769 | 36,788–42,722 | 57,343–63,277 | **74,669–86,710** |
| One page per retained topic | 31,817–33,150 | 51,770–53,103 | 72,325–73,658 | **105,070–107,775** |

For current route categories, the lower HTML count adds question, motion, clarification, and sitting pages. The upper count also permits one bill page per bill section and one member page per parsed name. Bill grouping and overlap with existing members can reduce this upper count. The scenario leaves 10,381 archive topics without their own detail routes; it must not be described as complete topic publication.

The all-topic scenario adds one page for every retained topic, including attendance and unclassified topics. Its upper count adds member pages. It does not also add separate bill-group pages. This is a complete retained-topic comparison, not a recommendation to give attendance its own page.

The last column applies the measured ratio of **20,535 Pagefind files / 19,953 HTML pages** to new HTML, while keeping existing output fixed. It is an estimate, not a lower or upper bound on actual search files. The before-search column keeps existing search files but adds no archive search coverage. A complete build must measure search output and maximum file size before deployment.

### Recommendation

**SSR is not necessary on the evidence so far.** The current-route scenario is provisionally below the Workers Paid 100,000-file limit, but it omits detail routes for many retained topics. Publishing every retained topic with similar Pagefind output is provisionally **5,070–7,775 files above** that limit. HTML alone is below the limit in both scenarios.

Decide which topics need separate pages before changing the rendering system. For full topic publication, first consider keeping prebuilt HTML and moving the search bundle or archive objects to R2, served through a Worker. This can preserve static generation while removing those objects from the Workers Static Assets upload. The resulting assets must be recounted. SSR is another option if runtime rendering has a separate product benefit; it is not the only response to a file-count limit.

- If the complete build is below 100,000 files with room for growth, Workers Paid can keep the current static design.
- If it approaches or exceeds 100,000 files, consider storing archive HTML and/or search files in R2 behind a Worker, or rendering historical detail pages on demand. Count the remaining deployed assets after the design change.
- If using on-demand pages, Pagefind needs a separate index-generation plan because it indexes build output. Removing prebuilt HTML alone does not preserve archive search.
- Date-based archive partitions can cap each deployment, but require explicit routing and cross-partition search. Keep this as an alternative if the full archive needs it.

Do not select the archive architecture from sitting count alone. The section inventory and search output determine the file count.


SSR is **not required solely because the archive is large**. Static HTML can remain the delivery format: a Worker can read an R2 object and return its body. This separates stored archive files from the Workers Static Assets file-count ceiling. It does add storage/request costs and a serving path to maintain. [Cloudflare R2 Worker API](https://developers.cloudflare.com/r2/api/workers/workers-api-reference/)

Pagefind normally reads static HTML after the site build and produces a static search bundle. An SSR change therefore still needs a way to build the archive index, such as an offline export or Pagefind's Node API. [Running Pagefind](https://pagefind.app/docs/running-pagefind/), [Pagefind Node API](https://pagefind.app/docs/node-api/)
