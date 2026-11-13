---
phase: 38-redacted-professional-review-packet
verified: 2026-07-17T14:12:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  note: "Initial verification. No prior 38-VERIFICATION.md existed. GAP CLOSED post-verification: the sole failing truth (publish-safe/SAFE-02) was caused by unmarked abs-path/secret example shapes in the tracked 38-REVIEW.md; allow-markers were added (commit). Re-verified: full suite 827 passed / 1 skipped / 355 subtests / 0 failed; check_publish_safe.py 0 violations; run_conformance.py PASS SAFE-01..04. All 5 PKT requirements + the release-gate invariant now hold."
gaps:
  - truth: "The v4.1 release-gate invariant holds: the full pytest suite is green, the publish-safe scanner reports 0 violations over the tracked tree, and run_conformance.py PASSes SAFE-01..04 (the SAFE-02 publish-safety invariant this phase forward-guards)."
    status: failed
    reason: "The phase shipped a git-TRACKED artifact — its own code-review doc 38-REVIEW.md — that quotes three leak-shape strings (a home-directory absolute-path shape on line 91; GitHub fine-grained PAT / Slack / generic credential-assignment secret shapes on lines 135-136) WITHOUT the sanctioned per-line '# publish-safe: allow' marker. The publish-safe scanner deliberately scans the .planning tree (its own docstring: '.planning IS scanned'), so all three lines trip it: check_publish_safe.py exits 1 (3 violations / 351 files), run_conformance.py FAILs the SAFE-02 gate, and three in-suite PII-perimeter/conformance tests fail. Full suite = 3 failed / 824 passed / 1 skipped / 355 subtests. The task acceptance bar ('expect 0 violations', 'PASS SAFE-01..04', 'full suite green, 0 failures') is therefore unmet. This does NOT falsify any PKT-01..05 behavior — the packet capability is fully implemented and reproduced live — but it breaks the release-gate invariant Phase 39 will consolidate."
    artifacts:
      - path: ".planning/phases/38-redacted-professional-review-packet/38-REVIEW.md"
        issue: "Lines 91, 135, 136 carry a home-dir abs-path shape and three secret shapes with no '# publish-safe: allow' marker, tripping the publish-safe scanner and 3 tests (test_conformance_v40_privacy_containment::test_publish_safe_main_zero_violations, test_extraction_pii_perimeter::test_tracked_tree_is_clean, test_full_audit_pii_perimeter::test_publish_safe_zero_violations)."
    missing:
      - "Append the sanctioned '# publish-safe: allow' marker to 38-REVIEW.md lines 91/135/136, OR neutralize the quoted leak shapes (break the literal tokens), so check_publish_safe.py returns 0, run_conformance.py PASSes SAFE-01..04, and the 3 PII-perimeter tests pass — then re-run the full suite to confirm 0 failures."
---

# Phase 38: Redacted Professional Review Packet Verification Report

**Phase Goal:** The applicant can preview and produce an opt-in, explicitly redacted lawyer/RCIC review packet from selected findings — staged only inside the vault, excluding raw documents by default.
**Verified:** 2026-07-17T14:12:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

Verification was performed goal-backward against the ACTUAL codebase and the real
14 MB `corpus/index.db` (present + extraction deps installed), NOT SUMMARY.md claims.
The whole applicant path was reproduced end-to-end through the real `crawler.cli` in a
scratch `PR_PERSONAL_DIR` tempdir: `vault profile set` (the shipped
`personal.example/crs-profile.example.yaml`) → `vault audit --all --db corpus/index.db`
(→ a completed run, `aud_cfbd…`, **9 GAP findings**) → `vault review-packet --dry-run`
(manifest previewed, **nothing written**) → `vault review-packet` (**9 findings**, JSON+MD
written ONLY under `candidates/ex/output/review-packet/`, PII-light stdout, no `ev_`, no
absolute path) → per-document opt-in / unknown-doc / duplicate-doc / missing-backing-file
scenarios → the structural firewall, the render-then-scan gate, path-escape, and the
no-second-trust-path proofs run in-process.

**All five PKT requirements (PKT-01..05) are functionally VERIFIED with real, live
evidence.** The packet capability, and every code-review fix (the CR-01 BLOCKER, WR-01,
WR-02), were confirmed present, tested, and independently reproduced.

**However, the phase is NOT release-green.** The full suite finished **3 failed / 824
passed / 1 skipped / 355 subtests** (862s); `check_publish_safe.py` exits 1 with **3
violations**; `run_conformance.py` **FAILs SAFE-02**. All three failures share a single
root cause: the phase's own git-TRACKED code-review document
`.planning/phases/38-redacted-professional-review-packet/38-REVIEW.md` (lines 91, 135,
136) quotes leak-shape strings — a home-directory absolute-path shape and three secret
shapes — without the sanctioned `# publish-safe: allow` marker. Because the publish-safe
scanner deliberately scans the `.planning` tree, those lines trip it, and three in-suite
PII-perimeter/conformance tests that assert "tracked tree scans clean, 0 violations" now
fail. This is a real, reproducible regression of the SAFE-02 publish-safety invariant that
Phase 39 (SAFE Conformance & Release Consolidation) will consolidate — leaving it red would
break Phase 39's release gate. The fix is trivial and known (the scanner ships a per-line
escape hatch precisely for legitimate references), but until applied the phase cannot be
marked `passed`.

### Observable Truths (ROADMAP Success Criteria + PLAN must_haves)

| #   | Truth (requirement) | Status | Evidence |
| --- | ------------------- | ------ | -------- |
| 1 | Applicant can select audit/remediation findings and preview a dry-run redaction manifest BEFORE creating a packet (PKT-01) | ✓ VERIFIED | Live: `vault review-packet --dry-run` over the real audit emitted a PII-light manifest on stdout (`manifest_counts={findings_total:9, findings_included:9, findings_excluded:0, documents_excluded:0, documents_included:0}`, `private_output_path="(dry-run — not written)"`) and wrote NOTHING — the `output/review-packet/` dir did not exist afterward. Selection filter: `--finding` (repeatable, `cli.py:1464-1466`) → `build_packet(..., selection)` filters `checklist.items` by `factor_id` (`review_packet.py:165-167`). `dry_run` short-circuits before any write (`review_packet.py:325-333`). Test `test_dry_run_writes_nothing`. |
| 2 | Closed allowlist projection whose schema STRUCTURALLY cannot carry raw applicant values, absolute paths, or `ev_` ids unless explicitly admitted (PKT-02) | ✓ VERIFIED | `PacketFinding`/`PacketCitation`/`IncludedDocument`/`RedactionManifest`/`ReviewPacket`/`PublicPacketSummary` all `ConfigDict(extra="forbid")` (`review_packet.py:51-146`). No `raw_value`/`evidence_id`/`absolute_path`/`candidate_id` field exists. Live construction: injected `raw_value`/`evidence_id`/`absolute_path`/`claimed_value`/`candidate_id` each raise `ValidationError`; `PacketCitation(citation_id="ev_…")` raises (`_reject_evidence_id`, `:59-65`); `PublicPacketSummary` with an absolute `private_output_path` raises (`_reject_absolute_path`, `:142-145`). Live packet `model_dump_json` carries no `ev_`, no candidate id, no abs path. Tests `test_models_reject_injected_pii_keys`, `test_packet_dump_carries_no_ev_or_abspath`. |
| 3 | Raw/rendered/OCR document content excluded by default; per-document opt-in stays vault-only (PKT-03) | ✓ VERIFIED | Live: default run with one imported doc → `documents_excluded=1`, `documents_included=0`. `--include-document <id>` → the doc staged ONLY under `candidates/ex/output/review-packet/<pkt_id>/documents/<doc_id>.pdf` (found there, nowhere else); manifest `documents_included` records the id only; stdout carries no raw filename/path. Foreign id → `unknown_document` refusal, zero artifacts. `list_candidate_documents`/`get_candidate_document` are parameter-bound + candidate-scoped (`vault.py:1240-1263`). Tests `test_include_document_stages_vault_only`, `test_include_unknown_document_refuses`, `test_documents_excluded_by_default`. |
| 4 | Records included/excluded/redacted; writes ONLY under the guarded vault packet subtree; refuses non-vault destinations/path escapes; scans rendered bytes before write (PKT-04) | ✓ VERIFIED | `RedactionManifest` records `findings_total/included/excluded`, `redacted_fields=["evidence_ids"]`, `documents_excluded`, `documents_included` (`review_packet.py:97-116, 181-188`). Writes are UNCONDITIONALLY vault-anchored via `paths.resolve_within(vault.root, "output","review-packet", …)` — no destination override is offered (`:342-355`); a crafted escaping component raises `PathEscapeError` (reproduced live). `_scan_rendered_bytes` flags home-dir / `/Users` / `/root` paths, `ev_` ids, PEM/AWS/`ghp_`/GitHub-PAT/Slack/bearer/JWT/generic-credential secrets, and returns `[]` on a clean render (all 13 vectors reproduced live). Render-then-scan runs BEFORE `new_packet_id`/`mkdir`/write (code order `:335-347`); `test_render_then_scan_ordering_via_quote` proves a rendered leak → `rendered_leak` refusal + ZERO artifacts. `run_review_packet` reuses `remediation._build_checklist_for_run` (one trust path, `:291`); AST walk → no `searchindex`/`grounding` import; `no_inlined_volatile_rules([review_packet.py])==[]`; `output/review-packet/` in publish-safe `VAULT_SUBTREES` (`check_publish_safe.py:71`). |
| 5 | Presents findings + score impact + resolvable citations with screening framing; no approval / eligibility / outcome prediction (PKT-05) | ✓ VERIFIED | Live packet JSON: 9 findings, each carrying `factor_id`/`verdict`/`reason_code`/`finding_kind`/`score_impact`/`substantiated_points`/`citations[](citation_id+quote)`/`action` — e.g. `core.age`/`GAP`/`missing_evidence` citing `guidance/crs-criteria.md#004` with a real quote. Both JSON and MD carry the verbatim `SCREENING_NOTICE` ("**not legal advice** … makes no eligibility ruling or outcome prediction"). The findings BODY carries no affirmative approval/eligibility/outcome claim (`test_render_carries_screening_notice_and_no_affirmative_claims` checks a denylist over the notice-excluded body). Retrieve-what-you-cite: `test_every_packet_citation_is_a_real_registry_pair`. |
| 6 | v4.1 release-gate invariant: full suite green + publish-safe 0 violations + `run_conformance.py` PASS SAFE-01..04 (the SAFE-02 publish-safety invariant this phase forward-guards) | ✗ FAILED | Full suite = **3 failed / 824 passed / 1 skipped / 355 subtests** (862.42s). `check_publish_safe.py` → exit 1, **3 violations**, ALL in the tracked `38-REVIEW.md` (lines 91/135/136). `run_conformance.py` → **FAIL** (SAFE-02). The 3 failing tests — `test_conformance_v40_privacy_containment::test_publish_safe_main_zero_violations`, `test_extraction_pii_perimeter::test_tracked_tree_is_clean`, `test_full_audit_pii_perimeter::test_publish_safe_zero_violations` — all assert the tracked tree scans clean and all fail on the same 3 lines. Root cause: the phase's own code-review doc quotes leak-shape strings without the `# publish-safe: allow` marker. |

**Score:** 5/6 must-haves verified. PKT-01..05 (the phase's five functional Success
Criteria) are each VERIFIED with live evidence; the sixth must-have — the green-suite /
publish-safe / conformance release-gate invariant (an explicit acceptance condition and a
frozen SAFE-02 project invariant) — is FAILED by a phase-introduced tracked artifact.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `crawler/review_packet.py` | closed-allowlist models + `RedactionManifest` + pure `build_packet` + render + `_scan_rendered_bytes`/`_LEAK_PATTERNS` + `run_review_packet` writer | ✓ VERIFIED | 367 lines. Six `extra="forbid"` models; pure `build_packet` (`:151-195`, no id/timestamp/IO — determinism test passes); `render_packet_markdown` carrying imported `SCREENING_NOTICE` (`:198-229`); `_LEAK_PATTERNS` (16 shapes incl. the 3 WR-01 additions) + `_scan_rendered_bytes` (`:239-270`); `run_review_packet` reads staged doc bytes BEFORE any write (CR-01), builds, dry-run short-circuit, render-then-scan, vault-only write, PII-light summary (`:273-366`). |
| `crawler/remediation.py` | extracted `_build_checklist_for_run` shared helper (one trust path) | ✓ VERIFIED | `_build_checklist_for_run` (`:377-412`) resolves the completed run → `_load_report` → registry-fingerprint drift gate → `build_remediation`; `run_remediation` (`:415-442`) delegates to it (behavior unchanged); reused by `review_packet.run_review_packet` (`review_packet.py:291`). |
| `crawler/vault.py` | `new_packet_id` (`pkt_`) + `list_candidate_documents` + `get_candidate_document` | ✓ VERIFIED | `new_packet_id` mints `pkt_`+12 hex (`:324-330`); `list_candidate_documents` (`:1240-1250`) + `get_candidate_document` (`:1253-1263`) are `?`-bound and candidate-scoped (no cross-candidate resolution). |
| `crawler/cli.py` | `_cmd_vault_review_packet` + `review-packet` subparser + `--dry-run`/`--include-document`/`--finding` + hints | ✓ VERIFIED | `_cmd_vault_review_packet` (`:1226-1271`) maps `RemediationError`→`invalid_input`/exit 2 with `_REMEDIATION_HINTS` (`rendered_leak`/`unknown_document`/`document_unreadable` added, `:1173-1178`); `review-packet` sub-subparser + all three flags (`:1453-1473`); metavar updated (`:1319`). Human finding detail → STDERR only, skipped under `--json`. |
| `scripts/check_publish_safe.py` | `output/review-packet/` in `VAULT_SUBTREES` | ✓ VERIFIED | `VAULT_SUBTREES` includes `"output/review-packet/"` (`:71`). NOTE: the scanner ITSELF now reports 3 violations — not from this registration, but from the tracked `38-REVIEW.md` doc (see Gap). |
| `crawler/tests/test_review_packet.py` | allowlist firewall + projection + selection + determinism + manifest + screening framing | ✓ VERIFIED | 121 lines, 9 tests. All pass. |
| `crawler/tests/test_review_packet_cli.py` | vault-only write + PII-light + refusals + dry-run + render-then-scan + per-doc opt-in + CR-01 missing-file + WR-02 dedupe | ✓ VERIFIED | 252 lines, 12 tests incl. `test_include_document_missing_file_fails_closed` (CR-01) and `test_duplicate_include_document_deduped` (WR-02). All pass. |
| `crawler/tests/test_review_packet_conformance.py` | structural firewall + render-then-scan bite (non-vacuous) + retrieve-what-you-cite + no-second-trust-path | ✓ VERIFIED | 120 lines, 6 tests. All pass. |
| `crawler/tests/test_crs_no_inlined_rules.py` | `review_packet.py` in the no-inlined scan surface | ✓ VERIFIED | `_EXPORT_MODULES` includes `crawler/review_packet.py` (`:31`); aggregate gate returns `[]`. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `cli._cmd_vault_review_packet` | `review_packet.run_review_packet` | build packet → vault-only write | ✓ WIRED | `cli.py:1246-1248`; `RemediationError`/`PathEscapeError`→`invalid_input`/exit 2; success → PII-light `_vault_ok`. |
| `review_packet.run_review_packet` | `remediation._build_checklist_for_run` | reuse report load + gate + build (ONE trust path) | ✓ WIRED | `review_packet.py:291`; identical resolve→load→fingerprint-gate→build as `run_remediation`. |
| `review_packet.build_packet` | `remediation.PrivateRemediationChecklist` | project selected items → `PacketFinding`, DROP `ev_` | ✓ WIRED | `:165-180`; copies allowlisted fields only; `evidence_ids` never read; `redacted_fields=["evidence_ids"]`. |
| `review_packet.run_review_packet` | `review_packet._scan_rendered_bytes` | render-then-scan BEFORE write | ✓ WIRED | `:336-339` scan runs before `new_packet_id`/`mkdir`/write at `:341-347`. |
| `review_packet.run_review_packet` | `paths.resolve_within` | vault-anchored write of packet + staged docs | ✓ WIRED | `:342-355`; escaping component → `PathEscapeError` (reproduced). |
| `review_packet.run_review_packet` | `vault.get_candidate_document` | read staged doc bytes up-front (CR-01) | ✓ WIRED | `:307-318`; `None`→`unknown_document`; `OSError`/`PathEscapeError`→`document_unreadable` BEFORE any write. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| review packet | `packet.findings` | `build_packet` over the Phase-37 checklist built from the real `vault audit --all` over `corpus/index.db` | Yes — 9 findings from 9 real GAP cards; not empty/static | ✓ FLOWING |
| finding citations | `finding.citations[].quote` | projected from `RemediationCitation` → registry rows | Yes — live `guidance/crs-criteria.md#004` quote is a real registry pair (retrieve-what-you-cite test) | ✓ FLOWING |
| redaction manifest | `manifest.counts()` | `build_packet` counts + caller-supplied doc counts | Yes — live `findings_total=9`, `documents_excluded` tracks real vault doc count | ✓ FLOWING |
| public summary | `PublicPacketSummary` | `run_review_packet` (vault-relative path, PII-light) | Yes — real `pkt_…` id, vault-relative path, no PII/`ev_` | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full applicant path over real index | `vault profile set` → `vault audit --all --db corpus/index.db` → `vault review-packet` | `ok:true`, `findings_included=9`, JSON+MD only under `candidates/ex/output/review-packet/`, no `ev_`/abs path | ✓ PASS |
| Dry-run previews, writes nothing | `vault review-packet --dry-run` | manifest on stdout, `private_output_path="(dry-run — not written)"`, no dir created | ✓ PASS |
| Structural firewall | in-process construction of injected keys / `ev_` citation / abs summary path | every injected key + `ev_` id + abs path → `ValidationError` | ✓ PASS |
| Leak scan (non-vacuous) | `_scan_rendered_bytes` over 13 crafted vectors + 1 clean | all 13 flagged (incl. GitHub-PAT/Slack/generic-credential — WR-01); clean → `[]` | ✓ PASS |
| Path escape | `resolve_within(root,"output","review-packet","../../escape.json")` | `PathEscapeError` | ✓ PASS |
| Per-document opt-in vault-only | `--include-document <id>` | staged only under `…/review-packet/<pkt_id>/documents/`; `documents_included=1` | ✓ PASS |
| Default doc exclusion | `--dry-run` with 1 imported doc | `documents_excluded=1`, `documents_included=0` | ✓ PASS |
| Unknown document refusal | `--include-document doc_does_not_exist` | `invalid_input`/exit 2, `reason=unknown_document`, zero artifacts | ✓ PASS |
| CR-01 missing backing file | delete backing file → `--include-document <id>` | `invalid_input`/exit **2**, `reason=document_unreadable`, ZERO artifacts, NO abs-path on stdout | ✓ PASS |
| WR-02 duplicate include | `--include-document <id> --include-document <id>` | `documents_included=1`, `documents_excluded=0` (no double-count / negative) | ✓ PASS |
| No second trust path | AST import walk + no-inlined self-scan | no `searchindex`/`grounding` import; `no_inlined_volatile_rules([review_packet.py])==[]` | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes are declared or implied by this phase's plans/summaries.

| Probe | Command | Result | Status |
| ----- | ------- | ------ | ------ |
| publish-safe scanner | `.venv/bin/python scripts/check_publish_safe.py` | exit **1**, **3 violations** (all in `38-REVIEW.md` lines 91/135/136), 351 files | ✗ FAILED |
| conformance gate | `.venv/bin/python scripts/run_conformance.py` | **FAIL** — `test_publish_safe_main_zero_violations` fails (1 failed / 50 passed); SAFE-02 red | ✗ FAILED |
| full suite | `.venv/bin/python -m pytest crawler/tests -q` | **3 failed, 824 passed, 1 skipped, 355 subtests** (862.42s) | ✗ FAILED |

The three full-suite failures are exactly the three publish-safe/PII-perimeter tests, all
failing on the same 3 lines of the tracked `38-REVIEW.md`. Every other test — including all
27 Phase-38 packet tests — passes.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| PKT-01 | 38-03 | Select findings + preview a dry-run redaction manifest before creating a packet | ✓ SATISFIED | Truth 1 — live dry-run manifest, writes nothing; `--finding` selection. |
| PKT-02 | 38-01/38-04 | Closed allowlist projection structurally cannot carry raw values / abs paths / `ev_` ids | ✓ SATISFIED | Truth 2 — `extra="forbid"` models, `ev_` citation rejection, abs-path validator, construction-time `ValidationError`. |
| PKT-03 | 38-03/38-04 | Docs excluded by default; per-document opt-in vault-only | ✓ SATISFIED | Truth 3 — default excluded, `--include-document` vault-only staging, unknown-doc refusal, CR-01 missing-file fail-closed. |
| PKT-04 | 38-02/38-03 | Records incl/excl/redacted; vault-only writes; refuse non-vault/escape; scan rendered bytes before write | ✓ SATISFIED | Truth 4 — manifest record, `resolve_within` anchoring, `PathEscapeError`, render-then-scan-before-write, publish-safe subtree. |
| PKT-05 | 38-01 | Findings + score impact + resolvable citations with screening framing; no approval/eligibility/outcome | ✓ SATISFIED | Truth 5 — full finding schema, real registry citation, verbatim `SCREENING_NOTICE`, no affirmative claims in body. |

All five v4.1 PKT requirements map to Phase 38 exactly once (REQUIREMENTS.md / ROADMAP.md),
each claimed by a plan, and each functionally implemented + reproduced live. No orphaned
requirements. **The gap is not a PKT-behavior failure** — it is a regression of the SAFE-02
publish-safety invariant (a Phase-39 requirement this phase forward-guards) caused by a
phase-introduced tracked documentation artifact.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `.planning/phases/38-…/38-REVIEW.md` | 91, 135, 136 | Tracked doc carries a home-dir abs-path shape + 3 secret shapes with NO `# publish-safe: allow` marker | 🛑 BLOCKER | Trips the publish-safe scanner → 3 in-suite tests fail, `run_conformance.py` FAILs SAFE-02, suite not green. See Gap. |

No `TBD`/`FIXME`/`XXX` debt markers and no `TODO`/`HACK`/`PLACEHOLDER` in any phase-modified
source/test file. The `return`/`raise` paths in `review_packet.py` are intentional
projection/fail-closed semantics (verified by tests + live runs), not empty handlers.

### Code Review Status (CR-01 / WR-01 / WR-02)

38-REVIEW.md: **1 Critical, 2 Warning, 2 Info** — resolution `resolved`. Each fix
independently re-verified against the code AND reproduced live:

- **CR-01 (BLOCKER — per-document staging left a partial packet + leaked an absolute path
  on a missing backing file):** **FIXED.** `run_review_packet` now RESOLVES + READS every
  opted-in document's bytes BEFORE any write (`review_packet.py:303-318`); an `OSError`/
  `PathEscapeError` maps to `RemediationError("document_unreadable")`, so the CLI refuses
  cleanly (`invalid_input`/exit 2) with ZERO artifacts and no path on stdout. Reproduced
  live (deleted backing file → `reason=document_unreadable`, exit 2, no `pkt_*` artifact, no
  abs path) + regression test `test_include_document_missing_file_fails_closed`.
- **WR-01 (incomplete secret scan):** **FIXED.** `_LEAK_PATTERNS` now includes the GitHub
  fine-grained PAT, Slack-token, and generic credential-assignment shapes
  (`review_packet.py:253-260`). All three reproduced as flagged live (previously clean).
- **WR-02 (duplicate `--include-document` → double-count / negative excluded):** **FIXED.**
  Order-preserving de-dupe (`review_packet.py:298-301`); reproduced live
  (`documents_included=1`, `documents_excluded=0`) + regression test
  `test_duplicate_include_document_deduped`.
- The 2 Info items (Windows-drive `.md`-only scan; empty-`--finding` packet) are acknowledged
  advisory — neither blocks the goal.

**Irony worth flagging:** the code-review document that *documents* these leak shapes is the
sole cause of the publish-safe regression — it quotes the very abs-path/secret shapes it
found, in a git-tracked file, without the scanner's sanctioned allow marker. This is not an
override candidate: the sanctioned mechanism (`# publish-safe: allow`, or neutralizing the
tokens) is trivial and the SAFE-02 gate must be green for Phase 39's release consolidation.

### Human Verification Required

None. This phase delivers a deterministic projection layer, a CLI verb, three vault helpers,
and a publish-safe subtree entry — no visual, real-time, or external-service surface. Every
observable behavior was covered by automated evidence AND independently reproduced during
this verification. The single gap is a deterministic, tool-detected, in-suite test failure —
not a human-judgement item.

### Gaps Summary

**The phase's packet capability (PKT-01..05) is fully delivered and reproduced live** — the
applicant can preview a dry-run redaction manifest and produce an opt-in, structurally-
redacted, screening-framed lawyer/RCIC packet, staged vault-only, excluding raw documents by
default, with the CR-01/WR-01/WR-02 code-review fixes all confirmed. **The phase is not
release-green, however:** its own git-tracked code-review document
`.planning/phases/38-redacted-professional-review-packet/38-REVIEW.md` (lines 91, 135, 136)
quotes a home-directory absolute-path shape and three secret shapes without the sanctioned
`# publish-safe: allow` marker. Because the publish-safe scanner deliberately scans the
tracked `.planning` tree, those lines trip it (`check_publish_safe.py` exit 1, 3 violations),
which fails `run_conformance.py` (SAFE-02) and turns three in-suite PII-perimeter/conformance
tests red (full suite = 3 failed / 824 passed / 1 skipped / 355 subtests). This violates the
task's explicit acceptance bar (0 violations, PASS SAFE-01..04, full suite green) and would
break Phase 39's release gate.

**Fix (trivial):** append `# publish-safe: allow` to 38-REVIEW.md lines 91/135/136, OR
neutralize the quoted leak shapes (break the literal tokens), then re-run
`check_publish_safe.py` (→ 0), `run_conformance.py` (→ PASS SAFE-01..04), and the full suite
(→ 0 failures). Not deferrable to Phase 39 — Phase 39 consolidates this gate rather than
fixing a leaked doc.

---

_Verified: 2026-07-17T14:12:00Z_
_Verifier: the agent (gsd-verifier)_
