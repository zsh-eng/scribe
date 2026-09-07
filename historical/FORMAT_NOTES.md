# Historical report formats

This adapter is for the separate archive. It does not write to the live database.
The raw API JSON is the source of record. Keep it with the output and its checksum.

## Supported layouts

- Semantic HTML: `hansardContent`, topic titles, and attendance lists.
- Flat HTML: centred headings and BR-separated attendance entries.
- Word-export HTML: explicit `SECTION_NAME` and `TITLE_NAME` comments. Split the
  original HTML at these markers before BeautifulSoup repairs invalid nesting.
  Each section keeps the text up to the next marker. Keep the preamble and
  attendance as sections for this format. Empty marker titles use an explicit
  unknown title. Explicit END_COL_TITLE column markers distinguish repeated titles when available.
  Remaining repeated titles use an occurrence suffix and an audit warning.
- Unknown layouts: retain one unsegmented report when flat layout detection fails.
  The audit format and segmentation_status both say unsegmented; retained text
  is not a claim that topic segmentation succeeded.

Word exports can contain repeated HTML and BODY tags inside an open paragraph.
A walk of only the first BODY's children can omit debate text. Raw marker offsets
avoid that failure. Group headings provide question type evidence; unknown types
remain null. No modern ministry or member identity is inferred.

## Institution and metadata

The report masthead can identify a Legislative Assembly or Legislative Council.
Otherwise, post-independence dates identify Parliament of Singapore. Earlier
reports with no such wording keep an unknown institution. The evidence is stored
with the institution. Do not treat an old source's `Parliament No` as proof of
institution identity.

Missing or nonnumeric metadata is null with an audit warning. Conflicting metadata
is recorded; the visible table value takes precedence over a META value. A valid
source date that differs from the requested date remains an error. Attendance
entries that cannot be resolved stay in the full source text and audit warnings.
They do not become guessed member records.

## Text retention and limits

`parse_audit.retained_source_text` keeps normalized text from the complete report,
including the masthead and attendance. Cleaning removes comments, script/style
content, event handlers, unsafe link targets, and exact font/class column markers.
It does not remove a container merely because its class is `column`. Whitespace
is normalized for plain text. Keep raw HTML for exact spacing, comments, page
markers, and original attributes.

`text_coverage` compares token counts in the full normalized source with section
text. Tokens outside sections can be masthead text, attendance, or group labels.
This check is a token multiset check. It does not prove correct order, speaker
links, or section boundaries. The full normalized source and raw report remain
available even when sections are incomplete. Unresolved speaker labels are listed.

Replay is deterministic for unchanged input. An occurrence suffix can change if
an earlier duplicate topic is added or removed. These IDs are archive identifiers;
they are not approved identifiers for live database imports.
