# Pitfalls Research

**Domain:** v4.1 hardening of a local, PII-safe, corpus-grounded CRS Profile ↔ Document Substantiation Auditor (post-ITA Express Entry) — closing fail-closed coverage gaps, cleaning failure surfaces, and adding grounded remediation + a redacted lawyer/RCIC review packet, all local-only / no-cloud / no-model.
**Researched:** 2026-07-17
**Confidence:** HIGH — grounded in direct inspection of the shipped v4.0 implementation (`crawler/auditor.py`, `crawler/auditors/*`, `crawler/crs_audit.py`, `crawler/crs_rules.py`, `crawler/audit_report.py`, `crawler/searchindex.py`, `crawler/grounding.py`, `crawler/vault.py`, `scripts/check_publish_safe.py`) and the v4.0 milestone audit's own `tech_debt` / `deferred` findings. The pitfalls are project-specific failure modes, not generic advice.

> **Scope note:** v4.1 is a focused v4.0.x hardening milestone. It must preserve the frozen trust path (`search` → `--cite` → grounding gate → JSON envelope), field-level confirmation, the `evidence_id` (`ev_`) vs `citation_id` (`relpath#ordinal`) namespace split, the vault-only PII boundary, deterministic (no-model) logic, and the "screening, not legal advice" framing. **Every new capability below is a fresh chance to breach one of those invariants** — that is the throughline of this document.

> **Suggested v4.1 phase vocabulary** (roadmap not yet created; used consistently below):
> - **P-COVERAGE** — Coverage Completion: ground higher-CLB first-official-language points; add a confirmed sibling-relationship evidence field/factor linkage.
> - **P-HARDEN** — Operational Hardening: convert missing/corrupt-index raw failures into stable fail-closed refusals; fix + conformance-test the example profile; strengthen extraction regressions on low-quality/ambiguous docs; kill fixture drift.
> - **P-REMEDIATE** — Grounded Remediation: derive a private, corpus-cited fix checklist strictly from `GAP`/`AT-RISK` verdicts.
> - **P-PACKET** — Redacted Review Export: opt-in, explicitly redacted lawyer/RCIC packet inside the vault, raw docs excluded by default.
> - **P-CONFORM (cross-cutting)** — Safety & conformance: extend the SAFE-01..04 suite to cover every new surface.

---

## Critical Pitfalls

### Pitfall 1: False completeness — a "SUBSTANTIATED"/complete-looking result that silently hides a fabricated or missing number

**What goes wrong:**
A factor renders as green/complete while a point value it depends on was never actually grounded. The shipped example is the v4.0 tech-debt item: first-official-language **points** rows ground CLB 9 but not CLB 10 (`crawler/data/crs_rules/core.yaml` `core.language.first.points` only carries `level: 9` entries), so a candidate whose scores convert to CLB 10 gets `verdict="SUBSTANTIATED"` with `substantiated_points=None` (see `core._sum_points` → returns `None` when any ability has no grounded row; `_grounded_points` returns `None` for an uncovered level). In v4.1 the same trap reappears the moment we (a) add higher-CLB points, (b) add a sibling factor, or (c) build a remediation checklist that treats "no GAP found" as "complete."

**Why it happens:**
The audit spine separates *verdict* from *points*: a SUBSTANTIATED verdict can carry `substantiated_points=None` (fail-closed on the number, open on the verdict). That is correct fail-closed behaviour for the *math*, but a naive completeness/remediation/packet layer that reads only the verdict string will report "all good" while the point contribution is silently absent — and a total built from `sum(points or 0 ...)` (`auditor.run_full_audit`) quietly under-counts without flagging it.

**How to avoid:**
- When adding higher-CLB grounding (P-COVERAGE), require the *points* row to cover every CLB level the *conversion* rows can emit — pin them set-equal with an anti-drift test (mirror the existing `testtypes.py`↔registry `accepted_enum` pin).
- Introduce an explicit `points_incomplete`/`ungrounded_points` signal so `SUBSTANTIATED` + `substantiated_points is None` is a **distinct, surfaced state**, never collapsed into "complete." The remediation checklist (P-REMEDIATE) and packet (P-PACKET) must treat it as an unresolved item, not a pass.
- Remediation must be built from the presence of a verified `GAP`/`AT-RISK` **and** from "SUBSTANTIATED-but-unpriced," never from "no GAP row exists."

**Warning signs:**
- A factor card with `verdict="SUBSTANTIATED"` and `substantiated_points: null`.
- `substantiated_total` moves when a conversion changes CLB band but no card flips verdict.
- A remediation/packet run that emits zero action items for a profile that has an unpriced factor.

**Verification:**
A conformance case (extend SAFE-01) that drives a CLB-10 (and every grounded CLB) applicant end-to-end and asserts either a priced SUBSTANTIATED **or** an explicitly-flagged `ungrounded_points` state — never a silent `None` folded into "complete." Grid-level test: for each `points_by_level` `level`, a matching conversion output exists and vice-versa.

**Phase to address:** P-COVERAGE (add + pin the grounding); P-CONFORM (assert the surfaced state); consumed by P-REMEDIATE / P-PACKET.

---

### Pitfall 2: Stale / historical policy grounding — citing a real chunk that no longer states current policy

**What goes wrong:**
The grounding gate proves a quote is a verbatim substring of a real, un-drifted corpus chunk — it does **not** prove the chunk is current or on-point (the `grounding.py` HONESTY BOUNDARY says so explicitly). A rule can therefore be "grounded" against a superseded IRCC page, a pre-repeal Ministerial Instruction, or last year's round table, and the auditor/remediation/packet will cite it authoritatively. The arranged-employment repeal (2025-03-25, RULE-05) is the canonical live example already defended; v4.1's new higher-CLB points and any remediation "how to fix" text re-open the same wound if they cite a stale points/threshold chunk.

**Why it happens:**
The corpus is a curated snapshot; policy dates and points tables are volatile; retrieval is keyword FTS5 with no recency awareness. A remediation checklist that paraphrases requirement text (validity windows, "get a new IELTS if expired") is especially exposed because it turns a cited *rule* into forward-looking *advice* that ages badly.

**How to avoid:**
- Keep every volatile figure inside grounded `machine_check` payloads with `volatility` + `crawl_date` metadata (already enforced by `no_inlined_volatile_rules`); extend the ban to remediation/packet prose so no window/points/date literal is inlined there either.
- Prefer date-guarded rules (the existing `within_validity` / `arranged_employment_guard` pattern that reads the policy date from the row) over free-text advice.
- Remediation text should quote the *rule's own cited span* and its `crawl_date`, not synthesize new claims. Never let P-REMEDIATE or P-PACKET emit a requirement statement that is not a resolvable citation.
- Add negative controls (SAFE-03 already does "wrong-family/historical/adjacent"): every new rule (higher-CLB points, sibling) needs a historical/adjacent negative control proving it grounds the *intended current* chunk.

**Warning signs:**
- A citation whose `crawl_date` is old relative to a known policy change.
- Remediation prose containing a number or deadline that appears nowhere in a grounded `machine_check`.
- A rule that grounds against `guidance/express-entry-year-end-report` or a `grid` family (already deny-listed in `core.yaml` selectors for a reason).

**Verification:**
Extend SAFE-03 retrieve-what-you-cite with a per-rule historical/adjacent negative control for the new rows, and a static scan asserting no volatile literal appears in remediation/packet renderers (reuse the `no_inlined_volatile_rules` scanner over the new modules).

**Phase to address:** P-COVERAGE + P-REMEDIATE (rules/prose); P-CONFORM (negative controls + literal scan).

---

### Pitfall 3: Evidence-to-factor mislinking — the right document proving the wrong factor (or nothing)

**What goes wrong:**
A confirmed value gets attributed to the wrong CRS factor, so a factor shows SUBSTANTIATED on evidence that does not actually belong to it (a false green), or real evidence is stranded UNLINKED (a false GAP). This is not hypothetical: v4.0's integration audit found exactly this — the original `ORDER BY factor_id LIMIT 1` linkage bound evidence to the alphabetically-first factor (BLOCKER A), fixed by the `_DOC_TYPE_FACTOR` map scoped to *claimed* factors (gap-closure 30-05). v4.1 re-enters this danger zone twice: adding a **sibling-relationship** field (a brand-new doc-type→factor mapping) and strengthening extraction on ambiguous docs (first-vs-second language, multi-employer letters).

**Why it happens:**
Extraction is heuristic/regex and one physical document can bear on several factors (a passport → age *and* identity; a language report → first *or* second language). Linkage is a property of the document type, resolved once; a new/edited mapping or an ambiguous doc can silently point evidence at the wrong factor. The `--factor` override exists precisely because first-vs-second language is ambiguous.

**How to avoid:**
- Add the sibling field to the shared `testtypes.py`/`_DOC_TYPE_FACTOR` vocabulary and its factor linkage in **one** place, scoped to claimed factors, with the fail-closed default of UNLINKED for unclaimed/injected targets (preserve the 30-05 invariant: an injected target contaminates nothing).
- Never let extraction default-link an ambiguous document; require the `--factor` disambiguation and leave it UNLINKED otherwise.
- Reuse the real `import→extract→confirm→audit` seam test (`test_full_audit_real_seam.py`) — extend it for sibling and multi-doc work, and assert **no cross-factor contamination** (a sibling document must not green the nomination or age factor).

**Warning signs:**
- A factor SUBSTANTIATED with an `evidence_ids` list whose backing document type doesn't match the factor.
- Sibling evidence appearing in another factor's card.
- A "works in the unit test but not through the real CLI" smell — the exact v4.0 blind spot (a structural test that bypasses the real `extract` seam).

**Verification:**
Extend the real-seam E2E test to cover sibling + multi-employer work; assert per-factor `evidence_ids` only reference the correct document type; add an anti-drift pin for the sibling doc-type→factor entry.

**Phase to address:** P-COVERAGE (sibling linkage); P-HARDEN (extraction regressions); P-CONFORM (real-seam + contamination test).

---

### Pitfall 4: Redaction failure — the "redacted" packet still leaks PII

**What goes wrong:**
The opt-in lawyer/RCIC review packet is meant to be *explicitly redacted*, but PII survives: a confirmed value snapshot leaks in (the auditor already builds PII-bearing `_confirmed_snapshot` dicts and vault-only `.md` cards), an `ev_` evidence id or a document filename/sha slips through, or "redacted" is implemented as a denylist that misses a field. The whole vault design keeps this data vault-only for a reason — a packet is the first artifact intended to *leave the applicant's hands* (to a lawyer), so a redaction miss is a real disclosure, not just a repo-hygiene issue.

**Why it happens:**
Redaction-by-removal is fragile: it's easy to build the packet from the rich `PrivateFactorCard` / `PrivateAuditReport` (which carry claimed/confirmed values, `ev_` ids, evidence pointers, aggregated years, DOB→age, benchmarks) and try to strip PII afterward. Denylists miss fields; new fields added in P-COVERAGE (sibling relationship, higher-CLB benchmarks) won't be in the denylist. The public envelope (`to_public_envelope` / `PublicAuditEnvelope`) is already the vetted PII-light projection — bypassing it to "include a bit more detail for the lawyer" is the trap.

**How to avoid:**
- **Allowlist, not denylist.** Build the packet from an explicit, closed set of redaction-safe fields (verdict, reason_code, factor_id, rule citation ids, generic corpus-cited claim text) — the same discipline as `PublicAuditEnvelope`. A field is excluded unless it is explicitly whitelisted as safe.
- Make redaction a *typed projection* the way `to_public_envelope` is, so adding a new PII field can't silently appear in the packet (a new field defaults to excluded).
- The applicant explicitly *opts in* per finding; default is exclude. Redaction level (e.g., "share verdict + citation only" vs "share confirmed value X") must be an explicit per-item choice, never a global "share everything."
- Run the packet through the same publish-safe / PII scanner (`scripts/check_publish_safe.py` patterns) before it is considered valid.

**Warning signs:**
- Packet built by copying `PrivateFactorCard`/`report.model_dump()` and deleting keys.
- An `ev_` id, DOB, raw test score, employer name, or file sha appearing in packet output.
- A new profile/evidence field added without a corresponding redaction decision.

**Verification:**
A conformance test (extend SAFE-02) that generates a packet for a fully-populated synthetic vault and asserts **no** `ev_`, no confirmed raw value, no filename/sha, no DOB reaches the packet; a schema test that a newly-added model field is excluded-by-default (fails closed) until explicitly whitelisted.

**Phase to address:** P-PACKET (allowlist projection); P-CONFORM (leak assertion + default-exclude schema test).

---

### Pitfall 5: Accidental raw-document export — the packet ships the actual scans by default

**What goes wrong:**
The requirement is raw documents **excluded by default**; a packet build instead copies/attaches the content-addressed raw files (`files/raw/<sha256><ext>`), rendered pages (`files/rendered/`), or OCR text (`files/text/`) — or writes the packet *outside* the vault where the publish-safe perimeter doesn't cover it. Because raw docs are the highest-sensitivity artifact (passports, biometrics-adjacent identity docs), an accidental export is the worst-case PII incident this project exists to prevent.

**Why it happens:**
"Give the lawyer everything they need" nudges toward attaching source files. The vault already stores raw docs on disk (not as BLOBs), so a packet builder that walks `files/raw/` is a one-line mistake. Writing the packet to a user-supplied `--out` path outside `personal/candidates/<id>/` escapes the `.gitignore` + `check_publish_safe` coverage that only knows the `VAULT_SUBTREES` allowlist.

**How to avoid:**
- Raw/rendered/text inclusion is **opt-in per document, off by default**, and even when opted-in the packet must stage inside the vault (`resolve_within(vault.root, ...)`), never to an arbitrary path — reuse the `run_audit` discipline (every path re-anchored through `paths.resolve_within`, rejecting `..`/symlink escapes; refuse non-vault output like `--json ground` already refuses non-`personal/` output).
- Add the packet subtree to `VAULT_SUBTREES` / `VAULT_ARTIFACT_EXTS` in `check_publish_safe.py` **at the same time** the writer lands, so the artifact is publish-safe-covered the moment it exists (the v4.0 pattern for `output/crs-audit/`).
- By default reference documents by generic label/evidence pointer, not by attaching bytes.

**Warning signs:**
- A packet builder importing/opening anything under `files/raw`, `files/rendered`, `files/text`.
- A packet `--out`/destination argument that accepts an absolute or repo-relative path.
- A new packet file extension/subtree not present in the publish-safe allowlist.

**Verification:**
SAFE-02 extension: assert a default packet contains **no** raw bytes and no reference resolvable to a raw file; a path-escape test that a non-vault destination is refused (`PathEscapeError`); a publish-safe self-scan proving the new subtree is covered and a planted raw file under it is flagged unstageable.

**Phase to address:** P-PACKET (default-exclude + vault-only staging); P-CONFORM (publish-safe coverage + path-escape refusal).

---

### Pitfall 6: A secondary ungrounded advice path — remediation/packet becomes a second, unaudited trust path

**What goes wrong:**
The remediation checklist or packet starts *generating* guidance ("you should get a provincial nomination," "ask your employer to reword the reference letter," "your CLB will likely rise if...") that is not derived from a grounded verdict + citation. This creates a second output surface that looks authoritative but bypasses the frozen `search` → gate → envelope trust path — precisely the thing the milestone's key decision forbids ("[v4.1] Remediation and professional-review exports derive only from existing grounded verdicts ... prevents a second ungrounded advice path").

**Why it happens:**
Remediation is where the temptation to be "helpful" is highest, and where it's easy to slip from *reporting a grounded GAP* into *inventing next steps*. Free-text "how to fix" naturally drifts into legal-adjacent advice and volatile specifics. The gate only checks `claims[]`; `prose`/`basis` are never citation-checked, so ungrounded advice can ride along in prose fields undetected.

**How to avoid:**
- Remediation is a **pure projection of existing verdicts**: for each `GAP`/`AT-RISK`/unpriced factor, emit only (a) the factor, (b) the reason_code, (c) the rule's own grounded citation + quote, (d) a fixed, template-bound action phrase keyed to the reason_code — no synthesized requirements, no new claims.
- Route any requirement statement through the same grounding gate (`grounding.check_answer`); if it can't be expressed as a resolvable cited claim, it can't be in the output.
- Keep it deterministic: same verdicts in → same checklist out. No model, no ranking heuristics, no "likelihood."
- Explicitly forbid outcome prediction / eligibility rulings (SAFE-04 framing already defines this boundary).

**Warning signs:**
- Remediation text with a claim that has no citation, or a citation added post-hoc to justify generated advice.
- Action items that vary run-to-run for identical input.
- Language like "you will likely," "we recommend applying for," "your chances."

**Verification:**
A test that every requirement-bearing line in remediation/packet output is a gate-passing cited claim (reuse `grounding.check_answer`), and a determinism test (same vault → byte-identical checklist). SAFE-04 denylist scan extended over the new renderers.

**Phase to address:** P-REMEDIATE (projection-only); P-PACKET (no synthesized advice); P-CONFORM (gate-every-claim + determinism).

---

### Pitfall 7: Unstable / leaky error surfaces — a raw traceback where a clean fail-closed refusal belongs

**What goes wrong:**
A missing or corrupt corpus index (or a missing vault, or a locked SQLite) surfaces as a raw `internal_error` / traceback instead of a stable, actionable refusal. This is a *named* v4.0 tech-debt item: "Empty/missing corpus index surfaces as a raw `internal_error` rather than a clean `AuditGroundingError` refusal." Today `searchindex.search`/`resolve` raise `sqlite3.OperationalError` ("unable to open database file") for a missing/typo'd DB path; the `vault audit` handler only catches `AuditGroundingError` and `PathEscapeError`, so an index problem falls through to the last-resort `main()` catch-all that emits a generic `internal_error`/exit 4 with the exception text on stdout and a traceback on stderr.

**Why it happens:**
The grounding gate assumes the index exists; the auditor only anticipated grounding failures, not the *prerequisite* (index/DB) being absent. The catch-all in `main()` is a safety net for pure-JSON output, not a substitute for a typed, stable refusal. Two risks: (a) an unstable/opaque error hurts operator trust and automation (agents key off `error.code`), and (b) a traceback on stderr can echo a machine path (a publish-safety concern; `check_publish_safe` rejects absolute home-directory prefixes in tracked files, but a runtime stderr leak is still undesirable).

**How to avoid:**
- Add a **preflight** for grounding prerequisites: detect a missing/corrupt/empty index (and missing vault DB) *before* running the audit and raise a typed, PII-free refusal (a new `AuditGroundingError` subtype or a dedicated `missing_grounding_prerequisite` error code) with a stable code + actionable message ("run `corpus-crawler index` first"), mapped to a deterministic exit code — the way `doctor` already maps a missing dependency to `missing_dependency`/exit 3 rather than `internal_error`.
- Keep the failure **artifact-free**: preserve the SC5 ordering (compute/verify before any write) so a prerequisite failure leaves zero report/rows — verify no partial `audit_runs` row is minted.
- Make the error message PII-free (rule ids/reasons/paths-relative only) and stable across runs.
- Distinguish "index corrupt" (sha-drift → `resolve` returns None today) from "index missing" (OperationalError) so the refusal is actionable.

**Warning signs:**
- `error.code == "internal_error"` for a missing/empty index instead of a typed code.
- A traceback on stderr mentioning an absolute path or sqlite internals.
- A half-written report or an orphan `audit_runs` row after a failed run.

**Verification:**
Tests driving `vault audit`/`vault audit --all` against (a) a missing index path, (b) a 0-byte/corrupt DB, (c) a missing vault, each asserting a stable non-internal error code, non-zero deterministic exit, PII-free message, and **zero artifacts** (no report file, no `audit_runs`/`factor_verdicts` rows). Add to SAFE-01/SAFE-02.

**Phase to address:** P-HARDEN (typed refusals + preflight); P-CONFORM (failure-surface + artifact-free tests).

---

### Pitfall 8: Schema / fixture drift — the shipped example and conformance fixtures diverge from the real grid

**What goes wrong:**
The tracked example profile and test fixtures no longer match the auditor's real factor ids / extraction contracts, so the "safe example" doesn't actually exercise the real path — or worse, appears to work while testing nothing. This is a *named* v4.0 tech-debt item: `personal.example/crs-profile.example.yaml` ships **underscored** factor ids (`core_age`, `core_education`, `core_first_language`, `spouse_education`) while the auditor grid uses **dotted** ids (`core.age`, `core.education`, `core.language.first`, `spouse.education` — see `auditors.FULL_GRID_FACTORS`). A profile loaded from that example never matches a grid factor, so `audit_one` treats each as unclaimed → N/A `not_claimed`, and the example silently audits to nothing.

**Why it happens:**
Two id vocabularies drifted (underscore vs dotted) with no pin between the example and the grid; the example predates the dispatch-spine factor ids. The v4.0 integration blockers were the *same* class of bug (test-type vocabulary drift P30↔P31, evidence-linkage drift) masked by tests that bypassed the real seam. Adding higher-CLB and sibling factors in v4.1 multiplies fixture surface area.

**How to avoid:**
- Correct the example to the real dotted grid ids and add a **pin test**: every `factor_id` in `personal.example/crs-profile.example.yaml` must be in `auditors.FULL_GRID_FACTORS` (and cover every group), and a conformance run over the example must produce non-N/A verdicts for its claimed factors. Mirror the existing `testtypes.py`↔registry anti-drift pin.
- Treat the example profile as a first-class conformance fixture, not documentation — drive the real `profile set → audit` path over it in CI.
- When P-COVERAGE adds sibling/higher-CLB, update the example + fixtures in the same change and extend the pin.

**Warning signs:**
- The example profile audits to all-N/A / `not_claimed`.
- A factor id present in the example but absent from `FULL_GRID_FACTORS` (or vice-versa).
- A fixture that green-passes but never reaches the decider it claims to test.

**Verification:**
A pin test (example ids ⊆ grid ids, all four groups represented) + an end-to-end conformance run over the corrected example asserting real verdicts (not blanket N/A). Reuse the anti-drift test pattern already protecting the P30↔P31 seam.

**Phase to address:** P-HARDEN (fix example + fixtures, add pin); P-COVERAGE (keep pin current for new factors); P-CONFORM (example-as-fixture E2E).

---

### Pitfall 9: Misleading professional-review framing — the packet reads as a legal opinion / green light

**What goes wrong:**
The lawyer/RCIC packet is framed (in wording, structure, or the mere fact of "here is my substantiated file") as an eligibility opinion, an approval prediction, or legal advice — undermining SAFE-04 ("output is substantiation *screening*, not legal advice"). A `SUBSTANTIATED`-heavy packet can read as "my case is approved," and a packet addressed *to a professional* can imply the tool has done the professional's job. Overclaiming here is both a trust failure and a real-world harm (an applicant relying on it in lieu of counsel).

**Why it happens:**
The narrow, deterministic meaning of `SUBSTANTIATED` (confirmed + audit-eligible + met threshold + grounded cited rule — *a deterministic match, nothing more*, per `audit_report.SCREENING_NOTICE`) is easy to lose when results are packaged for an authority figure. The packet's purpose ("review by a lawyer/RCIC") invites outcome language. AT-RISK items (semantic/NOC-duty fit, authenticity, officer discretion) can be under-emphasized when the headline is a substantiated total vs cutoff.

**How to avoid:**
- Render the existing `SCREENING_NOTICE` (or a packet-specific equivalent) prominently in **every** packet, and keep the narrow `SUBSTANTIATED` definition + the always-AT-RISK scope (semantic/NOC-duty/authenticity/officer discretion) explicit and unmissable.
- Frame the packet as "material *for* your professional's review," never "conclusions" — the cutoff comparison is an arithmetic delta, "not an eligibility ruling or legal advice" (existing `audit_report` wording).
- Keep the SAFE-04 denylist scan (negated "not legal advice" phrasing only) over the packet renderer; forbid outcome/eligibility verbs (tie to Pitfall 6).
- Do not let the packet imply completeness (tie to Pitfall 1): unpriced/undecided items must be visible.

**Warning signs:**
- Packet text asserting eligibility, approval odds, or "ready to submit."
- The screening notice missing, buried, or softened in the packet.
- A packet that lists only SUBSTANTIATED factors and omits AT-RISK/GAP context.

**Verification:**
SAFE-04 extension over the packet renderer: assert the screening notice is present, the narrow-SUBSTANTIATED + AT-RISK-scope language renders, and no eligibility/outcome verb appears (denylist scan). Human-eyeball checkpoint of one rendered packet (advisory).

**Phase to address:** P-PACKET (framing); P-CONFORM (SAFE-04 over the packet).

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Build remediation/packet from the rich `PrivateFactorCard`/`report.model_dump()` and strip PII after | Fast, "all the data is right there" | Denylist redaction misses new fields → PII leak (Pitfall 4) | **Never** — build from an allowlisted typed projection like `to_public_envelope` |
| Treat `SUBSTANTIATED` string as "complete" in remediation/packet | Simple check | Hides `substantiated_points=None` / unpriced factors (Pitfall 1) | Never — must also inspect points/priced state |
| Let the `main()` catch-all handle missing/corrupt index | No new code | Opaque `internal_error`, poor operator trust, possible stderr path leak (Pitfall 7) | Only as the *last* net; a typed preflight refusal must exist first |
| Add higher-CLB points rows without pinning to the conversion range | Ships coverage fast | Silent gaps at untested CLB levels (Pitfall 1) | Never without the set-equal anti-drift pin |
| Keep the underscored example profile "because docs" | No churn | Example tests nothing; masks real regressions (Pitfall 8) | Never — the example must be a real conformance fixture |
| Synthesize "how to fix" advice text for friendliness | Nicer UX | Second ungrounded trust path; volatile/legal drift (Pitfalls 2, 6, 9) | Never — projection of grounded verdicts only |
| Attach raw docs to the packet "so the lawyer has everything" | Convenient | Worst-case PII export (Pitfall 5) | Only opt-in per-document, staged inside the vault, publish-safe-covered |
| Add a sibling factor by hand-linking evidence outside `_DOC_TYPE_FACTOR` | Quick green | Cross-factor contamination / false green (Pitfall 3) | Never — one linkage source, claimed-scoped, fail-closed UNLINKED |

## Integration Gotchas

Common mistakes when connecting to the shipped subsystems.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Grounding gate (`grounding.check_answer`) | Assuming a passing quote means the claim is *current/true* | It only proves verbatim-substring in an un-drifted chunk; add recency/negative controls (Pitfall 2). Put requirement text in `claims[]`, never in unchecked `prose`/`basis` |
| Search index (`searchindex.search`/`resolve`) | Letting a missing/corrupt DB raise `OperationalError` into the generic catch-all | Preflight + typed `missing_grounding_prerequisite` refusal, stable code, artifact-free (Pitfall 7) |
| Public projection (`to_public_envelope`/`PublicAuditEnvelope`) | Bypassing it to add "a little more detail" to the packet | Extend the *typed allowlist* projection; new PII fields default excluded (Pitfall 4) |
| Vault paths (`paths.resolve_within`) | Writing packet/checklist to a user `--out` path | Re-anchor every write under `vault.root`; refuse non-vault destinations (`PathEscapeError`) (Pitfall 5) |
| Publish-safe scanner (`scripts/check_publish_safe.py`) | Landing a new artifact subtree/ext without updating the allowlist | Add the new subtree to `VAULT_SUBTREES`/`VAULT_ARTIFACT_EXTS` in the same change; self-scan a planted file |
| Evidence linkage (`_DOC_TYPE_FACTOR`, claimed-scoped) | Adding sibling/ambiguous docs with ad-hoc linkage | One linkage map, scoped to claimed factors, UNLINKED-by-default; extend the real-seam test (Pitfall 3) |
| Registry anti-drift pins (`testtypes.py` ↔ registry enum) | Adding rules/fixtures without extending the pin | Every new vocabulary/level/example id gets a set-equal pin test (Pitfalls 1, 8) |

## Performance Traps

Patterns that work at small scale but fail as usage grows. *(This is a single-user, local-first, small-corpus tool — scale is documents-per-candidate and rules-per-registry, not users. Traps are correctness/latency, not throughput.)*

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Re-grounding every rule per factor per run (`validate_registry` → gate → `resolve` per consumed row) | Audit latency grows with grid × rules; `--all` noticeably slow | Cache resolved chunks per run; the gate is already pure/read-only — memoize within one `run_full_audit` | Full-grid audits on a large registry / many re-runs during remediation iteration |
| Full document re-render/re-extract on every audit | Slow confirm→audit loops on multi-page scans | Extraction already writes `pending` values once; ensure audit reads confirmed values, never re-extracts | Multi-employer / many-page evidence sets |
| Packet built by walking all vault artifacts | Grows with document count; risks pulling raw files | Build from selected findings only, allowlisted fields, no filesystem walk of `files/*` | Vaults with many imported documents |
| Work aggregation over many employment letters (`aggregate_work`) | Overlap/double-count edge cases as periods grow | Keep the no-overlap aggregation + per-document grouping; regression-test many overlapping periods | Applicants with long/complex work histories |

## Security Mistakes

Domain-specific security issues (this domain = local PII custody of immigration documents on a repo intended for public sharing).

| Mistake | Risk | Prevention |
|---------|------|------------|
| Packet redaction as a denylist | PII (DOB, scores, names, `ev_` ids) leaks to a third party | Allowlist typed projection; new fields excluded by default (Pitfall 4) |
| Packet/checklist written outside `personal/candidates/<id>/` | Artifact escapes `.gitignore` + publish-safe perimeter; PII can be committed/pushed | `resolve_within` vault-only staging; refuse non-vault output (Pitfall 5) |
| Raw docs attached to packet by default | Highest-sensitivity scans leave the machine | Off by default, opt-in per doc, vault-staged, publish-safe-covered (Pitfall 5) |
| New vault artifact subtree not added to `check_publish_safe.py` | A PII file becomes stageable/pushable | Extend `VAULT_SUBTREES`/`VAULT_ARTIFACT_EXTS` + self-scan a planted file (VAULT-04 discipline) |
| Traceback/stderr leaking absolute machine paths on error | Machine path / partial PII disclosure; publish-safety noise | Typed PII-free refusals; keep messages relative + id-only (Pitfall 7) |
| `ev_` (vault) vs `citation_id` (corpus) namespaces blurred in new output | Candidate evidence treated as citable authority, or corpus id leaks a vault pointer | Keep the structural split; the spine attaches ids, deciders/remediation never mint them (existing invariant) |
| Corpus/PDF as an attack surface (a malicious PDF during extraction) | Local code exec / resource exhaustion during render/OCR | Keep extraction local, dependency-light, quarantined; scan-quality preflight (`doctor`); never auto-execute embedded content |

## UX Pitfalls

Common user-experience mistakes in this domain (single applicant preparing a high-stakes e-APR).

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Showing a green total that hides an unpriced factor | False confidence → submits with a real gap | Surface `ungrounded_points`/undecided items explicitly (Pitfall 1) |
| Opaque `internal_error` when the index is missing | User stuck, no idea to run `index` | Actionable typed refusal ("run `corpus-crawler index` first") (Pitfall 7) |
| Remediation that reads as legal advice | User skips their lawyer / over-relies | Screening framing, projection-only, cite-or-omit (Pitfalls 6, 9) |
| Packet that looks like an approval | Applicant misreads screening as eligibility | Prominent screening notice + AT-RISK scope in every packet (Pitfall 9) |
| Bulk "confirm all" convenience | Rubber-stamps unread extracted values → false greens | Keep per-field confirm (no bulk confirm-all — existing decision); don't add a bulk path in remediation |
| Silent example profile that audits to nothing | User copies a "working" example that tests nothing | Corrected example is a live conformance fixture (Pitfall 8) |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Higher-CLB points grounding:** Often missing — a `SUBSTANTIATED` verdict with `substantiated_points: null` for CLB levels the conversion emits but the points row doesn't cover. Verify points rows are set-equal to the conversion range (pin test).
- [ ] **Sibling factor:** Often missing — a doc-type→factor linkage entry, claimed-scope guard, and real-seam contamination test. Verify sibling evidence greens *only* the sibling factor.
- [ ] **Missing/corrupt-index refusal:** Often missing — a typed error code + preflight; still surfaces as `internal_error`. Verify a stable code, non-zero exit, PII-free message, and **zero artifacts**.
- [ ] **Example profile:** Often missing — dotted-id correction + pin. Verify it audits to real verdicts, not blanket N/A.
- [ ] **Remediation checklist:** Often missing — a gate-check on every requirement line + determinism. Verify no uncited claim and byte-identical output for identical input.
- [ ] **Packet redaction:** Often missing — default-exclude for new fields + a leak assertion. Verify no `ev_`, DOB, raw score, filename/sha, or raw bytes reach the packet.
- [ ] **Packet staging:** Often missing — vault-only path enforcement + publish-safe coverage. Verify a non-vault destination is refused and the new subtree is in the allowlist.
- [ ] **Packet framing:** Often missing — the screening notice + AT-RISK scope. Verify both render in every packet and no eligibility/outcome verb appears.
- [ ] **SAFE conformance:** Often missing — new surfaces (remediation, packet, prerequisite failures) added to SAFE-01..04. Verify the release gate (`scripts/run_conformance.py`) exercises them.

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| False completeness (unpriced green) | MEDIUM | Add the missing grounded points row + pin; re-run audit; the fail-closed `None` means no fabricated number shipped, so no data corruption — just under-count to correct |
| Stale/historical policy cited | MEDIUM | Re-crawl the affected family; update the rule row's citation + `crawl_date`; add a historical negative control; re-run SAFE-03 |
| Evidence mislinking | MEDIUM | Fix the `_DOC_TYPE_FACTOR` entry (claimed-scoped); re-confirm affected values; extend real-seam test; audit stays fail-closed until re-linked |
| Redaction leak (packet already generated) | HIGH | Treat as a disclosure: the vault artifact is local, but if a packet was shared, notify the applicant; fix to allowlist projection; add leak test; regenerate |
| Raw-doc export | HIGH | Same disclosure handling; switch to reference-by-pointer default; add publish-safe coverage + path-escape refusal |
| Ungrounded advice shipped | MEDIUM | Strip to projection-only; gate every requirement line; add determinism + gate tests |
| Opaque error surface | LOW | Add the typed preflight refusal + tests; no data impact (failure was already artifact-free/fail-closed) |
| Schema/fixture drift | LOW | Correct ids, add the pin test; drift is caught at test time, not in real applicant data |
| Misleading framing | LOW | Add/prominently render the screening notice; denylist scan; regenerate packet |

## Pitfall-to-Phase Mapping

How the suggested v4.1 phases should address these pitfalls. *(Phase numbers TBD — roadmap not yet created; v4.0 ended at Phase 34, so v4.1 likely begins ~Phase 35.)*

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. False completeness | P-COVERAGE (+ P-CONFORM) | CLB-range set-equal pin; E2E asserts priced-or-flagged, never silent `None` |
| 2. Stale/historical policy | P-COVERAGE, P-REMEDIATE (+ P-CONFORM) | Per-rule historical/adjacent negative control; `no_inlined_volatile_rules` over new renderers |
| 3. Evidence-to-factor mislinking | P-COVERAGE, P-HARDEN (+ P-CONFORM) | Real-seam E2E for sibling/multi-doc; per-factor `evidence_ids` type check; no cross-factor contamination |
| 4. Redaction failure | P-PACKET (+ P-CONFORM) | SAFE-02 leak assertion; default-exclude schema test for new fields |
| 5. Accidental raw-doc export | P-PACKET (+ P-CONFORM) | Default packet has no raw bytes; non-vault destination refused; publish-safe covers new subtree |
| 6. Secondary ungrounded advice path | P-REMEDIATE, P-PACKET (+ P-CONFORM) | Every requirement line gate-passes; determinism (byte-identical) test |
| 7. Unstable error surface | P-HARDEN (+ P-CONFORM) | Missing/corrupt/empty-index + missing-vault tests: stable code, non-zero exit, PII-free, zero artifacts |
| 8. Schema/fixture drift | P-HARDEN, P-COVERAGE (+ P-CONFORM) | Example ids ⊆ grid ids pin; example-as-fixture E2E produces real verdicts |
| 9. Misleading professional-review framing | P-PACKET (+ P-CONFORM) | SAFE-04 over packet: notice present, AT-RISK scope renders, no eligibility/outcome verb |

## Sources

- **Direct codebase inspection (HIGH):** `crawler/auditor.py` (`audit_one`/`run_full_audit`, `AuditGroundingError` as sole error surface, `sum(points or 0)` totalling); `crawler/auditors/__init__.py` (`FULL_GRID_FACTORS` dotted ids, `_default_decider` fail-closed AT-RISK); `crawler/auditors/core.py` (`_sum_points`/`_grounded_points` returning `None`, `_confirmed_snapshot` PII-bearing, `decide_age` DOB→age); `crawler/auditors/additional.py` (`decide_sibling` documented GAP — no sibling field yet; `decide_job_offer` RULE-05 guard); `crawler/crs_audit.py` (`score_factor`, `to_clb`, `within_validity`, `arranged_employment_guard`); `crawler/crs_rules.py`; `crawler/data/crs_rules/core.yaml` (`core.language.first.points` grounds CLB 9 only; deny-listed grid/year-end families); `crawler/audit_report.py` (`SCREENING_NOTICE`, vault-only PII-bearing markdown, `run_audit` fail-closed ordering, `resolve_within` staging); `crawler/searchindex.py` (`search`/`resolve` raise `OperationalError` on missing DB, sha-drift→None); `crawler/grounding.py` (HONESTY BOUNDARY: resolvability ≠ semantic truth; only `claims[]` checked); `crawler/cli.py` (`_cmd_*` catch set, `main()` last-resort `internal_error` catch-all); `crawler/vault.py` (per-field confirm, `audit_eligible_values`, `files/raw` content-addressed); `scripts/check_publish_safe.py` (`VAULT_SUBTREES`/`VAULT_ARTIFACT_EXTS` allowlist); `personal.example/crs-profile.example.yaml` (underscored ids).
- **v4.0 milestone audit tech-debt / deferred (HIGH):** `.planning/milestones/v4.0-MILESTONE-AUDIT.md` (higher-CLB CLB-10 points gap; sibling-evidence GAP; missing-index raw `internal_error`; example-profile factor-id verification; integration BLOCKERs A/B — evidence mislinking + test-type vocabulary drift, closed by gap-closure 30-05 and `test_full_audit_real_seam.py`).
- **Project constraints & decisions (HIGH):** `.planning/PROJECT.md` (no-PII-in-repo, no-cloud/no-model, grounded-only, screening-not-legal-advice; v4.1 key decisions — close fail-closed gaps first, remediation/exports derive only from grounded verdicts); `.planning/STATE.md` (frozen trust path, `evidence_id` vs `citation_id` split, per-field confirm, deferred LATER-05 packet); `.planning/milestones/v4.0-REQUIREMENTS.md` (SAFE-01..04, out-of-scope: semantic/NLI, vectors, cloud OCR); `SCREENING.md` (SAFE-04 framing).

---
*Pitfalls research for: v4.1 CRS Auditor Hardening & Remediation (local-only, no-cloud, no-model)*
*Researched: 2026-07-17*
