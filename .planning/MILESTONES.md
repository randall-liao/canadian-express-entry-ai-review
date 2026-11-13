# Milestones

## v12.0 Per-Document Autonomous Research, Synthetic Generation & Blind Self-Improvement Pipeline (Shipped: 2026-07-27)

**Phases completed:** 4 phases, 16 plans, 8 tasks

**Key accomplishments:**

- Truthful Gemini 3.6 Flash research agent runner with Pydantic schema enforcement, fail-closed error recording, portable Copilot CLI discovery, per-document staging isolation, and local corpus grounding gate.
- Bounded concurrent 23-agent research orchestrator with ThreadPoolExecutor, dual artifact generation (`research.json` & `research_summary.md`), truthful SHA256 execution provenance recording, and 23-pipeline conformance test suite.
- 1. [Rule 1 - Bug] Extended tool call extraction for Copilot CLI 1.0.73 JSONL events
- Delivered Pydantic v2 schemas (`GenerationSpec`, `DefectSpec`, `TestCaseSpec`, `PrivateCaseRecord`), automated side-channel leakage scanner (`scan_blind_artifact_leakage`), worker staging API (`stage_case_for_worker`), and refactored live Copilot CLI Gemini 3.6 Flash generator runner (`run_document_generator_agent`) with test double support.
- 1. [Rule 2 - Security] Closed T-73-12 Rasterization DoS bounds threat mitigation
- Delivered the multi-pipeline synthetic dataset generator coordinator (`crawler/eval/doc_synthetic_generator.py`), thread-safe PDFium rasterization/scanning, and comprehensive pipeline conformance test suite (`crawler/tests/test_doc_synthetic_conformance.py`).
- Executed the real 23-agent Gemini 3.6 Flash long-context synthetic document generation pass across all Express Entry document pipelines via GitHub Copilot CLI, generating 118 logical case specifications and 236 leak-free vector and 300 DPI scanned PDF fixtures, and passed the live 236-PDF release gate 100% green.
- 1. [Rule 1 - Bug] Corrected SDK attachment wire keys

---

## v5.0 Grounded Eligibility & Policy Edge-Case Screening (Shipped: 2026-07-21)

**Phases completed:** 7 phases, 29 plans, 57 tasks

**Key accomplishments:**

- Shared freshness, effectivity, snapshot preflight, and one reusable grounding gate now fail closed across every v5.0 screen.
- A refreshable, pinned authoritative DLI/PGWP corpus family grounds Canadian-study review without audit-time network access.
- Legacy and physician arranged-employment paths are grounded and manual-only, while program-eligibility offers remain distinct from frozen CRS points.
- Cited NOC duties and Canadian-study evidence use vault-only, confirm-first sidecars that never auto-green semantic judgments.
- A separate FSW/FST/CEC MEC screen evaluates grounded criteria from confirmed evidence without mutating CRS totals or the public audit envelope.
- The authoritative SAFE-01..12 command proves all screens, privacy, drift, supply-chain, framing, frozen contracts, and confirmed-vault E2E: 209/209 tests pass.

**Milestone gate:** 18/18 requirements, 7/7 phases, 8/8 integration bridges, and 7/7 E2E flows complete. Audit accepted four non-blocking maintenance/metadata items as tech debt.

---

## v4.1 CRS Auditor Hardening & Remediation (Shipped: 2026-07-17)

**Phases completed:** 5 phases (35–39), 17 plans

**Key accomplishments:**

- **Coverage completion (Phase 35, COV-01..04):** grounded first-official-language points for every conversion-emitted CLB benchmark {3–8,10} in both spouse/no-spouse modes (six verbatim `#006` citations, zero fabricated values); an additive `points_unresolved` flag + PII-light `counts["unpriced"]` tally + `UNRESOLVED (unpriced)` report line surface any unpriced `SUBSTANTIATED` factor without inflating the total; and a `sibling_proof` import→extract→confirm chain (one shared `siblingfields` vocabulary, anti-drift pinned) drives a reachable fail-closed `decide_sibling` that substantiates only a confirmed brother/sister + citizen/PR + Canadian-residence + adult (grounded 18+ threshold `#018`) chain — a minor is AT-RISK `sibling_minor`, never green.
- **Operational hardening (Phase 36, HARD-01..04):** a typed read-only `crawler/index_health.py` preflight turns a missing/empty/unreadable/corrupt/content-drifted corpus index into a stable PII-free `invalid_input`/exit-2 refusal with a specific `reason=<code>` + index/doctor recovery hint, refusing *before* any vault write (zero artifacts); the shipped `personal.example` profile is re-keyed to canonical dotted grid ids + anti-drift pinned (applicable non-N/A verdicts); and adversarial rotated/low-text/password-protected/ambiguous-date fixtures are proven quarantined through the real import→extract→confirm→audit seam.
- **Grounded remediation checklist (Phase 37, REM-01..04):** `crawler/remediation.py` + a `vault remediate` verb project a completed `PrivateAuditReport` into a private, corpus-cited fix checklist — exactly one actionable item per `GAP`/`AT-RISK`/unpriced finding (factor, verdict/reason, score impact, grounded citation + verbatim rule span, deterministic action) — as a *pure, deterministic projection* that reuses grounded verdicts/citations, fails closed on registry drift (a stamped `registry_fingerprint` gate), never re-grounds/re-scores (AST + call-level proof: no `searchindex`/`grounding` import), and stays vault-only with a PII-light summary + screening notice.
- **Redacted professional review packet (Phase 38, PKT-01..05):** `crawler/review_packet.py` + a `vault review-packet` verb produce an opt-in, explicitly-redacted lawyer/RCIC packet — a closed-allowlist projection that structurally cannot carry raw applicant values / absolute paths / `ev_` ids, with a `--dry-run` manifest preview, raw documents excluded by default (explicit per-document vault-only opt-in), a render-then-scan double gate that refuses any leak before write, vault-only writes via `resolve_within`, and prominent screening-not-legal-advice framing.
- **SAFE conformance & release consolidation (Phase 39, SAFE-05..08):** an authoritative `test_conformance_v41_*` layer (coverage/no-false-green, remediation/packet privacy, grounding/determinism/screening) consolidated behind ONE extended release-gate command (`scripts/run_conformance.py`, glob `test_conformance_v4[01]_*.py`) that proves the complete v4.x flow — **PASS SAFE-01..08** across 9 modules.

**Milestone gate:** 851 tests pass / 1 skipped / 355 subtests; publish-safe 0 violations; single release gate PASS SAFE-01..08; cross-phase integration INTEGRATED (audit→remediation→packet E2E). Zero new runtime dependencies; no second trust path; v4.1 closed all of v4.0's recorded tech debt.

---

## v4.0 CRS Profile ↔ Document Substantiation Auditor (Shipped: 2026-07-06)

**Phases completed:** 6 phases, 30 plans, 62 tasks

**Key accomplishments:**

- Single shared personal-path resolver (`crawler/paths.py`) with a resolve-then-contain guard that rejects `..`/symlink escapes, plus pydantic 2.13.4 + platformdirs 4.10.0 admitted behind an (auto-approved) supply-chain gate — all while keeping the frozen v3.x ground/checklist write-gate byte-identical.
- Private per-candidate `vault.sqlite` (schema + user_version migrations) that stores the CRS factor breakdown and ITA round/cutoff and ingests raw documents as content-addressed `files/raw/<sha256>` files with minted `ev_` evidence ids — provably disjoint from corpus `relpath#ordinal` citation ids, with PII kept in the DB and PII-light summaries for later stdout.
- Additive `corpus-crawler vault` subcommand (init / profile set·show / ita set / import / list) that drives the private vault through the frozen five-key JSON envelope, with every `--json` result proven PII-light — original filenames, absolute paths, and claimed point values never cross the stdout boundary.
- Extends publish-safe + `.gitignore` to flag every vault artifact type (SQLite DB + WAL/SHM sidecars, the `candidates/` tree, rendered/OCR/report files) and ships an SC3+SC4 conformance suite proving a candidate `evidence_id` is never citable as authority and vault artifacts can neither be staged nor written outside the vault.
- Schema-v2 vault migration + fail-closed trust logic (`is_audit_eligible`/`is_stale`) so automated extraction is born quarantined as `pending` and five-key staleness invalidates any confirmation on change — proven with 39 synthetic-row tests, no extraction deps required.
- Local-only render+read extraction engine (pypdfium2 + pdfminer.six + Pillow, optional pytesseract) that turns vault documents into `pending`-only EXTRACT-01 fields, flags scanned/rotated/low-text/ambiguous quality instead of failing silently, and writes all rendered images/OCR text into the vault only — proven with 11 synthetic-fixture tests.
- Field-level `vault extract`/`fields`/`confirm` CLI verbs that let the applicant review each extracted field's raw value, normalized value, source page/crop, affected CRS factor, and profile claim on the local terminal — while the `--json` machine envelope stays PII-light — and that surface the Plan-01 audit-eligibility gate + staleness so nothing pending/rejected/low-quality/ambiguous/stale can look green. 16 e2e tests prove SC1-SC4.
- A top-level `doctor` preflight that reports the required/optional extraction dependencies + per-document scan-quality flags (missing required dep → `missing_dependency`/exit 3, never a silent crash), publish-safe coverage of the new rendered-image/OCR-text artifacts, and a milestone SC1–SC5 conformance gate with adversarial fixtures proving no pending/low-quality/ambiguous/stale value is ever audit-eligible and no extraction PII reaches stdout.
- Closed the two milestone INTEGRATION blockers so the real CLI now produces a SUBSTANTIATED `core.language.first` (with a non-zero substantiated total that flows into the ITA cutoff) for a qualified applicant — by centralizing the test_type vocabulary against the registry, making per-document factor linkage deterministic and fail-closed, adding passport→core.age DOB extraction, and locking it all with a real extract→confirm→audit E2E regression + anti-drift gate. The frozen auditor/registry/PII perimeter is byte-for-byte untouched.
- PII-free typed CRS rule-row schema + a registry engine that validates every row through the SHIPPED grounding gate, reproduces cited chunks (retrieve-what-you-cite), reports full-grid coverage, and statically rejects inlined volatile thresholds — all proven corpus-less in CI.
- 17 corpus-grounded CRS rule rows for factor groups A (core human capital) and B (spouse/common-law) — every row resolves + verbatim-grounds through the shipped gate and passes retrieve-what-you-cite against the REAL corpus, with CLB/NCLC conversion sourced from the equivalency chart.
- 14 corpus-grounded rule rows for factor groups C (skill transferability, incl. grounded 50/50/100 caps) and D (additional points, incl. the 2025-03-25 arranged-employment repeal and a distinct grounded ITA-era legacy row) — completing the full CRS grid with zero coverage gaps.
- Pure, tested CRS math (`crawler/crs_audit.py`) — CLB/NCLC conversion, date math, work-duration aggregation, spouse-mode scoring, 50/50/100 transferability cap clamping, cutoff comparison, and the fail-closed arranged-employment guard — every threshold read from a grounded rule row, with the module itself passing the no-inlined-volatile-rule gate.
- The whole PII-free CRS registry validates as one unit against the REAL corpus — 31 rows, zero grounding violations, retrieve-what-you-cite agreement across all four groups, a COMPLETE 23-label coverage grid (0 gaps) published as a drift-guarded COVERAGE.md, and an aggregate no-inlined-volatile-rule gate proven non-vacuous.
- Typed two-tier audit contract making the PII boundary a structural pydantic guarantee: a closed four-value verdict vocabulary, a PII-light public envelope that cannot carry applicant values or `ev_` pointers, a vault-only PII-bearing report, and a single tested down-projection seam.
- Additive schema-v3 migration giving the auditor a durable, vault-only audit trail: an `audit_runs` table (one row per `vault audit`) and a `factor_verdicts` table (one row per verdict) that keep `ev_` evidence pointers and corpus `relpath#ordinal` citations in strictly separate columns.
- The heart of the vertical slice: `audit_factor` runs the complete first-official-language substantiation loop — grounding gate → eligibility quarantine → deterministic benchmark math → verdict — and returns a `PrivateAuditReport`, where `SUBSTANTIATED` is impossible without proof + eligibility + threshold + a grounded/cited rule, and any ungrounded rule refuses the whole output.
- `run_audit` turns an in-memory verdict into durable, vault-only output — fail-closed: it computes the verdict first so an `AuditGroundingError` leaves zero artifacts, then writes the evidence-bearing JSON+MD report only under `candidates/<id>/output/crs-audit/`, persists the `audit_runs`+`factor_verdicts` trail, and returns a PII-light public envelope with a vault-relative path.
- The operator surface that slams the PII door: an additive `vault audit` verb that runs the first-official-language slice and emits ONE PII-light envelope (run id, verdicts, counts, corpus-cited claims, vault-relative report path) — with the full evidence-bearing report quarantined to the vault, grounded GAP/AT-RISK as `ok:true`, and a grounding failure as `ok:false` + exit 2 writing no report.
- Generalized the Phase-32 single-factor audit slice into a factor→decider dispatch spine that fans one proven verdict contract across the whole CRS grid, landed the core human-capital module on top of it, and rolled SUBSTANTIATED points into a substantiated-total-vs-ITA-cutoff comparison surfaced by `vault audit --all`.
- Completed the grounded CLB/NCLC conversion tables for all five accepted language tests across all four abilities — verbatim-grounded from the real corpus — so `to_clb` resolves every band and language `SUBSTANTIATED` is reachable (closing the Phase-32 known item).
- Replaced the Wave-1 spouse stub with the real spouse/common-law module — spouse-mode gating on an explicit profile signal, spouse-table scoring with the grounded section cap, and structural ownership separation so a principal-owned value can never substantiate a spouse factor (SC5).
- Replaced the Wave-1 transferability stub with the real module — five combination deciders that recombine already-substantiated core cards, block on any unproven component (GAP/AT-RISK, never points), and clamp their contribution to the grounded 50/50/100 caps across combinations (SC5).
- Replaced the Wave-1 additional-points stub with the real module — the arranged-employment job-offer factor never auto-greens (delegates to the shipped RULE-05 guard), nomination awards its grounded maximum only when verified and non-expired, and strong French reuses the grounded NCLC conversion path.
- Proved the whole phase goal end-to-end: a full claimed profile audits through the four modules over the real registry/corpus, every grid factor gets exactly one verdict, language reaches SUBSTANTIATED, the substantiated total is compared to the ITA cutoff without legal advice, SC5 conflicts surface at the factor level, and the full-grid public envelope leaks no PII.
- `crs_audit.score_factor` now selects the grounded `with_spouse`/`without_spouse` column by label for core factors in BOTH modes — spouse-mode core language cards populate `substantiated_points=116` / `score_delta=8` and are counted in the substantiated total, while the `factor_ids[0]` ownership guard, cap clamp, and no-inlined-literal gate are preserved.
- Authoritative full-grid x blocking-evidence-state matrix proving no pending/unconfirmed/low-confidence/stale value can ever green any of the 18 CRS grid factors across all four modules, driving the real vault.is_audit_eligible choke point through the auditor spine.
- Authoritative end-to-end privacy proof that no applicant value or ev_ evidence id reaches stdout / the public envelope across the whole import→confirm→full-grid-audit→report flow, the PII-bearing report stays vault-only, non-vault output is refused, and the tracked tree scans publish-safe.
- Authoritative proof that every registry rule grounds the intended current rule against the real corpus, plus non-vacuous wrong-family / historical-superseded / adjacent-marker negative controls proving the source-family allow/deny + marker selection discipline actually bites.
- Frames the CRS auditor output as substantiation screening (not legal advice) in the report wording and release docs with a narrow SUBSTANTIATED definition and AT-RISK scope, and locks the milestone release gate behind one authoritative command that collects and passes all four SAFE conformance modules.

---

## v3.1 Express Entry Document-Agent Expansion (Shipped: 2026-06-24)

**Phases completed:** 1 phase (28), 1/1 requirement (CHK-04)

**Key accomplishments:**

- Grew the portable, CLI-agnostic document-agent pack from 6 to **22 agents**, adding a grounded review agent for every remaining mandatory / mandatory-if-applicable Express Entry e-APR document type plus the cross-cutting translation requirement: passport, digital photos, translation, job offer, proof of studies, certificate of qualification, birth certificate, marriage certificate, common-law union, divorce certificate, death certificate, adoption certificate, use-of-representative form, relative in Canada, other name, and authority-to-release form.
- Each new agent replicates the Phase-27 employment-letter pattern: a baked 2–4 token query plus a `contains_marker` selection rule (resolve hits in BM25 order, take the first whose text contains a non-volatile requirement phrase) that lands the document's requirements chunk in the canonical IRCC completeness-check PDI — never `hits[0]` blindly.
- No new trust-path code: the agents are thin authors over the frozen Phase 24/25 `corpus-crawler --json search`/`ground` primitives, emitting the same five-key answer object with generic labels in `claims[]` and all PII confined to `basis[]`.
- Grounding-by-construction proven end-to-end: every `(query, marker, quote)` triple was verified against the live `corpus/index.db`; the conformance harness's retrieve-what-you-cite proof now covers all 22 agents (19 tests + 22 subtests green), `run_eval` grounds all 24 fixture lines clean, rendered bytes are publish-safe, and the static gates (no inlined chunk-id/year/amount/duration, no bare-python, contract-linked) pass.

Archive: [milestones/v3.1-ROADMAP.md](milestones/v3.1-ROADMAP.md) · [milestones/v3.1-REQUIREMENTS.md](milestones/v3.1-REQUIREMENTS.md) · Audit: [v3.1-MILESTONE-AUDIT.md](v3.1-MILESTONE-AUDIT.md)

---

## v3.0 Grounded Answer Layer (Shipped: 2026-06-21)

**Phases completed:** 5 phases, 17 plans, 39 tasks

**Key accomplishments:**

- Dependency-free `crawler/searchindex.py` foundation: the fail-loud FTS5 availability probe and the pure deterministic heading-aware chunker, plus the FTS5/`chunks` external-content DDL constants — the two "no in-repo analog" pieces every later Phase 23 plan stands on.
- `build_index(corpus, db)` turns the clean 742-doc corpus into the citable `chunks` table + external-content `chunks_fts` index — minting the stable content-coordinate `chunk_id = relpath#ordinal`, stamping every chunk with its five citation fields (source_url read verbatim), and resyncing FTS with a single `'rebuild'`; re-running yields byte-identical ids. This is the heart of RET-01.
- Wires the FTS5 index builder into `corpus-crawler` as a thin `index` verb — `corpus-crawler --json index corpus/ --db corpus/index.db` emits exactly one `ok:true command:"index"` envelope (742 docs / 7935 chunks) — and documents it additively (new `command` + `result` shape, schema_version still `1.0`), proven end-to-end over the real 742-doc corpus behind a `skipUnless` guard. This completes RET-01 (the retrieval index is now a first-class, contracted CLI command).
- Adversarial-query-safe `_to_match()` FTS5 escaper plus a read-only `search()` BM25 query that returns BM25-ranked, citable `{query, db, count, hits}` hits (stable `relpath#NNN` chunk_id + five citation fields + ⟦⟧ snippet highlight) over the already-built Phase-23 index.
- Read-only `resolve(db, chunk_id)` that resolves a stable citation id back to its EXACT verbatim `chunks.text` (the quotable span the grounding gate grounds on) plus the five PII-free citation fields — failing closed to `None` (never raising) for an unknown id AND for a content-drifted row whose stored text no longer hashes to its `chunk_sha`.
- Wired the Plan-01 `search()` + Plan-02 `resolve()` read-side compute into the `corpus-crawler` CLI as a thin `search` verb with a `--cite <id>` resolve mode, documented it additively (no contract break), and proved the whole stack end-to-end over the real 742-doc index — completing RET-02 (SC1 the `--json search` envelope, SC2 the `--cite` resolver, SC3 empty-query→INVALID_INPUT at the boundary, SC4 the additive-contract promise).
- Pure-stdlib fail-closed grounding core (`crawler/grounding.py`) that resolves every claim citation in-process via `searchindex.resolve` and verifies the verbatim quote is a whitespace/case-normalized substring of a resolving chunk — any uncited/unresolvable/quote-mismatch claim fails the whole answer (GND-01/GND-02).
- The producer-facing `corpus-crawler --json ground` verb: a thin `_cmd_ground` dispatcher that reads one structured answer JSON from stdin, runs the Wave-1 `grounding.check_answer` compute, and maps the outcome to the frozen five-key contract — a grounding `verdict:"fail"` is an expected `ok:true`/exit-1 (render nothing), a fully-grounded answer is rendered → RPT-03 publish-safety-scanned → written ONLY to git-ignored `personal/output/` (exit 0), a scan hit refuses with `ok:false`/`internal_error`/exit 4, and bad input is `invalid_input`/exit 2 — documented additively in CONTRACT.md/contract.py without bumping `schema_version` or touching the exit-code taxonomy.
- The grounding gate doubles as the regression eval harness: `grounding.run_eval` runs the SAME fail-closed `check_answer` per-claim gate over every stored answer line in a tracked, PII-free `crawler/eval/questions.jsonl` reference set and aggregates the locked `eval_runner` `{total, passed, failed, failures}` shape (exit 1 if any line is ungrounded); `corpus-crawler --json ground --db <db> --eval <file>` wires it in before any stdin read, an adversarial `must_abstain` line carrying claims is a `should_have_abstained` failure, and the fixture's 2 grounded lines resolve with verbatim quotes against the real 742-doc index while a non-skipped PII self-scan keeps the committed fixture share-safe (GND-02, SC4).
- `crawler/checklist.py` loader (`$PR_PERSONAL_DIR` + safe-YAML `load_profile`) plus pure `applicable_items()` that selects the Layer-1 document set from a synthetic Express Entry profile, with PII isolated to each item's `basis` by construction.
- `grounded_claim` retrieves a GENERIC corpus chunk for each applicable item (short verified query → relpath backstop that refuses per-country police pages → resolve → verbatim quote), and `build_answer` assembles the Phase-25 answer object — PII confined to `basis[]`, every claim cited + verbatim-grounded — then runs it THROUGH `grounding.check_answer`, demoting anything ungroundable to an explicit abstention.
- None — plan executed exactly as written.
- A single CLI-agnostic `_contract.md` defining the 5-key answer object, the search→verbatim-quote→ground→abstain loop, the three fail-closed reasons, the PII-tier split, and the no-inlined-values rule — plus an additive skill-pack README pointing at all six agents — with zero new trust-path code.
- Three thin, plain-Markdown CLI-agnostic document agents that bake a short corpus-crawler search query, copy a verbatim generic quote, and ground it — with the police agent enforcing the residence-history no-leak backstop (--family guidance + per-country relpath skip + abstention).
- Two thin, plain-Markdown CLI-agnostic document agents that bake a short corpus-crawler search query, copy a verbatim generic quote, and ground it — proving volatile-value containment: proof-of-funds inlines no dollar figure (amount/program stay in basis[]), and medical reproduces the volatile IME-exemption date ONLY as a corpus-quoted span, never as prose.
- The headline sixth CLI-agnostic document agent: a thin plain-Markdown skill that bakes the short query `reference letter company letterhead` to land the Express Entry proof-of-work-experience reference-letter chunk, then copies a SEPARATE verbatim quote for each required element (letterhead, applicant name, company contact, signatory/signature, positions held, and the job-title/duties/status/dates/hours/salary details) into one generic PII-free claim per element — grounding the assembled 4-claim answer to verdict:"pass" (4/4) live, with a do-not-confuse guard against the arranged-employment job-offer letter and a per-element abstention rule.
- Ships the per-CLI conformance proof for the six CLI-agnostic document agents: a tracked, PII-free fixture (`crawler/eval/document_agents.jsonl`, 8 lines — one example answer per agent incl. the employment letter's four #019 element claims, plus an adversarial confabulation line and a must_abstain line) GENERATED by slicing verbatim spans (curly apostrophes and all) straight from the live corpus, and a stdlib-unittest harness (`crawler/tests/test_document_agents.py`, 16 tests) that feeds every example answer through the SHIPPED Phase-25 gate (`run_eval` → failed==0) — the same gate `corpus-crawler --json ground --eval` runs, so the fixture passing IS the per-CLI conformance proof — while locking fail-closed-on-confabulation (`quote_not_in_chunk`), zero-claim abstention, the police no-leak backstop, publish-safe rendered bytes, and a static grep gate over the six skills (no front-matter / no chunk_id / no inlined volatile value / no bare-python / each links `_contract.md`).

---

## v2.2 Corpus Duplicate Audit & Cleanup (Shipped: 2026-06-11)

**Phases completed:** 2 phases (20-21) + a tech-debt cleanup (Phase 22, quick task `260620-t6k`)

**Key accomplishments:**

- Cross-family exact + near-duplicate detection across all 16 families (`dupaudit`) with deterministic canonical selection and a shareable, PII-safe audit report.
- A fail-closed cleanup tool (`dupclean`) moved non-canonical copies into per-family `_dropped/`, leaving exactly one canonical copy per cluster with QC/completeness integrity intact (corpus 752→742 live docs, deletions kept local).
- Phase 22 tech-debt cleanup: removed dead `normalize_url` import / unused `--out` arg, added a `dupclean` fail-closed publish-safety self-gate (RPT-03 mirror), corrected the stale 752→742 real-corpus assertion, and added an empty-family robustness regression.

Archive: [milestones/v2.2-ROADMAP.md](milestones/v2.2-ROADMAP.md) · [milestones/v2.2-REQUIREMENTS.md](milestones/v2.2-REQUIREMENTS.md) · Audit: [v2.2-MILESTONE-AUDIT.md](v2.2-MILESTONE-AUDIT.md)

---

## v2.1 Authoritative Corpus Ingestion (Shipped: 2026-06-11)

**Phases completed:** 2 phases, 0 plans, 0 tasks

**Key accomplishments:**

- All relevant authoritative source families crawled into `corpus/` via the
- Every crawled document was QC-evaluated and enforced, drop verdicts applied,

---

## v2.0 Shareable Crawler (Shipped: 2026-06-10)

**Phases completed:** 5 phases, 0 plans, 26 tasks

**Key accomplishments:**

- Frozen byte-level parity baseline of the current engine plus a YAML-driven SiteProfile loader with fail-fast validation and crawl4ai-free pure functions (clean_markdown/is_excluded/normalize_url) that reproduce the baseline exactly.
- The built-in IRCC/canada.ca profile reproduces the current engine BYTE-FOR-BYTE — identical cleaned markdown, normalized URLs, exclusion decisions, and recorded/skipped-stub/skipped-scope/skipped-dup counts vs the frozen golden baseline — proven offline via a pure crawl4ai-free classifier, plus a documented copyable template profile.
- The site logic physically left the engine: deepcrawl.py and config.py now read every IRCC-specific rule from the loaded profile, with `--profile` defaulting to `ircc` so behavior is byte-for-byte unchanged and the 26-test offline suite stays green.
- Top-level MIT LICENSE plus a NOTICE documenting attribution, robots.txt compliance, source Terms-of-Service obligations, and non-commercial use — both linked from the crawler README (PKG-03).
- The crawler now installs as a Poetry-managed `corpus-crawler` 2.0.0 wheel with a lean PyYAML-only core and crawl4ai isolated as an opt-in `crawl` extra — proven reproducible by a clean-venv wheel install that loads packaged profile data and contains no crawl4ai.
- Pre-existing untracked core modules.
- Delivered `scripts/check_publish_safe.py`, a pure-stdlib publish-safety checker that scans only the git-tracked tree for absolute home/venv paths, secret patterns, and tracked personal/trial corpora — printing a `file:line: category: snippet` report and exiting non-zero on any violation, or a `✓ publish-safe` message and exit 0 when clean — then ran it as the green Phase-15 gate on the tree cleaned by plan 15-1.
- A versioned `--json` machine-readable contract — a single global flag makes all four `corpus-crawler` subcommands print exactly one stable JSON envelope to stdout (human text to stderr), with machine-readable error objects + documented exit codes for missing crawl4ai (3) and bad input (2).
- Rewrote `crawler/README.md` into a source-agnostic guide — install via the `corpus-crawler` console command, author a profile from `template.yaml`, run the full crawl→enforce→apply-verdicts→completeness→report pipeline, and drive it from an agent — while reconciling the three deferred Phase-14 findings (WR-02 generic prose, WR-03 dead license links, WR-04 single crawl4ai story).
- Rewrote `crawler/QC_RUNBOOK.md` into a source-agnostic config-authoring + QC guide: corpus purpose, domain, and out-of-scope topics are now parameterized placeholders, the IRCC/medical example is demoted to one worked example, and the crawl4ai install story is reconciled to the single `corpus-crawler[crawl]` path matching the README.

---

| Version | Shipped | Summary |
|---------|---------|---------|
| v1.0 | 2026-06-09 | CLI-agnostic, RAG-grounded Canadian e-APR document guidance — crawler (+ manual PDFs) → citable corpus (109 docs / 3,645 chunks) → FTS5 search/citation contract → grounding gate → Layer-1 checklist → 5 document agents → multi-CLI conformance. 8 phases, 24/24 requirements, 76 tests. |
| v1.1 | 2026-06-09 | Corpus Coverage & Completeness — coverage auditor, scope-guarded expanded crawl, completeness validator (skeleton + crawl4ai JS-render gate), refresh orchestrator + CI gates. 4 phases, 12/12 requirements. Corpus 73→319 docs / 5,250 chunks. |
| v2.2 | 2026-06-11 | Corpus Duplicate Audit & Cleanup — cross-family exact + near-duplicate detection (`dupaudit`) + fail-closed cleanup (`dupclean`), one canonical copy per cluster, QC/completeness intact. 2 phases (20-21) + tech-debt cleanup (Phase 22). 10/10 requirements. Corpus 752→742 live docs. |
| v3.1 | 2026-06-24 | Express Entry Document-Agent Expansion — portable CLI-agnostic document-agent pack grown 6 → 22 agents, covering every mandatory / if-applicable e-APR document type + translation; baked query + non-volatile marker selection, all PII in `basis[]`, no new trust-path code. 1 phase (28), 1/1 requirement (CHK-04). Conformance 19 tests + 22 subtests green. |
| v4.0 | 2026-07-06 | CRS Profile ↔ Document Substantiation Auditor — local, PII-safe post-ITA auditor proving the claimed CRS score is substantiated by confirmed evidence from real documents: git-ignored candidate vault, quarantined render+read extraction with field-level confirmation, PII-free corpus-grounded CRS rule registry + deterministic math, four context-light auditor modules with fail-closed `SUBSTANTIATED`/`GAP`/`AT-RISK` verdicts + vault-only reports, single-command SAFE conformance release gate. 2 integration blockers found in audit and closed (extraction→auditor seam), locked by a real E2E test. 6 phases (29-34), 24/24 requirements, 714 tests. |
