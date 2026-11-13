---
phase: 41-dli-pgwp-pinned-snapshot-family-refresh-generator
plan: 01
subsystem: corpus
tags: [dli, pgwp, ircc, snapshot, provenance, sha256, stdlib, urllib, atomic-write, schema-validation]

# Dependency graph
requires:
  - phase: 40-safe-freshness-effective-date-foundation
    provides: "freshness MECHANISM (within_freshness/row_in_effect) + strings-only field-name contract; crawl_date compatibility via crs_audit._as_date"
provides:
  - "crawler/dli_snapshot.py — stdlib-only IRCC DLI/PGWP snapshot generator (fetch, as_of_from, normalize, write, SchemaError)"
  - "Strict closed nine-field schema validation with fail-closed refusals (empty/truncated/missing/extra/non-str/bad-PGWP/malformed-DLI)"
  - "Per-DLI canonical markdown doc: one doc per DISTINCT normalized DLI#, union of name variants, per-campus tri-state PGWP table, current-status-only markers"
  - "Deterministic, dated (crawl_date=Last-Modified), body-only content_sha256 provenance + non-indexed manifest.json"
  - "Atomic full-family replace honoring the resolved out_dir (stage->validate->swap with rollback; stale-file deletion)"
  - "crawler/tests/fixtures/dli/dli-sample.json — 11-row verbatim official-payload subset covering every landmine (network-free)"
  - "crawler/tests/test_dli_snapshot.py — 39-test offline suite"
affects: [41-02-cli-refresh-dli, 41-03-grounded-row-golden-family, 41-04-phase-closeout, phase-44-study-decider]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-core/thin-network-seam split (pipeline.py analog) for offline testability"
    - "Fixed-host fetch seam with off-host redirect rejection + byte ceiling before json.loads (SSRF/DoS guard)"
    - "Body-only NFC sha256 as a content fingerprint (volatile date excluded from hash)"
    - "Atomic full-family replace via sibling stage + os.replace swap with rollback, generic paths.resolve_within containment"

key-files:
  created:
    - "crawler/dli_snapshot.py"
    - "crawler/tests/fixtures/dli/dli-sample.json"
    - "crawler/tests/test_dli_snapshot.py"
  modified: []

key-decisions:
  - "Snapshot date lives in front-matter crawl_date + manifest as_of, NOT in the hashed body, so content_sha256 is a true content fingerprint (drift-detectable, as_of-independent)"
  - "Fixture reconstructed from the LIVE authoritative payload (Last-Modified Thu, 16 Jul 2026 18:08:26 GMT) via curl — every row is a verbatim official record"
  - "Primary/title name is the first campus (sorted City,Campus) institution name — deterministic, no special-casing"
  - "write() accepts out_dir at the pure boundary (tests pass temp roots; CLI in 41-02 fixes it to corpus/dli)"

patterns-established:
  - "Fail-closed strict closed-schema ingestion boundary: any drift aborts the whole refresh, never a partial family"
  - "Per-campus tri-state PGWP preserved verbatim (Details never followed, conflicts never collapsed)"
  - "Non-indexed manifest.json provenance (.json extension keeps it out of dupaudit.live_docs / the index)"

requirements-completed: [STUDY-01]

# Metrics
duration: 20min
completed: 2026-07-18
---

# Phase 41 Plan 01: DLI/PGWP Pinned Snapshot Generator Core & Fixture Summary

**Stdlib-only IRCC DLI/PGWP snapshot generator: fixed-host fetch → strict closed nine-field schema validation → per-DLI canonical markdown with body-only sha256 provenance → atomic full-family replace + non-indexed manifest, plus an 11-row verbatim official-payload fixture and a 39-test offline suite.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-18T16:07:21-04:00
- **Completed:** 2026-07-18T16:26:16-04:00
- **Tasks:** 2 (both TDD: RED → GREEN)
- **Files modified:** 3 created

## Accomplishments
- New stdlib-only `crawler/dli_snapshot.py` (453 lines): `fetch` (fixed `_DLI_URL`, explicit timeout, off-host-redirect rejection, `_MAX_BYTES` ceiling before `json.loads`), `as_of_from` (RFC-1123 `Last-Modified` → ISO `Z`, fail-closed, never wall-clock), `normalize` (strict closed nine-field schema — ANY row-level violation, including a malformed DLI number, aborts the whole refresh fail-closed — plus deterministic per-DLI grouping), `_build_doc`/`_body_sha256`/`write`/`_write_manifest`, and `SchemaError`.
- Every generated per-DLI doc carries `source_type: dli`, normalized `dli_number`, `crawl_date` (= upstream `Last-Modified`), body-only `content_sha256`, `status_scope: current-only`, the exact `DLI number: <dli>` line, a current-status-only caveat, and a per-campus PGWP table preserving `Yes`/`No`/`Details` verbatim.
- Atomic full-family replace honors the resolved `out_dir`: sibling-staged, validated, `os.replace`-swapped with rollback; upstream-removed institutions leave no stale `.md`; any failure preserves the prior healthy family byte-for-byte.
- Curated `dli-sample.json` (11 rows, 5 distinct DLIs) reconstructed verbatim from the live authoritative payload — covers multi-campus, shared-DLI multi-name (U+2019), conflicting per-campus PGWP (`No`+`Details`), trailing-space DLI#, trailing-space institution name (union dedupe), non-ASCII (é/è), and all three PGWP values.

## Task Commits

Each task committed atomically (TDD RED → GREEN):

1. **Task 1 (RED): schema/fetch tests + curated fixture** — `9e6bf11` (test)
2. **Task 1 (GREEN): fetch seam, as_of_from, strict schema validation** — `fcb9535` (feat)
3. **Task 2 (RED): canonicalization/write/manifest/idempotence tests** — `cfbb10f` (test)
4. **Task 2 (GREEN): per-DLI doc build, atomic family write, manifest** — `cdd869c` (feat)

**Post-plan fail-closed hardening (source + test atomic):**

5. **Correct malformed-DLI handling: abort whole refresh (fail-closed)** — `541fdb1` (fix)

**Post-plan live-refresh compatibility/security correction (source + test atomic):**

6. **Drop custom `_UA` + `fetch` `url` param so the live DLI refresh succeeds** — `c6a0d65` (fix)

**Plan metadata:** committed separately (this SUMMARY + STATE/ROADMAP/REQUIREMENTS).

## Files Created/Modified
- `crawler/dli_snapshot.py` — stdlib-only DLI/PGWP snapshot generator core (fetch/validate/normalize/build/write/manifest).
- `crawler/tests/fixtures/dli/dli-sample.json` — 11-row verbatim official-payload subset (network-free), every landmine represented.
- `crawler/tests/test_dli_snapshot.py` — 39 offline unit tests (schema refusals, fetch seam, canonicalization, provenance hashing, atomic write/rollback/deletion, malformed-row whole-refresh abort + prior-family preservation, manifest non-enumeration, static self-scan).

## Verification Evidence
- `crawler/tests/test_dli_snapshot.py` → **39 passed** in <1 s (Task-1 selection `-k "schema or fetch or malformed or empty or as_of"` → 23 passed; `-k "malformed or schema"` → 19 passed).
- **Fail-closed malformed-row correction (post-plan `541fdb1`):** a mixed valid+malformed payload (`normalize({"data": [good, bad]})`, order-independent) raises `SchemaError`; the integration flow `write(normalize(tainted_payload))` raises in `normalize` before `write` runs, leaving a prior healthy family byte-for-byte untouched (`test_one_malformed_dli_row_aborts_whole_refresh`, `test_malformed_refresh_preserves_prior_family_byte_for_byte`).
- Phase 40/41 neighbor regressions: `test_freshness_staleness`, `test_crs_no_inlined_rules`, `test_crs_rules`, `test_index_health` → **44 passed**; `test_snapshot_health`, `test_snapshot_refusal` → **21 passed**.
- `grep -nE "import (crawl4ai|httpx|requests)|personal_root|candidate_root|repo_personal_root" crawler/dli_snapshot.py` → **no matches**.
- `grep -nE "max_age|snapshot_max_age|datetime\.now|_now\(" crawler/dli_snapshot.py` → **no matches**.
- `crs_rules.no_inlined_volatile_rules(["crawler/dli_snapshot.py"])` → **`[]`**.
- `git check-ignore crawler/tests/fixtures/dli/dli-sample.json` → committable; `python -m json.tool` parses.
- Full test collection (`pytest crawler/tests --collect-only`) → **928 tests, 0 import errors** (was 927 pre-hardening; net +1 write-preservation test).
- Exports present: `fetch, as_of_from, normalize, write, SchemaError` (+ `_build_doc, _body_sha256, _write_manifest, _DLI_RE, _nfc, _campus_key, _DLI_URL, _LABEL`); module = 453 lines (min 120). *(Post-plan `c6a0d65`: the `_UA` constant was removed and `fetch` no longer accepts a `url` parameter — see Deviation #3.)*

## Decisions Made
- **Snapshot date excluded from the hashed body.** `crawl_date` (front-matter) and `as_of` (manifest) carry the date; the body is a pure function of the DLI DATA, so `content_sha256` is a genuine content fingerprint that stays stable across re-fetches with a new `Last-Modified` but identical data (drift-detectable). See Deviations.
- **Fixture sourced from the live payload.** Network was reachable at build time (curl, out-of-band tier), so every fixture row is a verbatim copy of the real authoritative record (trailing spaces, accents, U+2019 preserved).
- **Deterministic primary name** = first sorted-campus institution name; **union names** = sorted distinct NFC-stripped set; **province/sector/grad** = sorted distinct joined — all deterministic, no special-casing.
- **`write(out_dir)`** parameterized at the pure boundary for temp/golden test roots; the CLI (41-02) is the only production caller and passes fixed `corpus/dli`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug/Correctness] Snapshot date removed from the hashed body**
- **Found during:** Task 2 (per-DLI doc build + provenance hashing)
- **Issue:** The plan's action (line 180) illustrated a `Designation status: … as of <YYYY-MM-DD>` line inside the body, but the plan's own behavior spec (line 171) and `must_haves` truth #4 require `content_sha256` to be a **body-only** fingerprint whose value does **not** change when only `as_of` changes (needed for drift detection — Pattern 4 "measurable freshness"). Embedding the volatile date in the hashed body is self-contradictory and would make every re-fetch with a bumped `Last-Modified` (identical data) change every doc hash and the `family_sha256`, defeating the provenance purpose. Test `test_changing_as_of_does_not_change_body_hash` proved the conflict.
- **Fix:** Kept the snapshot date where it belongs — front-matter `crawl_date` (required by `must_haves` #4) and manifest `as_of`/`last_modified` — and made the body carry a **date-free** current-status designation line. `_body_sha256` remains the plain sha256 of the NFC body (per action line 182), and is now genuinely `as_of`-independent.
- **Files modified:** `crawler/dli_snapshot.py` (`_build_doc` body block)
- **Verification:** `test_changing_as_of_does_not_change_body_hash`, `test_content_sha256_hashes_body_only_and_is_deterministic`, `test_body_sha256_matches_front_matter_value` all pass; full suite 38/38 at the time of Task 2.
- **Committed in:** `cdd869c` (Task 2 GREEN)

**2. [Rule 1 - Bug/Contract] Malformed DLI row now aborts the WHOLE refresh (post-plan hardening)**
- **Found during:** Post-plan review immediately after 41-01 close-out.
- **Issue:** `normalize()` `continue`d past a row whose `DLI #` failed `^O\d{6,}$`, retaining the other valid rows and silently emitting a **partial subset**. That contradicts the locked `must_haves` truth #3 ("…malformed DLI number… aborts the whole refresh fail-closed and never writes a partial or garbage family"). The original Task-1 implementation-detail lines (PLAN 119/132) said "skip (continue)", which conflicts with the top-of-plan contract; the contract wins. The prior SUMMARY's "fail-closed malformed-DLI drop" wording was therefore an inaccurate claim and has been corrected throughout this document.
- **Fix:** Replaced the `continue` with `raise SchemaError(f"invalid DLI number: {dli!r}")` — the message echoes only the normalized (NFC+stripped) DLI token, never institution/PII text, mirroring the existing `invalid PGWP value: …!r` convention. Removed the now-unreachable post-loop `no valid DLI rows` guard. Updated `normalize()` and `SchemaError` docstrings/comments so ALL row-level violations abort the whole refresh (no "drop malformed identity" language remains). Replaced `test_malformed_dli_row_skipped_valid_survives` with `test_one_malformed_dli_row_aborts_whole_refresh` (one malformed row among valid rows raises `SchemaError`, order-independent, no docs), renamed the all-malformed test, and added `test_malformed_refresh_preserves_prior_family_byte_for_byte` (the `normalize→write` flow fails in `normalize` before `write`, so a prior healthy family stays byte-for-byte intact).
- **Files modified:** `crawler/dli_snapshot.py` (`normalize` body + `normalize`/`SchemaError` docstrings), `crawler/tests/test_dli_snapshot.py` (`TestMalformed`, `TestWrite`).
- **Verification:** full suite **39/39**; `-k "malformed or schema"` → 19 passed; Phase 40/41 neighbors (freshness, crs, index_health, snapshot_health/refusal) → 65 passed.
- **Committed in:** `541fdb1` (fix — source + test atomic)

**3. [Rule 1 - Compatibility/Security] Live-refresh fix: removed custom `_UA` + `fetch` `url` parameter (post-plan, during 41-04 closeout)**
- **Found during:** The 41-04 real-refresh closeout gate blocker triage (see `deferred-items.md`).
- **Issue:** The shipped `fetch` seam sent a custom `User-Agent` (`_UA = "pr-review-agents DLI snapshot generator (personal, non-commercial)"`). The upstream Akamai CDN **deterministically blackholes that exact header** over HTTP/1.1 from this environment: the request hangs to a read timeout **iff** the custom UA is sent, so `--json refresh-dli` failed closed (exit 2, `The read operation timed out`) on every invocation, blocking whole-family generation. Stdlib `urllib`'s honest default identity returns `HTTP 200` (~0.4 MiB, correct `Last-Modified`) in ~3 s. Isolated empirically on the real seam (`_OPENER`: no-UA OK, Accept-only OK, custom-UA read-timeout). Separately, `fetch(url=_DLI_URL, …)` still exposed a caller-overridable initial-request URL — a residual SSRF seam inconsistent with the locked fixed-source boundary.
- **Fix:** (a) Removed the `_UA` constant and set **no** `User-Agent` header — stdlib `urllib` sends its honest client identity (empirically compatible; **NOT** a browser-spoofed or evasive UA). Kept `Accept: application/json` (verified compatible). (b) Changed the seam to `fetch(*, timeout: int = 60)` — no `url` parameter; the request is **always** built from the fixed `_DLI_URL`, structurally enforcing the fixed-source boundary and eliminating the initial-request SSRF surface. Preserved the explicit timeout, the `_MAX_BYTES` ceiling before `json.loads`, `_NoCrossHostRedirect` off-host rejection, `Last-Modified`, and fail-closed parsing.
- **Files modified:** `crawler/dli_snapshot.py` (`_UA` removed; `fetch` signature/body/docstring; `_DLI_URL` comment), `crawler/tests/test_dli_snapshot.py` (`fetch` has no `url` param and no `_UA`; request URL is exactly `_DLI_URL`; no custom User-Agent set by code; Accept is JSON; off-host-redirect rejection; static self-scan forbids a custom UA).
- **Verification:** `test_dli_snapshot.py` **42/42** (was 39; +3 assertions); `test_dli_refresh_cli.py` + `test_dli_grounding.py` → **22 passed / 1 skipped**. Live `.venv/bin/python -m crawler.cli --json refresh-dli` → **exit 0**, `ok:true`, 1136 institutions / 1454 campuses, `as_of=2026-07-16T18:08:26Z`; real git-ignored `corpus/dli/` (1136 `.md` + `manifest.json`) written; PII-free five-key envelope; `corpus/index.db` byte-for-byte unchanged (`d7e414f3…` — real index rebuild deferred to resumed 41-04).
- **Committed in:** `c6a0d65` (fix — source + test atomic)

---

**Total deviations:** 3 auto-fixed (Rule 1 — 1 correctness/provenance during Task 2; 1 fail-closed contract hardening post-plan; 1 live-refresh compatibility/security correction post-plan during 41-04 closeout).
**Impact on plan:** Deviations #1–#2 reconcile conflicting plan lines in favor of the locked `must_haves` contract. Deviation #3 makes the live refresh succeed with stdlib `urllib`'s honest identity and hardens the fixed-source boundary by removing `fetch`'s `url` parameter — no endpoint/redirect/schema/path protection weakened, no browser-spoofed UA added. No scope creep; CLI work stays owned by Plan 41-02; all other body/front-matter markers implemented exactly as specified.

## Issues Encountered
- **Initial `urllib` fetch of the live endpoint timed out** during fixture build (cold connection). Resolved by fetching the authoritative payload via `curl` (out-of-band build tier, network allowed at fixture-generation time), then selecting verbatim rows — the fixture is byte-faithful to the live IRCC data (`Last-Modified: Thu, 16 Jul 2026 18:08:26 GMT`, 1,454 rows, nine-field schema confirmed).

## Known Stubs
None — no placeholder/TODO/empty-data paths. The `write(out_dir)` parameter is a deliberate pure-boundary seam (CLI fixes it to `corpus/dli` in 41-02), not a stub.

## Threat Flags
None — no new security surface beyond the plan's `<threat_model>`. The only network egress is the fixed `_DLI_URL` (SSRF-guarded: fixed host, off-host redirect rejection, byte ceiling); filesystem writes are containment-guarded via `paths.resolve_within` under the resolved `out_dir`; the generator reads no vault/PII path.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- **41-02 (CLI `refresh-dli`)** can now dispatch to `dli_snapshot.fetch`/`as_of_from`/`normalize`/`write` and map `SchemaError` → `contract.INVALID_INPUT`/exit 2, passing fixed `corpus/dli`.
- **41-03 (grounded row + golden family)** can regenerate the golden family from `dli-sample.json` byte-identically and index it unchanged; the exact `DLI number: <dli>` span (chunk #000) is available for the `study.dli.designation` grounding.
- No blockers. Zero new dependencies, no max-age value, no wall-clock date, no vault read.

---
*Phase: 41-dli-pgwp-pinned-snapshot-family-refresh-generator*
*Completed: 2026-07-18*

## Self-Check: PASSED

- Files verified on disk: `crawler/dli_snapshot.py`, `crawler/tests/fixtures/dli/dli-sample.json`, `crawler/tests/test_dli_snapshot.py`, `41-01-SUMMARY.md` — all FOUND.
- Commits verified in git history: `9e6bf11`, `fcb9535`, `cfbb10f`, `cdd869c`, `541fdb1`, `c6a0d65` — all FOUND.
- Test suite: 42/42 passed (post-plan `c6a0d65` added +3 fetch-URL / no-custom-UA / off-host-redirect assertions); malformed/schema selection 19/19; static self-scan `[]`; no third-party/vault/wall-clock/max-age/custom-UA matches.
- Fail-closed contract (must_haves truth #3): a single malformed DLI row aborts the whole refresh (`SchemaError`); prior healthy family preserved byte-for-byte — verified.
- Live-refresh compatibility/security correction (`c6a0d65`): `.venv/bin/python -m crawler.cli --json refresh-dli` succeeds (exit 0; 1136 institutions / 1454 campuses; `as_of=2026-07-16T18:08:26Z`); real git-ignored `corpus/dli/` generated with a PII-free five-key envelope; `corpus/index.db` byte-for-byte unchanged. The `deferred-items.md` blocker is moved BLOCKED → RESOLVED.
