---
phase: 43-enhanced-noc-work-duty-review-worksheet
fixed_at: 2026-07-19T13:30:00Z
review_path: .planning/phases/43-enhanced-noc-work-duty-review-worksheet/43-REVIEW.md
iteration: 3
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 43: Code Review Fix Report

**Fixed at:** 2026-07-19T13:30:00Z
**Source review:** `.planning/phases/43-enhanced-noc-work-duty-review-worksheet/43-REVIEW.md`
**Iteration:** 3 (final adversarial re-review after `162b586`)

This report covers **all three** review iterations for Phase 43:

- **Iteration 3 (current)** — the final deep re-review (`43-REVIEW.md`, HEAD
  `162b586`) confirmed both prior warnings genuinely fixed and the security /
  isolation posture intact, but surfaced ONE operability Warning, **WR-01**: the
  new source-tree dependency's failure mode was MISDIAGNOSED (a missing corpus
  source blamed the user's `--noc-code`, and `noc-review` masked it as a clean
  success). Fixed here. The four Info items (IN-01…IN-04) are deliberately out of
  scope.
- **Iteration 2** — the WR-01/WR-02 grounded-worksheet fidelity fixes
  (`162b586`), preserved below.
- **Iteration 1** — the original CR-01/CR-02/WR-01/WR-02 fixes, preserved below
  for the full trail.

**Iteration-3 summary:**
- Findings in scope: 1 (Warning; the 4 Info items deliberately excluded)
- Fixed: 1 (**WR-01** — source-availability misdiagnosis)
- Skipped: 0

Info findings **IN-01…IN-04** were intentionally NOT implemented (out of scope
for this fix pass — see *Deferred* below).

**Verification run after the iteration-3 fix (in an isolated git worktree,
fast-forwarded to `master`):**
- New WR-01 slice — `TestNocSourceUnavailableHermetic` +
  `TestNocSourceUnavailableCli` (index-present/source-missing, unreadable,
  path-escaped, frontmatter-mismatched — generator, sidecar, CLI): **11 passed**.
- Focused NOC slice — `test_noc_overflow_regression.py`, `test_noc_review.py`,
  `test_noc_review_cli.py`, `test_conformance_v5_noc_no_auto_green.py`,
  `test_crs_no_inlined_rules.py`, `test_conformance_v41_grounding.py`: **all
  green** (`78 passed, 405 subtests` — incl. the real-corpus 376-group scan).
- Full crawler suite (`pytest crawler/`): **1098 passed, 2 skipped, 873 subtests
  passed** (`0:17:20`).
- v4.x conformance gate (`scripts/run_conformance.py`): **PASS**
  (SAFE-01…08; 82 conformance tests green).
- Publish-safety (`scripts/check_publish_safe.py`): **PASS**
  (430 tracked files, 0 violations).
- Frozen surfaces UNTOUCHED — `auditors/core.py`, `crs_audit.py`,
  `models/audit.py`, `auditors/__init__.py`, `searchindex.py` (indexer/chunker),
  `grounding.py`: all byte-identical. Atomic trailer / cache untouched. No BM25,
  no model/semantic classification, zero new deps, no schema migration.
  `review.noc` isolation, never-green invariant, PII-light contract,
  multi-citation / idempotency / candidate scoping all preserved.

---

## Iteration 3 — final re-review fix

### WR-01: Missing NOC markdown source is misdiagnosed — worksheet blames the user's NOC code; review reports a clean success

**Files modified:** `crawler/noc_worksheet.py`, `crawler/noc_review.py`,
`crawler/cli.py`, `crawler/remediation.py`,
`crawler/tests/test_noc_overflow_regression.py`
**Commit:** `54bb8b3`
**Status:** fixed: requires human verification (fail-closed control-flow +
diagnostics change across the generator / sidecar / CLI)

**The defect (reproduced against the real `corpus/index.db`):** the iteration-2
rebuild (`162b586`) made `split_duties` read the raw `noc-2021/noc-{code}.md`
SOURCE (legitimately required — the flattened chunk cannot distinguish a grouped
header's internal `" - "` nor recover a boundary split). But its failure mode was
MISDIAGNOSED. With the index present and the source tree absent, a valid, indexed
NOC (e.g. `72400`) refused with `reason=unresolved_noc` — telling the operator to
"check the 5-digit `--noc-code`" for a corpus-integrity / deployment fault — and
`noc-review` returned `ok:true` / `status:"N/A"` / `reason:"no_worksheet"`,
indistinguishable from a NOC that genuinely has no worksheet (a downstream
consumer could not tell "source unavailable" from "no duties").

**Applied fix — a distinct fail-closed source preflight with a typed error and an
accurate reason, validating code SYNTAX separately from source AVAILABILITY:**

- **Typed error (`crawler.noc_worksheet.NocSourceUnavailable`).** A new exception
  carrying a STABLE `reason = "noc_source_unavailable"` and NO absolute path / PII
  (the raising I/O sites use `raise … from None` so an underlying
  `OSError`/`PathEscapeError` can never chain its absolute path into a traceback;
  the message carries only the reason token + the already-caller-supplied, non-PII
  5-digit code). `_source_main_duty_items` now RAISES it for a
  missing/uncontained/unreadable/frontmatter-mismatched source or an absent
  `## Main duties` heading, and returns `None` ONLY for a malformed CODE (the
  existing invalid-input semantics — `resolve_noc_spans` guards this before the
  split is ever reached). `split_duties` raises it for an item that cannot be
  grounded in order across the chunk stream (a source/index drift), and propagates
  the source-read raise.
- **Generator (`generate_worksheet`).** Now distinguishes the two None-causes:
  `resolve_noc_spans is None` → `reason="unresolved_noc"` (bad/absent code);
  `split_duties` raising `NocSourceUnavailable` → `reason="noc_source_unavailable"`.
  Both remain fully fail-closed — ZERO worksheet / document / value artifacts.
- **CLI `vault noc-worksheet`.** Maps `noc_source_unavailable` to
  `invalid_input` / exit 2 with a STABLE `reason=noc_source_unavailable` and a
  recovery hint to **refresh / rebuild the authoritative corpus** (explicitly NOT
  "check the code"); `unresolved_noc` keeps its existing "check the 5-digit
  `--noc-code`" message. Zero artifacts on either refusal.
- **Sidecar `review_noc_duties`.** Catches `NocSourceUnavailable` and returns
  `status="AT-RISK"` / `reason="noc_source_unavailable"` in the CLOSED PII-light
  `PUBLIC_FIELDS` set — never green, never the clean `("N/A", "no_worksheet")` a
  duty-less NOC returns. The CLI verb stays `ok:true` (consistent with the
  sidecar contract), but its status/reason are now ACCURATE.
- **Remediation alias.** `noc_source_unavailable` aliases to the shipped
  `unresolved_noc` action template (`_REASON_ALIASES`) — NO duplicate template, NO
  new volatile literal (the no-inlined-volatile gate over the module stays clean).
- **Truly-absent NOC preserved.** An absent code (`99999`, not in source/index)
  keeps the existing `unresolved_noc` / `no_worksheet` behavior; a malformed code
  stays invalid input.

**Tests (hermetic, always-run — no corpus dependency):**
`TestNocSourceUnavailableHermetic` builds a synthetic index and then removes /
breaks ONLY the source, asserting the typed raise + fail-closed generator /
sidecar behavior for index-present/source-missing, **unreadable** (chmod),
**path-escaped** (symlink out of the corpus root) and **frontmatter-mismatched**
(wrong `noc_code` / `source_type`) sources — zero artifacts, stable
`reason=noc_source_unavailable`, no absolute path, never green — and PRESERVES the
absent-code (`99999`) `unresolved_noc` / `no_worksheet` behavior.
`TestNocSourceUnavailableCli` drives the same through `cli.main` over a HEALTHY
fixture index (chunks + populated `chunks_fts` + `meta`, so the SAFE-10 index
preflight passes and the fault is the SOURCE only): worksheet →
`invalid_input`/exit 2 with the stable reason + refresh hint + zero artifacts + no
abs path; review → accurate `AT-RISK` / `noc_source_unavailable`. The real-corpus
376-group byte-for-byte scan and all normal missing-code paths remain green.

_Flagged "requires human verification" because it changes fail-closed control flow
and operator-facing diagnostics across three modules — syntax + the full suite +
conformance + publish-safety all pass, but a human should confirm the
source-availability-vs-code-syntax split and the reason/status routing match
intent._

---

## Iteration 2 — re-review fixes

### WR-01 + WR-02: Flattened-chunk duty parser over-splits grouped headers and drops boundary-split continuations

**Files modified:** `crawler/noc_worksheet.py`, `crawler/noc_review.py`,
`crawler/tests/test_noc_overflow_regression.py`,
`crawler/tests/test_noc_review.py`,
`crawler/tests/test_noc_review_cli.py`,
`crawler/tests/test_conformance_v5_noc_no_auto_green.py`
**Commit:** `162b586`
**Status:** fixed: requires human verification (retrieval/parsing logic rebuild)

WR-01 and WR-02 share ONE root cause — the iteration-1 split parsed the
*flattened index chunk* for its bullet list — so they were fixed together as a
single **corpus-structure + index-grounding** rebuild of `split_duties` (the
review recommended exactly this: prefer the newline-delimited source over the
flattened chunk, and stitch/flag boundary-split continuations). Applied as one
atomic commit because the source rewrite + its dependent contract-test updates
must land together to keep every intermediate commit green.

**The defects (reproduced against the real `corpus/index.db`):**

- **WR-01** — a grouped sub-occupation header StatCan flattens onto ONE physical
  line (e.g. `72410` "Mechanical repairers - motor vehicle manufacturing") was
  OVER-SPLIT at its internal `" - "`, emitting `"Mechanical repairers"` and
  `"motor vehicle manufacturing"` as two nonsensical standalone "duties"
  (18 duties for a 17-bullet source list). The single-line/multi-line heuristic
  was exactly backwards for a header inside a flattened chunk.
- **WR-02** — a single Main-duties bullet the deterministic chunker split across a
  chunk boundary had its *tail* chunk (a continuation with NO leading `- `)
  silently DROPPED — `11202`'s last duty lost its "Performance agents…" /
  "Sports agents…" sentences, `31100`'s Preventive-medicine duty lost its "May
  diagnose and treat…" continuation — leaving a cited-but-empty `#003`.

**Applied fix — a corpus-structure + index-grounding design:**

- **Structural source parse (authoritative duty list).** `split_duties` no longer
  enumerates duties from the flattened chunk. It derives the NOC markdown source
  path deterministically from `Path(db).parent / "noc-2021/noc-{code}.md"`,
  CONTAINS it beneath the corpus root via `paths.resolve_within` (rejecting any
  symlink/`..` escape), validates the frontmatter is the RIGHT document
  (`source_type == "noc"` AND `noc_code == code`, `yaml.safe_load` only), and
  reads the exact `## Main duties` section (that heading line through the next
  `## `). **Each physical `- ` line is ONE item** — an internal `" - "` stays
  INSIDE the item (WR-01 closed: grouped headers are one verbatim item, never
  over-split), grouped headers are kept verbatim (no semantic classification),
  and only the exact `"This group performs…"` boilerplate line is dropped. Fails
  closed (`None`) on a malformed code, an absent/uncontained/unreadable source, or
  drifted frontmatter.

- **Index-grounded citation mapping (cross-chunk duties).** Each full source item
  is mapped DETERMINISTICALLY, in order, onto the ordinal-ordered Main-duties
  chunk STREAM via a whitespace-normalized token alignment (used ONLY to locate
  the span; the emitted quotes are VERBATIM chunk slices). An item that overflows
  a boundary emits **one `{chunk_id, quote}` citation fragment per chunk it
  spans** (WR-02 closed: `11202`/`31100`'s continuation is recovered and cited to
  `#003`). Every fragment is re-verified verbatim-present in its OWN
  sha-validated chunk via `grounding.quote_is_grounded`; an item that cannot be
  covered — contiguously, in order, fully — across grounded chunks FAILS CLOSED
  (`None`, never a partial/mis-cited/fabricated duty).

- **Contract extension.** `DutyItem` / captured value / worksheet now carry an
  ordered `citations` list (`[{chunk_id, quote}, …]`) for cross-chunk duties, plus
  a primary `citation` compatibility field. The stable `duty_id` keys off the
  **SOURCE-section item ordinal** (`{code}:{ordinal:02d}`) — not a fragile chunk
  ordinal, so a boundary move can't renumber a duty — and `duty_sha` fingerprints
  the FULL source item, so an exact rerun stays stable while any source edit yields
  a changed sha / a new pending value. `_render_worksheet` renders ALL citations
  per duty, so no cited chunk is ever advertised without rendered content.

- **Sidecar Layer 2.** `noc_review._current_key_sets` consumes the new split (fail
  closed on `None`); `_layer2_fresh` re-verifies EVERY stored citation fragment
  (re-resolve + re-ground) against the current index — a boundary-split duty is
  demoted the moment either chunk drifts — with a back-compat path for a legacy
  single-`citation` value. The public envelope stays PII-light (chunk-id list
  only; per-fragment quotes live vault-only).

**Tests (hermetic source+index fixtures + real-corpus proofs):**

- Rewrote `test_noc_overflow_regression.py` to build a self-contained corpus
  (BOTH the `chunks` index AND the matching NOC markdown SOURCE, since the split
  now grounds source against index) with EXACT counts for four formats:
  overflow (`#002`+flattened `#003`, reqs `#004`), grouped (internal `" - "`
  header stays one item), normal newline, and a NEW **cross-chunk** fixture whose
  one bullet spans `#002`/`#003` (the `#003` tail has NO leading `- `) — asserting
  all three sentences are one item with TWO grounded citations and that no cited
  chunk is empty.
- Real-corpus proofs: `72410`'s header is exactly one item (17 duties, not 18);
  `11202`'s last duty carries all three agent sentences and spans `#002`/`#003`
  with both citations grounded; `31100`'s Preventive duty includes its
  continuation; `72400` overflow is not mislabelled (18 duties from both chunks);
  and a **full 376-group scan** comparing emitted items BYTE-FOR-BYTE to the raw
  source bullets (after boilerplate) and proving EVERY citation fragment grounds
  against its sha-validated chunk (with the two known multi-chunk duties exercised).
- Updated the existing `72400` overflow / grouped / normal tests and the
  idempotency / changed-sha / stale / Layer-2-drift contracts in
  `test_noc_review.py` + `test_conformance_v5_noc_no_auto_green.py` to the
  source-item `duty_id` scheme and the `citations` shape.

_Flagged "requires human verification" because this is a retrieval/parsing logic
rebuild — syntax + the full test suite + conformance + publish-safety all pass,
but a human should confirm the source-parse + token-alignment semantics match
intent (the byte-for-byte 376-scan is the strongest evidence)._

---

## Iteration 1 — original fixes (preserved)

**Fixed at:** 2026-07-19T11:52:00Z · **Commits:** `d37e901`, `618153e`, `03bf847`

### CR-01 + CR-02: Positional-ordinal retrieval mislabels overflowed duties / single-line duty chunks yield zero duties

**Files modified:** `crawler/searchindex.py`, `crawler/noc_worksheet.py`,
`crawler/noc_review.py`, `crawler/tests/test_noc_review.py`,
`crawler/tests/test_noc_review_cli.py`
**Commit:** `d37e901`
**Status:** fixed: requires human verification (retrieval/split logic rebuild)

Section-aware retrieval (`resolve_noc_spans`) added a read-only, parameter-bound
`searchindex.relpath_sections` table-of-contents; classification is now by EXACT
trailing `section` label (never positional `#003`-is-requirements), collecting the
single lead + the ordinal-ordered LIST of Main-duties chunks + the
Employment-requirements chunk(s), each sha-validated through the frozen
`searchindex.resolve`. Fails closed on absent/ambiguous required sections. The
iteration-1 delimiter-robust split parsed both newline `- ` and inline `" - "`
encodings (scoped to single-physical-line chunks) — this is the parser the
iteration-2 rebuild replaces with the source-structure design (see WR-01/WR-02).

### WR-01 (iteration 1): Test suite validated only happy-path NOCs

**Files modified:** `crawler/tests/test_noc_overflow_regression.py` (new)
**Commit:** `618153e`
**Status:** fixed

Added the overflow/inline-slice regression module (hermetic + skip-guarded
376-subtest real-corpus scan). *Superseded by the iteration-2 rewrite*, which
tightens the scan to exact byte-for-byte counts + per-fragment grounding (the
iteration-1 scan only asserted `duty_count > 0`, which is why the WR-01/WR-02
re-review defects passed CI green).

### WR-02 (iteration 1): Candidate scoping inconsistent across the sidecar's read helpers

**Files modified:** `crawler/noc_review.py`, `crawler/cli.py`,
`crawler/tests/test_noc_review.py`
**Commit:** `03bf847`
**Status:** fixed

`review_noc_duties` threads an explicit `candidate_id`; both the eligible read
(`_candidate_eligible_duty_values`) and the rejected read
(`_rejected_current_duty_ids`) `JOIN documents … WHERE candidate_id = ?` and still
apply the shipped 5-key `vault.is_audit_eligible` choke point. (Unrelated to the
iteration-2 WR-02, which is a different finding under the same id in the
re-review.)

## Skipped Issues

None — all in-scope findings were fixed across the three iterations.

## Deferred (Info — intentionally not fixed)

Iteration-3 re-review Info items (all documentation/wording or cosmetic — NOT
fixed this pass, per "Do not implement Info"):

- **IN-01:** `resolve_noc_spans` collects ALL `Main duties`-labelled chunks rather
  than enforcing contiguity — harmless on the current corpus (they are always
  contiguous across all 376 groups). Wording/optional-hardening only.
- **IN-02:** `split_duties`' per-fragment `quote_is_grounded(fragment,
  span["text"])` is tautological (a verbatim slice always grounds) — the real
  re-verification is `noc_review._layer2_fresh`. No behavior change needed;
  docstring could be aligned.
- **IN-03:** `_find_token_run` first-match alignment is a latent fragility not
  pinned by a test — correct for all 376 groups today; consider an invariant
  assertion / doc.
- **IN-04:** carried-over CLI cosmetics — `open_vault` runs before the refusal (so
  the vault dir is created even when the command refuses; zero *worksheet*
  artifacts still holds), and the success message counts reused ids.

---

_Fixed: 2026-07-19T13:30:00Z_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 3_
