# Phase 46: SAFE Conformance & Release Gate - Research

**Researched:** 2026-07-20
**Domain:** Python/pytest safety conformance, release orchestration, grounded immigration-screening invariants
**Confidence:** HIGH

## User Constraints

No Phase 46 `CONTEXT.md` exists, so there are no discuss-phase decisions to copy. [VERIFIED: codebase grep]

### Direct Request (verbatim)

> Research final Phase46 release/conformance. Write/commit 46-RESEARCH.md. Read ROADMAP/REQUIREMENTS/PROJECT/STATE, all Phase40-45 verification/review/conformance tests/scripts, current full suite. Identify exact v5 rule families/screens/modules, existing v5 negative tests, gaps in SAFE11/12.
>
> Design one authoritative v5 release command extending run_conformance without breaking SAFE01-08. Must cover no-inlined volatile/retrieve-what-you-cite for MEC/POLICY/STUDY/DLI; stale/superseded/out-of-window/unconfirmed never greens across MEC/POLICY/STUDY/NOC; absent/drifted snapshot/config; unwired criterion; registry fingerprint drift; PII/no ev/abs paths stdout/envelopes/snapshot; zero deps/network audit; screening framing; frozen PublicAuditEnvelope/CRS; real cross-phase E2E using confirmed vault fixtures; snapshot provenance. Include independent negatives not circular production helpers. Determine baseline/full test commands/performance and known skips. Create/modify/freeze, plans/waves, threats, Validation Architecture, Open Questions RESOLVED. No source edits.

### Locked Project Constraints

- PII remains vault-only and stdout remains PII-light; only authoritative IRCC/Justice Laws/PDI sources may ground claims. [VERIFIED: planning docs]
- Verdicts fail closed; this phase must not add legal advice, outcome prediction, automated submission, semantic auto-resolution, cloud/vector/NLI paths, or a second trust path. [VERIFIED: planning docs]
- Volatile facts are read from pinned, refreshable local snapshots rather than fetched during audit. [VERIFIED: planning docs]
- Prefer zero new dependencies; Phase 46 should add none. [VERIFIED: planning docs]
- Extend the existing release gate and preserve SAFE-01 through SAFE-08. [VERIFIED: planning docs]
- Research only: no production/source edits are made while producing this document. [VERIFIED: user request]

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SAFE-11 | Extend no-inlined-volatile and retrieve-what-you-cite checks to MEC, POLICY, STUDY, and DLI so each threshold/date derives from a grounded citation. [VERIFIED: planning docs] | Exact manifests, enrolled source surfaces, real-index grounding, dynamic DLI provenance, and non-vacuous independent controls are specified below. |
| SAFE-12 | One v5 command covers all screens, never-green states, provenance, privacy, dependency integrity, and screening framing. [VERIFIED: planning docs] | The bounded runner extension, cross-phase E2E, independent negative matrix, release-prerequisite policy, and validation commands are specified below. |

</phase_requirements>

## Summary

The repository already has strong focused v5 conformance: four marked modules contain 66 tests—24 MEC, 6 POLICY, 23 STUDY, and 13 NOC—and the measured run passes all 66 with 494 subtests. Those files are not selected by `scripts/run_conformance.py`, whose bounded `test_conformance_v4[01]_*.py` glob currently advertises and runs only SAFE-01 through SAFE-08. [VERIFIED: codebase grep] [VERIFIED: test execution]

SAFE-11 is incomplete as an authoritative release proof. The whole-registry retrieve-what-you-cite test proves every static non-gap row only when the git-ignored real index is present, but it does not assert an exact v5 family partition. The aggregate no-inline surface includes MEC, NOC, and STUDY runtime modules but omits `policy_offer.py` and does not enroll `dli_snapshot.py` in the same authoritative surface. Dynamic DLI/PGWP candidate rows are generated at runtime and therefore need explicit provenance assertions in addition to the static registry proof. [VERIFIED: codebase grep]

SAFE-12 should extend—not replace—the existing runner with a bounded union of the v4.0/v4.1 and v5 globs. Add an exact grounding module, an independent release-flow module, and a runner self-test. The release-flow must use production entry points but build its own raw SQLite/vault/snapshot perturbations and expected-value oracles; importing donor test helpers or reproducing production helper logic would make the negatives circular. [VERIFIED: codebase grep]

**Primary recommendation:** Keep `.venv/bin/python scripts/run_conformance.py` as the sole command; make it collect the bounded v4 and v5 module families, and make real corpus/index/snapshot prerequisites mandatory under `PR_CONFORMANCE_RUNNER=1`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Release command/module selection | Local CLI orchestration | Test layer | `run_conformance.py` owns bounded pytest invocation, guard environment, working directory, and exit-code propagation. [VERIFIED: codebase grep] |
| Static volatile-rule enforcement | Test/static-analysis layer | Grounded registry | The scanner examines production/YAML surfaces; it must not become a second runtime loader. [VERIFIED: codebase grep] |
| Retrieve-what-you-cite | Local corpus/index | Test layer | Grounding is proven against SQLite chunks and exact citations from the canonical registry. [VERIFIED: codebase grep] |
| MEC/POLICY/STUDY/NOC evaluation | Local application/domain layer | Private vault + corpus/index | Production screens consume confirmed vault evidence and injected registry/snapshot data. [VERIFIED: codebase grep] |
| DLI snapshot provenance | Local corpus/snapshot storage | STUDY screen | Refresh creates pinned files/manifests; audit remains offline and validates hashes, dates, and index agreement. [VERIFIED: codebase grep] |
| PII containment/public contracts | Projection/publication layer | Test layer | Public envelopes and sidecars are closed projections while private evidence stays beneath candidate roots. [VERIFIED: codebase grep] |

## Project Constraints (from copilot-instructions.md)

- Use Python for shared crawler/index/validator tools. [VERIFIED: project instructions]
- Keep personal data and documents in structurally separate, local, git-ignored storage; no PII may enter the public repository. [VERIFIED: project instructions]
- Keep the harness CLI-agnostic and avoid proprietary CLI dependencies. [VERIFIED: project instructions]
- Back requirement claims with curated authoritative-corpus citations; third-party/blog content is not authoritative. [VERIFIED: project instructions]
- Follow existing architecture patterns where no architecture convention is mapped. [VERIFIED: project instructions]
- This work was initiated through the Phase 46 GSD research workflow before changing the planning artifact. [VERIFIED: project instructions]

## Exact v5 Inventory

### Grounded Rule Families

| Family | Exact static rows | Citations | Release proof |
|--------|-------------------|-----------|---------------|
| MEC / FSW | 17 rows: `fsw.work.primary_noc`, `teer`, `paid`, `recency`, `continuity_duration_hours`, `noc_duties`; `fsw.language.first`; `fsw.education.minimum`; six `fsw.grid.*` factors plus `pass_mark`; `fsw.funds.requirement`; `fsw.destination.outside_quebec` | 42 | Assert exact manifest equality, then every non-gap row agrees/grounds against the real index. [VERIFIED: codebase grep] |
| MEC / FST | 11 rows: trade NOC, same NOC, paid, qualification, student exclusion, duration/hours, duties/requirements, language, offer-or-certificate, funds, destination | 20 | Assert exact manifest equality and grounding. [VERIFIED: codebase grep] |
| MEC / CEC | 10 rows: TEER, in-Canada, authorized status, paid, duration/hours, student exclusion, self-employment exclusion, duties, language, destination | 13 | Assert exact manifest equality and grounding. [VERIFIED: codebase grep] |
| POLICY | `additional.job_offer.current`, `.legacy`, `.physician` | 5 | Prove exact effective-dated rows remain separate, cited, and never award CRS points. [VERIFIED: codebase grep] |
| STUDY | `additional.study`, `study.r73_definition` | 3 | Prove static rows plus candidate-specific runtime DLI/PGWP rows. [VERIFIED: codebase grep] |
| DLI | `study.dli.designation` plus runtime transient designation/PGWP candidate rows | 1 static citation plus runtime citations | Prove manifest/file/index hashes, common crawl date, exact DLI match, and citation selectors. [VERIFIED: codebase grep] |

The static MEC manifest contains 38 exact rows and 75 citations. POLICY has 3 rows/5 citations, while the static STUDY/DLI set has 3 distinct rows/4 citations when `additional.study`, `study.r73_definition`, and `study.dli.designation` are counted once. [VERIFIED: test execution]

### Screen Entry Points and Trust Surfaces

| Screen | Production entry point | Supporting modules that Phase 46 must enroll |
|--------|------------------------|-----------------------------------------------|
| MEC | `mec_screen.screen_mec` | `models/mec.py`, `mecfields.py`, `mec_screen.py`, `mec_publish.py`, `snapshot_policy.py`, `crs_rules.py` [VERIFIED: codebase grep] |
| POLICY | `policy_offer.offer_for_program_eligibility` plus frozen `crs_audit.arranged_employment_guard` | `policy_offer.py`, `crs_audit.py`, effective-dated registry rows [VERIFIED: codebase grep] |
| STUDY | `study_review.review_study` | `study_review.py`, `snapshot_policy.py`, DLI manifest/index and vault evidence [VERIFIED: codebase grep] |
| NOC | `noc_worksheet.generate_worksheet` and `noc_review.review_noc_duties` | `noc_worksheet.py`, `noc_review.py`, index chunks, vault duty confirmations [VERIFIED: codebase grep] |
| DLI refresh boundary | `dli_snapshot.py` generator, never imported into audit path | `dli_snapshot.py`, tracked golden fixtures, local `corpus/dli/manifest.json` [VERIFIED: codebase grep] |

## Existing Negative Coverage and SAFE Gaps

| Domain | Existing v5 coverage | Remaining Phase 46 release gap |
|--------|----------------------|--------------------------------|
| MEC | Unknown/missing/unwired/duplicate/invalid statuses; stale/out-of-window rows; five-key evidence staleness; publication failures; privacy; no network; frozen envelope/grid. [VERIFIED: codebase grep] | Add an independently constructed superseded threshold and unwired criterion to the composite flow; prove registry drift closes every composed sidecar. |
| POLICY | Legacy/post-repeal/physician/no-ITA/malformed paths never auto-green; CRS guard stays zero. [VERIFIED: codebase grep] | Construct raw out-of-window and unconfirmed evidence without importing donor test helpers; assert both program input and CRS remain non-green. |
| STUDY | Pending/rejected/corrected/stale evidence; missing/gap/tampered rows; absent/stale/drifted/corrupt index/snapshot/config; privacy; frozen dependencies/network. [VERIFIED: codebase grep] | Make absence, byte drift, bad config, provenance, and real confirmed-vault success mandatory in the release command rather than local-only skips. |
| NOC | Pending/partial/rejected/stale/superseded duty SHA never green; grid isolation; privacy; confirmed-vault paths. [VERIFIED: codebase grep] | Add a spine-level unconfirmed duty case and a real cross-phase flow; independently seed rows rather than call test helper constructors. |
| SAFE-11 aggregate | Whole-registry proof and positive scanner controls exist. [VERIFIED: codebase grep] | Exact v5 family manifests are not asserted; `policy_offer.py` is absent from aggregate no-inline enrollment; DLI generator coverage is separate; dynamic rows need explicit provenance. |
| SAFE-12 runner | SAFE-01..08 command passes and self-tests permit a future superset. [VERIFIED: codebase grep] [VERIFIED: test execution] | All four v5 modules are intentionally outside the current glob; no composite v5 E2E or v5 runner self-test exists. |

Phase 40–45 verification and review artifacts report no surviving blocker or warning findings. Nonblocking observations relevant to planning include no Phase-42 spine-level unconfirmed physician-NOC test, several NOC parser/remediation/exit-code observations, and no direct Phase-41 empty-document generator guard; Phase 46 should close only the release-proof gaps, not reopen production design by default. [VERIFIED: planning docs]

## Standard Stack

### Core

| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| CPython | local 3.10.12; project range `>=3.10,<4.0` | Runner, AST checks, hashing, SQLite fixtures, subprocess orchestration | Already authoritative for the project; no new runtime is needed. [VERIFIED: environment probe] [VERIFIED: codebase grep] |
| pytest | local 9.0.3 | Collection, markers, unittest compatibility, release execution | Existing framework and marker configuration. [VERIFIED: environment probe] [VERIFIED: codebase grep] |
| `unittest`, `sqlite3`, `hashlib`, `ast`, `subprocess`, `socket`, `tempfile` | stdlib | Independent fixtures, negative perturbations, integrity, process checks | Covers Phase 46 without dependencies. [VERIFIED: codebase grep] |

### Existing Runtime Dependencies

| Library | Local version | Purpose | Phase 46 disposition |
|---------|---------------|---------|----------------------|
| PyYAML | 6.0.3 | Existing registry/config parsing | Freeze dependency declaration; do not add or upgrade. [VERIFIED: environment probe] |
| Pydantic | 2.13.4 | Existing closed typed contracts | Freeze; assert `PublicAuditEnvelope` fields and source hash. [VERIFIED: environment probe] |
| platformdirs | 4.10.1 | Existing private local path resolution | Freeze; use temporary/private roots in E2E. [VERIFIED: environment probe] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Extend `run_conformance.py` | Add a second v5 shell script | Rejected: creates two release commands and can let SAFE-01..08 drift out of the final gate. |
| Bounded v4+v5 file globs | `-m conformance` alone | Rejected: marker-only selection can silently omit an unmarked release file; keep markers as a parity assertion, not the sole oracle. [CITED: https://github.com/pytest-dev/pytest/blob/main/doc/en/example/markers.rst] |
| Raw independent fixtures | Reuse helpers from focused v5 modules | Rejected: shared bugs can make production and expected values agree incorrectly. |
| Mandatory local release prerequisites | Skip when corpus/snapshot is absent | Rejected for release runs: a skipped grounding/E2E proof is not a valid release result. |

**Installation:** none. Phase 46 must leave `[project].dependencies` and `poetry.lock` unchanged. [VERIFIED: planning docs]

## Package Legitimacy Audit

Not applicable: the recommended phase installs no packages and freezes the existing dependency set. [VERIFIED: codebase grep]

## Architecture Patterns

### System Architecture Diagram

```text
.venv/bin/python scripts/run_conformance.py [pytest flags]
            |
            v
 bounded module union: v40 + v41 + v5
            |
            +--> SAFE-01..08 existing modules --------------------+
            |                                                      |
            +--> SAFE-11 exact manifests + no-inline + grounding   |
            |         |                                            |
            |         +--> canonical registry --> real index ------+
            |         +--> DLI manifest/files/index provenance ----+
            |                                                      v
            +--> SAFE-12 independent negative matrix          pytest return code
            |         |                                            |
            |         +--> raw SQLite/vault/snapshot mutations     |
            |         +--> MEC / POLICY / STUDY / NOC screens -----+
            |                                                      |
            +--> real confirmed-vault cross-phase E2E              |
                      |                                             |
                      +--> frozen registry snapshot/fingerprint     |
                      +--> public/private projections + scanners ---+
                                                                    |
                              PASS only if no skips/refusals --------+
```

The runner remains a pure orchestration boundary: list-form `subprocess.run`, `shell=False` by default, explicit repository `cwd`, copied environment, guard variable only on real runs, and exact pytest return-code propagation. [CITED: https://github.com/python/cpython/blob/main/Doc/library/subprocess.rst]

### Recommended Test Structure

```text
crawler/tests/
├── test_conformance_v5_grounding.py       # SAFE-11 exact manifests/surfaces/provenance
├── test_conformance_v5_release_flow.py    # independent negatives + real positive E2E
├── test_conformance_v5_release_gate.py    # runner coverage/marker/prerequisite self-test
├── test_conformance_v5_mec_no_false_meets.py
├── test_conformance_v5_policy_no_job_offer_green.py
├── test_conformance_v5_study_no_false_green.py
└── test_conformance_v5_noc_no_auto_green.py
scripts/
└── run_conformance.py                     # one bounded v4+v5 command
```

### Pattern 1: Bounded Superset Runner

Use two explicit patterns—`test_conformance_v4[01]_*.py` and `test_conformance_v5_*.py`—deduplicate and sort paths, retain `--collect-only`/`--list`, and keep passing unknown options to pytest. Do not use an unbounded `test_conformance_v*.py` pattern because a future unfinished milestone could enter the release gate accidentally.

```python
# Source: existing scripts/run_conformance.py plus official pytest collection docs
_GLOBS = (
    "crawler/tests/test_conformance_v4[01]_*.py",
    "crawler/tests/test_conformance_v5_*.py",
)

def conformance_modules() -> list[Path]:
    return sorted({path for pattern in _GLOBS for path in _REPO_ROOT.glob(pattern)})
```

Explicit path collection and `--collect-only` are supported pytest collection mechanisms. [CITED: https://github.com/pytest-dev/pytest/blob/main/doc/en/example/pythoncollection.rst]

### Pattern 2: Independent Negative with Paired Positive

For each invariant, build the smallest valid raw fixture, prove the valid control reaches the branch, apply one mutation, invoke only the public production entry point, and assert a closed status plus stable reason and no forbidden output. Never derive the expected result by calling the same production helper being tested.

```python
# Source: repository conformance style; illustrative planner pattern
valid = build_raw_registry_row(effective_to=None)
assert run_public_screen(valid).status == EXPECTED_VALID_STATUS

expired = dataclasses.replace(valid, effective_to="2024-12-31")
result = run_public_screen(expired)
assert result.status != "MEETS"
assert result.reason_code == "rule_out_of_window"
```

### Pattern 3: Release-Mode Prerequisite Enforcement

Normal focused/full-suite runs may retain honest local-only skips. When `PR_CONFORMANCE_RUNNER=1`, the v5 release-flow module must turn missing `corpus/index.db`, DLI snapshot/manifest, or required confirmed fixtures into an explicit failing assertion with a stable setup message. This preserves developer portability while preventing a release from passing structurally without the real grounding proof.

### Anti-Patterns to Avoid

- **Importing helper builders from another conformance module:** creates a shared oracle and circular negatives.
- **Only asserting “not green”:** also assert the stable closed reason, zero points/artifacts, and a valid positive control.
- **Mocking the screen under test:** mock only time/network/filesystem seams; call real screen composition.
- **Marker-only or unbounded discovery:** can omit unmarked v5 files or include unfinished future files.
- **Silently skipping release prerequisites:** turns SAFE-11/12 into structural-only claims.
- **Hashing every production file into one brittle monolith:** freeze named contractual surfaces; use behavior/AST checks elsewhere.
- **Requiring a notice inside POLICY’s inert dictionary:** assert framing at actual rendered/public boundaries; POLICY remains a non-rendered internal sidecar. [VERIFIED: codebase grep]

## Authoritative Negative and E2E Matrix

| Case | Independent perturbation | Required assertions |
|------|--------------------------|---------------------|
| Superseded MEC threshold | Clone a real criterion row into an isolated registry with expired `effective_to`; do not call MEC freshness helper to create the expectation. | Positive row can proceed; expired row is out-of-window and program never `MEETS`. |
| Unwired MEC criterion | Remove one exact manifest mapping or inject `wired=False` after proving complete manifest control. | Program is `AT-RISK`, reason identifies unwired criterion, no public/private green. |
| POLICY out-of-window | Build synthetic effective-dated offer rows and an ITA date outside the selected window. | Eligibility sidecar remains manual/`AT-RISK` or `N/A`; CRS guard remains zero. |
| POLICY unconfirmed | Seed a pending/unconfirmed vault offer value directly. | It cannot become an audit-eligible MEC input and cannot award points. |
| STUDY absent snapshot | Point an isolated candidate/config to no DLI family. | Stable PII-free refusal, nonzero CLI code, zero report/database artifacts. |
| STUDY drift/config | Mutate a copied DLI markdown byte, manifest hash, chunk hash/crawl date, then separately inject invalid freshness config. | Each single mutation refuses independently; no report; no stale last-known-good overwrite. |
| NOC unconfirmed | Insert pending duty values through the vault schema/API, preserving candidate/document linkage. | Review remains `AT-RISK`/`GAP`; no inflated confirmed count. |
| NOC superseded | Confirm an old duty SHA, then load a worksheet with changed SHA. | Old confirmation is ineligible and cannot green current review. |
| Registry drift | Create evidence/sidecars from snapshot A, mutate canonical registry JSON to snapshot B, then compose each screen. | `registry_fingerprint` mismatch closes MEC/NOC/POLICY/STUDY composition; completed evidence cannot re-green. |
| Privacy | Use unmistakable canary PII, `ev_...` IDs, and absolute temp paths in private inputs. | None appear in captured stdout/stderr, `PublicAuditEnvelope`, public sidecars, or DLI snapshot/manifest; private report remains under candidate root. |
| Zero network/deps | Parse enrolled import trees; deny `socket.socket` during real E2E; compare exact dependency set and lock hash. | No audit-time network path, alternate loader, dependency addition, or lock drift. |
| Framing | Exercise MEC public summary, STUDY report/notice, and NOC worksheet/public artifact. | Every rendered/public screening artifact says screening/not legal advice/no eligibility determination as appropriate; POLICY is verified through its containing MEC artifact. |
| Frozen contracts | Hash named files and assert exact model/grid fields. | `PublicAuditEnvelope`, CRS guard/math, auditor dispatch/grid, and lock remain unchanged except intentional runner/marker pin rollover. |

### Real Cross-Phase E2E

Use the actual local `corpus/index.db` and DLI snapshot/golden lineage, but create a fresh temporary vault. Seed candidate/document/page records, import values through shipped APIs, and confirm each field using distinct evidence IDs and real file/render hashes. Generate and confirm a NOC worksheet, run STUDY, build POLICY input, run one MEC program, and project through the frozen CRS/public envelope. [VERIFIED: codebase grep]

The positive flow must prove citations resolve, snapshot provenance agrees across file/manifest/index, one immutable registry fingerprint is threaded through all screens, confirmed five-key evidence is consumed, sidecars do not alter CRS totals, and public outputs contain neither canary PII nor evidence IDs nor absolute paths. Then rerun from the same evidence after registry mutation and assert fail-closed drift behavior. [VERIFIED: planning docs]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Test execution | New shell wrapper/process manager | Existing Python runner + pytest | Preserves SAFE-01..08 behavior and return codes. |
| Effective-date/freshness decisions | Test-local duplicate date algorithm | Independent fixture dates plus production screen entry point | The oracle should assert externally visible boundaries, not clone implementation. |
| Registry canonicalization/fingerprint | Alternate JSON/hash scheme | `RegistrySnapshot` public fingerprint behavior | A second canonicalizer becomes another trust path. [VERIFIED: codebase grep] |
| Vault eligibility | Direct “confirmed=True” fake objects for E2E | Shipped vault import/confirm APIs and raw DB only for deliberate negative corruption | Exercises the actual five-key quarantine. [VERIFIED: codebase grep] |
| DLI generation | Live HTTP fixture or mock crawler | Tracked golden DLI family and copied local snapshot/index | Release audit must be offline and reproducible. |
| Privacy scanning | New regex policy | Existing `check_publish_safe` and projection scanners, with independent canaries | Keeps one privacy policy while proving it bites. [VERIFIED: codebase grep] |
| Cryptography | Custom digest | stdlib SHA-256 | Existing provenance/fingerprint surfaces already use standard hashing. [VERIFIED: codebase grep] |

**Key insight:** Phase 46 should compose and challenge the shipped trust path, not introduce a parallel release implementation.

## Create / Modify / Freeze Contract

| Disposition | File/surface | Planning rule |
|-------------|--------------|---------------|
| CREATE | `crawler/tests/test_conformance_v5_grounding.py` | Exact SAFE-11 manifests, source enrollment, real grounding, DLI provenance, positive controls. |
| CREATE | `crawler/tests/test_conformance_v5_release_flow.py` | Independent SAFE-12 negatives and confirmed-vault cross-phase E2E. |
| CREATE | `crawler/tests/test_conformance_v5_release_gate.py` | Assert bounded runner union, required module subset, markers, non-recursion, and release prerequisite behavior. |
| MODIFY | `scripts/run_conformance.py` | Extend bounded discovery/banner/criteria to SAFE-12; preserve CLI, env guard, subprocess, cwd, and return-code semantics. |
| MODIFY | `crawler/tests/test_crs_no_inlined_rules.py` | Enroll `policy_offer.py` and `dli_snapshot.py` in an exact v5 surface without weakening existing controls. |
| MODIFY | `pyproject.toml` | Change only the marker description from v4.x/SAFE-01..08 to v5/SAFE-01..12. |
| MODIFY | `crawler/tests/test_conformance_v5_mec_no_false_meets.py` | Roll only intentional `run_conformance.py` and `pyproject.toml` SHA pins after reviewing diffs. |
| FREEZE | `poetry.lock`, `[project].dependencies` | Byte/set unchanged. [VERIFIED: codebase grep] |
| FREEZE | `crawler/models/audit.py` | Current SHA-256 `642e6f...2159`; exact six `PublicAuditEnvelope` fields unchanged. [VERIFIED: test execution] |
| FREEZE | `crawler/crs_audit.py` | Current SHA-256 `cac704...5ac`; arranged-employment guard/math unchanged. [VERIFIED: test execution] |
| FREEZE | `crawler/auditors/__init__.py` | Current SHA-256 `48305e...e01d`; full CRS dispatch/grid unchanged. [VERIFIED: test execution] |
| FREEZE BY DEFAULT | Production MEC/POLICY/STUDY/NOC/vault/snapshot modules | Do not edit unless a new independent conformance test exposes a release blocker; isolate any such fix in a separately justified task. |

The existing MEC conformance file pins the current runner SHA `b31711...0fe` and `pyproject.toml` SHA `bd105b...9eb`; both expected hashes must be rolled after the two intentional edits, while the lock and frozen contract hashes must not move. [VERIFIED: codebase grep] [VERIFIED: test execution]

## Recommended Plans and Waves

| Wave | Plan | Scope | Depends on |
|------|------|-------|------------|
| 1 | 46-01 SAFE-11 authoritative grounding | Create exact family/surface manifests; extend no-inline enrollment; prove static and dynamic grounding/provenance with non-vacuous controls. | Phases 40–45 |
| 1 | 46-02 SAFE-12 independent invariants | Add raw-fixture stale/superseded/out-of-window/unconfirmed/unwired negatives; privacy, framing, dependency/network, frozen-contract checks. | Phases 40–45 |
| 2 | 46-03 composite E2E | Confirmed-vault MEC/POLICY/STUDY/NOC flow, real index/DLI lineage, fingerprint-drift rerun, release-mode prerequisite enforcement. | 46-01, 46-02 |
| 3 | 46-04 authoritative runner/release | Extend runner, add self-test, update marker prose, roll intentional pins, run focused/baseline/full/release/publish-safe gates. | 46-03 |

## Common Pitfalls and Threat Model

### Pitfall 1: Structural Green with Missing Local Evidence
**What goes wrong:** Real grounding tests skip and the release appears green.
**How to avoid:** Convert prerequisite absence to failure only under the runner guard; show required paths in a PII-free setup message.
**Warning signs:** Release summary contains skips or only structural fixture tests.

### Pitfall 2: Circular Negative Controls
**What goes wrong:** A donor helper and production code share the same incorrect assumption.
**How to avoid:** Build raw fixture bytes/rows independently and pair each mutation with a valid positive control.
**Warning signs:** Phase 46 imports any `test_conformance_v5_*` helper or computes expected status through production freshness/gating helpers.

### Pitfall 3: Runner Recursion or Module Omission
**What goes wrong:** The runner self-test launches itself, or an unmarked/unglobbed module is omitted.
**How to avoid:** Retain `--collect-only` and `PR_CONFORMANCE_RUNNER`; compare a hard required-module subset against bounded discovery and marker parity.
**Warning signs:** Nested pytest processes, marker warnings, or required module absent from collected node IDs.

### Pitfall 4: Vacuous “Never Green”
**What goes wrong:** Every fixture is invalid before reaching the intended branch.
**How to avoid:** Run the paired positive first and assert the exact closed reason after one mutation.
**Warning signs:** Only `status != green` is asserted.

### Pitfall 5: Registry TOCTOU/Fingerprint Drift
**What goes wrong:** Evidence created under registry A is composed under B and re-greens.
**How to avoid:** Hold one immutable snapshot per run, thread its fingerprint everywhere, mutate only between runs, and assert all consumers refuse mismatches.
**Warning signs:** Any screen loads the registry independently or omits fingerprint from its trust input.

### Pitfall 6: PII/Path Leakage Through Diagnostics
**What goes wrong:** A refusal is safe in JSON but leaks through stdout/stderr, exception text, snapshot metadata, or absolute private paths.
**How to avoid:** Capture both streams and every public artifact using unique canaries; scan before publication.
**Warning signs:** `ev_`, candidate names, temp-root prefixes, or platform absolute paths in output.

### Pitfall 7: Audit-Time Network or Supply-Chain Drift
**What goes wrong:** A transitive import reaches refresh/network code or a package changes during the release phase.
**How to avoid:** AST-scan the transitive enrolled screen surface, deny sockets in E2E, assert exact dependencies and lock hash.
**Warning signs:** `dli_snapshot` imported by runtime screen modules, networking imports, changed lock.

### Pitfall 8: Brittle Pin Rollover
**What goes wrong:** Intentional runner/marker edits fail old SHA assertions, or broad rebaselining hides unrelated source changes.
**How to avoid:** Update only the two expected hashes after diff review and rerun frozen-contract tests.
**Warning signs:** Any production hash changes or `poetry.lock` diff.

## Code Examples

### Preserve Exact Pytest Exit Status

```python
# Source: https://github.com/python/cpython/blob/main/Doc/library/subprocess.rst
proc = subprocess.run(
    [sys.executable, "-m", "pytest", *modules, *passthrough],
    cwd=str(repo_root),
    env=env,
)
return proc.returncode
```

### Marker/Collection Parity Without Recursive Execution

```python
# Source: existing v4 release-gate tests and official pytest collection docs
proc = subprocess.run(
    [sys.executable, str(runner), "--collect-only", "-q"],
    cwd=repo_root,
    env={**os.environ, "PR_CONFORMANCE_RUNNER": "1"},
    capture_output=True,
    text=True,
)
assert proc.returncode == 0
for module in REQUIRED_MODULES:
    assert module in proc.stdout
```

## State of the Art

| Old/current approach | Phase 46 approach | Impact |
|----------------------|-------------------|--------|
| v4.0/v4.1 bounded glob, SAFE-01..08 | Bounded union of v4.0/v4.1 and v5, SAFE-01..12 | One command preserves prior coverage and adds final milestone proof. |
| Focused v5 modules run manually | Focused modules plus authoritative grounding/E2E/self-test in runner | SAFE-12 becomes release-enforced. |
| Static whole-registry proof with broad coverage report | Exact v5 family manifests plus whole-registry proof | A family omission cannot hide behind aggregate counts. |
| Local-only grounding skips | Honest skips normally, mandatory prerequisites in release mode | Portable development without structurally green releases. |
| Focused fingerprint mismatch checks | Composite post-success drift rerun | Proves new rows cannot re-green completed evidence. |

**Deprecated/outdated:** the `pyproject.toml` marker description currently says “v4.x ... SAFE-01..08”; it must be updated as part of the runner extension. [VERIFIED: codebase grep]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python virtualenv | All tests | ✓ | Python 3.10.12 | None needed. [VERIFIED: environment probe] |
| pytest | Release/full suites | ✓ | 9.0.3 | None needed. [VERIFIED: environment probe] |
| SQLite/FTS | Corpus/index and fixtures | ✓ | SQLite 3.37.2 | No release fallback. [VERIFIED: environment probe] |
| `corpus/index.db` | Real grounding/E2E | ✓, git-ignored | local file | Release blocks if absent. [VERIFIED: environment probe] |
| Tracked DLI golden family | Provenance/regeneration | ✓ | 5 markdown documents + manifest | No fallback; tracked fixtures are canonical test lineage. [VERIFIED: codebase grep] |
| Poetry | Lock/dependency inspection | ✓ | 2.2.1 | Parse TOML/lock directly if command is unnecessary. [VERIFIED: environment probe] |
| uv | Optional project execution | ✓ | 0.10.7 | Use `.venv/bin/python`; runner must not require uv. [VERIFIED: environment probe] |

**Missing dependencies with no fallback:** none in the researched environment. [VERIFIED: environment probe]

**Missing dependencies with fallback:** optional `crawl4ai` is absent; it is not required by Phase 46 or audit-time screens, and one unrelated deep-crawl contract test skips. [VERIFIED: test execution]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 collecting stdlib `unittest` suites [VERIFIED: environment probe] |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` [VERIFIED: codebase grep] |
| Per-task quick run | `.venv/bin/python -m pytest <changed-test-module> -q -x` |
| Existing SAFE baseline | `.venv/bin/python scripts/run_conformance.py -q` |
| Existing v5 baseline | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_*.py -q` |
| Full suite | `.venv/bin/python -m pytest crawler/tests scripts/tests -q` |
| Final authoritative release | `.venv/bin/python scripts/run_conformance.py -q` after runner extension |
| Publication safety | `.venv/bin/python -m pytest scripts/tests/test_check_publish_safe.py -q` and the repository’s `check_publish_safe` invocation |

### Measured Baselines

| Command | Result | Pytest elapsed | Wall/max RSS |
|---------|--------|----------------|--------------|
| Current SAFE-01..08 runner | 82 passed, 224 subtests, exit 0 | 150.26 s | 143.50 s [VERIFIED: test execution] |
| Current four v5 modules | 66 passed, 494 subtests, exit 0 | 219.44 s | 209.11 s [VERIFIED: test execution] |
| Full `crawler/tests scripts/tests` suite | 1408 passed, 2 skipped, 1793 subtests, exit 0 | 1909.99 s | 1805.50 s; 149,068 KB max RSS [VERIFIED: test execution] |

The measured sequential SAFE plus current-v5 baseline is 352.61 wall seconds (about 5m53s). No project performance SLA exists, so planning should record regressions relative to these baselines rather than invent a hard threshold. [VERIFIED: test execution] [VERIFIED: planning docs]

### Known Full-Suite Skips

1. The live IRCC DLI endpoint contract is skipped unless `PR_LIVE_DLI=1`; release conformance must remain offline and must not enable it. [VERIFIED: codebase grep]
2. The optional deep-crawl import test skips when `crawl4ai` is absent; Phase 46 must not install it. [VERIFIED: codebase grep] [VERIFIED: test execution]

The final release run should have zero skipped Phase 46 prerequisites even though the unrelated full suite retains those two known skips. [VERIFIED: test execution]

### Phase Requirements → Test Map

| Req ID | Behavior | Test type | Automated command | File exists? |
|--------|----------|-----------|-------------------|--------------|
| SAFE-11 | Exact MEC/POLICY/STUDY/DLI manifests, no-inline surface, static grounding, dynamic provenance | integration/static | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_grounding.py -q -x` | ❌ Wave 0 |
| SAFE-12 | Independent never-green/privacy/framing/frozen/network matrix | integration | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_release_flow.py -q -x` | ❌ Wave 0 |
| SAFE-12 | One runner collects SAFE-01..12 without recursion | integration | `.venv/bin/python -m pytest crawler/tests/test_conformance_v5_release_gate.py -q -x` | ❌ Wave 0 |
| SAFE-01..08 regression | Existing gate remains green after superset extension | regression | `.venv/bin/python -m pytest crawler/tests/test_conformance_v40_release_gate.py crawler/tests/test_conformance_v41_release_gate.py -q -x` | ✅ |

### Sampling Rate

- **Per task commit:** changed module with `-q -x`, then existing affected focused v5 module.
- **Per wave merge:** current runner plus all `test_conformance_v5_*.py`.
- **Phase gate:** final extended runner, full suite, and publish-safe checks all green; no Phase 46 prerequisite skip.

### Wave 0 Gaps

- [ ] `crawler/tests/test_conformance_v5_grounding.py` — SAFE-11.
- [ ] `crawler/tests/test_conformance_v5_release_flow.py` — SAFE-12 independent E2E/negatives.
- [ ] `crawler/tests/test_conformance_v5_release_gate.py` — authoritative runner self-test.
- [ ] Release-mode prerequisite fixture/seam inside the new modules; no new shared production helper.

## Security Domain

Security enforcement is enabled at ASVS Level 1. [VERIFIED: planning config]

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | No | Local CLI has no authentication boundary in this phase. [VERIFIED: codebase grep] |
| V3 Session Management | No | No web/session state. [VERIFIED: codebase grep] |
| V4 Access Control | Yes | Candidate-root path confinement, vault-only PII, read-only corpus/index access. [VERIFIED: codebase grep] |
| V5 Input Validation | Yes | Pydantic closed models, typed registry rows, stable reason codes, canonical path/hash/date validation. [VERIFIED: codebase grep] |
| V6 Cryptography | Yes | stdlib SHA-256 for content, manifest, evidence, and registry integrity; never hand-roll crypto. [VERIFIED: codebase grep] |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Registry/snapshot tampering or TOCTOU | Tampering | Immutable per-run snapshot, canonical fingerprint, provenance/hash checks, post-success drift negative. |
| PII/evidence/path disclosure | Information disclosure | Closed public models, canary scans over both streams and artifacts, private-root confinement. |
| Missing prerequisite represented as pass | Repudiation | Release-mode hard failure and explicit zero-skip assertion. |
| Network import/live lookup | Information disclosure / tampering | AST closure audit, socket denial, pinned local data. |
| Dependency/lock drift | Tampering | Exact dependency set and lock hash; no installs. |
| Circular fixture/oracle | Spoofing | Independent raw builders and paired positive controls. |
| Runner recursion/resource exhaustion | Denial of service | Guard environment and collect-only self-test. |

## Open Questions — RESOLVED

| Question | Resolution |
|----------|------------|
| What is the one release command? | `.venv/bin/python scripts/run_conformance.py`; extend the existing command rather than add another. |
| How should v5 be selected? | Bounded union of v4.0/v4.1 and `test_conformance_v5_*.py`, sorted/deduplicated; marker parity asserted separately. |
| Should absent local corpus/snapshot skip? | In normal suites, existing honest skips may remain; under the authoritative runner, missing release prerequisites fail. |
| Must POLICY itself render a notice? | No. It is an inert internal dictionary; prove framing on its rendered MEC/public boundary and prove POLICY fields remain manual/non-green. [VERIFIED: codebase grep] |
| Should existing donor helpers be reused? | No for Phase 46 load-bearing negatives; construct independent raw fixtures and call only production entry points. |
| May production modules change? | Default no. Change only tests/runner/marker/enrollment; isolate any independently discovered release blocker before touching production. |
| Is a new dependency or performance SLA needed? | No. Install nothing; use measured baselines and report regressions. |
| Which frozen hashes may move? | Only runner and `pyproject.toml` expected pins after intentional edits; lock, envelope, CRS, and grid surfaces remain fixed. |

No unresolved planning questions remain.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | None. All repository/environment claims were checked in this research session. | — | — |

## Sources

### Primary (HIGH confidence)

- `.planning/ROADMAP.md`, `.planning/REQUIREMENTS.md`, `.planning/PROJECT.md`, `.planning/STATE.md` — Phase scope, success criteria, standing constraints. [VERIFIED: planning docs]
- Phase 40–45 `*-VERIFICATION.md` and `*-REVIEW.md` files — completion evidence, carried observations, prior commands. [VERIFIED: planning docs]
- `scripts/run_conformance.py`, `pyproject.toml`, `crawler/crs_rules.py`, screen modules, and all v4/v5 conformance modules — current implementation and gaps. [VERIFIED: codebase grep]
- Local pytest runs and environment/hash probes — counts, versions, timing, memory, exact manifests, hashes. [VERIFIED: test execution]
- CPython subprocess documentation — invocation and return-code semantics. [CITED: https://github.com/python/cpython/blob/main/Doc/library/subprocess.rst]
- pytest collection and marker documentation — explicit collection, `--collect-only`, markers. [CITED: https://github.com/pytest-dev/pytest/blob/main/doc/en/example/pythoncollection.rst] [CITED: https://github.com/pytest-dev/pytest/blob/main/doc/en/example/markers.rst]

### Secondary (MEDIUM confidence)

- None.

### Tertiary (LOW confidence)

- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — existing project/runtime inspected; no package addition.
- Architecture: HIGH — based on production entry points, runner, registry, and focused conformance.
- Pitfalls/threats: HIGH — derived from observed skip guards, helper reuse, hash pins, trust boundaries, and prior phase reviews.
- Performance: HIGH for this machine/session — commands were executed and measured; timings are not a cross-machine SLA.

**Research date:** 2026-07-20
**Valid until:** 2026-08-19, or immediately stale if Phase 40–45 production/conformance surfaces change.
