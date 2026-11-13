# Project Research Summary

**Project:** PR Review Agents — v4.1 CRS Auditor Hardening & Remediation
**Domain:** Local-first, PII-safe, corpus-grounded CRS Profile ↔ Document Substantiation Auditor (post-ITA Express Entry e-APR) — a hardening + remediation milestone layered on the shipped v4.0 codebase
**Researched:** 2026-07-17
**Confidence:** HIGH (coverage/hardening) · MEDIUM (remediation content model, packet redaction schema)

## Executive Summary

v4.1 is a **focused v4.0.x hardening milestone, not a new-technology or new-policy build.** v4.0 already shipped the whole auditor — a git-ignored per-candidate vault, quarantined extraction with per-field confirm/correct/reject, a corpus-grounded CRS rule registry (31 rows, full grid, 0 gaps) + deterministic CRS math, four fail-closed auditor modules (`SUBSTANTIATED`/`GAP`/`AT-RISK`/`N/A`), a two-tier PII firewall, and a SAFE conformance release gate (6 phases, 24/24 requirements, 714 tests). v4.1's job is to close five carried-forward tech-debt gaps and then turn already-grounded verdicts into two new **action** surfaces (a private remediation checklist and an opt-in redacted lawyer/RCIC review packet) **without inventing a second, ungrounded trust path.**

**The single most important recommendation across all four research files is unanimous and load-bearing: add nothing.** Ship v4.1 on the exact stack that shipped v4.0 — zero new runtime dependencies. Every capability is pure Python + corpus-grounded YAML over primitives that already exist, are already tested, and are already inside the PII/publish-safe perimeter. The "stack decisions" here are almost entirely about *discipline* — deliberately **not** adding a PDF engine, a templating engine (`jinja2`), a CLI framework (`typer`/`click`), an encryption library, or a PII/NER scrubber (`presidio`/`spaCy`). Each is a plausible-but-wrong instinct for "remediation checklist" or "redacted export," each would break a standing constraint, and several (`jinja2`/`typer`/`click`/`cryptography`) exist in the lock file **only transitively** via optional extras — relying on them in core code would silently promote a heavy optional extra to a hard requirement.

**The dominant risk is not technical difficulty — it is a quiet breach of the trust model.** The two new output surfaces (remediation, packet) are exactly where "being helpful" tempts a developer into (a) fabricating a point value to make a factor look complete, (b) synthesizing ungrounded "how to fix" advice, (c) leaking PII into a packet built by stripping a rich private model, or (d) shipping raw documents by default. Mitigation is architectural and consistent across the research: remediation and the packet are **pure projections of an already-grounded `PrivateAuditReport`** — they consume the citation ids the audit already gated, never re-ground or re-score; the packet is a **typed allowlist projection** (like `PublicAuditEnvelope`), redaction is deny-by-default, raw docs are excluded unless an explicit opt-in flag is passed, and both are staged **only** inside the git-ignored vault behind the publish-safe allow-list, gated by a render-then-scan tripwire before write.

## Key Findings

### Recommended Stack

**Zero new runtime dependencies. This is the headline conclusion.** All four research files converge on it, and the STACK research verifies it against `pyproject.toml` + `poetry.lock` module-by-module: every v4.1 capability maps to an existing, tested primitive. `poetry install` is unchanged; the only justified `pyproject.toml` edits are **non-dependency metadata** (registering a v4.1 pytest sub-marker; optionally a new console verb). The extraction-regression sub-goal exercises the **already-declared** optional extras (`doc-extract`, `ocr`) with fixtures only — no version bumps, no new code paths.

**Core technologies (all already in the locked graph):**
- **Python `>=3.10,<4.0`** — runtime for all new code; no newer floor needed.
- **`sqlite3` (stdlib, FTS5)** — vault store + corpus index; the sibling-evidence field is a new `field_name` row (no DDL); any export trail is an **additive `PRAGMA user_version` migration** (the shipped schema-v2/v3 pattern).
- **`pydantic` 2.13.4** — typed two-tier boundary models; the packet's redacted tier is a new `extra="forbid"` model that *structurally cannot* hold a raw applicant value or `ev_` pointer, exactly like `PublicAuditEnvelope`.
- **`pyyaml` 6.0.3** — the higher-CLB grounded point rows and the corrected example profile are plain YAML compiled into pydantic rows (more rows, not new machinery).
- **`platformdirs` 4.10.0** — vault-root resolution for the new `output/remediation/` + `output/review-packet/` subtrees (unchanged).
- **`argparse` (stdlib)** — new `vault remediate` / `vault review-packet` verbs extend the existing subparser tree and emit the frozen five-key `--json` envelope. **The shipped CLI is stdlib argparse, not typer.**
- Rendering is **f-string / `"\n".join(lines)`** (the shipped `audit_report.py` pattern) + `json` + `hashlib` — no templating engine.

**Explicitly rejected (anti-stack):** PDF generators (`reportlab`/`weasyprint`/`pandoc`), `jinja2`, `typer`/`click`, encryption libs by default, and NER/PII scrubbers (`presidio`/`scrubadub`/spaCy — a model, fail-open, and a constraint violation). See STACK.md "What NOT to Use."

### Expected Features

**Must have (table stakes — correctness/robustness, penalized when absent, no credit when present):**
- **Complete higher-CLB first-language points grounding** — a CLB-10 candidate currently gets `SUBSTANTIATED` with `substantiated_points=None` (truthful-but-incomplete); ground the full per-ability point table so it yields a complete, non-fabricated total (data-only; verified groundable in `crs-criteria.md#006`).
- **Confirmed sibling-relationship evidence field → reachable `additional.sibling` verdict** — the 15-pt row is already grounded but `decide_sibling` is structurally unreachable (no extraction field); close the gap **on the extraction side, not by relaxing the decider** (the 30-05 pattern).
- **Clean fail-closed refusal for missing/corrupt corpus index** — today an absent/corrupt `--db` falls through to a raw `internal_error`/exit-4 traceback; convert to a stable, PII-free, artifact-free refusal.
- **Corrected + conformance-pinned example profile** — `crs-profile.example.yaml` ships underscored ids (`core_age`) while the grid uses dotted ids (`core.age`), so the shipped example audits to nothing; re-key + pin with a test.
- **Strengthened low-quality/ambiguous extraction regressions** — adversarial fixtures (rotated, ambiguous `A/B/YYYY` dates, low-text, password-protected) proving a bad read never greens.
- **`SCREENING_NOTICE` framing on every new artifact.**

**Should have (differentiators — the reason v4.1 exists beyond bug-fixing):**
- **Grounded private remediation checklist** — deterministically derive one item per `GAP`/`AT-RISK` (and per unpriced factor) from the existing `PrivateFactorCard` (verdict + `reason_code` + `rule_citation_ids` + `score_delta`), vault-only, PII-light public envelope; the payoff that turns findings into fixes.
- **Opt-in, explicitly-redacted lawyer/RCIC review packet** — applicant-selected findings → a redacted packet staged only in the vault, **raw docs excluded by default**, with a `--dry-run` redaction preview and a recorded redaction map.
- **Per-item score-impact delta + aggregate-vs-cutoff** — reuse the existing `score_delta`/`cutoff_delta` (arithmetic only, no outcome language).

**Defer (v4.2+ / out of scope):** legacy/physician arranged-employment resolver (LATER-01), live DLI/PGWP lookup (LATER-02), NOC-duty semantic review (LATER-03), MEC sidecar (LATER-04) — these stay `AT-RISK` and become RCIC-packet review items, never auto-resolved; structured multi-recipient export presets; PDF export; packet encryption.

### Architecture Approach

The architecture is a **map of existing integration seams and a disciplined plan of what to extend vs. freeze**, not a greenfield design. The hard invariant: **reuse the frozen `search` → `--cite` → grounding gate → JSON envelope trust path — do NOT fork a second trust path, index, or advice engine.** Every new output is a *projection of already-grounded audit verdicts*. The two new modules (`remediation.py`, `review_packet.py`) are **peers of `audit_report.py`**, each with its own two-tier model and its own vault subtree, so the frozen audit writer stays untouched. Both **read a completed audit run by id** (`output/crs-audit/<aud_id>.json`) and project it — decoupling them from grounding entirely and making a false-green structurally impossible.

**Major components (disposition):**
1. **`data/crs_rules/core.yaml`** (MODIFY-data) — add CLB-10 `PointsEntry` rows; no auditor code change (`_grounded_points`/`score_factor` already generalize over levels).
2. **`extraction.py` + new `siblingfields.py` + `auditors/additional.decide_sibling`** (MODIFY) — new sibling doc-type/field vocab pinned in one place (mirror `testtypes.py`), consumed by the decider; grounded row already exists.
3. **`searchindex.ensure_readable()` (NEW probe) + `auditor.py` + `cli.py`** (MODIFY-small) — one owner of "is the index usable?"; typed refusal raised up-front, mapped by the CLI to a stable envelope, artifact-free.
4. **`crawler/remediation.py` + `models/remediation.py`** (NEW) — `GAP`/`AT-RISK` cards → grounded next-action checklist (public envelope + vault-only artifact).
5. **`crawler/review_packet.py` + `models/review_packet.py` + `RedactionManifest`** (NEW) — allowlist redaction projection + render-then-scan double gate + `output/review-packet/` subtree.
6. **`scripts/check_publish_safe.py`** (MODIFY-data) — add both new subtrees to `VAULT_SUBTREES` **in the same change** the writers land.
7. **Conformance suite / `run_conformance.py`** (MODIFY) — extend SAFE-01..04 to cover every new surface.

Seven architectural patterns govern the work: grounding-by-construction reuse (no second trust path), derive-from-verdicts, two-tier PII boundary, fail-closed prerequisite guard, additive `user_version` migration, shared vocabulary anti-drift pin, and the render-then-scan double gate for the packet. **Dependency-aware build order:** coverage completion (A: points, B: sibling) and hardening (C: index refusal, D: example, E: extraction) are two mostly-parallel early tracks; C and D should precede remediation (F); F precedes the packet (G); the conformance gate (H) lands last. **Critical path: A/B → F → G → H.**

### Critical Pitfalls

1. **False completeness (a `SUBSTANTIATED` card hiding `substantiated_points=None`)** — never treat "no GAP" as "complete." Pin the points rows **set-equal to the CLB conversion range** with an anti-drift test; surface an explicit `ungrounded_points`/unpriced state; remediation must treat "SUBSTANTIATED-but-unpriced" as an unresolved item, never a pass. **Never fabricate a point value to fill the gap.**
2. **Secondary ungrounded advice path** — remediation/packet must be a **pure projection of existing grounded verdicts**: only `(factor, reason_code, the rule's own grounded citation+quote, a fixed template action phrase)`. No synthesized requirements, no volatile literals in prose, no model, no ranking, no "you will likely." Deterministic: same vault in → byte-identical checklist out. Gate every requirement-bearing line.
3. **Redaction failure (PII survives the "redacted" packet)** — build the packet from an **explicit closed allowlist of redaction-safe fields** (the `to_public_envelope` discipline), never by copying `PrivateFactorCard`/`model_dump()` and deleting keys. A new field defaults to *excluded*; opt-in is per-finding; run the render through `check_publish_safe.scan_text` as a tripwire.
4. **Accidental raw-document export** — raw/rendered/text inclusion is **off by default, opt-in per document**, and even when opted-in stays vault-internal via `resolve_within`; refuse any non-vault `--out`; add the new subtree to the publish-safe allow-list the moment the writer lands.
5. **Unstable/leaky error surface (missing/corrupt index → raw `internal_error`)** — add a preflight that raises a typed, PII-free, artifact-free refusal with a stable code + actionable message ("run `corpus-crawler index` first"). Distinguish "index missing" (`OperationalError`) from "index corrupt" (sha-drift). **Preserve the frozen error-type vocabulary — see Gaps.**
6. **Evidence-to-factor mislinking (right doc, wrong factor)** — one claimed-scoped `_DOC_TYPE_FACTOR` linkage source, UNLINKED-by-default; extend the real `import→extract→confirm→audit` seam test to assert no cross-factor contamination (a sibling doc must not green age/nomination).
7. **Schema/fixture drift** and **misleading professional-review framing** (packet reading as a legal opinion / approval) round out the list — both closed by pin tests and prominent `SCREENING_NOTICE` + AT-RISK-scope rendering.

## Implications for Roadmap

Based on combined research, the suggested phase structure follows the architecture's dependency-aware build order. Phase numbers are TBD (v4.0 ended at Phase 34; v4.1 likely begins ~Phase 35). SAFE conformance is cross-cutting — extend the release gate *within each phase* for the surface it introduces, with a final consolidation pass.

### Phase 1: Coverage Completion (P-COVERAGE)
**Rationale:** Data/evidence completeness is the lowest-risk, highest-leverage start and it unblocks a *complete* audit report that remediation later consumes. Higher-CLB points is data-only (verified groundable); sibling evidence is extraction-side + a decider read — independent of each other.
**Delivers:** Grounded CLB-10 (and any non-9 band) first-language `PointsEntry` rows so a supported factor produces complete, non-fabricated points; a confirmed sibling relationship+status+residence evidence chain that makes `additional.sibling` reachably `SUBSTANTIATED`.
**Addresses:** Complete higher-CLB first-language points; confirmed sibling-relationship evidence field.
**Uses:** `data/crs_rules/core.yaml`, `crs_rules.validate_registry` (frozen gate), new `siblingfields.py`, `extraction.py`, `auditors/additional.decide_sibling`.
**Avoids:** Pitfall 1 (false completeness — pin points set-equal to the conversion range), Pitfall 2 (stale/historical grounding — per-rule negative controls), Pitfall 3 (mislinking — one claimed-scoped linkage, contamination test).

### Phase 2: Operational Hardening (P-HARDEN)
**Rationale:** Parallel to Phase 1 but must land before remediation/packet, because those exercise the shared audit path. Produces the reusable dotted-id example fixture the later phases consume.
**Delivers:** A typed `IndexUnavailable` preflight (`searchindex.ensure_readable`) converting missing/corrupt-index failures into stable, PII-free, **zero-artifact** refusals with a `doctor` hint; a re-keyed example profile pinned by a conformance test; adversarial low-quality/ambiguous extraction fixtures proving no green from a bad read.
**Addresses:** Clean missing/corrupt-index refusal; corrected + pinned example profile; strengthened extraction regressions.
**Uses:** `searchindex.py`, `auditor.py`, `cli.py`, `contract.py`, `personal.example/crs-profile.example.yaml`.
**Avoids:** Pitfall 5 (unstable error surface), Pitfall 8 (schema/fixture drift), Pitfall 3 (ambiguous-doc mislinking).

### Phase 3: Grounded Remediation Checklist (P-REMEDIATE)
**Rationale:** Depends on Phase 1 (a complete report to project) + Phase 2 (the dotted-id fixture + clean refusal on the shared path). The core "findings → fixes" payoff.
**Delivers:** A new `crawler/remediation.py` + two-tier `models/remediation.py` + `vault remediate` verb + `output/remediation/` subtree; exactly N items for N `GAP`/`AT-RISK`/unpriced factors, each with ≥1 resolvable `citation_id`, a `score_delta`, a template-bound action phrase, and the `SCREENING_NOTICE`.
**Implements:** Derive-from-verdicts + grounding-by-construction-reuse patterns; extend `no_inlined_volatile_rules` over the new module.
**Avoids:** Pitfall 2 (secondary ungrounded advice path — projection-only, gate every requirement line, determinism test), Pitfall 1 (must inspect priced state, not just the verdict string).

### Phase 4: Redacted Review Packet (P-PACKET)
**Rationale:** Highest-complexity, highest-PII-risk surface; depends on Phase 3 (reuses finding-selection + report-load). The first artifact intended to *leave the applicant's hands*.
**Delivers:** A new `crawler/review_packet.py` + `models/review_packet.py` + `RedactionManifest` + `vault review-packet` verb + `output/review-packet/` subtree; an **allowlist** redaction projection, raw docs excluded by default (`--include-documents` explicit + vault-internal), render-then-scan double gate, `--dry-run` preview, and (optional, additive schema v4) an `export_manifests` audit trail.
**Implements:** Two-tier PII boundary + render-then-scan double gate; add the subtree to `VAULT_SUBTREES` in the same change.
**Avoids:** Pitfall 4 (redaction failure — allowlist, default-exclude), Pitfall 5-raw (accidental raw export), Pitfall 9 (misleading framing — prominent screening notice + AT-RISK scope).

### Phase 5: SAFE Conformance / Release-Gate Consolidation (P-CONFORM, cross-cutting)
**Rationale:** Each prior phase extends SAFE-01..04 for its own surface; this final pass proves the whole line holds and updates `scripts/run_conformance.py`.
**Delivers:** Retrieve-what-you-cite negative controls for the new rows; no-false-green + priced-or-flagged assertions; two new subtrees covered + non-vault-output refused + packet redaction leak assertions; determinism + gate-every-claim tests; screening-framing scans.

### Phase Ordering Rationale
- **Data completeness first** because remediation is a pure projection of a *complete* report — an unpriced factor upstream becomes a silent hole downstream.
- **Hardening before the new output surfaces** because remediation and the packet exercise the shared audit/refusal path; the clean refusal and the pinned example fixture are prerequisites, not afterthoughts.
- **Remediation before the packet** because the packet is a curated, redacted *export layer on top of* the checklist's finding-selection.
- **Conformance woven through, consolidated last** because every new capability is a fresh chance to breach a frozen invariant — the release gate is the proof the line held.

### Research Flags

Phases likely needing deeper research/decision during planning (`/gsd-plan-phase --research-phase`):
- **Phase 4 (Packet):** MEDIUM-confidence design surface. Needs a **redaction-depth policy decision** — the closed allow/deny field set (name/UCI/passport/DOB → placeholder; scores/dates → range or coarse label) that keeps the packet useful to a reviewer while excluding raw docs by default; and a decide on the optional schema-v4 `export_manifests` trail.
- **Phase 3 (Remediation):** MEDIUM-confidence content model. Needs the **action-template content model** — templates keyed by `(factor_id, reason_code)` that are generic and non-volatile, with every concrete figure read from the grounded rule row, not the template.

Phases with well-documented patterns (skip research-phase):
- **Phase 1 (Coverage):** data-only; CLB-10 quote verified groundable; the sibling seam and `decide_sibling` are already mapped.
- **Phase 2 (Hardening):** all seams are named integration points (`ensure_readable`, `AuditGroundingError`, example re-key, extraction classification) with established patterns.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Verified module-by-module against `pyproject.toml` + `poetry.lock`; zero new deps is a checked fact, not an aspiration. Every capability maps to a tested existing primitive. |
| Features | HIGH (hardening) / MEDIUM (remediation content + packet redaction schema) | Hardening features are grounded in shipped code + the v4.0 tech-debt list. The remediation wording and packet redaction defaults are new design surfaces needing phase-time decisions; the *grounding* they draw from is HIGH. |
| Architecture | HIGH | Grounded in direct source inspection of the shipped v4.0 modules (exact file:line seams named), not external survey. CLB-10 groundability empirically verified in `crs-criteria.md#006`. |
| Pitfalls | HIGH | Project-specific failure modes drawn from the shipped implementation and the v4.0 integration blockers (A/B) actually hit and closed — not generic advice. |

**Overall confidence:** HIGH — this is a hardening milestone over an already-shipped, 714-test stack with no new library APIs to verify. The only MEDIUM zones are two *policy/content* decisions (redaction depth, action-template wording), both deferrable to the F/G phase plans and both low-risk to iterate.

### Gaps to Address

- **Error-type + exit-code for the index refusal (RECONCILED — conservative default):** ARCHITECTURE suggests an additive new `grounding_unavailable` error type; STACK argues to preserve the frozen five-key error vocabulary and reuse `invalid_input` (exit 2) via `AuditGroundingError` with a precise, PII-free `reason_code`. **Resolution: preserve the frozen error vocabulary — reuse `invalid_input` with a distinct `reason_code` — unless an additive *stable* new error type is proven necessary during implementation.** Either path keeps the refusal fail-closed and artifact-free; the envelope schema does not enumerate error types, so an additive type stays available as a last resort, not a default.
- **Review-packet redaction model (RECONCILED):** treat redaction as an **explicit allowlist projection** (deny-by-default, `extra="forbid"`, mirroring `PublicAuditEnvelope`), **vault-only staged**, with **raw documents excluded by default** (opt-in `--include-documents` flag, per-document, logged, still vault-internal). Never a denylist/strip-after-copy. Settle the exact allow/deny field set in the Phase 4 plan.
- **Remediation trust boundary (RECONCILED):** remediation may consume **only already-grounded verdicts + citations** from a completed `PrivateAuditReport`; it must **not** re-ground, re-score, or synthesize requirements — no second trust path. Action prose is template-bound; volatile figures are read from grounded rows.
- **Second-language / French higher-CLB parity:** the v4.0 tech-debt names only *first*-language CLB-10. Verify whether `core.language.second.points` / `additional.french` share the same latent "grounded verdict, `None` points" gap and fold into Phase 1 if so.
- **Export audit trail (schema v4 vs derive-only):** recommend **derive-only** for remediation (no schema change); decide in Phase 4 whether the packet warrants an additive `export_manifests` table for the applicant-controlled audit story (low-risk either way).
- **`ungrounded_points` / unpriced surfaced state:** confirm the audit spine exposes an explicit signal so a `SUBSTANTIATED` + `substantiated_points is None` card is never collapsed into "complete" by remediation/packet — pin points rows set-equal to the conversion range.

## Sources

### Primary (HIGH confidence)
- **Direct shipped-code inspection** — `crawler/auditor.py` (`AuditGroundingError`, `audit_one`/`run_full_audit`, SC5 fail-closed ordering), `crawler/auditors/{__init__,core,additional}.py` (`FULL_GRID_FACTORS` dotted ids, `_grounded_points`/`_sum_points` `None`-on-miss, `decide_sibling` GAP), `crawler/crs_audit.py` (`to_clb`, `score_factor`), `crawler/crs_rules.py` + `data/crs_rules/{core,additional}.yaml` + `COVERAGE.md` (CLB-9-only first-language points; grounded 15-pt sibling row), `crawler/searchindex.py` (`OperationalError`/sha-drift), `crawler/grounding.py` (HONESTY BOUNDARY: resolvability ≠ currency/truth), `crawler/audit_report.py` (`SCREENING_NOTICE`, vault-only writer), `crawler/models/audit.py` (two-tier firewall, `ev_` rejection), `crawler/vault.py` (`is_audit_eligible`, additive migrations), `crawler/extraction.py` (`_DOC_TYPE_FACTOR`, scan-quality classification), `crawler/cli.py` (argparse tree, `internal_error` catch-all), `crawler/contract.py`, `scripts/check_publish_safe.py` (`VAULT_SUBTREES`/`VAULT_ARTIFACT_EXTS`), `personal.example/crs-profile.example.yaml` (underscored ids).
- **Corpus groundability probe** — `guidance/crs-criteria.md#006` verified to contain "CLB 10 or more | 32 | 34" (higher-CLB is a data-only change).
- **Locked dependency graph** — `pyproject.toml` + `poetry.lock`: pydantic 2.13.4 / pydantic-core 2.46.4, pyyaml 6.0.3, platformdirs 4.10.0; Python `>=3.10,<4.0`; `typer`/`click`/`jinja2`/`cryptography` confirmed transitive-only via optional extras.
- **Planning context** — `.planning/PROJECT.md` (v4.1 goal, constraints, Key Decisions: close fail-closed gaps first, exports derive only from grounded verdicts, autonomous planning), `.planning/STATE.md` (frozen trust path, `ev_`↔`citation_id` split, deferred LATER-05), `.planning/milestones/v4.0-MILESTONE-AUDIT.md` (five carried-forward tech-debt items; integration BLOCKERs A/B), `.planning/milestones/v4.0-REQUIREMENTS.md` (SAFE-01..04; out-of-scope NLI/vector/cloud), `SCREENING.md` (SAFE-04 framing).

### Secondary (MEDIUM confidence)
- Remediation action-template content model and packet redaction allow/deny field set — new design surfaces to settle in the Phase 3/4 plans (grounding they draw from is HIGH).
- IRCC CRS per-ability CLB point table and sibling-in-Canada 15-pt rule — resolved from the local authoritative corpus at implementation time, not third-party sources.

### Tertiary (LOW confidence)
- None. This milestone introduces no external ecosystem survey; every finding traces to shipped code, the locked graph, the v4.0 audit, or the authoritative corpus.

---
*Research completed: 2026-07-17*
*Ready for roadmap: yes*
