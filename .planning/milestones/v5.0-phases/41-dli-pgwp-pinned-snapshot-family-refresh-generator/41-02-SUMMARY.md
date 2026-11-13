---
phase: 41-dli-pgwp-pinned-snapshot-family-refresh-generator
plan: 02
subsystem: cli
tags: [dli, pgwp, ircc, cli, argparse, json-contract, envelope, ssrf-guard, offline-tests, refresh-dli]

# Dependency graph
requires:
  - phase: 41-01-dli-pgwp-pinned-snapshot-generator-core
    provides: "crawler/dli_snapshot.py (fetch/as_of_from/normalize/write/SchemaError) + fixtures/dli/dli-sample.json"
provides:
  - "Top-level `corpus-crawler refresh-dli` verb (STUDY-01 operator surface) — fixed IRCC endpoint, writes only corpus/dli/, no --url/--out/--from-file"
  - "crawler.cli._cmd_refresh_dli — thin dispatcher mapping fetch/schema failure → invalid_input/exit 2, success → PII-free five-key envelope"
  - "New frozen-contract command value \"refresh-dli\" (schema_version unchanged at 1.0)"
  - "crawler/tests/test_dli_refresh_cli.py — network-free CLI suite (patched fetch, cwd-isolated) proving envelope/refusal/no-arbitrary-input/publish-safe"
affects: [41-03-grounded-row-golden-family, 41-04-phase-closeout, phase-44-study-decider]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin argparse dispatcher (_cmd_index analog): validate → LAZY-import compute → map error to contract envelope → human summary to stderr"
    - "Fixed-endpoint/fixed-output operator verb — NO --url/--out/--from-file (SSRF + accidental-publication guard); cwd is the sole test-isolation seam"
    - "Network-free CLI test via unittest.mock.patch('crawler.dli_snapshot.fetch') + os.chdir tempdir (3.10-compatible; no contextlib.chdir)"

key-files:
  created:
    - "crawler/tests/test_dli_refresh_cli.py"
  modified:
    - "crawler/cli.py"

key-decisions:
  - "refresh-dli registered TOP-LEVEL on the main subparsers (beside index/crawl); NO `corpus` parent — vault stays the only nested verb tree"
  - "Global --json is parsed on the main parser and MUST precede the subcommand (argv [\"--json\", \"refresh-dli\"]); no per-subparser --json added"
  - "Envelope result literal out=\"corpus/dli\" (relative) — PII-free provenance only (public counts / as_of / family_sha256), never an absolute path"
  - "_require_readable_snapshot (Phase-40 preflight) deliberately NOT wired — refresh only WRITES; the max-age audit path is Phase-44"

patterns-established:
  - "Operator refresh verb: fixed authoritative source + fixed output, fail-closed to invalid_input/exit 2 while preserving the prior healthy family byte-for-byte"
  - "cwd-isolated offline CLI test for a no-output-flag verb: os.chdir into a TemporaryDirectory so a relative write root resolves under temp"

requirements-completed: [STUDY-01]

# Metrics
duration: 19min
completed: 2026-07-18
---

# Phase 41 Plan 02: `refresh-dli` CLI Verb & Network-Free Tests Summary

**A new top-level fixed-endpoint/fixed-output `corpus-crawler refresh-dli` verb that regenerates the pinned `corpus/dli/` family via the Wave-1 generator and emits the frozen five-key PII-free contract envelope — with no `--url`/`--out`/`--from-file` surface, fail-closed `invalid_input`/exit 2 on any fetch/schema failure, and a 11-test cwd-isolated offline suite that patches `dli_snapshot.fetch`.**

## Performance

- **Duration:** ~19 min (incl. a 15-min full-repo regression run)
- **Started:** 2026-07-18T20:42:34Z
- **Completed:** 2026-07-18T21:01:41Z
- **Tasks:** 2
- **Files modified:** 2 (1 modified, 1 created)

## Accomplishments
- Added `crawler.cli._cmd_refresh_dli(args) -> int`: a thin dispatcher (mirroring `_cmd_index`) that LAZY-imports `dli_snapshot`, fetches the FIXED IRCC endpoint (network only inside `fetch`), derives the deterministic `as_of` from the upstream `Last-Modified`, strictly validates + canonicalizes, and atomically writes only `corpus/dli/`.
- Fail-closed error mapping: a fetch failure (`URLError`/`TimeoutError`/`OSError`) or a `SchemaError` (empty/truncated/missing-field/invalid-PGWP/missing `Last-Modified`) → machine-readable `invalid_input` envelope + exit 2; `write()` is never reached on a refusal, so a prior healthy family stays byte-for-byte intact.
- Registered `refresh-dli` as a **top-level** subparser directly on the main `subparsers` (beside `index`/`crawl`, no `corpus` parent), exposing **no** `--url`/`--out`/`--from-file`, and extended the `add_subparsers(..., metavar=...)` string to include `refresh-dli`.
- Success path emits the frozen five-key envelope with `command:"refresh-dli"` and a PII-free `result` keyed exactly `{out, institutions, campuses, as_of, family_sha256}` (`out=="corpus/dli"`, a relative path); the human summary goes to stderr only so stdout stays pure JSON.
- Created `crawler/tests/test_dli_refresh_cli.py` — 11 network-free tests (+5 subtests) that patch `crawler.dli_snapshot.fetch` and `os.chdir` into a `TemporaryDirectory`, proving the success envelope, deterministic family generation, three refusal paths, family-untouched-on-refusal, no-arbitrary-input rejection, `--json` ordering, and publish-safety.

## Task Commits

Each task was committed atomically:

1. **Task 1: top-level `refresh-dli` verb + `_cmd_refresh_dli` handler** — `5140c05` (feat)
2. **Task 2: network-free CLI envelope/refusal/publish-safe tests** — `212eea4` (test)

**Plan metadata:** committed separately (this SUMMARY + STATE/ROADMAP/REQUIREMENTS).

## Files Created/Modified
- `crawler/cli.py` — added `_cmd_refresh_dli` thin dispatcher (fetch → error-map → PII-free envelope) and the top-level `p_refresh` subparser (no arbitrary URL/output/input args); extended the subcommand metavar with `refresh-dli`.
- `crawler/tests/test_dli_refresh_cli.py` — stdlib `unittest` (run via pytest), patched-fetch + cwd-isolated offline suite covering envelope shape, PII-freedom, deterministic family, fetch/schema/missing-`Last-Modified` refusals, byte-for-byte family preservation, forbidden-flag rejection, `--json` ordering, and `check_publish_safe` 0 violations.

## Verification Evidence
- **Plan verification 1** — `pytest crawler/tests/test_dli_refresh_cli.py crawler/tests/test_json_contract.py -x -q` → **37 passed, 1 skipped, 5 subtests passed** (frozen envelope unbroken).
- **Plan verification 2** — `grep -nE "add_parser\(\s*[\"']refresh-dli|set_defaults\(func=_cmd_refresh_dli" crawler/cli.py` → both matches present (lines 1652, 1654).
- **Plan verification 3** — `.venv/bin/python scripts/check_publish_safe.py` → **`✓ publish-safe: 393 tracked files scanned, 0 violations`** (exit 0).
- **Task 1 acceptance:** `grep -c "def _cmd_refresh_dli" crawler/cli.py` == 1; `build_parser().parse_args(["refresh-dli"]).command == "refresh-dli"` with `func is _cmd_refresh_dli`; no `--url`/`--out`/`--from-file` attached to `p_refresh`; metavar contains `refresh-dli`; no `corpus` parent parser; `test_json_contract.py` still green.
- **Task 2 acceptance:** patched successful fetch → exactly one five-key PII-free envelope, `ok:true`, exit 0, `institutions==5`, `campuses==11`, `as_of=="2026-07-16T18:08:26Z"`; fetch error + empty-data schema failure + missing-`Last-Modified` each → `ok:false`/`invalid_input`/exit 2 with `result` null; a refusal leaves a pre-seeded family byte-for-byte unchanged; `parse_args(["refresh-dli","--url",...])` raises `SystemExit`; every fetch is patched (no real network).
- **Wave-1 + neighbor regression** — `test_dli_snapshot.py`, `test_snapshot_health.py`, `test_snapshot_refusal.py`, `test_freshness_staleness.py`, `test_crs_no_inlined_rules.py`, `test_index_health.py`, `test_cli.py` → **91 passed**.
- **Full repo regression** — `pytest crawler/tests scripts/tests` → **974 passed, 1 skipped, 385 subtests passed** in 912.73s; 0 import/collection errors.

## Decisions Made
- **Top-level registration, no `corpus` parent.** `refresh-dli` sits directly on the main `subparsers` beside `index`/`crawl`; `_add_vault_subparser` remains the only nested verb tree (per RESEARCH/PATTERNS).
- **Global `--json` precedes the subcommand.** The flag is owned by the main parser; argv is exactly `["--json", "refresh-dli"]`. A trailing `refresh-dli --json` is rejected — encoded as a test.
- **PII-free provenance-only result.** The envelope carries public counts / `as_of` / `family_sha256` and the relative literal `out="corpus/dli"` — never institution PII or an absolute path.
- **cwd is the sole test-isolation seam.** Because the verb exposes no `--out`, tests `os.chdir` into a `TemporaryDirectory` (3.10-compatible; `contextlib.chdir` is 3.11+ and unavailable here), so the relative `corpus/dli` write root resolves under temp and never the repo.
- **Phase-40 `_require_readable_snapshot` intentionally not wired** — refresh only WRITES; the max-age audit preflight belongs to the Phase-44 audit path.

## Deviations from Plan

None — plan executed exactly as written. Both tasks landed with the specified handler shape, top-level registration, no-arbitrary-input surface, frozen five-key envelope, and network-free test coverage.

_(Implementation note, not a plan deviation: the plan's PATTERNS/RESEARCH illustrate `contextlib.chdir` for cwd isolation, but the runtime is Python 3.10 where that context manager does not exist; the plan's own action text explicitly permits `os.chdir` in setUp/tearDown as the alternative, which is what was used.)_

## Issues Encountered
None. The Wave-1 `dli_snapshot` seam patched cleanly (the handler's lazy `dli_snapshot.fetch` attribute access resolves to the mock at call time), and the deterministic generator output (5 institutions / 11 campuses / `family_sha256`) matched expectations on the first run.

## Known Stubs
None — the verb is fully wired end-to-end to `dli_snapshot.fetch/as_of_from/normalize/write`. No placeholder/empty-data paths, no TODO/FIXME markers introduced.

## Threat Flags
None — no new security surface beyond the plan's `<threat_model>`. All five registered threats are mitigated and test-owned: T-41-02 (no `--url`/`--out`/`--from-file`; fixed `_DLI_URL`; writes only `corpus/dli/`), T-41-01 (fetch + schema failure → `invalid_input`/exit 2, prior family preserved), T-41-05 (PII-free envelope + `check_publish_safe` 0 violations), T-41-03 (delegates to the proven atomic `dli_snapshot.write`), T-41-07 (reuses the frozen `contract.envelope`; `test_json_contract.py` still green).

## User Setup Required
None - no external service configuration required. (The verb reaches the network only at operator-invoked refresh time, against the fixed IRCC endpoint.)

## Next Phase Readiness
- **41-03 (grounded row + golden family)** can now regenerate the golden family and rely on the operator-facing `refresh-dli` verb as the STUDY-01 refresh surface.
- **41-04 (phase closeout)** has the CLI surface + offline test coverage in place for the conformance/closeout gate.
- No blockers. Zero new dependencies, no max-age value, no wall-clock date, no vault/PII read, no later-phase wiring.

---
*Phase: 41-dli-pgwp-pinned-snapshot-family-refresh-generator*
*Completed: 2026-07-18*

## Self-Check: PASSED

- Files verified on disk: `crawler/cli.py`, `crawler/tests/test_dli_refresh_cli.py`, `41-02-SUMMARY.md` — all FOUND.
- Commits verified in git history: `5140c05` (feat — verb + handler), `212eea4` (test — offline CLI suite) — all FOUND; each carries the required `Co-authored-by: Copilot` trailer.
- Acceptance greps: `def _cmd_refresh_dli` == 1; `add_parser("refresh-dli"` + `set_defaults(func=_cmd_refresh_dli)` present; metavar includes `refresh-dli`; no `--url`/`--out`/`--from-file` on `p_refresh`; no `corpus` parent parser.
- Tests: `test_dli_refresh_cli.py` 11 passed + 5 subtests; combined with `test_json_contract.py` 37 passed, 1 skipped; full repo regression 974 passed, 1 skipped, 385 subtests; `check_publish_safe.py` 0 violations.
- Fail-closed contract: fetch error / empty-data schema failure / missing `Last-Modified` each → `invalid_input`/exit 2 with a byte-for-byte-preserved prior family — verified.

