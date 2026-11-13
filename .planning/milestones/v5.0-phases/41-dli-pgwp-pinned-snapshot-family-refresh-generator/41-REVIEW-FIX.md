---
phase: 41-dli-pgwp-pinned-snapshot-family-refresh-generator
fixed_at: 2026-07-18T20:52:17-04:00
review_path: .planning/phases/41-dli-pgwp-pinned-snapshot-family-refresh-generator/41-REVIEW.md
iteration: 2
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
phase_status: verifying
cumulative_fixed: 3
cumulative_fixed_ids: [CR-01, WR-01, WR-02]
---

# Phase 41: Code Review Fix Report

**Fixed at:** 2026-07-18T20:52:17-04:00
**Source review:** `.planning/phases/41-dli-pgwp-pinned-snapshot-family-refresh-generator/41-REVIEW.md` (re-review after CR-01 / WR-01)
**Iteration:** 2

**Summary (iteration 2 — this pass):**
- Findings in scope (Warning): 1 (WR-02)
- Fixed: 1 (WR-02)
- Skipped (error/rollback): 0
- Info findings (IN-01, IN-02, IN-03, IN-04): intentionally deferred per fix directive (see below)

**Cumulative across the phase:** 3 findings fixed (CR-01, WR-01 in iteration 1;
WR-02 in iteration 2), each locked by deterministic, network-free regressions. No
frozen indexer / dedup / grounding code was touched by ANY fix (`dupaudit.py`,
`searchindex.py`, `grounding.py`, the CRS-grid YAML, and `study_dli.yaml` are
byte-for-byte unchanged — the conformance `TestFrozenContractsUnchanged` gate
confirms it, and iteration 2's commit is confirmed to touch only `dli_snapshot.py`
+ `test_dli_snapshot.py`). The committed golden family still regenerates
byte-identically (grounding suite green).

---

## Iteration 2 (this pass) — Fixed Issue

### WR-02: `normalize` does not reject control characters in free-text fields — allows body/marker injection into grounded chunk #000

**Files modified:** `crawler/dli_snapshot.py`, `crawler/tests/test_dli_snapshot.py`
**Commit:** `5452c59`
**Classification:** input-validation / fail-closed hardening (not an algorithmic
logic bug) — the guard is a pure structural predicate over string content,
covered before/after by deterministic regressions.

**Root cause.** `normalize()`'s closed-schema validation checked the field SET,
that every value `isinstance(..., str)`, the `PGWP` tri-state domain, and the
`DLI #` regex — but it never validated the CONTENT of the seven free-text fields
(`Institution`, `City`, `Campus`, `Province`, `Grad Program`, `HTML`,
`Public/Private`). `_nfc(...).strip()` only trims LEADING/TRAILING whitespace, so
an embedded newline (or CR/NEL) in a free-text field survived verbatim into the
generated body — including into the pre-heading block that is grounding **chunk
#000**, the exact region the STUDY-01 grounding selector keys on.

Reproduced exactly as the review described (upstream row with
`Institution = "Evil U\nDLI number: O00000000\nForged: injected"`, all other
fields valid): the H1 was truncated at the newline and a **forged `DLI number:`
marker line was injected into chunk #000** (`"DLI number: O00000000" in
<chunk#000>` → True). This defeated two invariants the module explicitly asserts:
(1) the docstring's fail-closed guarantee (a field carrying a raw control char is
drift/garbage yet passed validation and yielded a malformed doc); and (2) the
STUDY-01 grounding contract, whose selector pins on `marker: "DLI number: O…"`
and whose citation must be a verbatim body substring — a forged `DLI number:`
line in chunk #000 could flip `retrieve_what_you_cite` marker selection or
produce a chunk whose `chunk_id` disagrees with the rule (a false grounding
result). Real-world likelihood is LOW (the fixed IRCC CDN would have to serve a
control char via data-entry error / upstream compromise), but this validator's
whole purpose is to fail closed on exactly that drift; the gap was untested.

**Exact design (dli_snapshot.py only; frozen indexer/dedup/grounding/YAML
untouched).**

1. **Explicit-codepoint predicate `_has_control_char(text)`.** A deterministic
   predicate — NEVER a locale-/Unicode-version-dependent category-table lookup —
   so it is byte-stable across Python builds. It rejects exactly the C-category
   control block that is meaningful in JSON text:
   - ASCII **C0** `0x00`–`0x1F` (includes `\n` / `\r` — the line breakers that can
     forge a `DLI number:` marker or a markdown heading — plus `\t` and `NUL`),
   - **DEL** `0x7F`, and
   - the **C1** block `0x80`–`0x9F` (Unicode category `Cc`; notably `NEL` `U+0085`,
     which several line-oriented processors also treat as a break).

   **Rejecting the C1 block means the predicate rejects part of Unicode category
   `Cc` beyond ASCII — this is intentional and is documented here and locked by a
   test** (`nel_c1` in `_CONTROL_SAMPLES`). It deliberately does **not** reject
   ordinary Unicode letters/punctuation: accents like `è` (`U+00E8`) and the curly
   apostrophe `’` (`U+2019`) live above `0x9F` and pass unharmed, so legitimate
   institution/campus names survive verbatim (positive test below).

2. **Per-field enforcement in `normalize()`.** In the existing per-field loop,
   immediately after the `isinstance(value, str)` check, any string value
   containing a control character raises a fail-closed
   `SchemaError(f"row field {key!r} contains a control character")`. The message
   names ONLY the fixed, public schema field key — it **never echoes the raw
   offending content**, so it stays stable and PII-free. Because a single tainted
   row aborts the WHOLE `normalize()` **before any doc is built**, `write()` is
   never reached and a prior healthy family is preserved byte-for-byte (the
   fail-closed contract now extends from identity drift to content drift).

**CLI mapping — confirmed unchanged (no CLI edit).** `_cmd_refresh_dli` already
catches `dli_snapshot.SchemaError` from `normalize()` and maps it to
`contract.INVALID_INPUT` / **exit 2** (`cli.py:348-359`), and that mapping is
already covered by `test_dli_refresh_cli.py ::
RefreshDliRefusal.test_empty_data_schema_failure_refuses`. A control-char drift
raises the same `SchemaError` from the same call site, so it follows the identical
`invalid_input` / exit 2 fail-closed envelope — no new CLI code and no new focused
CLI test were required.

**Regressions added** (`test_dli_snapshot.py :: TestControlCharRejection`,
9 tests / 29 subtests):
- **Predicate boundary** — every representative control (`\n`, `\r`, `\t`, `NUL`,
  unit-separator `0x1F`, `DEL`, C1 `NEL`) is rejected, while accents and `U+2019`
  are accepted.
- **Newline forging `DLI number:`** in **Institution** AND in **Campus** each
  raise `SchemaError` (the exact review scenario, now fail-closed).
- **Carriage return, tab, NUL, DEL, and a C1 control** each abort the refresh.
- **Control char rejected in EVERY one of the nine string fields** (subTest over
  `_FIELDS`).
- **A single tainted row among good rows aborts the WHOLE normalize** —
  order-independent (bad row first or last), returns NO docs.
- **Integration `normalize -> write`** — a tainted rerun aborts in `normalize()`
  BEFORE `write()`, so the prior healthy family on disk is preserved
  byte-for-byte and no doc is emitted.
- **PII-free refusal** — the message names the field (`Institution`) but never
  echoes the planted secret content or a raw newline.
- **POSITIVE non-ASCII coverage** — a row with accented letters and `U+2019`
  normalizes cleanly and the content survives verbatim (NFC) in the body.

---

## Iteration 1 (prior pass) — Fixed Issues

_Preserved verbatim from the first fix pass; both findings remain fixed and
gated. Commits `db1e241` (CR-01) and `b7a3a0b` (WR-01)._

### CR-01: `refresh-dli` mis-maps `fetch()` size-ceiling and JSON-decode failures

**Files modified:** `crawler/dli_snapshot.py`, `crawler/cli.py`,
`crawler/tests/test_dli_refresh_cli.py`, `crawler/tests/test_dli_snapshot.py`
**Commit:** `db1e241`
**Classification:** error-mapping / control-flow (not an algorithmic logic bug) — covered
by before/after empirical repro + deterministic regressions.

**Root cause.** `_cmd_refresh_dli` wrapped `dli_snapshot.fetch()` in
`except (urllib.error.URLError, TimeoutError, OSError)` only. But `fetch()` can raise
its OWN refusals that are none of those subclasses:
- the T-41-01 size-ceiling `SchemaError` (`dli_snapshot.py`), and
- `json.JSONDecodeError` / `UnicodeDecodeError` from a non-JSON / truncated / non-UTF-8
  CDN response (e.g. a canada.ca HTML maintenance page served with HTTP 200).

These escaped the handler. Reproduced before the fix (exactly matching the review):

```
A) fetch SchemaError (size ceiling), --json  -> error type=internal_error, exit 4
B) fetch SchemaError (size ceiling), human   -> UNCAUGHT SchemaError traceback, exit 1
C) fetch json.JSONDecodeError, human         -> UNCAUGHT JSONDecodeError traceback, exit 1
```

This contradicted the handler docstring and VALIDATION row 41-02-01
("fetch/schema failures return `invalid_input`/exit 2"): a security DoS-guard refusal
was mislabeled `internal_error`/exit 4 in `--json`, and human mode crashed with a raw
traceback.

**Exact design.**
1. **Normalize at the source (preferred).** `dli_snapshot.fetch()` now converts
   `UnicodeDecodeError` -> `SchemaError("DLI dataset is not valid UTF-8")` and
   `json.JSONDecodeError` -> `SchemaError("DLI dataset is not valid JSON: <exc.msg>")`.
   Messages are **stable and PII-free** — raw payload bytes are never echoed; only the
   parser's short reason (`exc.msg`, e.g. "Expecting value") is included, never the
   positional/`str(exc)` suffix or content. The size ceiling already raised `SchemaError`.
2. **Broaden the handler catch.** `_cmd_refresh_dli`'s fetch `try/except` now also
   catches `dli_snapshot.SchemaError` (plus `UnicodeDecodeError` / `json.JSONDecodeError`
   as belt-and-suspenders in case a caller bypasses fetch's normalization), mapping every
   fetch-stage refusal to the SAME `invalid_input` / exit 2 envelope. `import json` was
   added to the handler alongside the existing `import urllib.error`.

`URLError` / `TimeoutError` / `OSError` handling and the second `as_of`/`normalize`
`SchemaError` branch are **unchanged**. `write()` is still never reached on a refusal,
so a prior healthy `corpus/dli/` family is preserved byte-for-byte (fail-closed contract
intact). After the fix, A/B/C all return `invalid_input` / exit 2 with pure stdout and no
traceback.

**Regressions added.**
- `test_dli_refresh_cli.py :: RefreshDliFetchStageRefusal` — drives the REAL `fetch()`
  through a patched network seam (`_OPENER` + `_MAX_BYTES`) for four realistic CDN faults
  (oversized, invalid-UTF-8, non-JSON HTML, truncated JSON), asserting `invalid_input` /
  exit 2 in `--json` (one clean envelope, `result` null) AND exit 2 / no-traceback /
  pure-stdout in human mode, with the pre-seeded healthy family byte-for-byte intact.
- `test_dli_snapshot.py :: TestFetch` — unit tests that `fetch()` normalizes each
  decode/JSON fault to `SchemaError`, plus a PII-free-message assertion (an institution
  name planted in the body never leaks into the error text).

### WR-01: crash-window orphan stage/backup dirs indexed as live DLI docs

**Files modified:** `crawler/dli_snapshot.py`, `crawler/tests/test_dli_snapshot.py`
**Commit:** `b7a3a0b`
**Classification:** path/containment — deterministic regressions prove the containment
property; the true SIGKILL window is simulated (a real kill cannot be scripted portably).

**Root cause.** `write()` staged/backed up into PID-suffixed **siblings of the family
root** inside the indexed corpus tree (`corpus/.dli.stage-<pid>`, `corpus/.dli.bak-<pid>`).
A hard-kill in the swap window (after `os.replace(root, backup)` and before the final
cleanup) left a full family copy of valid front-matter `.md` docs under `corpus/`.
`dupaudit.live_docs` / `searchindex.build_index` enumerate `root.parent.rglob("*.md")`,
which **descends dot-directories**, so the orphan's docs were enumerated as live.
Reproduced before the fix: `live_docs(corpus)` went 5 -> 10 with duplicate
`.dli.bak-*/O….md` relpaths and doubled `DLI number:` markers. `write()` only swept its
OWN pid's temp dirs, never a prior crash's.

**Exact design (containment moves; the frozen indexer/dedup are NOT touched).**
- Stage and backup now live in a **collision-resistant transient container under
  `root.parent.parent`** — one directory ABOVE the indexed corpus tree — named
  `.dli-refresh-<hash16>-<pid>-<rand>/{stage,bak}`, where `hash16` is a stable 16-hex
  SHA-256 of the absolute resolved root and `rand` is `os.urandom(6).hex()`. Concrete
  outcomes: production `corpus/dli` stages under the **repo root** (not `corpus/`);
  golden `.../golden/dli` stages outside `golden/`; a temp `.../<tmp>/dli` stages outside
  `<tmp>/`. The container is one level up from `root`, so it stays on the **same
  filesystem** and `os.replace` remains an **atomic rename**.
- The stage -> validate -> swap/rollback flow is otherwise **unchanged**. If the rollback
  restore itself raises, container cleanup is skipped so the backup is **preserved
  out-of-tree** (recoverable, never indexed) rather than deleted.
- **On-entry sweep of THIS family's dead crash-orphans** (best-effort POSIX `kill -0`;
  `ProcessLookupError` => dead, any other error => conservatively alive). A
  live/concurrent container is **spared**. No locks; correctness never depends on the
  sweep succeeding because orphans are already outside the indexed tree.

**Regressions added.** `test_dli_snapshot.py :: TestCrashOrphanContainment`:
- a simulated crash orphan is proven NOT enumerated by `dupaudit.live_docs(corpus)`
  (only 5 canonical, no dup relpaths, no doubled DLI markers);
- a normal write leaves no transient dir in the indexed tree and no leftover container;
- entry-sweep clears a dead-PID orphan but spares a live one (concurrency-safe);
- rollback preserves the prior family byte-for-byte with no in-tree debris;
- PID parse / self-liveness sanity.

---

## Deferred Issues (Info — out of fix scope by directive)

The fix directive explicitly said **"Do not implement Info findings or broaden
scope."** These are recorded verbatim for the phase owner; none were touched.

### IN-01: same-host redirect guard checks hostname only, not scheme *(carried forward)*
**File:** `crawler/dli_snapshot.py` (`_NoCrossHostRedirect.redirect_request`)
**Original issue:** a same-host `https -> http` downgrade redirect would be followed;
low risk (no credentials/cookies sent, public payload) but weakens the SSRF/exfil guard.
**Status:** deferred (Info, out of scope).

### IN-02: manifest `last_modified` holds an ISO value, not the raw RFC-1123 header *(carried forward)*
**File:** `crawler/dli_snapshot.py` (`_write_manifest`)
**Original issue:** `"last_modified": as_of` duplicates `"as_of"` (ISO), so a consumer does
not get the upstream `Last-Modified` header value the field name implies.
**Status:** deferred (Info, out of scope).

### IN-03: `write()` has no empty-`docs` guard *(carried forward)*
**File:** `crawler/dli_snapshot.py` (`write`)
**Original issue:** `write([], out_dir)` would atomically replace a healthy family with an
empty one; today `normalize` guarantees >=1 doc so the production path is safe, but the
standalone function has no self-guard. The WR-01 rewrite left this unchanged.
**Status:** deferred (Info, out of scope).

### IN-04: WR-01 container move adds a same-filesystem coupling (`root.parent.parent`) *(new in re-review)*
**File:** `crawler/dli_snapshot.py` (`container_parent = root.parent.parent`; atomic swap)
**Original issue:** staging one level UP requires `root.parent` AND `root.parent.parent`
to be on the same filesystem; if `corpus/` were ever a separate mount, `os.replace` would
raise a cross-device `OSError`. In this repo `corpus/` is a normal git-ignored
subdirectory, so the assumption holds today — a low-risk coupling note for operators.
**Status:** deferred (Info, out of scope).

---

## Gates (iteration 2, post-WR-02)

All run with `.venv/bin/python` from the repo root, after commit `5452c59`:

| Gate | Result |
|------|--------|
| Targeted (`TestControlCharRejection`) | 9 passed, 29 subtests |
| Phase 41 focused surface (`test_dli_snapshot`, `test_dli_refresh_cli`, `test_dli_grounding`, `test_dli_conformance`) | 100 passed, 1 skipped, 67 subtests |
| Full crawler suite (`crawler/tests/`) | 988 passed, 2 skipped, 425 subtests (0:18:55) |
| Publish-safe (`scripts/check_publish_safe.py`) | 399 tracked files scanned, 0 violations |
| Conformance release gate (`scripts/run_conformance.py`) | PASS — SAFE-01..08, 75 passed |
| Frozen contracts unchanged (`git diff` vs prior HEAD) | dupaudit/searchindex/grounding/CRS-YAML/study_dli.yaml/cli.py untouched by WR-02 |

(Deltas vs iteration 1's gate run — full crawler 979 -> 988 passed and 396 -> 425
subtests — are exactly the 9 new tests / 29 new subtests added for WR-02.)

## Constraint adherence

- Only `dli_snapshot.py` + `test_dli_snapshot.py` were changed for WR-02
  (`git show --stat 5452c59` confirms 2 files). No CLI change was needed — the
  existing `normalize`-`SchemaError` -> `invalid_input`/exit 2 mapping and its test
  already cover the new refusal, so no focused CLI test was added.
- Prior fixes/contracts preserved: fixed endpoint / no custom UA / no URL param,
  strict whole-payload validation, fixed CLI output shape, no `max_age`, inert
  row, zero new dependencies, and the CR-01 / WR-01 designs — all intact.
- Frozen indexer / dedup / grounding code and both YAMLs untouched by this pass.
- Research cache untouched; no new top-level files created; no history rewrite
  (one new fix commit + this docs commit); each commit carries the required
  `Co-authored-by: Copilot` trailer. Info findings NOT implemented; scope not
  broadened.

## Deviations

- **No isolated git worktree was used** — same rationale as iteration 1, now
  concretely re-verified: the required gates mandate `.venv/bin/python`, and the
  editable `crawler` install resolves to the repository's MAIN working-tree
  `crawler` package rather than an isolated checkout.
  A throwaway `/tmp` worktree has no `.venv` and its edits would NOT be exercised
  by the mandatory suites (imports would resolve to the main tree), so worktree
  isolation is incompatible with the required verification here. There is no
  concurrent foreground session in this environment, so the isolation rationale
  does not apply. Work was done in-place on `master` with an atomic per-finding
  commit — no history rewrite, clean tree.
- **`gsd-tools` is not installed**; the commit was made with `git commit` using
  the conventional `fix(41): WR-02 …` subject and the required co-author trailer.
- **This report was committed by the fixer** (per the phase objective's explicit
  "update/commit 41-REVIEW-FIX.md"), rather than deferred to an orchestrator.

## Completion marker

The sole in-scope re-review finding (WR-02) is fixed, tested, and gated; CR-01 and
WR-01 remain fixed. The phase is left in **Verifying** — NOT marked complete.
Human verification recommended for: (1) the WR-01 crash-window behavior under a
real SIGKILL (only simulated here); and (2) whether the four deferred Info
findings (IN-01..IN-04) should be scheduled.

---

_Fixed: 2026-07-18T20:52:17-04:00_
_Fixer: the agent (gsd-code-fixer)_
_Iteration: 2_
