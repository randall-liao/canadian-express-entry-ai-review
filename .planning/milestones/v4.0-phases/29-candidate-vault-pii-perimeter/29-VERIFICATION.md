---
phase: 29-candidate-vault-pii-perimeter
verified: 2026-07-06T05:45:08Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
re_verification:
  # No — initial verification (no prior 29-VERIFICATION.md existed)
requirements_verified: [VAULT-01, VAULT-02, VAULT-03, VAULT-04]
notes:
  - "SC4 names 'publish-safe/gitleaks/path-guard' as the blocking mechanisms. No literal gitleaks/pre-commit hook ships in the repo, but the SC's observable truth (vault artifacts cannot be staged or written outside the vault) is fully achieved and tested via publish-safe (scan_vault_artifact) + .gitignore + resolve_within path-guard. No plan committed to a gitleaks config; the blocking behavior is proven end-to-end. Informational only — not a gap."
  - "The 29-01 package-legitimacy checkpoint (blocking-human) was auto-approved during execution per standing autonomous authorization; installed deps confirmed official (pydantic 2.13.4, platformdirs 4.10.0)."
---

# Phase 29: Candidate Vault & PII Perimeter — Verification Report

**Phase Goal:** Applicant can safely store their CRS profile, ITA round/cutoff, and raw documents in a private vault that cannot contaminate the public repo or authoritative corpus.
**Verified:** 2026-07-06T05:45:08Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

Every success criterion was verified against the shipped code with a mix of source
inspection, the full test suite, and independent behavioral probes (synthetic data
only — no PII printed). All four ROADMAP success criteria are objectively TRUE, the
frozen v3.x trust path is unchanged, and there are no gaps or human-verification items.

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | SC1 — Applicant can create/select a non-PII candidate vault and store CRS factor breakdown + ITA round/cutoff under the git-ignored personal boundary | ✓ VERIFIED | `vault.open_vault` resolves `candidate_root` via `paths.candidate_root` (git-ignored `personal/candidates/<slug>/`), runs `PRAGMA user_version` migrations creating `crs_profile_factors` + `ita_rounds`. Behavioral probe (tmp `$PR_PERSONAL_DIR`): `vault init` → `{candidate_id, vault_kind:candidate, created:true}`; `vault ita set --cutoff 500` → `{round_id: ita_…, has_cutoff:true}`; `vault.sqlite` written under the candidate root. `.gitignore` ignores `personal/`. |
| 2 | SC2 — Applicant can import raw PDFs/images → vault-local document/evidence IDs, content-addressed, kept out of repo/corpus/reports | ✓ VERIFIED | `vault.import_document` computes sha256, writes bytes to `resolve_within(root,"files","raw",<sha256><ext>)`, mints `doc_`/`ev_` ids, returns PII-light `DocumentSummary`. Probe imported `Jane_Doe_UCI123.pdf` → on-disk `files/raw/105156…7c.pdf`; stdout carried `ev_bad8c531dc86` + `sha256_prefix` but NOT the filename token nor abs path. No `corpus/` dir created. Test `test_vault.py` asserts on-disk dedup + corpus-untouched. |
| 3 | SC3 — `evidence_id` never interchangeable with `citation_id`; candidate text never citable as authority | ✓ VERIFIED | `is_evidence_id("ev_…")=True / is_citation_id=False`; corpus `relpath#3`: `is_citation_id=True / is_evidence_id=False` (probe + `test_vault_pii_perimeter.py`). `searchindex.resolve(corpus_db, evidence_id)` does `WHERE chunk_id=?` → an `ev_` id is never a corpus chunk → returns `None`. Conformance test asserts import leaves a sibling `corpus/` byte-unchanged. |
| 4 | SC4 — Staging/writing vault DB/WAL, images, OCR text, logs, reports outside the vault is blocked by publish-safe/path-guard | ✓ VERIFIED | Independent probe: throwaway git repo seeded with the project `.gitignore`, `git add -A` staged only `.gitignore` — vault.sqlite/-wal/files-raw all ignored (`git check-ignore` confirms all 4). `scan_vault_artifact` flags DB/sidecars, `candidates/` segment, and vault-subtree files (0 false positives on README.md/logo.png/cli.py). `resolve_within` refuses `..`, absolute, and symlink escapes (`PathEscapeError`). |
| 5 | Frozen v3.x trust path unchanged (search/`--cite`/grounding gate/JSON envelope, SCHEMA_VERSION "1.0") | ✓ VERIFIED | `contract.SCHEMA_VERSION = "1.0"` unchanged; `vault` added additively to the command enum; CLI probe envelope carries `schema_version:"1.0"` + five keys. `cli._personal_root`→`repo_personal_root` (unconditional `<repo>/personal`), `checklist.personal_dir`→`legacy_personal_dir` (verbatim). Regression suite `test_grounding/test_checklist/test_json_contract/test_searchindex` = 203 passed, 1 skipped. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `crawler/paths.py` | Shared resolver + `resolve_within` containment guard | ✓ VERIFIED | 172 lines; `resolve_within`, `PathEscapeError`, `safe_candidate_id`, `candidate_root`, lazy `platformdirs`. Wired: imported by cli.py, vault.py, checklist.py. |
| `crawler/vault.py` | Schema/migrations, lifecycle, profile/ITA store, content-addressed ingest, id minting | ✓ VERIFIED | 526 lines; `PRAGMA user_version` migrations, 5 tables, `import_document`, `is_evidence_id`/`is_citation_id`. Wired: imported by cli.py + tests. |
| `crawler/models/vault.py` | pydantic models incl. PII-light summaries | ✓ VERIFIED | 117 lines; `CrsProfileFactor`, `ItaRound`, `VaultDocument`, PII-light `DocumentSummary`/`VaultSummary`. Wired: imported by vault.py. |
| `crawler/cli.py` (vault verbs) | `vault init/profile/ita/import/list` subcommand | ✓ VERIFIED | `_add_vault_subparser` registered in `build_parser` (line 1136); 6 handlers dispatch into `crawler.vault`; single `envelope("vault", …)` per call. |
| `scripts/check_publish_safe.py` | `VAULT_ARTIFACT` detection | ✓ VERIFIED | 310 lines; `scan_vault_artifact` wired into `main()` per-file loop (line 283); flags DB/sidecars/candidates/subtrees, 0 false positives. Live run: 0 violations. |
| `.gitignore` | Vault DB + sidecar ignores | ✓ VERIFIED | `personal/` (with `!personal.example/`), `*.db*`, `*.sqlite`, `*.sqlite-shm`, `*.sqlite-wal`, `corpus/`. |
| `personal.example/crs-profile.example.yaml` | Synthetic PII-free example | ✓ VERIFIED | 74 lines; explicit "ZERO real personal data" header; spans all four factor groups; passes publish-safe scan. |
| `crawler/CONTRACT.md` | Additive `vault` result-shape docs | ✓ VERIFIED | `### vault` section; `schema_version "1.0"` stability promise intact; envelope unchanged. |
| Test suites (5 files) | Resolver/vault/CLI/perimeter/guard tests | ✓ VERIFIED | test_paths + test_vault + test_vault_cli + test_vault_pii_perimeter + test_check_publish_safe = 97 passed, 25 subtests. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `cli._personal_root` | `paths.repo_personal_root` | frozen write-gate anchor | ✓ WIRED | cli.py:434-435 delegates unconditionally (env-independent). |
| `checklist.personal_dir` | `paths.legacy_personal_dir` | verbatim legacy default | ✓ WIRED | checklist.py:63; behavior byte-identical (test_checklist green). |
| `vault.py` (writes) | `paths.resolve_within` | every FS write anchored | ✓ WIRED | `open_vault`/`import_document` route dest via `resolve_within`; forged `..` raises PathEscapeError (tested). |
| `vault.import_document` | `files/raw/<sha256>` | content-addressed copy | ✓ WIRED | `hashlib.sha256` → `files/raw/<sha256><ext>`; probe produced `105156…7c.pdf`. |
| `cli.py` vault handlers | `crawler.vault` | lazy dispatch | ✓ WIRED | `from crawler import paths, vault` in each handler. |
| `cli.py` | `contract.envelope("vault")` | single PII-light envelope | ✓ WIRED | cli.py:745,754; SCHEMA_VERSION unchanged. |
| `check_publish_safe.py` | `personal/candidates/**` | path-name scan | ✓ WIRED | `candidates` segment rule; probe confirmed VAULT_ARTIFACT + CORPORA both trip. |
| `test_vault_pii_perimeter` | `searchindex.resolve` | ev_ id → None | ✓ WIRED | conformance asserts a candidate evidence_id is not a corpus chunk. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `vault list` / `profile show` | `summary.document_count`, `documents[]`, `factor_count` | `vault.summarize_vault` → live `SELECT`/`COUNT(*)` on `vault.sqlite` | Yes — probe after import returned `document_count=1` with the real `doc_`/`ev_` ids | ✓ FLOWING |
| `vault import` | `DocumentSummary` + `sha256_prefix` | real `import_document` write + `SELECT file_sha256` | Yes — real sha256 of imported bytes | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Vault init produces valid PII-light envelope | `cli --json vault init` (tmp `$PR_PERSONAL_DIR`) | `schema_version 1.0`, `created:true` | ✓ PASS |
| ITA round/cutoff stored | `cli --json vault ita set --cutoff 500` | `{round_id: ita_…, has_cutoff:true}` | ✓ PASS |
| Import is content-addressed + PII-light | `cli --json vault import Jane_Doe_UCI123.pdf` | `ev_` id on stdout; filename token + abs path ABSENT; on-disk `files/raw/<sha256>.pdf` | ✓ PASS |
| List reflects real DB state | `cli --json vault list` | `document_count=1` with real ids | ✓ PASS |
| `git add -A` cannot stage vault artifacts | tmp git repo + project `.gitignore` | only `.gitignore` staged; 4 vault paths check-ignored | ✓ PASS |
| Publish-safe flags all vault artifact types | `scan_vault_artifact(...)` | DB/sidecars/candidates/subtrees flagged; 0 false positives | ✓ PASS |
| Path guard refuses `..`/absolute/symlink | `resolve_within(...)` | all raise `PathEscapeError` | ✓ PASS |
| Publish-safe live scan clean | `scripts/check_publish_safe.py` | `202 tracked files scanned, 0 violations` (exit 0) | ✓ PASS |

### Probe Execution

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| PII-perimeter conformance (SC3+SC4) | `pytest crawler/tests/test_vault_pii_perimeter.py` | included in 97-pass phase run | ✓ PASS |
| Full phase-relevant suite | `.venv/bin/python -m pytest crawler/tests scripts/tests -q` | **400 passed, 1 skipped, 106 subtests passed** in 619.63s | ✓ PASS |
| Publish-safety gate | `.venv/bin/python scripts/check_publish_safe.py` | 0 violations, exit 0 | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| VAULT-01 | 29-01/02/03 | CRS factor breakdown + ITA round/cutoff in a git-ignored, unstageable local vault | ✓ SATISFIED | Truths 1, 5; profile/ITA store + `.gitignore` + git-staging probe. |
| VAULT-02 | 29-02/03 | Import raw documents as content-addressed files kept out of repo/corpus/reports | ✓ SATISFIED | Truth 2; `import_document` + on-disk sha256 file + no corpus write. |
| VAULT-03 | 29-02/03/04 | Candidate evidence strictly separate; `evidence_id` distinct from `citation_id` | ✓ SATISFIED | Truth 3; disjoint predicates + `resolve()` None + no-contamination test. |
| VAULT-04 | 29-04 | Publish-safe/gitleaks gates extended to all vault artifacts | ✓ SATISFIED | Truth 4; `VAULT_ARTIFACT` category + `.gitignore` + path-guard (see note re: gitleaks). |

No orphaned requirements — REQUIREMENTS.md maps exactly VAULT-01..04 to Phase 29, all claimed by plans and all satisfied.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No `TBD`/`FIXME`/`XXX` debt markers in any phase-modified file | ℹ️ Info | None |
| `scripts/check_publish_safe.py` | 22,40 | word "placeholder" | ℹ️ Info | Docstring describing the vendored `.github/` framework's generic paths — not a stub. |
| — | — | No stub returns / NotImplementedError in vault source | ℹ️ Info | All handlers dispatch to real compute; `page_count NULL` is an intentional Phase-30 field, documented. |

### Human Verification Required

None. Every success criterion is programmatically observable and was verified with
passing tests plus independent behavioral probes. The only human-gated item in the
phase was the 29-01 pre-install package-legitimacy checkpoint, which was actioned
during execution (auto-approved per standing autonomous authorization; installed
versions confirmed official: pydantic 2.13.4, platformdirs 4.10.0) — it is not a
deferred end-of-phase check.

### Gaps Summary

No gaps. All 5 must-have truths VERIFIED, all 9 artifacts substantive and wired, all 8
key links WIRED, data flows real, full suite green (400 passed / 1 skipped), publish-safe
clean (0 violations), and the frozen v3.x trust path is byte-preserved (SCHEMA_VERSION
"1.0", regression anchors green).

One informational observation (not a gap): SC4 lists "publish-safe/gitleaks/path-guard"
as blocking mechanisms; no literal `gitleaks`/`.pre-commit-config.yaml` ships in the repo.
The SC's observable truth — vault artifacts cannot be staged or written outside the vault —
is nonetheless fully achieved and tested via publish-safe (`scan_vault_artifact`),
`.gitignore`, and the `resolve_within` path guard. No plan committed to a gitleaks hook,
and the plan-level must-haves (publish-safe flags artifacts; `git add -A` cannot stage;
path guard refuses escape) are all VERIFIED. If a literal gitleaks pre-commit hook is
desired as belt-and-suspenders, it can be tracked as a future hardening item, but the
Phase 29 goal is achieved without it.

---

_Verified: 2026-07-06T05:45:08Z_
_Verifier: the agent (gsd-verifier)_
