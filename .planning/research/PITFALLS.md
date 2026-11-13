# Pitfalls Research

**Domain:** v5.0 Grounded Eligibility & Policy Edge-Case Screening — adding five NEW screens (MEC / POLICY / STUDY / NOC / SAFE) to an already-shipped, local-first, PII-safe, corpus-grounded, fail-closed post-ITA Express Entry auditor (851 tests, PASS SAFE-01..08). The subject is **integration risk**: how adding program-eligibility + policy edge-case *screening* to THIS grounded/fail-closed system can silently break its trust guarantees.
**Researched:** 2026-07-17
**Confidence:** HIGH — every pitfall below is tied to a real, inspected seam (`crawler/crs_audit.py::arranged_employment_guard`, `crawler/crs_rules.py::no_inlined_volatile_rules`/`validate_registry`/`retrieve_what_you_cite`, `crawler/models/crs_rules.py::MachineCheck`/`VolatilityMeta`, `crawler/auditors/__init__.py::_default_decider`/`resolve`, `crawler/auditors/additional.py::decide_study`/`decide_job_offer`, `crawler/index_health.py::probe_index`, `crawler/vault.py::is_audit_eligible`, `scripts/check_publish_safe.py`, `scripts/run_conformance.py`) and cross-checked against the sibling `STACK.md`/`FEATURES.md`. The one MEDIUM area is the DLI snapshot schema (an IRCC endpoint that can drift — which is precisely why the design pins a dated snapshot).

## How to read the "Phase to address" field

v5.0 requirements group under five prefixes that become the v5.0 phases (global numbering continues after Phase 39 → v5.0 begins at Phase 40): **MEC** (program-eligibility roll-up), **POLICY** (arranged-employment resolver), **STUDY** (DLI/PGWP snapshot gate), **NOC** (duty-match worksheet), and **SAFE** (cross-cutting effective-date / freshness / drift + the release gate).

**The load-bearing distinction for the roadmapper:** the *"stale or superseded rule can never green a result"* invariant is a **cross-cutting SAFE conformance concern** — it must be proven once, centrally, over *every* screen, not re-implemented per screen. A screen-specific pitfall (a wrong DLI match, a NOC auto-entailment) is owned by that screen's phase; but the *guarantee that the wrongness fails closed* is owned by SAFE. Pitfalls below are tagged **[SAFE-owned]** (cross-cutting invariant + conformance proof) or **[screen-owned]** (the specific phase builds the mitigation, SAFE proves it holds).

## Critical Pitfalls

### Pitfall 1: A stale / superseded rule silently greens a screen (the milestone's dominant risk)

**What goes wrong:**
A program-eligibility criterion or an arranged-employment rule that changed on an effective date silently substantiates a factor because (a) the corpus/snapshot is stale, (b) the current-policy row is missing so an *older* grounded row ends up backing the claim, or (c) the decider never checked the effective window. The result reads `SUBSTANTIATED` / `MEETS` on a rule that no longer holds — a false green on a refusal-risk factor.

**Why it happens:**
The registry *already* models `MachineCheck.effective_from/effective_to/window_days` and `VolatilityMeta(volatility, crawl_date, effective_from, effective_to)`, but a new decider can simply *not read them* and still return a green. The failure is one of omission, not commission — the machinery to gate on the date exists (`crs_audit._in_window`, `within_validity`), so a decider that forgets to call it looks correct in tests that only use in-window fixtures.

**How to avoid:**
Make "no in-window grounded row ⇒ not green" the **default**, mirroring the shipped `_default_decider` (an unwired factor is `AT-RISK`, never `SUBSTANTIATED`). Every new dated row carries its window in `machine_check`/`VolatilityMeta`; every new decider compares the ITA/reference date via `_in_window` (stdlib `datetime`) and returns `GAP`/`AT-RISK` when out-of-window or superseded — **never** falls back to a stale row. Reuse `retrieve_what_you_cite` + `selector.deny_families` (already suppresses superseded MI amendments / year-end reports) for the new families. Prove it centrally in SAFE: a superseded policy row + an in-window candidate ⇒ `AT-RISK`, and an expired snapshot ⇒ refusal.

**Warning signs:**
A verdict is `SUBSTANTIATED`/`MEETS` while the backing row's `effective_to` precedes the reference date; a decider references a row id but never `_in_window`; the verdict carries no as-of (`crawl_date`/`effective_from`) provenance; a test suite with only current-dated fixtures and zero superseded/out-of-window negative controls.

**Phase to address:**
**SAFE-owned** (the invariant + conformance matrix), consumed by MEC / POLICY / STUDY. SAFE lands *with or before* the rules it guards — a dated rule shipped without effective-window gating is a latent false-green.

---

### Pitfall 2: Ungrounded MEC thresholds inlined as Python / prose literals

**What goes wrong:**
The FSW 67 pass mark, the age-grid points, the CLB/NCLC minimums, CEC's 12-month/36-month windows, FST's 2-year requirement, or the LICO settlement-funds amounts get hard-coded into `crawler/auditors/mec.py` (or a docstring/heading) instead of being read from grounded rows. A later policy change makes the literal silently stale — and a stale literal that greens a fail is exactly Pitfall 1 with no metadata to even detect it.

**Why it happens:**
MEC introduces many small volatile numbers at once, and "it rarely changes / I'll ground it later" is the path of least resistance. The `no_inlined_volatile_rules` static gate exists — but it scans a fixed path set (`crawler/auditors/` prose today); a brand-new MEC/DLI/NOC decider module that isn't added to the scan path escapes the gate entirely.

**How to avoid:**
Every MEC criterion value lives in a new grounded `crawler/data/crs_rules/mec.yaml` `RuleRow` (`machine_check` payload + verbatim `quote` + `relpath#ordinal` citation), read at runtime — the registry is the one place a volatile value may live. **Extend `no_inlined_volatile_rules`'s `paths` argument to include every new v5.0 decider module and rule/prose file**, and extend `_VOLATILE_POINTS_RE`/window regexes to catch the new magnitudes (67, 12, 24, 36 months) if they aren't already caught. A decider that cannot resolve a threshold row fails closed (`AT-RISK`), never a guessed number. `validate_registry` must show the new rows ground (0 violations).

**Warning signs:**
A number like `67`, `12`, `36`, a CLB level, or a dollar LICO amount appears in a comparison in a `.py` file outside a `machine_check` payload; the SAFE gate's literal-scan count of covered files didn't grow when the MEC module landed; a new decider module not listed in the `no_inlined_volatile_rules` invocation.

**Phase to address:**
**MEC** builds the grounded rows + literal-free decider; **SAFE-owned** extends the static gate's scan path and proves the scan is non-vacuous over the new modules.

---

### Pitfall 3: Legacy / physician arranged-employment auto-green

**What goes wrong:**
An in-window pre-2025-03-25 (ITA-era) legacy job offer, or a physician public-policy case, is treated as `SUBSTANTIATED` (or awarded non-zero `points`) instead of `AT-RISK`/manual — recreating the exact false-green the shipped `arranged_employment_guard` exists to prevent. This is the single highest-stakes regression: auto-awarding job-offer CRS on a repealed regime.

**Why it happens:**
v5.0 *extends* arranged-employment (physician row + feeding the offer into MEC's FST offer-or-cert branch and FSW funds exemption). It is tempting to (a) "finish" the legacy branch by awarding the MI's 200/50 points, or (b) let MEC's "valid offer" input promote the offer to a green, bypassing the guard. Both weaken a guard that currently returns `AT-RISK` with `points is None` (legacy) / `points == 0` (repeal) and **never** `SUBSTANTIATED`.

**How to avoid:**
Keep `crawler/crs_audit.py::arranged_employment_guard` the single chokepoint and *extend, never weaken* it: in-window legacy ⇒ `AT-RISK`, `points is None` (`arranged_employment_legacy_manual`); post-repeal non-zero ⇒ `AT-RISK`/0 (`arranged_employment_current`); a **new grounded physician-public-policy row** (citing `corpus/guidance/job-offer.md`, on/after 2023-04-25) ⇒ `AT-RISK`/manual, never auto-award even for an in-window physician. When MEC consumes the offer for FST R87.2(3)(d) or FSW R76(1)(b)(ii), it consumes it **as an `AT-RISK` human-confirmed input**, never as a green. SAFE proves no `additional.job_offer` path ever yields `SUBSTANTIATED`.

**Warning signs:**
`decide_job_offer` (or a new POLICY decider) returns a `SUBSTANTIATED` verdict or a non-`None`/non-zero `points`; a physician branch that awards points; an MEC criterion card that flips to `MEETS` because an offer was present without a human confirmation; the legacy `points is None` contract changed.

**Phase to address:**
**POLICY** (physician row + eligibility-vs-CRS separation, preserving the guard); **SAFE-owned** locks the "no job-offer green" property in the conformance matrix.

---

### Pitfall 4: Live-lookup / fuzzy-match / institution≠program conflation for DLI/PGWP

**What goes wrong:**
Three distinct failures in the STUDY screen: (a) reaching out to the network at audit time (or trusting an unpinned/undated DLI list); (b) matching the institution by fuzzy *name* rather than the DLI number; (c) treating institution-level PGWP-eligibility as sufficient — greening study points without the field-of-study / program-level / DLI-*during-study* temporal judgment, which is human-confirmed. Any of the three greens the 15/30 study points wrongly.

**Why it happens:**
The shipped `decide_study` today greens on a confirmed `credential_level` **alone** (verified: `crawler/auditors/additional.py::decide_study` → `SUBSTANTIATED` from `credential_level` with no DLI gate). Adding "just look it up" feels like the smallest change; DLI numbers are annoying so name-matching is tempting; and "the school offers PGWP" reads like a green even though PGWP-eligibility ≠ DLI-designation-during-study ≠ credential-length tier ≠ R73(1) "Canadian educational credential."

**How to avoid:**
The audit path reads **only** `corpus/index.db`. DLI facts are a **pinned `corpus/dli/` snapshot** (a normal corpus family, auto-indexed by `searchindex.build_index`, grounded by `relpath#ordinal`), refreshed by a **separate operator verb** using stdlib `urllib.request` at refresh time — never a client in the audit path. Match on the **confirmed DLI number (exact)**, never the name; no match / ambiguous ⇒ `AT-RISK`, missing ⇒ `GAP`. Keep three separate grounded checks — DLI designation *during the program*, R73(1) credential definition, credential-length tier — and leave "does my specific program qualify for PGWP" as a human-confirmed `AT-RISK`. If the snapshot can't prove designation *during* the study window (current ≠ historical), stop at `AT-RISK`.

**Warning signs:**
Any `import httpx`/`requests`/`urllib.request` reachable from the audit path; a name-similarity/`difflib`/`fuzzy` call in the DLI decider; `decide_study` still greening on `credential_level` alone after STUDY ships; a green study verdict with no DLI-number citation; conflating a `pgwp: "Yes"` snapshot flag with credential-points eligibility.

**Phase to address:**
**STUDY** (snapshot family + DLI-number gate + credential precondition on `decide_study`); **SAFE-owned** for the staleness bound on the snapshot (Pitfall 8).

---

### Pitfall 5: NOC-duty semantic auto-resolution creep

**What goes wrong:**
The NOC screen slides from a structured, cited, human-confirmed duty-match worksheet into automated "match" scoring — a model/NLI/embedding entailment, an auto-classification of free-text duties into a NOC code, or a keyword-overlap percentage between the reference letter and the NOC main duties. A wrong auto-match greens a refusal-risk factor (the officer's own duty-match determination).

**Why it happens:**
"Just tell me if it matches" is the most-requested feature, and a keyword-overlap score *feels* objective. But it recreates the exact false-confidence risk v4.x excluded (VAL-02 is permanently out of scope), violates the no-model/no-NLI/no-vector/no-cloud constraint, and is fail-open by nature.

**How to avoid:**
Present the grounded NOC 2021 **lead statement + main duties (essential flagged) + employment requirements** from `corpus/noc-2021/noc-<code>.md` via the shipped `search`→`--cite` path; capture a **binary human confirmation** in new vault fields (`noc_lead_match`, `noc_main_duties_match`) through the existing confirm/correct/reject loop. Default and fallback is `AT-RISK unresolved_noc` (extend `decide_work`'s existing branch). **No score, no % threshold, no auto-classification** — the tool never emits the semantic match itself; the verdict can only reach `SUBSTANTIATED` after an explicit operator confirmation against the cited duties. SAFE proves no NOC path greens without the confirmation field.

**Warning signs:**
Any `import nltk`/`numpy`/`litellm`/`sentence-transformers`; a "match score" / overlap ratio / cosine similarity in the NOC module; a NOC verdict reaching `SUBSTANTIATED` without a confirmed `noc_*_match` field; auto-deriving a NOC code from free-text; a fixed "substantial duties = N%" constant.

**Phase to address:**
**NOC** (present-and-confirm worksheet); **SAFE-owned** proves the human-confirmation gate and scans for the forbidden ML imports.

---

### Pitfall 6: PII / privacy regression via new fields, sidecar surfaces, or the snapshot generator

**What goes wrong:**
A new study/NOC/MEC applicant value (DLI number, institution name, intended province, TR status, trade certificate, program stream) or a new sidecar/worksheet surface leaks applicant values, `ev_` evidence ids, or absolute paths onto stdout / the `--json` envelope / a snapshot file — or the DLI snapshot *generator* accidentally embeds an applicant value into a repo-shaped `corpus/dli/*.md`. Any of these breaks the vault-only PII boundary the whole project is built to protect.

**Why it happens:**
v5.0 adds several new PII-bearing inputs and a new artifact type (the duty-match worksheet, the MEC program matrix) plus a new *corpus* family (the DLI snapshot). The snapshot is the subtle one: it lives in the git-ignored `corpus/` but is **repo-shareable-shaped public data** — a generator that reads the vault (e.g. to "personalize" the snapshot) would poison a public-shaped file with PII. The v4.1 audit already noted the render-then-scan leak-pattern gate is **kept in sync manually** — new surfaces widen that gap.

**How to avoid:**
New applicant inputs are **vault-only** via an additive `PRAGMA user_version` migration (the shipped v1→v3 pattern); stdout/`--json` stays PII-light (verdict + counts + reason codes only, per the shipped envelope). Any new vault artifact subtree is added to `check_publish_safe.py::VAULT_SUBTREES` and carries the `SCREENING_NOTICE`. The **DLI snapshot generator reads only the IRCC dataset — never the vault**; it writes only public facts (institution, DLI number, PGWP flag). Run `check_publish_safe.py` over the whole tracked tree including the new snapshot family; keep the packet render-then-scan `_LEAK_PATTERNS` in sync with any new redactor (extend the manually-synced gate). Applicant program/enrolment values stay in the vault; public DLI facts stay in `corpus/dli/`.

**Warning signs:**
An applicant DLI number / institution / TR status appears in a stdout line or `--json` field; an `ev_` id or `evidence_ids` in a sidecar/worksheet/packet JSON; an absolute home-directory, venv, or pinned-interpreter path in a new report; a `corpus/dli/*.md` file containing a candidate id/name; a new vault artifact type not covered by `VAULT_SUBTREES`; `check_publish_safe` violation count > 0.

**Phase to address:**
**SAFE-owned** (privacy containment conformance + publish-safe coverage of the new subtrees/family); each screen (MEC/STUDY/NOC) contributes the vault-only migration + PII-light surfacing for its own fields.

---

### Pitfall 7: Dependency / trust-path creep

**What goes wrong:**
Adding these screens pulls in a rules engine (`durable-rules`/`business-rules`), a date library (`dateutil`/`arrow`/`pendulum`), a PDF/templating engine (`reportlab`/`weasyprint`/`jinja2`), or promotes a transitive-only extra (`httpx`/`typer`/`click`) to a hard dependency — or a new decider re-grounds via its own substring check / a second DLI datastore, forking a **second trust path** around the frozen `search → --cite → grounding gate → typed envelope` spine.

**Why it happens:**
Each new screen looks like it "needs" a helper: a policy DSL for effective dates, a date library for windows, a PDF renderer for the worksheet, a JSON store for the DLI list. But the shipped stack already covers all of it — the temptation is convenience, and the cost (a forked trust path, a promoted heavy extra, volatile numbers escaping the grounding gate) is invisible until it's shipped. `[project].dependencies` is exactly three packages (`pyyaml`, `pydantic`, `platformdirs`); everything else in the lock is transitive-only via optional extras.

**How to avoid:**
Zero-new-dependency discipline (v4.0 and v4.1 each added zero). All date math is stdlib `datetime` (`_in_window`, `age_on_date`, `within_validity` already prove this). Policy dates are grounded `RuleRow` metadata + deterministic deciders, **not** a rules engine (a DSL forks a second trust path around the registry + `no_inlined_volatile_rules`). Rendering is f-string / `"\n".join(...)` + `json` (the shipped `audit_report.py` pattern). New CLI verbs extend the stdlib `argparse` subparser tree. The DLI snapshot is **one more corpus family in the single FTS5 index**, never a second datastore; new deciders `import` neither `searchindex` nor `grounding` for re-grounding — they consume gated grounded rows only (enforce with the v4.1 AST-import scan pattern). Any `pyproject.toml` dependency change triggers a supply-chain gate + strong justification.

**Warning signs:**
A `poetry add` in the diff; `import httpx`/`typer`/`click`/`jinja2`/`dateutil` in core (non-extra) code; a new decider importing `searchindex`/`grounding` to re-ground; a standalone DLI `.json` read directly by a decider (outside the index); a hand-rolled "policy interpreter."

**Phase to address:**
**SAFE-owned** (release-gate / supply-chain assertion: `[project].dependencies` unchanged, AST-import scan for a second trust path); every screen phase honors the discipline as it builds.

---

### Pitfall 8: Snapshot freshness / provenance missing or non-reproducible

**What goes wrong:**
The DLI (and any future LICO) snapshot ships without a `crawl_date`/as-of stamp, or with no staleness bound forcing refusal/`AT-RISK`, or via a non-reproducible refresh. A stale snapshot then greens study points (or funds) silently — Pitfall 1, but for the one genuinely-new external artifact.

**Why it happens:**
The snapshot is the milestone's only new corpus artifact and the only thing touching the network (at refresh time). It's easy to generate the markdown and index it but forget the freshness *bound* — the snapshot indexes fine and grounds fine, so the gap only shows when the data ages. There's no shipped freshness bound for a *snapshot family* yet (`within_validity` covers language/ECA document windows, `index_health` covers index integrity — neither yet covers "this snapshot is too old").

**How to avoid:**
The refresh generator stamps `crawl_date` **and** a content-hash (sha256) provenance id in front matter (the NOC-CSV generator pattern), so a refresh is diffable and byte-reproducible over the same upstream payload. A **grounded max-age freshness bound** forces `AT-RISK`/refusal when the snapshot's `crawl_date` exceeds it (mirror `within_validity`'s fail-closed "no window ⇒ not valid"). Extend the `index_health.probe_index` preflight (or add a sibling snapshot-freshness preflight) to refuse cleanly — PII-free reason code, non-zero exit, **zero artifacts** — when the snapshot family is missing/stale/corrupt (reuse the `AuditGroundingError` + `IndexHealth` closed reason-code pattern). Refresh is an explicit, separate operator run; audit never refreshes.

**Warning signs:**
A `corpus/dli/*.md` doc with no `crawl_date` front-matter key; a study verdict that greens with no snapshot as-of surfaced; a refresh that produces different bytes for the same input (non-idempotent); no reason code for "snapshot stale"; `index_health` unaware of the new family.

**Phase to address:**
**STUDY** builds the generator + provenance stamp; **SAFE-owned** owns the staleness bound, the preflight refusal, and the conformance proof (an expired snapshot ⇒ refusal, never a green).

---

### Pitfall 9: MEC roll-up composition false-green (an unknown / AT-RISK criterion doesn't block `MEETS`)

**What goes wrong:**
A program shows `MEETS` while one of its criterion cards is `AT-RISK`, unknown, or backed by an unwired decider — because the roll-up composer treats a non-`GAP` verdict, or an `N/A`, as "not a blocker." Program eligibility is pass/fail (*"must meet all of the requirements"*); a single unproven criterion greening the whole program is a structural false-green distinct from any single rule being wrong.

**Why it happens:**
MEC is the *integrator* — it composes shipped deciders (`decide_language`/`decide_work`/`decide_education`) + NOC confirmation + POLICY + STUDY + new criterion rows. A composer that defaults to "pass unless explicitly failed" (rather than "block unless explicitly satisfied") inverts the fail-closed posture, and `N/A` (legitimately neutral) is easy to over-use to paper over an unproven criterion.

**How to avoid:**
`MEETS` requires **every** grounded criterion to be `SUBSTANTIATED` **or** `N/A`; any `GAP` ⇒ `DOES-NOT-MEET`; any `AT-RISK` / unknown / unwired ⇒ `NEEDS-REVIEW`, never `MEETS`. The composer is fail-closed by construction: unknown blocks. Reuse `_default_decider` (`AT-RISK unaudited_factor`) for any unwired MEC criterion so a missing criterion can never silently pass. `N/A` is reserved for genuinely inapplicable criteria (FST cert-of-qualification when an offer is claimed; CEC PGWP-education for a non-PGWP stream), never for "couldn't determine." SAFE proves: one `AT-RISK` criterion ⇒ the program never `MEETS`.

**Warning signs:**
A program `MEETS` with an `AT-RISK`/unknown criterion card present; `N/A` used where the truth is "unproven"; the composer branching on `!= GAP` rather than `in (SUBSTANTIATED, N/A)`; no negative-control test where one criterion is AT-RISK.

**Phase to address:**
**MEC** (fail-closed roll-up composer); **SAFE-owned** proves the roll-up can't green with an unproven criterion.

---

### Pitfall 10: Fail-open field vocabulary for the new confirmed inputs

**What goes wrong:**
A new confirmed-input canonicalizer (DLI number, TR status, intended province, trade certificate, program stream, `noc_*_match`) coerces an **unknown surface form to an accepted token** — or a new field bypasses the `is_audit_eligible` quarantine chokepoint — so an unverified/garbled value crosses into a green verdict.

**Why it happens:**
Each new screen needs new confirmed fields, and it's tempting to "be helpful" by defaulting an unrecognized value to the nearest accepted enum. The shipped fields solve this with closed-enum alias maps (`crawler/siblingfields.py`, `crawler/testtypes.py`) pinned by anti-drift tests, and every value must pass `is_audit_eligible` (confirmed/corrected + `quality_flag == 'ok'` + not stale) — but a new field can quietly skip that pattern.

**How to avoid:**
New vocabularies follow the `siblingfields.py`/`testtypes.py` pattern: a case/space-folding alias map keyed on a **closed** set of accepted tokens, pinned by an anti-drift test, that **never coerces an unknown surface form to an accepted token** (unknown ⇒ quarantine / `AT-RISK`, not a default). New inputs are written `pending` by extraction (the shipped quarantine invariant), require confirm/correct/reject, capture the five-key staleness, and must pass `is_audit_eligible` before any decider trusts them. Extraction of new PDFs (DLI enrolment / NOC reference) stays behind the optional `doc-extract` extra and the shipped quarantine.

**Warning signs:**
A canonicalizer with an `else: return <default_accepted_token>`; a new field read by a decider without going through `is_audit_eligible`/`audit_eligible_values`; extraction writing a non-`pending` field; no anti-drift test pinning the new alias map.

**Phase to address:**
**STUDY / NOC / MEC** each build their field vocabularies to the shipped pattern; **SAFE-owned** proves an unknown surface form never becomes an accepted token and never greens.

---

### Pitfall 11: The registry drift-guard doesn't cover the new rows (a drifted new rule re-greens a completed run)

**What goes wrong:**
New MEC/DLI/policy rows are added, but the `registry_fingerprint` / drift gate isn't proven to cover them — so a tampered or drifted new rule could re-ground a completed run, or a downstream projection (remediation/packet) doesn't fail closed on a drifted new factor. The v4.1 seam already fails `remediate`/`review-packet` closed (`exit 2 reason=registry_drift`) on a tampered stored fingerprint — new screens must inherit, not bypass, that guard.

**Why it happens:**
`registry_fingerprint` covers whatever `load_registry` loads, so it *should* extend automatically — but a new screen that reads rows via a side path, or a new report that doesn't stamp/re-check the fingerprint, can silently sit outside the guard.

**How to avoid:**
Ensure the new MEC/DLI/policy rows are loaded through `load_registry` so `registry_fingerprint` covers them automatically; every new screen's report stamps `crs_rules.registry_fingerprint` and every downstream projection re-checks it (the shipped audit→report→remediation→packet flow). SAFE proves a tampered/added row changes the fingerprint and trips the drift gate on the new surfaces.

**Warning signs:**
A new report without a `registry_fingerprint` stamp; a new screen reading rules outside `load_registry`; the drift gate green after a deliberate row tamper on a new family; a projection that doesn't re-verify the fingerprint.

**Phase to address:**
**SAFE-owned** (extend the drift-guard conformance to the new families + surfaces).

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Inline a MEC threshold (67 / CLB min / 12mo) "because it rarely changes" | One fewer grounded row | A silent stale literal greens a fail; breaks `no_inlined_volatile_rules`; no metadata to even detect staleness | **Never** — every volatile number is a grounded row |
| Keep `decide_study` greening on `credential_level` alone | Ships MEC/CRS sooner | A study false-green (no DLI/credential gate) — the exact STUDY defect v5.0 exists to close | Only until STUDY ships its DLI/credential precondition — must not survive the milestone |
| Skip the snapshot "DLI-during-study" temporal check (assume current == historical) | Simpler lookup | Wrong green when designation changed over time | Acceptable **only** as `AT-RISK` (never a green) with the limitation surfaced |
| Manually keep `check_publish_safe` `_LINE_CATEGORIES` and the packet render-then-scan `_LEAK_PATTERNS` in sync (v4.1 debt) | No refactor now | A new redactor/surface drifts from the scan; a leak slips | Short-term; extend both together whenever a new surface lands, and add a sync test |
| Rely on `index_health`'s bounded 64-chunk drift sample (v4.1 debt) as the only drift signal for the new family | Cheap happy path | Drift beyond the sample lacks the specific `index_drifted` reason (still caught fail-closed by per-citation `searchindex.resolve`) | Acceptable — the per-citation resolve guard is the authoritative backstop; note it |
| Fold all 1,454 DLI campuses into "current == valid" without provenance | Fewer docs | Non-reproducible, un-dated snapshot; Pitfall 8 | Never — stamp `crawl_date` + content-hash even if campuses are folded |

## Integration Gotchas

Common mistakes when connecting to the (few) external / internal integration points.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| IRCC DLI JSON endpoint (`.../json/dli/dli-full-list.json`) | Treat the URL/schema as eternal; query it at audit time | Pin a **dated, content-hashed snapshot** as `corpus/dli/`; fetch only at refresh time via stdlib `urllib`; fail closed if the schema drifts on refresh |
| The single FTS5 corpus index | Create a second DLI datastore / second retrieval path | Add `corpus/dli/` as one more family; `searchindex.build_index` auto-enumerates it — rebuild the index after refresh, no new store |
| The frozen grounding gate (`search → --cite → ground`) | A new decider re-grounds with its own substring/second index | New deciders consume **gated** grounded rows only; never `import searchindex`/`grounding` to re-ground (AST-scan enforced) |
| Vault schema (`PRAGMA user_version`) | Rewrite/repurpose an existing column for a new field | **Additive** migration only (v1→v3 pattern); new columns, never mutate shipped ones |
| The shipped `arranged_employment_guard` | A new POLICY/MEC path awards the offer directly, bypassing the guard | All arranged-employment verdicts route through the guard; MEC consumes the offer as an `AT-RISK` input, never a green |

## Performance Traps

This is a **local, single-user, offline CLI** — throughput/latency are not the risk surface; corpus-size and index-rebuild cost are the only real considerations. Kept honest and scoped.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Emitting one tiny `corpus/dli/*.md` per campus row (1,454+ docs) | Corpus doc count ~3× (742 → ~2,200); slower index rebuild; noisier search | Fold campuses under one doc per DLI number where possible; the DLI family is grounded by exact DLI-number marker, not recall-sensitive | Only matters at index-rebuild time; audit reads are O(1) lookups — no runtime concern at this scale |
| Re-validating the whole registry / rebuilding the index inside the audit path | Audit slows as rules grow | Keep `build_index`/`validate_registry` as separate refresh/CI steps; audit reads the built `index.db` only | Not a user-facing concern for a single-run CLI; avoid coupling refresh into audit |
| Adding a snapshot-freshness network check on the read path | Audit blocks on the network; breaks offline | Freshness is a **local** `crawl_date` comparison against a grounded bound — no network | Would break offline/PII-safety immediately — never do it |

## Security Mistakes

Domain-specific issues beyond general hygiene (the project's whole threat model is PII containment + trust-path integrity).

| Mistake | Risk | Prevention |
|---------|------|------------|
| The DLI snapshot generator reads the vault to "personalize" the snapshot | Applicant PII poisons a repo-shareable-shaped `corpus/dli/*.md` | Generator reads **only** the IRCC dataset; writes only public facts; `check_publish_safe` scans the new family |
| A network call in the audit path (DLI/LICO live lookup) | Data exfiltration + injection of unpinned data that can silently green | Audit reads only `corpus/index.db`; refresh is a separate, explicit stdlib-`urllib` operator action |
| A new `--json` envelope field carries the applicant's DLI number / institution / TR status | PII on stdout / in a shareable artifact | Envelope/stdout stays PII-light (verdict + counts + reason codes); applicant values vault-only |
| An absolute home-directory, venv, or interpreter path in a new report/worksheet | Machine fingerprint leak (threat T-29-05) | Vault-relative paths only; `check_publish_safe` `ABS_PATH_PATTERNS` over the tracked tree |
| A new confirmed field trusted before quarantine | An unverified/garbled value greens a verdict | Everything crosses `is_audit_eligible` (confirmed/corrected + `ok` + not stale); unknowns quarantine |

## UX Pitfalls

Common user-experience mistakes specific to an eligibility-screening tool that must never become advice.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Presenting `MEETS FSW` as "you are eligible / will be invited / will be approved" | Reads as an outcome **prediction** — prohibited; MI eligibility is an officer determination | "You **meet the minimum entry criteria as grounded** for FSW/CEC" (screen), with the `SCREENING_NOTICE`, no outcome language |
| Recommending which program to "apply under" | Strategy / legal advice; crosses into pre-ITA optimization (out of scope) | Present all programs' MEC verdicts neutrally; the applicant/representative chooses |
| Hiding the staleness / as-of date to reduce noise | A stale rule silently greens; reviewer can't see the vintage | Always surface `source_family` + `crawl_date`/`effective_from`; make staleness a first-class `AT-RISK` |
| Showing NOC duties as an auto-decided "match" | False confidence on the officer's own duty determination | Present cited duties (essential flagged) as a **confirm** prompt; verdict stays `AT-RISK` until the human confirms |
| Rolling up MEC so an `AT-RISK` criterion reads as "basically fine" | User treats a NEEDS-REVIEW program as a pass | Any `AT-RISK`/unknown criterion ⇒ `NEEDS-REVIEW`; show the blocking card explicitly |

## "Looks Done But Isn't" Checklist

Verification items that distinguish a demo-green screen from a trust-safe one.

- [ ] Every new dated rule is gated by `_in_window` against the reference date — proven with an **out-of-window / superseded negative control** (not just current-dated fixtures). *(Pitfall 1)*
- [ ] `no_inlined_volatile_rules` is invoked over **every** new v5.0 decider module + rule/prose file, and the scan is non-vacuous (a deliberately-inlined `67` is caught). *(Pitfall 2)*
- [ ] No `additional.job_offer` / physician path returns `SUBSTANTIATED` or non-zero/`non-None` points. *(Pitfall 3)*
- [ ] `decide_study` no longer greens on `credential_level` alone; a green requires an exact DLI-number match in a fresh snapshot; name-only / ambiguous ⇒ `AT-RISK`. *(Pitfall 4)*
- [ ] No `nltk`/`numpy`/`litellm`/similarity import in the NOC path; a NOC green requires a confirmed `noc_*_match` field. *(Pitfall 5)*
- [ ] `check_publish_safe` = 0 violations over the tracked tree **including `corpus/dli/`**; no applicant value / `ev_` id / absolute path in any new stdout/envelope/snapshot surface. *(Pitfall 6)*
- [ ] `[project].dependencies` unchanged (still exactly `pyyaml`, `pydantic`, `platformdirs`); no new decider imports `searchindex`/`grounding` to re-ground. *(Pitfall 7)*
- [ ] Every `corpus/dli/*.md` carries `crawl_date` + a content-hash; an expired snapshot ⇒ clean refusal (PII-free reason, exit non-zero, zero artifacts); refresh is byte-reproducible. *(Pitfall 8)*
- [ ] A program `MEETS` only when every criterion is `SUBSTANTIATED`/`N/A`; one `AT-RISK` criterion ⇒ `NEEDS-REVIEW`. *(Pitfall 9)*
- [ ] Every new field vocabulary refuses to coerce an unknown token; every new value crosses `is_audit_eligible`. *(Pitfall 10)*
- [ ] `registry_fingerprint` covers the new rows; a tampered new row trips the drift gate on report/remediate/packet. *(Pitfall 11)*
- [ ] The v5.0 SAFE release gate runs green in one command alongside SAFE-01..08. *(cross-cutting)*

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls. **SAFE owns the cross-cutting invariant + the conformance proof; the screen phase owns building the mitigation.**

| Pitfall | Owning phase(s) | Verification (in the SAFE gate unless noted) |
|---------|-----------------|----------------------------------------------|
| 1. Stale/superseded rule greens | **SAFE** (invariant) + MEC/POLICY/STUDY (gate on their dates) | Superseded row + in-window candidate ⇒ `AT-RISK`; expired snapshot ⇒ refusal |
| 2. Ungrounded MEC thresholds inlined | **MEC** (grounded rows) + **SAFE** (extend static gate) | `no_inlined_volatile_rules` covers new modules; `validate_registry` 0 violations |
| 3. Legacy/physician auto-green | **POLICY** | No `additional.job_offer` path yields `SUBSTANTIATED`/points; physician ⇒ `AT-RISK`/manual |
| 4. Live-lookup / fuzzy / institution≠program | **STUDY** + **SAFE** (freshness) | No network import in audit path; DLI-number-exact match; green requires DLI + credential + tier |
| 5. NOC semantic auto-resolution | **NOC** | No ML import; NOC green requires confirmed `noc_*_match`; no score/threshold |
| 6. PII / snapshot / sidecar leak | **SAFE** (privacy + publish-safe) + each screen (vault-only fields) | `check_publish_safe` = 0 over tree incl. `corpus/dli/`; PII-light envelope proof |
| 7. Dependency / trust-path creep | **SAFE** (release/supply-chain gate) | `[project].dependencies` unchanged; AST-scan finds no second trust path |
| 8. Snapshot freshness / provenance | **STUDY** (generator) + **SAFE** (bound + preflight) | `crawl_date`+hash present; stale ⇒ refusal, zero artifacts; refresh reproducible |
| 9. MEC roll-up composition false-green | **MEC** | One `AT-RISK` criterion ⇒ program never `MEETS` |
| 10. Fail-open field vocabulary | **STUDY/NOC/MEC** | Unknown token never coerced to accepted; new value crosses `is_audit_eligible` |
| 11. Drift-guard doesn't cover new rows | **SAFE** | Tampered new row changes `registry_fingerprint`; trips drift gate on all surfaces |

## Sources

- **Codebase inspected (real seams — HIGH, curated first-party):** `crawler/crs_audit.py` (`arranged_employment_guard` fail-closed contract, `_in_window`, `within_validity`, `age_on_date`, stdlib `datetime`); `crawler/crs_rules.py` (`no_inlined_volatile_rules` static gate + `_ALLOW_KEYS`/`_VOLATILE_POINTS_RE`, `validate_registry`, `retrieve_what_you_cite`/`_select_chunk` + `deny_families`, `registry_fingerprint`, `load_registry`); `crawler/models/crs_rules.py` (`MachineCheck.effective_from/effective_to/window_days`, `VolatilityMeta`, `CheckType: policy`, `policy_flag`); `crawler/auditors/__init__.py` (`_default_decider` AT-RISK, `resolve`/`register`, `FULL_GRID_FACTORS`, `DecisionContext`/`DecisionResult`); `crawler/auditors/additional.py` (`decide_study` greens on `credential_level` alone today, `decide_job_offer` never SUBSTANTIATED, `decide_sibling` AT-RISK pattern); `crawler/index_health.py` (`probe_index` closed reason-code preflight, bounded drift sample); `crawler/vault.py` (`is_audit_eligible` quarantine chokepoint, `PRAGMA user_version` v1→v3 additive migration, `ev_` id separation, five-key staleness); `scripts/check_publish_safe.py` (`VAULT_SUBTREES`, `ABS_PATH_PATTERNS`, `SECRET_PATTERNS`, `_LINE_CATEGORIES`); `scripts/run_conformance.py` (SAFE-01..08 release gate).
- **Prior pitfalls framing reused (trust-model, NOT repeated — HIGH):** `.planning/research/PITFALLS-v4.1.md` (false-completeness, stale/historical grounding, evidence-to-factor mislinking, redaction failure, second-ungrounded-advice-path, unstable error surfaces, schema/fixture drift, screening-framing) and `.planning/research/PITFALLS-v4.0.md`. The v4.x-specific items are the substrate; this file covers only the **new** v5.0 integration risks.
- **Sibling v5.0 research aligned with — HIGH:** `.planning/research/STACK.md` (zero-new-dependency module map, DLI snapshot mechanics, the anti-stack: no HTTP-at-audit / no rules-engine / no date-lib / no ML), `.planning/research/FEATURES.md` (MEC/POLICY/STUDY/NOC/SAFE categories, AT-RISK boundaries, anti-features, verdict grammar, dependency ordering).
- **Milestone constraints + advisory tech-debt — HIGH:** `.planning/PROJECT.md` (v5.0 Current Milestone, Key Decisions on pinned-snapshot-not-live-lookup and "stale/superseded never greens"), `.planning/milestones/v4.1-MILESTONE-AUDIT.md` (LATER-01..04 promotions; advisory debt: `index_health` bounded-sample drift, manually-synced leak-pattern gates), `.planning/ROADMAP.md`.

---
*Pitfalls research for: v5.0 Grounded Eligibility & Policy Edge-Case Screening (adding MEC/POLICY/STUDY/NOC/SAFE screens to a shipped grounded/fail-closed auditor)*
*Researched: 2026-07-17*
