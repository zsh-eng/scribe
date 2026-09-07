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

## Final rebuilt corpus

A fresh scan after the full rebuild found all 1,422 outputs marked `parsed`, no
pending outputs, and 30,395 sections. Formats were 1,100 flat, 205 Word-export,
28 semantic, and 89 structured-takes. No present-member roster was empty.

There are 10,381 null-type sections: 2,393 attendance sections, deliberately given
no debate type, and 7,988 other sections. For example, 1955-04-22 `ADMINISTRATION
OF OATHS` is retained without assigning a question, bill, or statement type.
There are 491 `Untitled source section` sections in 120 reports. They have source
text but insufficient title evidence. For example, 2011-02-14 has six untitled
sections. Section order 8 begins `The increases were necessary to meet rising
costs` and order 11 begins `Mr Raymond Lim Siang Keat`. These appear to be speech
continuations split by empty source markers; they are not empty sections. The
scanner lists all 120 affected dates in `untitled_section_dates`. Other concrete
cases are 2003-10-16 (five untitled sections; order 7 begins `Hence, our proposal`)
and 2011-04-11 (four; order 7 begins `Mr Lim Hng Kiang`).

Speaker resolution has 2,878 unresolved report-label occurrences across 1,137
reports; these are not distinct people. Examples include 2000-02-22 `Dr Aline Wong`
and `The Minister of State for Defence (Mr David T.E. Lim)`, 2011-02-14 the malformed
`Ms Grace Fu Hai Yien) (for the Minister for Education)`, and 2011-10-17
`Mr Muhamad Faizal Bin Abdul Manap,`. The archive keeps these labels and avoids a
guessed link. Name variants, punctuation, and role-first labels still need review.

Attendance warnings total 724 unresolved entries and five duplicate/conflicting
roster warnings. Some unresolved entries are procedural text, not members.
The structured 2012-09-10 source also contains one invalid attendance row with
null name/location and attendance false; the audit retains the original row.
This is an unresolved source row, not a missing full report roster.

The 1986-03-18 report has unknown `session_no`. Nine META-date parse warnings,
three date-representation conflicts, and one malformed visible date remain in
the audit. The three conflicts are 2005-02-28 (corrupt visible date), 2006-11-09,
and 2011-04-11 (ISO versus DD-MM-YYYY representation); all reports now parse.

Residual token counts are nonzero in 1,128 HTML reports, totalling 51,513 tokens.
The largest ratio is 47/2,511 (1.872%) on 1960-06-01. Its residual list consists
of metadata, masthead, and meeting-time words. None exceeds 10%. These are words
outside sections, still retained in full normalized text; the check does not
establish the meaning of every residual token.

Ten December 1965 reports have a source institution label of Legislative Assembly
while their date falls after independence. The inspected 1965-12-08 and 1965-12-23
mastheads explicitly say `FIRST SESSION OF THE LEGISLATIVE ASSEMBLY (TO BE CALLED
THE FIRST PARLIAMENT)`. This transitional source wording explains the distinction
from the archive envelope. The envelope uses the official inventory era,
`Parliament`, while metadata preserves the masthead evidence. The ten dates are
1965-12-08, 1965-12-13, 1965-12-14, 1965-12-15, 1965-12-16, 1965-12-17,
1965-12-20, 1965-12-21, 1965-12-22, and 1965-12-23. This distinction is not
evidence of missing text.

There are 532 occurrence-suffix warnings and 214 cases where content is retained
under a group heading. Structured-source warnings flag vernacular lists in 75
reports and annexure lists in 25. These counts are warning occurrences. No new
substantial source loss was found in this review. Source-hash and full-text
verification is a separate check; this scan does not replace it.

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
sections. Ten format-extension regression tests passed. These selected-case results preceded the final rebuild counts above.

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
