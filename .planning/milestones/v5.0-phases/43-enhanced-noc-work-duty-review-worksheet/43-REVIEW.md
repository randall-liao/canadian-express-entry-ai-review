---
phase: 43-enhanced-noc-work-duty-review-worksheet
reviewed: 2026-07-19T14:13:07Z
depth: deep
files_reviewed: 5
files_reviewed_list:
  - crawler/noc_worksheet.py
  - crawler/noc_review.py
  - crawler/cli.py
  - crawler/remediation.py
  - crawler/tests/test_noc_overflow_regression.py
findings:
  critical: 0
  warning: 0
  info: 6
  total: 6
status: issues_found
---

# Phase 43: Code Review Report (final re-review after 54bb8b3 / 413682a)

**Reviewed:** 2026-07-19T14:13:07Z
**Depth:** deep (cross-file + full real-corpus reproduction against `corpus/index.db`, 376 NOC-2021 source files, HEAD `413682a`)
**Files Reviewed:** 5 (4 source + 1 test — the exact source change surface of `54bb8b3`; `413682a` is docs-only)
**Status:** issues_found (0 Blocker, 0 Warning, 6 Info — the prior WR-01 Warning is fixed; only deferrable Info remains)

## Summary

This is an adversarial re-review of the WR-01 fix commit `54bb8b3` ("typed
`NocSourceUnavailable` fail-closed for missing/drifted NOC source"). The prior
review (`162b586` baseline) flagged one Warning: a present index with an
absent/drifted authoritative `noc-2021/*.md` SOURCE was MISDIAGNOSED — `noc-worksheet`
blamed the user's `--noc-code` (`reason=unresolved_noc`), and `noc-review` masked the
fault as a clean `("N/A", "no_worksheet")` success. I did **not** trust the test suite;
I reproduced every claim end-to-end against the pinned `corpus/index.db` (376 groups)
and a real vault, and I traced the exception across every caller.

**The WR-01 Warning is genuinely fixed, source availability is now cleanly separated
from code syntax, and the security / isolation / never-green posture is intact.** No
Blocker and no Warning survive. Independently verified:

- **Typed diagnostic, generator — verified.** `_source_main_duty_items` returns `None`
  ONLY for a malformed code (regex miss) and raises `NocSourceUnavailable(code)` for a
  missing/uncontained/unreadable/frontmatter-drifted/heading-less source;
  `split_duties` raises it for an item ungroundable in order; `generate_worksheet`
  catches it and returns `reason="noc_source_unavailable"` distinct from
  `reason="unresolved_noc"`. Reproduced: index-only dir (source tree removed) →
  `resolve_noc_spans` still resolves, `split_duties` raises the typed fault, and
  `generate_worksheet` returns `{worksheet_doc_id: None, value_ids: [], duty_count: 0,
  reason: "noc_source_unavailable"}`.
- **Typed diagnostic, sidecar — verified.** `_current_key_sets` propagates the
  exception (does not swallow); `review_noc_duties` catches it and returns
  `("AT-RISK", "noc_source_unavailable")` with zero counts — never `SUBSTANTIATED`,
  never the clean `("N/A", "no_worksheet")`. The returned dict is exactly the closed
  `PUBLIC_FIELDS` set. Reproduced against a real vault.
- **Typed diagnostic, CLI — verified.** `vault noc-worksheet` on source-absent →
  `invalid_input` / exit 2 with a "refresh or rebuild the authoritative corpus (this
  is NOT a bad --noc-code)" hint; `vault noc-review` → `ok:true` with the AT-RISK /
  `noc_source_unavailable` closed dict. The genuinely-absent code `99999` still routes
  to `unresolved_noc` (worksheet, exit 2) and `("N/A", "no_worksheet")` (review) —
  regression preserved. Reproduced through `cli.main`.
- **Remediation — verified.** `_REASON_ALIASES` maps `noc_source_unavailable ->
  unresolved_noc`, reusing the shipped `unresolved_noc` template with no duplicate
  entry and no new volatile literal (see IN-01 for a semantic caveat).
- **Zero artifacts — verified.** A source-unavailable refusal wrote NO worksheet file
  (`rglob("noc-*.md") == []`), 0 rows in `documents WHERE doc_type='noc_worksheet'`,
  and 0 rows in `extracted_values WHERE factor_id='review.noc'`. The artifact write and
  all vault mutations sit AFTER the guarded `split_duties`, so the exception path
  touches nothing.
- **No path leak — verified.** `NocSourceUnavailable.__init__` builds a stable token
  (`"NOC {code} authoritative source unavailable (reason=noc_source_unavailable)"`) —
  code + reason only, no path. The I/O raise sites use `raise … from None`, so an
  underlying `OSError` / `PathEscapeError` cannot chain an absolute path into a
  traceback (confirmed: `__cause__`/`__context__` are `None`, and the formatted
  traceback + the JSON'd summary/review dicts contain no tmp/corpus/vault path). `code`
  at every raise site is a validated `\d{5}` string (the regex guard precedes every
  raise), so it can never carry PII.
- **Exception containment — verified.** The only non-test callers of `split_duties` /
  `_current_key_sets` are `generate_worksheet` (line 660, try/except) and
  `review_noc_duties` (line 260, try/except); the only callers of those two are the two
  CLI verbs. No unguarded path lets `NocSourceUnavailable` escape to a stack trace.
  `paths.resolve_within` raises only `PathEscapeError`, which is caught.
- **Normal behavior + prior parser fixes (WR-01/WR-02 from 162b586) — intact.** Full
  independent 376-group scan: every group resolves + splits (0 fail-closed, 0 raised),
  emitted items equal the raw source bullets BYTE-FOR-BYTE in order, `72410`'s grouped
  header "Mechanical repairers - motor vehicle manufacturing" stays a SINGLE item (17
  duties, not 18), and exactly the two known boundary-split duties (`11202:15`,
  `31100:21`) carry two citations. Happy-path CLI on `72400` produced 18 duties + a
  cited worksheet. Never-green / `core.work` isolation unchanged (`review.noc` absent
  from `FULL_GRID_FACTORS` and the auditors dispatch/remediation wiring).
- **Tests — reviewed and sound.** The 295 added lines (`TestNocSourceUnavailableHermetic`
  + `TestNocSourceUnavailableCli`) are fully hermetic (synthetic index, break only the
  source), assert the distinct reason, zero artifacts, closed `PUBLIC_FIELDS`, no
  absolute path, never-green, and the preserved `99999` behavior — real assertions, no
  vacuous passes. The unreadable-source test correctly `skipTest`s under root. Full
  Phase-43 suite: 68 passed / 405 subtests; noc+remediation+conformance: 239 passed /
  861 subtests.

**No incorrect grounding, no fabrication, no security gap, no never-green/isolation
breach, no path leak.** Every failure mode is fail-closed and every emitted span
remains a verbatim, sha-validated corpus/source substring. The six Info items below are
deferrable diagnostics/cosmetics — two new (introduced or clarified by this commit) and
four carried over from the prior review; none blocks ship.

## Info

### IN-01: `noc_source_unavailable` aliases to a remediation message that misdirects the operator (currently unreachable — defensive only)

**File:** `crawler/remediation.py:164-167` (alias), `crawler/remediation.py:103-105` (`unresolved_noc` template)

**Issue:** The new alias `"noc_source_unavailable": "unresolved_noc"` reuses the
`unresolved_noc` action prose: *"The occupation details for {factor} need review; this
requires human or professional assessment of the job-duty fit and cannot be
auto-substantiated."* That is the WRONG remediation for a source-unavailable fault —
which is a corpus-integrity / deployment problem whose fix is "refresh or rebuild the
authoritative corpus," not a professional review of the job-duty fit. This re-introduces,
at the remediation layer, the same class of misdirection WR-01 fixed at the CLI layer.
It is NOT currently reachable: `noc_review` is inert and not wired into the
`auditors`/`remediation` dispatch (`remediation` reason codes come from audit
`card.reason_code`, never from the sidecar — verified), so the alias is purely
forward-looking. The commit message's justification ("BOTH are exactly the 'occupation
details need review' remediation") is inaccurate for the source-unavailable case.

**Fix:** If a future consumer ever routes the sidecar reason through remediation, give
`noc_source_unavailable` its own template pointing at the corpus rebuild (mirroring the
CLI hint) rather than aliasing it to the job-duty-fit prose; otherwise drop the
speculative alias until a real consumer exists.

### IN-02: `noc-review` returns exit 0 for a corpus-integrity fault while `noc-worksheet` returns exit 2 for the same fault

**File:** `crawler/cli.py:1497-1510` (`_cmd_vault_noc_review`), `crawler/cli.py:1428-1447` (`_cmd_vault_noc_worksheet`)

**Issue:** For the SAME underlying `noc_source_unavailable` fault, `noc-worksheet`
refuses with `invalid_input` / exit 2, whereas `noc-review` returns `ok:true` / exit 0
carrying `status="AT-RISK"`. A consumer that parses the JSON `status`/`reason` can
distinguish "source unavailable" from a healthy review (which was the WR-01 goal, and it
is met), but a script keying only on the process exit code sees a broken-deployment
review as success. This is a defensible design choice — the sidecar is a roll-up report
that always emits a verdict, and a genuinely duty-less NOC also returns exit 0 `N/A` —
so it is noted, not a defect.

**Fix:** None required for ship. Optionally document in the verb help that `noc-review`
callers MUST inspect `status`/`reason` (exit 0 is not "healthy"), or reserve a distinct
non-zero exit for the corpus-integrity `status` if exit-code-only automation is ever a
supported consumer.

### IN-03: `resolve_noc_spans` collects ALL `Main duties`-labelled chunks, not the "consecutive" ones the docstring claims (carried over)

**File:** `crawler/noc_worksheet.py:7` (module docstring), `crawler/noc_worksheet.py:219-228` (classification loop)

**Issue:** The module docstring says retrieval collects "ALL consecutive Main-duties
chunks," but the loop appends every chunk whose exact trailing section label is
`Main duties` regardless of contiguity. Harmless on the current corpus (verified: the
Main-duties chunks are contiguous across all 376), but a stray/duplicate `… › Main
duties` breadcrumb would be silently merged into the duty stream rather than flagged as
ambiguity. Either enforce contiguity (fail closed on a non-consecutive second run) or
correct the wording to "all Main-duties chunks."

### IN-04: `split_duties`' per-fragment `quote_is_grounded(fragment, span["text"])` is tautological (carried over)

**File:** `crawler/noc_worksheet.py:480-482`

**Issue:** `fragment = span["text"][meta[i][1]:meta[j][2]]` is a verbatim slice of
`span["text"]` on token boundaries, so `grounding.quote_is_grounded(fragment,
span["text"])` is always True for a non-empty run — it can only reject a whitespace-only
fragment, which the non-empty needle guard already precludes. The docstring presents
this as a strong in-split safeguard, but the real grounding guarantee comes from (a)
`searchindex.resolve` having sha-validated each chunk and (b) slicing verbatim from that
text; the meaningful re-verification is `noc_review._layer2_fresh`. No behavior change
needed — keep as harmless defense-in-depth or align the docstring so the guarantee is
not overstated.

### IN-05: `_find_token_run` first-match alignment is a latent fragility not pinned by any test (carried over)

**File:** `crawler/noc_worksheet.py:387-405`, `:459-485`

**Issue:** The source-item → chunk-stream mapping uses a plain first-match-at-cursor
sublist search. Correct for all 376 groups today (each item's normalized token run first
appears at its true position), but it rests on an unstated invariant: no source item's
token sequence occurs earlier in the stream than its own position. A future corpus edit
(a repeated phrase / duplicated grouped header) could mis-locate a citation (still a
verbatim, grounded slice — bounded, not a fabrication) or fail closed via the new
`NocSourceUnavailable`. Consider an assertion/regression pinning "cursor is monotonic and
every item is found exactly once past the previous item," or document the assumption at
`_find_token_run`.

### IN-06: Carried-over CLI cosmetics — vault dir created on refusal + success-message value count (carried over)

**File:** `crawler/cli.py:1420-1424` (`open_vault` before the refusal), `crawler/cli.py:1465-1469` (success message)

**Issue:** Two cosmetic carryovers, unchanged by this commit: (a) `open_vault` runs
before the source-unavailable / unresolved refusal, so the candidate dir + `vault.sqlite`
are created even when the command refuses — the "a refusal writes zero artifacts"
guarantee is precise for worksheet/document/value artifacts, not the vault directory;
(b) the success message `"{len(result['value_ids'])} pending value(s) captured"` counts
the lead statement plus any reused ids (e.g. 19 values for a 18-duty NOC), so it reads
as an off-by-one against the adjacent `{duty_count} duty item(s)`. No action required to
ship; re-noted so it is not lost.

---

_Reviewed: 2026-07-19T14:13:07Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
