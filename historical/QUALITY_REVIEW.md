# Historical archive quality review

## Scope and method

The raw corpus has 1,422 reports: 1,100 flat/other HTML, 205 Word-export HTML,
28 semantic HTML, and 89 structured-takes reports. These counts use source layout
signatures, not dates. The signatures are independent of whether parsing succeeds.

Run `python historical/quality_review.py` to inspect current output statuses,
format counts, warnings, empty attendance, untitled sections, institution/date
conflicts, and high residual cases. The script reads files only. Outputs can be
in progress; inspect `pending_dates` before treating counts as a final result.

This review checked every raw report's signature and every available normalized
report's audit. It also inspected selected source HTML and normalized sections.
It did not manually compare all report text line by line.

## Confirmed defects and repairs

- 2005-02-28: source date `20/f-28-0502ont>` caused a complete parsing fallback.
  The adapter now records a malformed-date warning and uses the requested date.
- 2006-11-09 and 2011-04-11: valid ISO dates in the visible source table were
  compared with DD-MM-YYYY without normalization. Both now parse. A valid date
  that denotes another day still causes an error.
- 1977-02-07: the attendance block also contains the Serjeant at Arms procedure.
  1986-02-20 has the President's entrance and time in that block. Previously these
  lines survived in full source text but were absent from sections. All HTML
  attendance blocks now remain as sections with category `attendance` and null
  type. This also protects procedural text in semantic attendance containers.
- 2004-03-13, 2004-03-15, 2005-03-03, 2005-03-07, 2005-03-08, and 2005-03-09:
  `<!SECTION_NAME:ATTENDANCE>` is a malformed source declaration. It previously
  put the roster in the preamble with no resolved members. The adapter now accepts
  this observed marker form. Ordinary comment markers can contain HTML such as
  `<BR>`; their closing boundary remains `-->`.

Direct replay after these repairs gave 2004-03-13 11 sections/83 present members;
2005-02-28 29/91; 2006-11-09 8/77; and 2011-04-11 37/89. Each had zero tokens outside
sections. Ten format-extension regression tests passed. These are selected-case
results; use the full rebuild and scanner for the final corpus status.

## Remaining uncertainty

- Zero residual tokens means that the section token multiset covers the normalized
  full text. It does not prove order, correct boundaries, or speaker attribution.
- A `parsed` output can still have unresolved speakers, unknown section types,
  unknown metadata, or untitled source markers. It is not a manual quality label.
- Some Word markers have empty titles. The archive labels these explicitly as
  `Untitled source section`. Repeated titles without an explicit column or anchor
  need an occurrence suffix; edits to earlier duplicates can change that suffix.
- Short flat reports can have a high outside-section ratio because masthead text
  is a large share of the report. Inspect the retained full source text before
  treating this ratio as missing transcript. Group headings also contribute.
- Structured reports can contain vernacular and annexure lists outside takes.
  Their original structured data must remain available; warning counts are not
  proof that these lists have been converted into searchable sections.
- Roster parsing and speaker resolution remain conservative. No present-member
  records means no resolved roster, not that the House had no members present.
- Raw gzip JSON remains the exact source of record. Normalized text changes
  whitespace and removes known HTML furniture. Retain both representations.
