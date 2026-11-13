# Feature Research

**Domain:** v4.1 CRS Auditor Hardening & Remediation — closing fail-closed coverage/operational gaps in a local, PII-safe post-ITA Express Entry document-substantiation auditor, then turning grounded verdicts into a private remediation checklist and an explicitly-redacted lawyer/RCIC review packet
**Researched:** 2026-07-17
**Confidence:** HIGH for the hardening/coverage-completion features (each is grounded in the shipped v4.0 code, the v4.0 milestone audit tech-debt list, and the existing authoritative corpus + rule registry) · MEDIUM for the remediation-checklist content model and the redacted-packet redaction schema (these are new design surfaces; the *grounding* they draw from is HIGH-confidence, but the exact next-action wording and redaction defaults require phase-time decisions and a few corpus resolutions)

## Context for this Research

v4.1 is **not** a new scoring engine, a new policy domain, or a new trust path. v4.0 already shipped the whole CRS substantiation auditor: a git-ignored candidate vault, quarantined extraction with field-level confirm/correct/reject, a corpus-grounded CRS rule registry, four context-light auditor modules emitting fail-closed `SUBSTANTIATED`/`GAP`/`AT-RISK`/`N/A` verdicts, and a SAFE conformance release gate. The v4.0 milestone audit **PASSED** (24/24 requirements) but explicitly logged five carried-forward tech-debt items. v4.1's job is to close those, then convert the auditor's existing grounded verdicts into two new **action** surfaces without inventing a second ungrounded advice path.

The v4.1 features fall into two buckets:

1. **Finish what v4.0 started (table stakes).** A trustworthy audit tool cannot ship with a factor it *claims* to support silently returning `substantiated_points=None`, a shipped example that does not match the auditor's own factor ids, or a missing corpus index that crashes into a raw `internal_error` traceback. These are correctness/robustness gaps, not features — users penalize their absence and give no credit for their presence.

2. **Turn verdicts into action (differentiators).** The auditor tells you *where* your documents fail to substantiate your claimed CRS. v4.1's differentiators tell you *what to do next* — a private, corpus-cited fix checklist derived from `GAP`/`AT-RISK` findings — and let you *share it safely* — an opt-in, explicitly-redacted packet for a licensed consultant/lawyer/RCIC, staged inside the vault with raw documents excluded by default. No competitor (IRCC's own pre-ITA calculator, third-party CRS blogs, generic document managers) offers grounded, private, fail-closed remediation.

### Non-negotiable constraints carried forward (every v4.1 feature must preserve these)

| Constraint | What it means for v4.1 |
|------------|------------------------|
| **Authoritative-source grounding** | Every new requirement/threshold/next-action must cite a resolvable corpus chunk that passes the frozen `search` → `--cite` → grounding gate. No inlined volatile CLB/points/window literals in Python or prose (the `no_inlined_volatile_rules` static scan already enforces this and must keep passing). |
| **Fail-closed** | New coverage must never fabricate a point value; a missing grounded row stays `substantiated_points=None`/`GAP`/`AT-RISK`, never a guessed green. New failure surfaces (missing/corrupt index) must refuse cleanly and write **zero** artifacts. |
| **PII vault-only** | The remediation checklist and the review packet may carry applicant values and evidence pointers — so both are written **only** under `candidates/<id>/output/…`, covered by the shipped publish-safe allow-list, never on stdout, never in the repo/corpus. The public `--json` envelope stays PII-light. |
| **No legal advice** | Remediation is *screening* next-actions grounded in cited IRCC/IRPA/IRPR/PDI rules ("your ECA must be < 5 years old at e-APR — cited here"), never strategy/outcome prediction ("you should apply under CEC instead"). The `SCREENING_NOTICE` framing must render into both new artifacts. |
| **No cloud / vector / model / NLI** | Remediation and export are deterministic joins over existing verdicts + citations. No new dependency, no embedding, no entailment, no remote call. The redacted packet is produced locally; sharing it (email/print) is a manual user action outside the tool. |

## Verdict Semantics (recap — the input to remediation)

The remediation checklist and export packet are **pure functions of the existing v4.0 factor verdicts**. They add no new judgement:

| Verdict | Remediation meaning | Export inclusion (default) |
|---------|---------------------|----------------------------|
| `SUBSTANTIATED` | No action needed; optionally shown as "confirmed" context. | Included as a green line (no raw doc) if the user selects it. |
| `GAP` | Actionable: the required proof is missing / wrong type / below the claimed threshold. Produces a cited "what's missing + which rule" checklist item. | Primary candidate for a review packet — this is where a consultant adds value. |
| `AT-RISK` | Actionable: needs human/professional judgement (semantic/NOC-duty fit, near-expiry, ambiguous extraction, legacy job-offer). Produces a "needs review — here's why + the cited rule" item. | Primary candidate for a review packet. |
| `N/A` | Not claimed / not applicable. No remediation item. | Excluded by default. |

## Feature Landscape

### Table Stakes (Users Expect These)

Correctness and robustness the tool must have to be trustworthy at all. A local immigration-document auditor that miscounts a supported factor, ships a broken example, or crashes on a missing index feels unfinished — users penalize these harshly and give no credit for fixing them.

| Feature | Why Expected | Complexity | Notes / Concrete testable behavior |
|---------|--------------|------------|------------------------------------|
| **Complete higher-CLB first-official-language points grounding** | The auditor advertises first-language substantiation, but `core.language.first.points` only grounds the CLB 9 row (`clb9_with_spouse=29`, `clb9_without_spouse=31`). A candidate whose confirmed scores convert to CLB 10 (or any non-9 band) hits `_sum_points → None`, so they get a `SUBSTANTIATED` verdict with `substantiated_points=None` — a truthful-but-incomplete result that under-reports the substantiated total. | MEDIUM | Add grounded per-ability points rows for the full first-language table (CLB 4/5 → 6, CLB 6 → 8/9, CLB 7 → 16/17, CLB 8 → 22/23, CLB 9 → 29/31, CLB 10+ → 32/34) from IRCC `crs-criteria` corpus, each with a verbatim quote passing the gate. **Testable:** a confirmed CLB-10-all-abilities applicant now yields `substantiated_points=136` (no-spouse) / `128` (spouse), not `None`; the golden boundary fixtures gain CLB 8/9/10 edges; `no_inlined_volatile_rules` still passes; `retrieve-what-you-cite` grounds each new row against the intended chunk (not an adjacent/historical one). |
| **Confirmed sibling-relationship evidence field + reachable sibling verdict** | `additional.sibling` grounds 15 points in the registry, but `decide_sibling` always returns `GAP` because the EXTRACT field vocabulary carries no sibling signal — so a legitimately-documented sibling can never be substantiated. The factor is advertised but structurally unreachable. | MEDIUM | Add a confirmed evidence chain (relationship + sibling's citizen/PR status + current Canadian residence) on the extraction/confirmation side (mirroring the 30-05 "close the gap on the extraction side, not by relaxing the decider" decision). **Testable:** with a confirmed sibling relationship + status + residence, `additional.sibling` → `SUBSTANTIATED` / `substantiated_points=15`; with any link missing/unconfirmed/stale → `GAP` (fail-closed, never guessed); the sibling-in-Canada residence recency rule stays cited. |
| **Clean fail-closed refusal for missing/corrupt corpus index** | v4.0 audit flagged that an empty/missing index surfaces as a raw `internal_error`/exit 4 traceback rather than a clean `AuditGroundingError` refusal. It is still fail-closed (no report written) but the surface is ugly and could echo internals. A trustworthy tool refuses *legibly*. | LOW–MEDIUM | The grounding path already raises `AuditGroundingError` for ungrounded/gap rows; extend the prerequisite check so a missing/typo'd/0-byte/corrupt index (the `sqlite3.OperationalError` from `searchindex.resolve`/`search`, or a chunk-sha drift) becomes a stable `AuditGroundingError` (or a dedicated `missing_index` refusal reason) → `ok:false` / clean error object / non-zero exit, **not** `internal_error`. **Testable:** running `vault audit` with `--db` pointing at a nonexistent/empty/corrupt DB yields a PII-free refusal with a machine reason code, exit code stable, and **zero** artifacts written (no report `.json`/`.md`, no `audit_runs`/`factor_verdicts` rows); a `doctor`/preflight check reports "corpus index missing/unreadable" before the run. |
| **Corrected & conformance-tested example profile** | `personal.example/crs-profile.example.yaml` ships `factor_id: core_age` / `core_education` / `core_first_language` (underscored ids) while the auditor keys on the grid ids `core.age` / `core.education` / `core.language.first`. The shipped example does not exercise the auditor it is meant to demonstrate — a credibility bug for a public repo. | LOW | Align the example's `factor_id`s to the real grid ids (and add spouse/transferability/additional rows that actually route), then pin it with a conformance test that loads the example and asserts every `factor_id` is a registered auditor factor. **Testable:** a test loads `crs-profile.example.yaml`, resolves each factor through the auditor dispatch, and asserts 0 unrouted/unknown factors; the example remains PII-free (publish-safe self-scan clean). |
| **Strengthened extraction regressions for low-quality / ambiguous documents** | Extractor recall/precision on real-world docs is the standing risk (regex/heuristic only). The quarantine guarantees no *green* from a bad read, but the classification (scanned/rotated/password/low-text/ambiguous-date) needs adversarial fixtures so a misread never silently becomes `ok`. | MEDIUM | Add adversarial fixtures (rotated scans, ambiguous `A/B/YYYY` dates where both ≤ 12, low-text pages, password-protected) asserting they classify `low_quality`/`ambiguous` and therefore stay non-audit-eligible. **Testable:** each adversarial fixture drives `is_audit_eligible → False` and produces at most `AT-RISK` (never `SUBSTANTIATED`); an ambiguous date surfaces `ambiguous: True` and blocks a green verdict until corrected. |
| **`SCREENING_NOTICE` framing on every new artifact** | The SAFE-04 "screening, not legal advice" notice already renders into the audit report; any new user-facing artifact (remediation checklist, export packet) must carry the same framing or the tool drifts toward implied advice. | LOW | Reuse the existing `audit_report.SCREENING_NOTICE` (generic, PII-free). **Testable:** the rendered remediation checklist and the export packet both contain the negated "not legal advice" disclaimer; the SAFE-04 denylist scan stays clean. |

### Differentiators (Competitive Advantage)

New value no competitor offers with grounding + privacy + fail-closed discipline. These are the reason v4.1 exists beyond bug-fixing.

| Feature | Value Proposition | Complexity | Notes / Concrete testable behavior |
|---------|-------------------|------------|------------------------------------|
| **Grounded private remediation checklist** | Converts every `GAP`/`AT-RISK` factor verdict into a document-specific next action — "what's missing, why it fails the rule, and the cited authority" — so the applicant knows exactly what to fix before e-APR. This is the payoff of the whole auditor: findings become fixes. | MEDIUM | Deterministic derivation from the existing `PrivateFactorCard` (verdict + `reason_code` + `rule_citation_ids` + claimed/confirmed values). Each item = {factor, verdict, machine reason, human next-action, corpus citation}. The next-action text must be grounded (drawn from the cited rule's `claim_text`/quote), never freely invented. **Testable:** every checklist item carries ≥ 1 resolvable `citation_id`; a checklist over a report with N `GAP`/`AT-RISK` factors emits exactly N items (0 for an all-`SUBSTANTIATED`/`N/A` report); the checklist is written vault-only under `output/` and the public envelope stays PII-light (counts only); a `no_inlined_volatile_rules` scan over the generator passes; the `SCREENING_NOTICE` is present. |
| **Opt-in, explicitly-redacted lawyer/RCIC review packet (vault-only, raw docs excluded by default)** | Lets an applicant hand a licensed consultant/RCIC exactly the findings + evidence pointers they choose — with PII redaction on by default and **no raw documents** unless explicitly opted in. Turns "here's my whole vault" (privacy disaster) into "here's a curated, redacted screening summary." | HIGH | Applicant-controlled selection of findings/evidence → a redacted packet (Markdown/JSON) staged **only** under a vault subtree already covered by `VAULT_SUBTREES`/`VAULT_ARTIFACT_EXTS`. Redaction is *explicit and shown* (fields masked, redaction map recorded), raw `files/raw/*` excluded unless `--include-raw` is deliberately passed. **Testable:** default packet contains **zero** raw-document bytes and **zero** unredacted PII fields the user didn't opt to include; the packet is refused if targeted at a non-vault output path; publish-safe flags the packet artifacts unstageable; opting into raw inclusion requires an explicit flag and is logged; the packet carries the screening disclaimer. |
| **Profile ↔ evidence remediation delta (score-impact of fixing each gap)** | Shows, per remediation item, how many CRS points are currently un-substantiated and would be recovered if the gap is closed — quantifying priority without giving advice. | MEDIUM | Reuse the existing `score_delta` (claimed − substantiated) already on each factor card. **Testable:** each `GAP`/`AT-RISK` item shows its `score_delta`; the checklist surfaces the aggregate un-substantiated total vs the ITA cutoff (arithmetic only, reusing `cutoff_delta`/`meets_cutoff`) with no outcome language. |
| **Redaction preview / dry-run** | Before writing/sharing, the user can preview exactly what the packet will disclose, building trust in the privacy boundary. | LOW–MEDIUM | A `--dry-run` that renders the redacted view to stderr (like `vault fields`) without writing the artifact. **Testable:** dry-run writes no file and prints the redacted (not raw) preview; the previewed content is byte-identical to what a real run would persist minus the file write. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem helpful but would break a constraint or the trust model. Documented to prevent scope creep back into them.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **AI/free-text remediation advice ("how to improve your case")** | Users want a coach that tells them what to do. | Becomes ungrounded legal/immigration *advice*, violates the no-legal-advice + grounding constraints, and creates a second trust path outside the gate. | Remediation items are **derived only** from existing grounded verdicts + cited rules; wording comes from the cited `claim_text`/quote, never invented. |
| **Raw documents included in the review packet by default** | "The lawyer needs to see my actual PDFs." | Ships maximal PII out of the vault by default — the single biggest privacy risk; one careless export leaks passport/UCI/scores. | Raw docs **excluded by default**; explicit `--include-raw` opt-in, per-document, logged, still staged only inside the vault (the user does the actual hand-off manually). |
| **Auto-emailing / uploading the packet to a consultant** | Convenience — "just send it." | Requires a cloud/network egress path for PII — violates no-cloud and PII-vault-only; also implies an endorsement of a specific consultant. | The tool *produces* a local redacted file; sharing is a deliberate manual user action outside the tool. |
| **Fabricating higher-CLB points to "complete" the score** | A `substantiated_points=None` looks like a bug to fill in. | Guessing a point value breaks fail-closed and the grounding guarantee. | Ground the real IRCC point rows; if a band is genuinely un-groundable from the corpus, keep it `None`/`GAP` and document the coverage gap (never a fabricated citation). |
| **A "remediation wizard" that mutates the profile or re-optimizes CRS** | Users want the tool to fix it for them / suggest a higher-scoring configuration. | Crosses into pre-ITA CRS optimization (explicitly out of scope) and implies strategy advice. | Read-only checklist: it reports what to substantiate for the *already-claimed* score, never proposes a different claim. |
| **Silently upgrading low-confidence extraction to feed remediation "faster"** | Fewer confirmation clicks. | A misread value producing a confident remediation item recreates the false-confidence risk the quarantine exists to prevent. | Remediation reflects the *confirmed* audit state; low-quality/ambiguous inputs stay `AT-RISK` and their remediation item says "confirm/re-extract this first." |
| **Turning the missing-index refusal into a silent auto-build/auto-crawl** | "Just build the index for me." | A read path that writes/creates the index blurs the read/write boundary and could mask a real misconfiguration; the shipped read path deliberately never creates a 0-byte DB. | Refuse cleanly with a machine reason + a `doctor` hint telling the user to build/point at the index; never auto-mutate on the audit read path. |
| **Adding an NLI/semantic model to auto-resolve `AT-RISK` remediation items** | "Let the model decide if the duties match." | Requires a model/vectors — violates no-model/no-NLI/no-vector; recreates the exact thing v4.0 kept out of scope. | `AT-RISK` items stay flagged for human/professional review — this is precisely what the redacted RCIC packet is *for*. |

## Feature Dependencies

```
[v4.0 shipped: candidate vault + extraction quarantine + confirm/correct/reject]
        └──feeds──> [confirmed, audit-eligible evidence]
                          └──consumed by──> [v4.0 auditor modules → PrivateFactorCard verdicts]

[v4.0 shipped: grounded CRS rule registry + grounding gate]
        ├──requires completion──> [Higher-CLB first-language points rows] ──> complete substantiated_points
        └──already grounds──> [additional.sibling 15pt row] ──needs──> [NEW: confirmed sibling evidence field]
                                                                              └──> reachable sibling SUBSTANTIATED

[v4.0 auditor verdicts (PrivateFactorCard: verdict + reason_code + rule_citation_ids + score_delta)]
        └──required by──> [Grounded remediation checklist]
                                 └──required by──> [Redacted lawyer/RCIC review packet]
                                                          └──requires──> [Redaction layer + vault publish-safe subtree]

[v4.0 AuditGroundingError refusal surface]
        └──extended by──> [Clean missing/corrupt-index refusal]

[v4.0 SCREENING_NOTICE + SAFE-04 framing]
        └──reused by──> [remediation checklist] AND [review packet]

[v4.0 publish-safe VAULT_SUBTREES / VAULT_ARTIFACT_EXTS allow-list]
        └──must cover──> [new remediation + packet artifact paths/extensions]

[example profile fix] ──conflicts-if-stale-with──> [auditor grid factor ids] (must be aligned, then pinned)
```

### Dependency Notes

- **Remediation checklist requires the auditor verdicts (AUDIT-01/04):** it is a pure projection of `PrivateFactorCard` — it cannot exist before, and must not re-derive, the verdicts. If the auditor didn't run (grounding refusal), there is nothing to remediate → the refusal propagates.
- **Review packet requires the remediation checklist:** the packet is a *curated, redacted* view of selected checklist items + evidence pointers. Build the checklist first; the packet is the export layer on top.
- **Sibling `SUBSTANTIATED` requires the new evidence field, not a registry change:** the `additional.sibling` row is already grounded (15 pts). The gap is on the extraction/confirmation side — add the confirmed relationship/status/residence signal; `decide_sibling` then reads it (mirroring the 30-05 "fix on the extraction side, keep the decider fail-closed" pattern).
- **Higher-CLB points completion requires only registry rows + fixtures:** the conversion (`to_clb`) and per-ability summation already exist; the missing piece is grounded point rows for the non-9 bands. No auditor logic change beyond `_sum_points` now finding all bands.
- **Missing-index refusal extends the existing `AuditGroundingError` seam:** do not invent a parallel error path; route the `OperationalError`/drift into the same PII-free refusal that already guarantees "no partial report."
- **New artifact paths must be pre-covered by publish-safe:** either write under an already-listed subtree (`output/crs-audit/` style) or extend `VAULT_SUBTREES`/`VAULT_ARTIFACT_EXTS` in the same change, so the artifact is unstageable the moment it lands (mirroring the Phase-32 report).
- **Example fix conflicts with drift:** once aligned to grid ids, a conformance test must pin it so the example and the auditor can never silently diverge again (same anti-drift discipline as the P30↔P31 test-type vocabulary).

## MVP Definition

### Launch With (v4.1 core)

The hardening + the primary remediation value — the minimum that makes the milestone coherent.

- [ ] Complete higher-CLB first-language points grounding — a supported factor must produce complete, non-fabricated points.
- [ ] Confirmed sibling evidence field → reachable `additional.sibling` `SUBSTANTIATED` — closes the last advertised-but-unreachable factor.
- [ ] Clean fail-closed refusal for missing/corrupt corpus index — no more raw `internal_error`; artifact-free refusal + `doctor` hint.
- [ ] Corrected + conformance-pinned example profile — the shipped example exercises the real auditor.
- [ ] Strengthened low-quality/ambiguous extraction regressions — adversarial fixtures prove no green from a bad read.
- [ ] Grounded private remediation checklist from `GAP`/`AT-RISK` findings — the core "findings → fixes" payoff.

### Add After Validation (within v4.1)

- [ ] Opt-in, explicitly-redacted lawyer/RCIC review packet (raw docs excluded by default) — depends on the checklist landing first.
- [ ] Redaction preview / dry-run — trust-builder for the export.
- [ ] Per-item score-impact delta + aggregate-vs-cutoff on the checklist — prioritization polish (reuses existing `score_delta`/`cutoff_delta`).

### Future Consideration (v4.2+ / deferred)

- [ ] Legacy/physician arranged-employment resolver (LATER-01) — still deferred; remediation just flags job-offer `AT-RISK` with the cited repeal.
- [ ] Live DLI/PGWP eligibility lookup (LATER-02), NOC-duty semantic review (LATER-03), MEC sidecar (LATER-04) — remain deferred; these stay `AT-RISK` and become RCIC-packet review items rather than auto-resolved.
- [ ] Structured multi-recipient export profiles (e.g. different redaction presets per recipient) — only if a real second recipient type emerges.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Higher-CLB first-language points grounding | HIGH | MEDIUM | P1 |
| Confirmed sibling evidence → reachable verdict | MEDIUM | MEDIUM | P1 |
| Clean missing/corrupt-index refusal | HIGH | LOW–MEDIUM | P1 |
| Corrected + pinned example profile | MEDIUM | LOW | P1 |
| Low-quality/ambiguous extraction regressions | HIGH | MEDIUM | P1 |
| Grounded private remediation checklist | HIGH | MEDIUM | P1 |
| Redacted lawyer/RCIC review packet | HIGH | HIGH | P2 |
| Redaction preview / dry-run | MEDIUM | LOW–MEDIUM | P2 |
| Per-item score-impact delta on checklist | MEDIUM | LOW | P2 |
| Legacy job-offer resolver / DLI-PGWP / NOC-duty / MEC | LOW (deferred) | HIGH | P3 |

**Priority key:** P1 = must have for the milestone · P2 = should have, add once P1 lands · P3 = deferred/out of scope for v4.1.

## Competitor Feature Analysis

| Feature | IRCC official CRS calculator | Third-party CRS calculators / immigration blogs | Licensed RCIC / immigration lawyer | Our v4.1 Approach |
|---------|------------------------------|-------------------------------------------------|------------------------------------|-------------------|
| Substantiation against real documents | No (score input only, pre-ITA) | No | Yes (manual, expensive) | Deterministic, grounded, local, fail-closed |
| Grounded next-action remediation | No | Sometimes, ungrounded/stale, ad-supported | Yes (paid, human) | **Yes — cited to IRCC/IRPA/IRPR/PDI, private, no advice** |
| Privacy of the applicant's documents | N/A (no docs) | Poor (web forms, tracking) | Confidential but off-machine | **PII stays in a local git-ignored vault; nothing leaves by default** |
| Safe hand-off to a professional | No | No | N/A (they are the professional) | **Explicitly-redacted, opt-in packet; raw docs excluded by default** |
| Fail-closed / no false-green | N/A | No (optimistic) | Human judgement | **Yes — no `pending`/stale/ambiguous value ever greens** |
| Higher-CLB / full factor coverage | Yes (score table) | Varies, often stale | Yes | **Yes after v4.1 (complete grounded point rows)** |

**Positioning:** we sit between the free-but-ungrounded calculators and the authoritative-but-expensive human consultant — a grounded, private, fail-closed *screening* that makes the eventual human review cheaper and better-targeted (the RCIC packet), without ever pretending to *be* the human's advice.

## Concrete Testable Behaviors (acceptance checklist for the roadmap)

Grouped by feature; each is a behavior a phase can assert directly against the real CLI + real corpus/vault.

**Coverage completion**
- CLB-10-all-abilities confirmed applicant → `core.language.first` `SUBSTANTIATED` with `substantiated_points` = 136 (no-spouse) / 128 (spouse), not `None`.
- Every newly-added first-language band row passes `retrieve-what-you-cite` against the intended `crs-criteria` chunk (non-vacuous wrong-family/historical negative controls fail).
- `no_inlined_volatile_rules` self-scan over registry + auditors stays `[]` after the new rows.
- Confirmed sibling (relationship + PR/citizen status + current residence) → `additional.sibling` `SUBSTANTIATED` / 15 pts; any missing/unconfirmed/stale link → `GAP` (never fabricated).

**Operational hardening**
- `vault audit --db <nonexistent|empty|corrupt>` → `ok:false`, PII-free machine reason (e.g. `missing_index`/`AuditGroundingError`), stable non-zero exit, and **zero** artifacts (no report `.json`/`.md`, no `audit_runs`/`factor_verdicts` rows).
- `doctor`/preflight reports "corpus index missing/unreadable" as a clean status, not a traceback.
- Loading `crs-profile.example.yaml` routes every factor through the auditor dispatch with 0 unknown/unrouted ids; publish-safe self-scan on the example is clean.
- Adversarial extraction fixtures (rotated, ambiguous `A/B/YYYY`, low-text, password-protected) each classify `low_quality`/`ambiguous` → `is_audit_eligible=False` → at most `AT-RISK`, never `SUBSTANTIATED`.

**Grounded remediation**
- A report with N `GAP`/`AT-RISK` factors → checklist with exactly N items, each carrying ≥ 1 resolvable corpus `citation_id` and a `score_delta`; an all-`SUBSTANTIATED`/`N/A` report → 0 items.
- Checklist written only under the vault `output/` subtree; the `--json` envelope for the command is PII-light (counts/paths only, no applicant values, no `ev_` ids).
- Checklist carries the `SCREENING_NOTICE`; SAFE-04 denylist scan clean.

**Privacy-safe review export**
- Default packet contains 0 raw-document bytes and 0 unredacted PII fields the user did not opt into; a redaction map records what was masked.
- Packet targeted at a non-vault output path is refused (`PathEscapeError`-style); publish-safe flags packet artifacts unstageable; tracked-tree scan stays 0 violations.
- `--include-raw` requires an explicit flag, is logged, and still writes only inside the vault.
- `--dry-run` writes no file and prints the redacted (not raw) preview to stderr.

## Sources

- Shipped v4.0 code (authoritative for current behavior, HIGH): `crawler/auditors/{core,additional,spouse,transferability}.py`, `crawler/auditor.py` (`AuditGroundingError`), `crawler/audit_report.py` (`SCREENING_NOTICE`, vault-only report writer), `crawler/models/audit.py` (PII-light vs PII-bearing tiers), `crawler/searchindex.py` (read-only-index `OperationalError`/sha-drift), `crawler/extraction.py` (scan-quality/ambiguity classification), `crawler/vault.py` (`is_audit_eligible`, five-key staleness), `scripts/check_publish_safe.py` (`VAULT_SUBTREES`/`VAULT_ARTIFACT_EXTS`).
- Registry + grounding (HIGH): `crawler/data/crs_rules/{core,additional,spouse,transferability}.yaml`, `COVERAGE.md` — confirms only the CLB 9 first-language points row is grounded and the `additional.sibling` 15-pt row exists but is extraction-unreachable.
- `.planning/milestones/v4.0-MILESTONE-AUDIT.md` (HIGH) — the five carried-forward tech-debt items this milestone closes (CLB-10 points, sibling evidence, missing-index `internal_error`, example-profile factor ids, remediation+RCIC export LATER-05).
- `.planning/milestones/v4.0-REQUIREMENTS.md` + `SCREENING.md` (HIGH) — the frozen constraints (fail-closed `SUBSTANTIATED` definition, PII-vault-only, no legal advice, no cloud/vector/model/NLI) every v4.1 feature must preserve.
- `.planning/PROJECT.md` / `.planning/STATE.md` (HIGH) — v4.1 goal, active requirements, and Key Decisions (remediation/export derive only from grounded verdicts; autonomous planning).
- Domain (HIGH, corpus-grounded at implementation time): IRCC Comprehensive Ranking System criteria (per-ability CLB point table, sibling-in-Canada 15 pts) — resolved from the local authoritative corpus, not third-party sources.

---
*Feature research for: v4.1 CRS Auditor Hardening & Remediation (subsequent-milestone feature scope)*
*Researched: 2026-07-17*
