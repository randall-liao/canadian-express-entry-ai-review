---
phase: 41-dli-pgwp-pinned-snapshot-family-refresh-generator
reviewed: 2026-07-19T01:20:22Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - crawler/dli_snapshot.py
  - crawler/cli.py
  - crawler/data/crs_rules/study_dli.yaml
  - crawler/tests/test_dli_snapshot.py
  - crawler/tests/test_dli_refresh_cli.py
  - crawler/tests/test_dli_grounding.py
  - crawler/tests/test_dli_conformance.py
  - crawler/tests/test_dupaudit.py
  - crawler/tests/test_searchindex.py
findings:
  critical: 0
  warning: 0
  info: 5
  total: 5
status: clean
---

# Phase 41: Code Review Report (final confirmation re-review — CR-01 doc-leak resolved)

**Reviewed:** 2026-07-19T01:20:22Z
**Depth:** standard
**Files Reviewed:** 9
**Status:** clean (0 Critical/Blocker + 0 Warning + 5 non-blocking Info)

## Summary

Final confirmation re-review. The single blocking finding from the prior pass —
**CR-01: a committed absolute home-directory path in `41-REVIEW-FIX.md:309`** that
tripped the publish-safety scanner and failed the SAFE release-conformance gate — is
now **RESOLVED**. This re-review verifies the redaction, confirms both release gates
are green, and confirms the redaction did not mask any other issue. No source-level
Critical or Warning remains. Five previously-identified non-blocking Info observations
are carried forward (all deferred by fix directive), each re-checked against the
current source and still accurate.

**CR-01 (was BLOCKER) — RESOLVED & re-verified.** The offending line in
`41-REVIEW-FIX.md` (Deviations section) previously embedded a real machine path
in an interpreter-output example. The
working-tree diff replaces it with repository-relative prose:
*"the editable `crawler` install resolves to the repository's MAIN working-tree
`crawler` package rather than an isolated checkout."* No absolute home/user/root path
remains anywhere in the phase directory (the publish-safe absolute-home-path sweep
returns no matches), and no secret/credential pattern was masked by the edit.

**Redaction did not mask another issue.** The only change in the working tree is this
single-hunk doc edit (`git status` shows just `41-REVIEW-FIX.md` modified; the source
fixes for CR-01/WR-01/WR-02 were already committed in `db1e241`/`b7a3a0b`/`5452c59`).
A doc-only markdown edit cannot alter source behavior, and the full Phase-41 test
surface (including grounding byte-identity and frozen indexer/dedup regressions) is
green, so nothing was hidden.

**Prior source fixes remain in place (spot-verified in committed source):**
- CR-01 source half: `fetch()` normalizes size-ceiling/decode/JSON refusals to
  `SchemaError`, and the CLI fetch-stage catch tuple maps `SchemaError`,
  `UnicodeDecodeError`, `json.JSONDecodeError` → `invalid_input`/exit 2
  (`cli.py:326-343`); normalize-stage `SchemaError` mapped at `cli.py:348-359`.
- WR-01: stage/backup staged into an out-of-tree collision-resistant container under
  `root.parent.parent` with an on-entry dead-PID sweep (`dli_snapshot.py:501-563`).
- WR-02: `normalize()` rejects any C0/DEL/C1 control character in every string field
  via `_has_control_char` (`dli_snapshot.py:120-140`, enforced at `:299-300`).

**Gates re-run this review (all green):**
- `scripts/check_publish_safe.py` → **rc 0, 0 violations across 399 tracked files**.
- `scripts/run_conformance.py` (SAFE-01..08) → **rc 0, 75 passed / PASS**.
- Phase-41 focused surface (`test_dli_snapshot`, `test_dli_refresh_cli`,
  `test_dli_grounding`, `test_dli_conformance`) → **100 passed, 1 skipped** (was
  1 failed last pass — the publish-safety regression is cleared).
- The three tests that failed last pass now pass:
  `test_dli_refresh_cli.py::RefreshDliPublishSafe::test_check_publish_safe_zero_violations`,
  `test_conformance_v40_privacy_containment.py::TestTrackedTreeScansClean::test_publish_safe_main_zero_violations`,
  `test_conformance_v41_privacy.py::RemediationPacketPrivacy::test_tracked_tree_scans_clean`.

The phase is shippable: no blocking findings remain. Only the five non-blocking Info
observations below are carried forward (deferred by directive).

## Narrative Findings (AI reviewer)

No Critical or Warning findings. The five non-blocking Info observations below are
carried forward from prior passes; each was re-verified against the current source and
remains accurate. None blocks shipping; all were intentionally deferred by the fix
directive.

## Info

### IN-01: same-host redirect guard checks hostname only, not scheme *(carried forward — still open/deferred)*

**File:** `crawler/dli_snapshot.py:175-183`

**Issue:** `_NoCrossHostRedirect.redirect_request` compares `hostname` only
(`new_host != old_host`), so a same-host `https → http` downgrade redirect would be
followed. Low risk (no credentials/cookies are ever sent — only
`Accept: application/json`; the payload is public), but it weakens an
explicitly-labeled SSRF/exfil guard.
**Fix:** also require `urllib.parse.urlparse(newurl).scheme == "https"` (or
`== old_scheme`) before delegating to `super().redirect_request`.

### IN-02: manifest `last_modified` duplicates the ISO `as_of`, not the raw header *(carried forward — still open/deferred)*

**File:** `crawler/dli_snapshot.py:582-586`

**Issue:** `_write_manifest` sets `"last_modified": as_of`, where `as_of` is the derived
ISO-8601 value already stored under `"as_of"`. A consumer reading `last_modified` does
not get the upstream RFC-1123 `Last-Modified` header the field name implies; the field
is redundant and mildly misleading.
**Fix:** drop the duplicate field, or store the original RFC-1123 header string under
`last_modified` and keep the derived ISO value only in `as_of`.

### IN-03: `write()` has no empty-`docs` guard *(carried forward — still open/deferred)*

**File:** `crawler/dli_snapshot.py:484-570` (esp. `:503`)

**Issue:** `write([], out_dir)` would stage nothing, compute a family hash over `[]`,
and atomically replace an existing healthy family with an empty one (plus an
empty-`files` manifest). `as_of = docs[0]... if docs else None` handles the empty case
defensively but the swap still proceeds. Today `normalize` guarantees ≥1 doc (raises
`SchemaError` on empty `data`), so the production path is safe, but `write` is a
standalone function with no self-guard; a future caller could silently wipe the family.
**Fix:** early-return or raise on `if not docs:` before touching the root.

### IN-04: WR-01 container move adds a same-filesystem coupling (`root.parent.parent`) *(carried forward — still open/deferred)*

**File:** `crawler/dli_snapshot.py:512` (`container_parent = root.parent.parent`),
`:549-551` (atomic swap)

**Issue:** staging/backup one level UP (to `root.parent.parent`) to keep crash orphans
out of the indexed tree means the atomic `os.replace(root, backup)` /
`os.replace(stage, root)` now require `root.parent` AND `root.parent.parent` to be on
the same filesystem, whereas the previous sibling-of-root scheme only required
`root.parent`. If `corpus/` were ever a separate mount point, `os.replace` would raise
a cross-device `OSError` that escapes `write()` uncaught (called unguarded at
`cli.py:362`): human mode → traceback/exit 1, `--json` → the `main()` catch-all →
`internal_error`/exit 4. For production this container lands directly in the repo root
(`Path("corpus/dli").resolve().parent.parent`), a normal same-fs directory today, so
the assumption holds; this is a low-risk coupling note for operators who might relocate
the corpus onto a dedicated mount.
**Fix:** none required now; if the corpus can move to a separate mount, derive the
container from a same-fs anchor or fall back to a sibling-of-root stage when a
cross-device rename is detected.

### IN-05: `_sweep_stale_containers` docstring/code disagree on unparseable-name orphans *(carried forward — low impact)*

**File:** `crawler/dli_snapshot.py:466-478`

**Issue:** the docstring states orphans with an "unparseable name … stay" (are spared),
but the code removes them: `_container_pid` returns `None` for an unparseable name
(`:437-445`), so the guard `if pid is not None and _pid_alive(pid): continue`
(`:476-477`) is False and control falls through to `_rmtree(leftover)` (`:478`). In
practice this is harmless — every container this module creates is named
`{prefix}{pid}-{rand}` and always parses, and the glob is scoped to this root's hash —
so no live concurrent run is ever destroyed. But the code does not implement the
conservative "spare on doubt" contract the docstring promises for the unparseable case.
**Fix:** either align the docstring (unparseable names are cleaned up, not spared), or
make the code conservative to match the stated intent, e.g.
`if pid is None or _pid_alive(pid): continue`.

---

_Reviewed: 2026-07-19T01:20:22Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
