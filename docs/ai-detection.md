# AI-detection pipeline

An internal research pipeline that tests prepared parliamentary speeches with
[Pangram](https://www.pangram.com), an AI-text detector. It reads the site database and never
writes to it. Results link named MPs to scores, so they stay out of the repository: everything
under `data/ai_detection/` is git-ignored and shared through the team's Drive folder with a
snapshot of the database.

```
SQLite ─ export_pangram_speeches.py ─▶ speeches.jsonl, upload CSVs, manifest.json
          estimate_pangram_cost.py  ─▶ words and cost per year (nothing sent)
speeches ─ run_pangram_bulk.py ─▶ Pangram bulk API ─▶ pangram/jobs.jsonl, raw/, results.jsonl
         └ run_pangram_bulk.py --write-csv ─▶ dashboard upload ─▶ saved reports
                                   import_pangram_dashboard.py ─▶ results.jsonl
Wikipedia ─ fetch_mp_photos.py ─▶ photos/<member_id>.jpg, credits.json
results + photos + attendance ─ build_pangram_explorer.py ─▶ who-wrote-the-address.html
everything ─ build_pangram_verification.py ─▶ pipeline-verification.html
```

Commands and options are in [the Python README](../python/README.md#ai-detection).

## 1. Export: from Hansard sections to speeches

`export_pangram_speeches.py` chooses sections, splits them into one row per speaker turn and
labels each row.

- **Sections.** The default scope keeps the President's Address debate: `motion` sections whose
  title, lower-cased without apostrophes, is one of the three names Hansard has used for it.
  `--scope prepared` keeps every motion (including the Budget debate and Committee of Supply),
  adjournment motion and bill second-reading debate. Question time, written answers,
  clarifications and first readings are never included. `--through MM-DD` keeps the same
  calendar window in each year so that a partial year compares like for like.
- **Turns.** A new turn starts only where a paragraph opens with a bold name and a colon, so
  notices such as "[Deputy Speaker in the Chair]" stay inside the speech they interrupt.
- **Removed text.** Hansard prints Mandarin, Malay and Tamil passages in English translation,
  which are not the MP's own words. They are cut from the "(In Malay)" marker, or a closing
  "in Malay, please." request, until "(In English)" or the next speaker, and the number of
  words removed is kept as `translated_words_removed`.
- **Dropped turns.** The Speaker, Deputy Speakers and Chairman, the President's own address,
  and turns under `--min-words` (500 for the datasets so far, because detection is less reliable
  on short text). Counts of each are in the manifest.
- **Labels.** The speaker label is matched to a member by name, then given the constituency and
  designation from that sitting's attendance list. *Office holder* means the label starts with
  "The " or the designation names a Minister, Parliamentary Secretary or the Attorney-General.
  *First Parliament* means the member's first recorded attendance falls on or after the first
  sitting of that Parliament; attendance starts in January 2016, so earlier service is invisible.
- **IDs.** `<type>-<date>-<section>-t<turn>`, for example `bp-2026-01-12-3bc2bace-t002`. The type
  is `pa` (Address), `bp` (bill), `bu` (Budget and Committee of Supply), `mo` (other motion) or
  `am` (adjournment), so a speech has the same ID in either scope. The ID is also the `tag`
  in every upload, which is how results join back.
- **Outputs.** `speeches.jsonl` (the exact text sent plus every label), `members.csv`, one
  `pangram_upload_<year>.csv` and `manifest.json` with the parameters, counts, exclusions,
  unmatched labels, the database's latest sitting and a SHA-256 hash of every file. The same
  database and parameters always reproduce the same hashes.

## 2. Scan: API or dashboard

Pangram bills in 100-word units per speech, rounded up. `estimate_pangram_cost.py` prices a
selection without sending anything.

- **Bulk API.** `run_pangram_bulk.py` is a dry run unless given `--submit`. It packs speeches into
  requests of at most 900 units (Pangram allows 1,000), records every submission in
  `pangram/jobs.jsonl`, saves every response page unchanged under `pangram/raw/<bulk_id>/` and
  writes one line per speech to `pangram/results.jsonl`. A speech that has been submitted, even
  with an unknown outcome, is never sent again. Only GET requests are retried. Pangram deletes
  bulk results 48 hours after a job finishes.
- **Dashboard.** `run_pangram_bulk.py --write-csv` writes the same selection as a `tag,text` file
  to upload on the Pangram dashboard, leaving out any speech that already has a result. Reports
  are saved from the dashboard history as JSONL. `import_pangram_dashboard.py` keeps a report
  only if the text Pangram scanned equals the exported text, renames the dashboard's window
  fields to the API's ("Human" to "Human Written"; `ai_likelihood` also stored as
  `ai_assistance_score`) and appends to the same `results.jsonl` with `source: dashboard`.
  Each downloaded file is copied unchanged to `pangram/raw/dashboard/`.

## 3. Results and measures

Each successful line of `results.jsonl` holds Pangram's result: its copy of the text, overall
fractions and a list of windows, each with a label (AI-Generated or Human Written), a confidence
(Low, Medium or High), a score, a word count and character offsets. Pangram collapses blank lines
and drops zero-width spaces, so window offsets refer to Pangram's text, never ours. When a speech
has several results, the latest line wins.

- **Speech share:** `fraction_ai`, the share of the speech's characters in AI-generated windows.
- **High-confidence share:** characters in AI-generated windows rated High and at least 75 words
  long, over the speech's characters. The explorer leads with this.
- **Group share:** speech shares weighted by each speech's word count.

## 4. Portraits

`fetch_mp_photos.py` looks for an openly licensed portrait of every MP who spoke:

1. Search English Wikipedia for "*name* Singapore politician" and take the first of five results
   whose title shares at least two words with the MP's name and whose description mentions
   Singapore.
2. Take that article's lead image only if Wikipedia marks it as freely licensed.
3. Read the file page, author and licence from Wikimedia Commons, download a thumbnail about
   320 pixels wide as `photos/<member_id>.jpg` and record the credit in `photos/credits.json`.

Members already in `credits.json` are skipped. Official portraits from parliament.gov.sg are
not used; its terms forbid reproduction without written permission. `build_pangram_explorer.py`
shrinks each portrait to 176 pixels (with macOS `sips`, otherwise unchanged), embeds it in the
page, and lists every embedded portrait's author and licence. MPs without one get a monogram.

## 5. Explorer and verification page

`build_pangram_explorer.py` joins the export, the results, attendance on the debate days and the
portraits into one self-contained HTML page. Party is not in the database: three seats are
Workers' Party, every other seat is PAP and NCMPs are matched by name. The Timeless fonts are
embedded from a local download because their licence forbids redistributing the files.

`build_pangram_verification.py` writes the internal verification page. It copies code excerpts
and line numbers from the source files, runs every check below to record its expected output,
and recomputes the headline figures from `results.jsonl`, so no number on the page is typed in.

## Verifying the data pipeline

Run from the repository root with the results folders in `data/ai_detection/`. The
verification page has the full set with expected outputs.

1. **Unit tests** use temporary databases, fake Pangram servers and fake dashboard downloads:
   `(cd python && uv run python -m unittest discover -s tests)`.
2. **Reproduce the exports.** Re-run each export into a temporary folder with the parameters in
   its `manifest.json` and compare the file hashes. Every file should match.
3. **Nothing left to send.** A dry run of `run_pangram_bulk.py` for the scanned years should select
   no speeches; it makes no network calls.
4. **Returned text.** For every result, our text with blank lines collapsed and zero-width spaces
   removed should equal Pangram's text.
5. **Headline figures.** Recompute the shares from `speeches.jsonl` and `results.jsonl` alone and
   compare them with the explorer's opening figures.
6. **Uploads and imports.** Dashboard upload files should hold no office holders and no speech
   that already has a result; every imported report's text should match the export.

## Verifying the image pipeline

1. **Credits and files agree.** Every `photos/*.jpg` has a credit, every credit names a file
   that exists, and every credit has an author, licence and file page.
2. **Licences.** Count credits by licence; anything other than CC, public domain or a government
   open licence needs a look.
3. **Embedded portraits.** In the built explorer, the number of members with a portrait equals
   the number of credit lines.
4. **By eye.** The verification page has a contact sheet of every accepted portrait with the
   article it came from. Matching is automatic, so check each face and article by hand.

## Known limits

- Attendance records start in January 2016, so members who served only before then count as new.
- Party comes from a seat rule, not from the database.
- The dashboard's `ai_likelihood` is assumed to be the API's `ai_assistance_score`; scanning a
  few speeches through both would confirm it.
- Pangram counts slightly more words than we do (about 1%), so its bills run a little higher
  than our estimates.
