---
phase: 26-personalized-layer-1-checklist-pii-separation
plan: 01
subsystem: checklist
tags: [pyyaml, pii-separation, applicability, express-entry, layer-1, unittest]

# Dependency graph
requires:
  - phase: 25-grounding-gate
    provides: "structured answer object shape {question, claims[], basis[], abstentions, prose} that this checklist will produce and gate through in Plan 02"
  - phase: 24-search-verb
    provides: "searchindex.search/resolve retrieval (consumed by Plan 02, not this plan)"
provides:
  - "crawler/checklist.py: ProfileError, personal_dir(), load_profile(), applicable_items()"
  - "personal.example/profile.yaml: tracked synthetic sentinel post-ITA Express Entry profile (zero real PII)"
  - "crawler/tests/test_checklist.py: stdlib-unittest profile-loading + applicability suite (20 tests)"
  - "PII-tier split at its source: generic PII-free requirement text vs separate PII basis reason"
affects: [26-02, 26-03, checklist-assembler, checklist-cli]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Checklist-local ProfileError(ValueError) fail-fast — distinct from crawler.profile.ProfileError (crawl-site profile)"
    - "$PR_PERSONAL_DIR env resolver with ./personal/ default (git-ignored PII boundary)"
    - "Personalization = pure claim SELECTION (applicable_items) — never requirement-text mutation"
    - "PII isolation by construction: generic text/query PII-free; profile values route ONLY to basis"

key-files:
  created:
    - crawler/checklist.py
    - personal.example/profile.yaml
    - crawler/tests/test_checklist.py
  modified: []

key-decisions:
  - "applicable_items routes the specific residence-country list into the police-certificates basis sentence (PII tier) while keeping text/query generic — makes the separation guarantee testable, not just asserted absent"
  - "ECA included when claiming_foreign_education_points OR stream==FSW (per RESEARCH table); proof-of-funds only for FSW/FST (CEC/PNP exempt)"
  - "Sparse profiles read defensively via .get + safe int() coercion so a near-empty profile yields the always-on set without KeyError"
  - "yaml.safe_load ONLY (mirrors crawler/profile.py:150-164) — never yaml.load (threat T-26-01)"

patterns-established:
  - "Pattern: PII source module — only the profile carries PII; pure compute turns it into items whose generic fields are PII-free and whose basis holds the WHY"
  - "Pattern: synthetic sentinel fixture (Wakanda/Latveria) drives every test and lets a later self-scan assert non-leakage"

requirements-completed: [CHK-01, CHK-02]

# Metrics
duration: 26min
completed: 2026-06-21
---

# Phase 26 Plan 01: Personalized Layer-1 Checklist PII Source Summary

**`crawler/checklist.py` loader (`$PR_PERSONAL_DIR` + safe-YAML `load_profile`) plus pure `applicable_items()` that selects the Layer-1 document set from a synthetic Express Entry profile, with PII isolated to each item's `basis` by construction.**

## Performance

- **Duration:** ~26 min
- **Started:** 2026-06-21T10:47:00Z
- **Completed:** 2026-06-21T11:13:00Z
- **Tasks:** 2 (both TDD: RED → GREEN)
- **Files modified:** 3 created

## Accomplishments

- Tracked **synthetic** `personal.example/profile.yaml` (sentinel fake PII: Wakanda/Latveria, CEC + foreign-education) that exercises both the proof-of-funds exemption and the ECA inclusion paths — zero real personal data.
- `crawler/checklist.py` skeleton: checklist-local `ProfileError`, `personal_dir()` (`$PR_PERSONAL_DIR`, default `./personal/`), and `load_profile()` parsing via `yaml.safe_load` ONLY with fail-fast on unreadable/non-mapping input (mirrors `crawler/profile.py`).
- Pure `applicable_items(profile)` implementing the RESEARCH applicability table: always-on passport/language/medical/biometrics; ECA iff claiming-foreign-education OR FSW; proof-of-funds iff FSW/FST (CEC/PNP exempt); job-offer iff `has_job_offer`; police-certificates iff any residence country OR family ≥18 — each item carrying a generic PII-free `text`/`query` and a separate PII `basis` reason.
- `crawler/tests/test_checklist.py`: 20 stdlib-unittest tests (loader fail-fast, env override, applicability selection, sparse-profile no-KeyError, and a PII-separation assertion that sentinel tokens never appear in `text`/`query` and DO appear only in the police `basis`).

## Task Commits

Each task was executed TDD (test → feat), committed atomically:

1. **Task 1 (RED): profile-loading + `$PR_PERSONAL_DIR` tests** - `b9412db` (test)
2. **Task 1 (GREEN): checklist loader + synthetic profile fixture** - `a3e5cf5` (feat)
3. **Task 2 (RED): `applicable_items()` applicability tests** - `c7be452` (test)
4. **Task 2 (GREEN): pure `applicable_items()` selection** - `c61b63c` (feat)

**Plan metadata:** committed separately with this SUMMARY (docs).

_TDD tasks each have a test → feat commit pair; no refactor commit was needed (code matched the reference pattern cleanly)._

## Files Created/Modified

- `crawler/checklist.py` - NEW module: `ProfileError`, `personal_dir()`, `load_profile()` (safe-YAML, fail-fast), `applicable_items()` (pure applicability → items with `doc_type`/`query`/generic `text`/PII `basis`).
- `personal.example/profile.yaml` - NEW tracked synthetic sentinel profile (applicant/program/education/residence_since_18); drives every test; obvious fake PII only.
- `crawler/tests/test_checklist.py` - NEW stdlib-unittest suite (20 tests): `TestPersonalDir`, `TestLoadProfile`, `TestApplicability`.

## Decisions Made

- **PII genuinely routed into `basis`:** the police-certificates `basis` interpolates the specific residence countries (the PII), while `text`/`query` stay generic. This makes the CHK-02 separation boundary *testable* (the separation test positively asserts sentinels appear in `basis` but never in `text`/`query`) rather than merely asserting their absence everywhere.
- **`stream` upper-cased** before comparison so case variants in a hand-edited profile still classify correctly.
- **Defensive reads** (`.get` + guarded `int()`) so a sparse/partial profile yields the always-on set instead of raising — the loader is the fail-fast boundary, applicability is total.

## Deviations from Plan

None - plan executed exactly as written. The only design latitude exercised (placing the literal residence-country list in the police `basis` vs. the RESEARCH "specific countries kept local" phrasing) is explicitly within the plan's stated intent that PII lives in `basis`, and is covered by the separation test.

## Issues Encountered

- The full test suite is slow because `crawler/tests/test_dupaudit.py::TestRealCorpus` walks the real `corpus/index.db`. Verification was therefore split: the suite minus dupaudit (`206 passed, 1 skipped, 59 subtests`) and the dupaudit module minus `TestRealCorpus` (`25 passed`). The single `TestRealCorpus` failure is **pre-existing and unrelated** to this phase (documented in STATE.md / phase notes) — no new regression was introduced.

## Verification

- `.venv/bin/python -m pytest crawler/tests/test_checklist.py -q` → **20 passed**.
- `.venv/bin/python -m pytest crawler/tests -q --ignore=crawler/tests/test_dupaudit.py` → **206 passed, 1 skipped, 59 subtests passed**.
- `.venv/bin/python -m pytest crawler/tests/test_dupaudit.py -q -k "not RealCorpus"` → **25 passed** (only the pre-existing `TestRealCorpus` remains failing — out of scope).
- `git check-ignore personal.example/profile.yaml` → exit 1 (the example is **TRACKED**, not ignored).
- `git ls-files personal/` → empty (real PII tree stays out of the repo).
- `grep -v '^\s*#' crawler/checklist.py | grep 'yaml.load(' | grep -v safe_load | wc -l` → **0** (never the unsafe loader).

## Known Stubs

The `query` strings in `applicable_items()` (e.g. `"police certificate"`, `"proof of funds settlement"`) are intentional SHORT placeholders per the plan (Pitfall 3) — **Plan 02 tunes/verifies them live against the real corpus** when building grounded `claims[]`. This is explicitly deferred by the plan, not an accidental stub. No data-source stubs flow to any rendered UI in this plan (no rendering happens here).

## Next Phase Readiness

- `applicable_items()` provides the deterministic item list (with generic text + PII basis) that **Plan 02** will turn into grounded, cited PII-free `claims[]` via `searchindex.search`/`resolve` + `grounding`, then assemble + gate the Phase-25 answer object.
- The synthetic fixture is ready to drive Plan 02/03 end-to-end tests and the Plan-03 publish-safety self-scan.
- No blockers. PII boundary verified (example tracked, `personal/` empty, safe-YAML only).

---
*Phase: 26-personalized-layer-1-checklist-pii-separation*
*Completed: 2026-06-21*

## Self-Check: PASSED

- FOUND: crawler/checklist.py
- FOUND: personal.example/profile.yaml
- FOUND: crawler/tests/test_checklist.py
- FOUND: .planning/phases/26-personalized-layer-1-checklist-pii-separation/26-01-SUMMARY.md
- FOUND commit b9412db (test: Task 1 RED)
- FOUND commit a3e5cf5 (feat: Task 1 GREEN)
- FOUND commit c7be452 (test: Task 2 RED)
- FOUND commit c61b63c (feat: Task 2 GREEN)
