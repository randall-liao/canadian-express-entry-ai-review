---
phase: 26-personalized-layer-1-checklist-pii-separation
plan: 03
subsystem: cli
tags: [cli, argparse, grounding, publish-safety, pii-separation, layer-1, express-entry, unittest, contract]

# Dependency graph
requires:
  - phase: 25-grounding-gate
    provides: "grounding.check_answer / render_answer (fail-closed gate + claims-only renderer) and the _cmd_ground render→scan→write trust path reused verbatim"
  - phase: 26-personalized-layer-1-checklist-pii-separation
    provides: "Plan 01 checklist.personal_dir/load_profile + Plan 02 build_answer (gated, PII-free-by-construction Phase-25 answer object) that this verb wraps"
  - phase: 24-search-verb
    provides: "the contract envelope (contract.envelope/emit/EXIT_*) + cli build_parser subparser idiom the new verb plugs into"
provides:
  - "crawler/cli.py: _cmd_checklist + `checklist` subparser — profile → build_answer → check_answer → (pass) render→RPT-03-scan→anchored write under personal/output/"
  - "crawler/contract.py + crawler/CONTRACT.md: additive `checklist` command value (schema_version '1.0', 5 keys, EXIT_* UNCHANGED)"
  - "crawler/tests/test_checklist.py: CLI dispatch/containment + real-corpus integration + rendered-bytes publish-safe + tracked-tree fail-closed suite (55 tests total)"
  - "End-to-end PII boundary: personalized Layer-1 checklist written ONLY under git-ignored personal/output/, rendered bytes proven PII-free, personal/ tracked-tree empty"
affects: [phase-27, personalized-checklist, publish-safety]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Verb-reuses-verb: _cmd_checklist copies the _cmd_ground render→scan→write trust path verbatim (CR-03 anchored containment + WR-01 neutral scan label) — no re-implementation of the share-safety gate"
    - "Additive-only contract evolution: a new command VALUE + a parallel CONTRACT.md section, schema_version + EXIT_* frozen (envelope() takes a plain command:str, so the literal is doc-only)"
    - "Scoped publish-safety gate: the SC4 fail-closed scan is over the RENDERED checklist bytes (neutral 'checklist.md' label) — NOT a whole-tree scan (pre-existing unrelated ABS_PATH debt is explicitly out of scope)"
    - "--emit-answer composability: print the assembled answer JSON and stop, so a checklist pipes straight into the `ground` verb"

key-files:
  created: []
  modified:
    - crawler/cli.py
    - crawler/contract.py
    - crawler/CONTRACT.md
    - crawler/tests/test_checklist.py

key-decisions:
  - "Reused grounding.render_answer (claims+quote+citation only, never basis[]) as the checklist renderer — PII-free by construction, identical gate/render/scan pipeline to `ground`, so CHK-01 'every line is a gated cited claim' holds without a bespoke renderer"
  - "Deterministic output filename 'checklist.md' (not a question-slug) — the anchored personal/ containment is the real control; a fixed name makes the 'exactly one .md' acceptance assertion trivial"
  - "The CLI re-runs grounding.check_answer over the build_answer output to surface a verdict-fail branch (exit 1) even though build_answer gates-by-construction; tested by mocking build_answer to return an uncited claim"
  - "--profile takes the profile DIRECTORY (the personal root); the verb reads <dir>/profile.yaml via checklist.load_profile, mapping ProfileError → invalid_input/exit 2 (mirrors _cmd_ground's grounding.InvalidAnswer mapping)"

patterns-established:
  - "Pattern: trust-path reuse — a new write-gated verb inherits CR-03 + WR-01 + the exit taxonomy by copying _cmd_ground, so the security review surface is one shared path, not N"
  - "Pattern: render-bytes-scoped acceptance — prove SC4 over the exact bytes the write-gate scans (scan_text('checklist.md', rendered) == []) + a sentinel self-scan, never a whole-tree scan that reds on unrelated debt"

requirements-completed: [CHK-01, CHK-02]

# Metrics
duration: 12min
completed: 2026-06-21
---

# Phase 26 Plan 03: Personalized Layer-1 Checklist CLI Verb + PII Boundary Summary

**The `checklist` CLI verb reads `$PR_PERSONAL_DIR/profile.yaml`, assembles + gates the Phase-25 answer via Plan-02 `build_answer`, and on a pass renders ONLY the cited `claims[]`, RPT-03 publish-safety-scans the rendered bytes, and writes a personalized Layer-1 document checklist ONLY under git-ignored `personal/output/` — reusing the exact `_cmd_ground` render→scan→write trust path, with an additive-only `checklist` contract value (schema_version "1.0", `EXIT_*` unchanged).**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-21T07:45:38-04:00
- **Completed:** 2026-06-21T07:57:00-04:00
- **Tasks:** 3 (Task 1 TDD: RED → GREEN)
- **Files modified:** 4 (all extended; 0 created)

## Accomplishments

- **`_cmd_checklist` + `checklist` subparser** (`crawler/cli.py`) — profile → `checklist.build_answer` → `grounding.check_answer` → (pass) `grounding.render_answer` → `check_publish_safe.scan_text("checklist.md", …)` → anchored write under `personal/output/`. It REUSES `_personal_root()` (CR-03 repo-anchored containment), the neutral WR-01 scan label, and the `contract.envelope/emit/EXIT_*` taxonomy verbatim — no re-implementation of the share-safety gate. Exit mapping mirrors `ground`: verdict-fail = `ok:true`/exit 1/render-nothing; publish-unsafe = `ok:false`/`internal_error`/exit 4; bad profile / non-file `--db` / out-of-`personal` `--out-dir` = `invalid_input`/exit 2. Adds `--emit-answer` (print answer JSON, write nothing) for piping into `ground`.
- **Additive contract** (`crawler/contract.py` + `crawler/CONTRACT.md`) — the `checklist` command value threaded into the two docstring command unions, and a new `### checklist` section parallel to `### ground` documenting the identical `result` shape + exit mapping + the locked "schema_version stays 1.0, the only additive change is the `checklist` command value and this section" line. `SCHEMA_VERSION` "1.0", the 5 envelope keys, and ALL `EXIT_*` constants are UNCHANGED (`grep -c 'EXIT_'` == 4, before and after).
- **Acceptance proof** (`crawler/tests/test_checklist.py`, 39 → 55 tests) — a `@skipUnless(corpus/index.db)` real-corpus integration that loads the TRACKED `personal.example/profile.yaml`, builds + gates against the live 742-doc index (verdict **pass**, ≥1 claim, every citation a GENERIC relpath — no `police-certificates/<country>` leak); a NOT-skip-guarded scan over the rendered checklist bytes (`scan_text("checklist.md", rendered) == []` + no sentinel token); a sentinel-PII self-scan over the tracked example; and a `personal/` tracked-tree fail-closed guard (`git ls-files personal/` empty, example tracked, `scan_path_name` → `TRACKED_CORPORA`).
- **End-to-end real-corpus smoke** (manual): `PR_PERSONAL_DIR=personal.example … checklist --db corpus/index.db --out-dir personal/output` → `ok:true`, verdict `pass`, 6 grounded claims, written to git-ignored `personal/output/checklist.md`; the police requirement cites the GENERIC `guidance/police-certificates.md`, and no `Wakanda`/`Latveria` sentinel appears in the rendered file.

## Task Commits

Each task committed atomically (Task 1 followed TDD RED → GREEN):

1. **Task 1 (RED): failing checklist CLI verb tests** — `69c58d0` (test)
2. **Task 1 (GREEN): checklist CLI verb (gate→render→RPT-03 scan→anchored write)** — `4479d47` (feat)
3. **Task 2: additive contract docs (contract.py + CONTRACT.md)** — `09699d4` (docs)
4. **Task 3: acceptance proof (real-corpus + rendered publish-safe + tracked-tree)** — `2cc430f` (test)

**Plan metadata:** committed separately with this SUMMARY (docs).

_Task 1 RED introduced 9 failing CLI tests (`checklist` subcommand absent → argparse exit 2); the GREEN feat made all 9 pass with no refactor commit needed (the verb mirrored `_cmd_ground` cleanly). Task 3 needed no production change — the PII/containment guarantees are by-construction from the Task-1 trust-path reuse, so the acceptance classes are the regression assertions._

## Files Created/Modified

- `crawler/cli.py` — EXTENDED: `_cmd_checklist(args) -> int` (NEW verb handler) + the `checklist` subparser in `build_parser()` (flags `--db`, `--out-dir`, `--profile`, `--emit-answer`); `checklist` added to the subparsers `metavar`. Reused unchanged: `_personal_root()`, `grounding.render_answer`/`check_answer`, `check_publish_safe.scan_text`, `contract.envelope/emit/EXIT_*`.
- `crawler/contract.py` — EXTENDED (doc-only): `| "checklist"` in the module-docstring command union (:13) + `checklist` in the `envelope()` docstring command list (:69). No constant/schema change.
- `crawler/CONTRACT.md` — EXTENDED: `checklist` added to the `## The envelope` command enumeration + a NEW `### checklist` per-command section (result shape + exit mapping + the "schema_version stays 1.0" locked line).
- `crawler/tests/test_checklist.py` — EXTENDED (+~210 lines): `_ChecklistCliCase`/`TestChecklistCli` (CLI dispatch + CR-03 containment + verdict-fail + invalid_input boundaries + RPT-03 refusal + `--emit-answer` + stdout purity), `_load_cps` helper, `TestRealCorpusChecklist` (`@skipUnless`), `TestRenderedChecklistPublishSafe`, `TestExampleProfilePublishSafe`, `TestPersonalTrackedTree`.

## Decisions Made

- **Renderer reuse over a bespoke layout:** `grounding.render_answer` renders claims + verbatim quote + resolved citation and NEVER touches `basis[]`, so the rendered checklist is PII-free by construction and the render/scan/write pipeline stays byte-identical to `ground`. A checklist-specific renderer would have duplicated the trust path for no gain.
- **CLI re-gate to expose the verdict-fail branch:** although `build_answer` gates-by-construction (always returns `pass`), `_cmd_checklist` re-runs `grounding.check_answer` and honors a `verdict != "pass"` as `ok:true`/exit 1/no-write — matching `_cmd_ground` exactly. The branch is tested by mocking `build_answer` to return an uncited claim.
- **Deterministic `checklist.md` filename:** the anchored `personal/` containment is the real write control; a fixed filename makes "exactly one `.md` written" a clean acceptance assertion and is idempotent across reruns.
- **Phase-scoped publish-safety:** acceptance asserts the RENDERED bytes scan clean and `git ls-files personal/` is empty — NOT a whole-tree `check_publish_safe` exit 0 (that reds on ~22 pre-existing unrelated ABS_PATH violations in Phase-25 planning docs / test marker strings, per RESEARCH lines 470–474). Zero new violations introduced.

## Deviations from Plan

**None — plan executed exactly as written.** The optional `--emit-answer` flag (explicitly "if implemented" in the plan) was implemented and tested. The contract change stayed additive-only as specified (`EXIT_` count 4 → 4, `SCHEMA_VERSION` "1.0" unchanged). No architectural changes, no new dependencies (stdlib + the in-repo modules + PyYAML only); `grounding.py` / `searchindex.py` / `check_publish_safe.py` are UNMODIFIED.

## Issues Encountered

- The full `crawler/tests` suite is slow because the PRE-EXISTING `crawler/tests/test_dupaudit.py::TestRealCorpus` walks the real `corpus/index.db` (documented in the 26-01/26-02 summaries). Verification was split as before: the suite minus dupaudit, and dupaudit minus `TestRealCorpus`. That single `TestRealCorpus` condition is **pre-existing and unrelated** to this phase (I touched only `cli.py` / `contract.py` / `CONTRACT.md` / `test_checklist.py`) — **no new regression introduced**.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_checklist.py -q` → **55 passed** (real-corpus integration RAN, not skipped — `corpus/index.db` present).
- `.venv/bin/python -m pytest crawler/tests/test_checklist.py -k "cli or containment" -q` → CLI/containment tests pass; `-k "real_corpus or publish_safe or pii or tracked"` → acceptance tests pass.
- `.venv/bin/python -m pytest crawler/tests -q --ignore=crawler/tests/test_dupaudit.py` → **241 passed, 1 skipped, 59 subtests passed**.
- `.venv/bin/python -m pytest crawler/tests/test_dupaudit.py -q -k "not RealCorpus"` → **25 passed** (only the pre-existing `TestRealCorpus` remains failing — out of scope).
- `.venv/bin/python -m crawler.cli checklist --help` → exit 0, lists `--db`, `--out-dir`, `--profile`, `--emit-answer`; `--json checklist --help` shows `checklist` in the subparsers metavar.
- Real-corpus CLI smoke: `… --json checklist --db corpus/index.db --out-dir personal/output` → `ok:true`, verdict `pass`, 6/6 grounded, `result.out` = `personal/output/checklist.md`; `git status --short personal/` empty (git-ignored); `grep -E "Wakanda|Latveria" personal/output/checklist.md` → 0 (PII-free).
- Contract additive: `grep -c 'EXIT_' crawler/contract.py` == **4** (unchanged), `grep -c 'SCHEMA_VERSION = "1.0"' crawler/contract.py` == **1**; `grep -n '### checklist' crawler/CONTRACT.md` matches; `grep -n 'scan_text("checklist.md"' crawler/cli.py` matches (neutral WR-01 label).
- `git ls-files personal/` → empty; `git ls-files personal.example/profile.yaml` → tracked.

## Known Stubs

None. The `checklist` verb wires the real Plan-01/02 data path end-to-end (profile → grounded claims → rendered, scanned, written output); no placeholder/empty data flows to the rendered checklist. The `--emit-answer` path emits the real assembled answer object.

## Next Phase Readiness

- The personalized Layer-1 checklist is now produceable end-to-end via `corpus-crawler --json checklist`, gated + cited + PII-free, written only under git-ignored `personal/output/`. CHK-01 (gated cited checklist from `$PR_PERSONAL_DIR/profile.yaml`) and CHK-02 (PII separation: PII confined to never-rendered `basis[]`) are closed and proven against the live corpus.
- The PII boundary rests on four independent layers proven by tests: Plan-02 relpath backstop + verified generic queries, render_answer's claims-only rendering, the RPT-03 rendered-bytes scan, and the `personal/` `.gitignore` + `CORPORA_PREFIXES` fail-closed tracked-tree guard.
- No blockers. The phase's three plans (PII source → assembler → CLI verb) are complete; the orchestrator owns marking the overall phase done.

---
*Phase: 26-personalized-layer-1-checklist-pii-separation*
*Completed: 2026-06-21*

## Self-Check: PASSED

- FOUND: crawler/cli.py (_cmd_checklist + checklist subparser)
- FOUND: crawler/contract.py (additive checklist command value)
- FOUND: crawler/CONTRACT.md (### checklist section)
- FOUND: crawler/tests/test_checklist.py (CLI + acceptance suite, 55 tests)
- FOUND: .planning/phases/26-personalized-layer-1-checklist-pii-separation/26-03-SUMMARY.md
- FOUND commit 69c58d0 (test: Task 1 RED)
- FOUND commit 4479d47 (feat: Task 1 GREEN)
- FOUND commit 09699d4 (docs: Task 2 additive contract)
- FOUND commit 2cc430f (test: Task 3 acceptance proof)
