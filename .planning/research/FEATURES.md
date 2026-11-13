# Feature Research

**Domain:** v5.0 Grounded Eligibility & Policy Edge-Case Screening — extending a shipped local, PII-safe, corpus-grounded post-ITA Express Entry CRS *substantiation* auditor into deterministic, authoritative-source-grounded *screening* for (a) program eligibility (FSW/FST/CEC minimum entry criteria) and (b) the policy edge cases v4.x deliberately left `AT-RISK` (legacy/physician arranged employment, DLI/PGWP study evidence, NOC work-duty fit), plus cross-cutting effective-date/freshness/drift handling.
**Researched:** 2026-07-17
**Confidence:** HIGH for every feature's authoritative grounding and verdict mapping (each maps to a real, verified corpus family — `pr-pdi`, `noc-2021`, `ministerial-instructions`, `legislation-irpr`/`irpa`, `guidance`, `definitions` — and reuses shipped, tested mechanisms: the CRS rule registry, `arranged_employment_guard`, `decide_work`'s `unresolved_noc` path, `within_validity`, `_in_window`, `retrieve_what_you_cite`, `no_inlined_volatile_rules`, `index_health` preflight). MEDIUM on two *new-surface design* points: the exact MEC verdict-composition model (all-criteria pass/fail vs per-criterion cards) and the DLI/PGWP snapshot schema/refresh cadence (the DLI list is a live canada.ca page **not currently in the corpus** — it must be pinned as a new authoritative snapshot). No feature is a scoring engine, an eligibility/outcome prediction, or a new trust path.

## Context for this Research

**This is a subsequent milestone.** The shipped v4.0/v4.1 system is not re-researched here — only the *new* v5.0 behavior. The reusable substrate is: a git-ignored candidate vault (profile/ITA + content-addressed docs, `ev_`-namespaced evidence ids); quarantined extraction with field-level confirm/correct/reject and five-key staleness; a PII-free corpus-grounded CRS **rule registry** (`crawler/data/crs_rules/*.yaml`, 31 grounded rows, 0 gaps) whose rows carry `machine_check` + `citations` + `volatility` (`effective_from`/`effective_to`/`crawl_date`/`source_family`); four context-light auditor modules emitting fail-closed `SUBSTANTIATED`/`GAP`/`AT-RISK`/`N/A` verdicts; a grounded remediation checklist + a redacted RCIC review packet (pure projections); and a single SAFE conformance release gate. 22 portable per-document review agents already cover the full e-APR document set.

**All research below is grounded in the local authoritative corpus + shipped code, which I inspected directly** (verified file paths and verbatim spans cited inline). This is the highest-confidence source class (curated authoritative + shipped-and-tested), so no external web lookup was warranted; the `research-plan` seam was not needed for these curated-source findings.

### The v5.0 organizing principle: SUBSTANTIATION → SCREENING, but the wall stays up

v4.x answers "is your *claimed CRS score* backed by your documents?" v5.0 adds "which *program(s)* do you meet the minimum entry criteria for, and are the policy edge cases we punted on now resolved — deterministically, from authoritative text, without ever auto-deciding a semantic question?" The dividing wall from v4.x is preserved and **extended**: every arithmetic/threshold/date fact is grounded and can green a result; every *semantic* fact (does this work match this NOC? is this offer a valid legacy offer? is this institution/credential eligible?) stays **human-confirmed** and can at most reach `AT-RISK` until the operator confirms grounded evidence. Nothing new predicts eligibility or an outcome — the officer decides; the tool *screens and cites*.

### Non-negotiable constraints every v5.0 feature must preserve

| Constraint | What it means for v5.0 |
|------------|------------------------|
| **Authoritative-source grounding** | Every new threshold/window/definition/duty cites a resolvable corpus chunk passing `search`→`--cite`→grounding gate. No inlined volatile literals (`no_inlined_volatile_rules` static scan must keep passing). New MEC/policy/study rules live in the registry, not Python. |
| **Fail-closed** | A missing grounded row, an unresolved semantic match, a stale/superseded rule, or a missing snapshot → never a green. Program-eligibility "MEETS" requires *every* grounded criterion satisfied; any unmet/unknown criterion → `GAP`/`AT-RISK`. |
| **PII vault-only** | Program-eligibility results and duty-review worksheets may carry applicant values → written only under `candidates/<id>/output/…`, covered by the shipped publish-safe allow-list; stdout stays PII-light (verdict + counts). |
| **No legal advice / no prediction** | "You meet the FSW minimum entry criteria as grounded here" is screening. "You will be approved / apply under CEC instead" is prediction/strategy — prohibited. The `SCREENING_NOTICE` framing renders into every new artifact. |
| **No model/NLI/vector/cloud** | NOC duty fit and ambiguous policy are **presented and human-confirmed**, never entailed by a model. DLI/PGWP is a **pinned local snapshot**, never a live remote lookup during audit. Deterministic joins only; zero new runtime dependencies preferred. |

### Verdict vocabulary — how v5.0 reuses the shipped four-verdict grammar

The four verdicts are unchanged; v5.0 gives each a *screening* reading per feature. Program eligibility (MEC) is composed of per-criterion verdicts using the same grammar, then rolled up:

| Verdict | v5.0 screening meaning (per criterion / factor) | Can it green a program "MEETS"? |
|---------|------------------------------------------------------|---------------------------------|
| `SUBSTANTIATED` | Grounded criterion satisfied by confirmed evidence (arithmetic/threshold/date/enumerated-value). | Yes — but only if **all** the program's criteria are `SUBSTANTIATED`/`N/A`. |
| `GAP` | Required proof missing / wrong type / below the grounded minimum. | No — forces program verdict to `DOES-NOT-MEET (gap)`. |
| `AT-RISK` | Needs human/professional judgement: NOC duty fit, legacy offer, ambiguous/ineligible institution, unresolved date/effective-window, snapshot stale. | No — forces program verdict to `NEEDS-REVIEW`. Never auto-green. |
| `N/A` | Criterion not applicable to this applicant/program (e.g. FST cert-of-qualification when a job offer is claimed instead; CEC PGWP-education for the non-PGWP stream). | Neutral — does not block, does not green on its own. |

## Feature Landscape

Organized by the five downstream requirement categories: **MEC**, **POLICY**, **STUDY**, **NOC**, **SAFE**. Each category lists Table Stakes / Differentiators / Anti-Features and calls out the AT-RISK / human-confirmation boundary, the grounding corpus family, complexity, and dependency on shipped modules.

---

## Category MEC — Minimum Entry Criteria sidecar (FSW / FST / CEC program eligibility)

**What it is:** A *program-eligibility SCREEN distinct from CRS scoring* answering "which of the three Express Entry programs does the applicant meet the minimum entry criteria for?" — grounded in the FSW/FST/CEC PDIs + IRPR + the Ministerial Instructions' eligibility clause, composed from per-criterion fail-closed verdicts. Promotes deferred **LATER-04**.

**Why now / why distinct from CRS:** CRS ranks; MEC gates. An applicant can have a high CRS yet fail a program's minimum entry criteria (e.g. FST without a certificate of qualification *or* qualifying offer). IRCC's own MI makes this the eligibility test: *"In order to be eligible to be issued an invitation, a foreign national must … be able to meet the requirements to be a member of that class as well as the selection criteria"* (`ministerial-instructions/current.md` §5(1); the three classes are FSW/CEC/FST per §2(a)–(c)). This is exactly a fail-closed all-criteria pass/fail screen.

### Table Stakes (users expect these)

| Feature | Why Expected | Complexity | Grounding family / span |
|---------|--------------|------------|-------------------------|
| **Per-program minimum-entry criterion set, grounded** | An eligibility screener that can't tell you the *criteria* is not a screener. Each program has an explicit, enumerable minimum-requirement list. | MEDIUM | **FSW:** `pr-pdi/…assessing-applications-against-minimum-requirements.md` — ≥1 yr continuous FT (or PT-equiv) skilled work in TEER 0/1/2/3 within 10 yrs [R75(2)(a)]; language threshold in all 4 abilities [R75(2)(d)]; education = Canadian credential **or** foreign credential + ECA <5 yrs, min a completed Canadian secondary credential [R75(2)(e)]. **FST:** `pr-pdi/…federal-skilled-trades-assessing-application-against-selection-criteria.md` — ≥2 yrs FT in the skilled trade within 5 yrs; language threshold; **certificate of qualification OR a ≥1-yr full-time offer from ≤2 employers** [R87.2(3)]. **CEC:** `pr-pdi/…canadian-experience-class-determining-membership-class.md` + `…qualifying-work-experience.md` — ≥12 mo FT Canadian skilled work in TEER 0–3 within 36 mo [R87.1(2)(a)]; language by TEER of most experience; intend to reside outside Quebec; TR status maintained. |
| **All-criteria fail-closed roll-up** (`MEETS` only if every grounded criterion is `SUBSTANTIATED`/`N/A`) | IRCC programs are pass/fail: *"applicants must meet all of the requirements"* (FST) / *"must meet the minimum qualifying requirements for all criteria"* (CEC). A single unmet criterion = not a member. | LOW–MEDIUM | FST membership PDI: *"must meet **all** of the requirements of R87.2(3)"*; CEC membership PDI: *"must meet the minimum qualifying requirements for all criteria"*. |
| **Reuse of already-confirmed vault evidence** (no new confirm loop where a factor already exists) | The applicant already confirmed language scores, work periods+TEER, ECA/credential, DOB. MEC should *compose* those, not re-ask. | MEDIUM | Reuses `decide_language`, `aggregate_work`/`decide_work`, `decide_education` confirmed snapshots + the grounded validity windows (`within_validity` for ECA/language). |
| **PII-light program-eligibility summary on stdout; full worksheet vault-only** | Same privacy contract as the audit report. | LOW | Reuses `VAULT_SUBTREES`/publish-safe allow-list + `SCREENING_NOTICE`. |

### Differentiators (competitive advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Multi-program eligibility matrix in one pass** | "You meet FSW and CEC minimum entry criteria (grounded); FST is `N/A` (no trade occupation claimed)." No public tool grounds all three programs' MEC against the applicant's *confirmed* documents, fail-closed, with citations. | MEDIUM | A per-program column of per-criterion verdict cards; each card carries `{criterion, verdict, reason, citation_ids, verbatim span}`. Deterministic composition of shipped deciders + new grounded criterion rows. |
| **FSW 67-point selection grid as a *screen*, not a score** | FSW uniquely requires a pass mark (*"The pass mark is 67 points"*, `…making-selection-decision.md`, R76(2)) in addition to the minimum requirements. Presenting the 6-factor grid (age/education/language/experience/arranged-employment/adaptability) as a grounded checklist with the confirmed inputs, and flagging `≥67 / <67` arithmetically, is genuinely useful and fully groundable. | MEDIUM–HIGH | Age grid (`…selection-criteria.md`: 18–35→12 … 47+→0), pass mark 67, settlement-funds requirement [R76(1)(b)(i), 50% LICO] with the arranged-employment exemption [R76(1)(b)(ii)]. **Boundary:** the *arithmetic* (sum vs 67) can green; the *arranged-employment* sub-factor stays `AT-RISK` (see POLICY) and *substituted evaluation* (officer discretion, R76(3)) is never modelled — always `AT-RISK`/officer-only. |
| **Settlement-funds screen with its own exemption logic** | FSW/FST require proof of funds unless exempt (authorized to work + qualifying arranged employment, or CEC). Surfacing "funds required vs exempt" grounded in R76(1)(b)(ii) is high-value and deterministic. | MEDIUM | Grounded from `…making-selection-decision.md` §Settlement funds. The *LICO amount* is volatile → grounded row (family-size table), never inlined; if not groundable to a current snapshot → `AT-RISK` (fail-closed), never a guessed threshold. |

### Anti-Features (do NOT build)

| Feature | Why Requested | Why Problematic | Instead |
|---------|---------------|-----------------|---------|
| **"You are eligible / will be invited / will be approved"** | Users want a yes. | Eligibility/outcome **prediction** — prohibited; MI eligibility is an officer determination incl. admissibility, medical, security. | "You **meet the minimum entry criteria as grounded** for FSW/CEC" (screen), with the SCREENING_NOTICE and no outcome language. |
| **Recommending which program to "apply under"** | "Which is best for me?" | Strategy/legal advice + crosses into pre-ITA optimization (out of scope). | Present all programs' MEC verdicts neutrally; the applicant/representative chooses. |
| **Modelling substituted evaluation / H&C to turn a fail into a pass** | The PDIs mention officers *may* substitute. | Pure officer discretion (R76(3)/R87.2(4) require a second officer; H&C is A25) — inherently non-deterministic, non-groundable to a green. | Any criterion that would rely on discretion stays `AT-RISK` with the discretion cited; never auto-green. |
| **Inlining the 67 pass mark / LICO / age points as Python constants** | "They rarely change." | Breaks grounding + `no_inlined_volatile_rules`; a silent stale value could green a fail. | Every threshold is a grounded registry row with `volatility`; unresolvable → fail-closed. |
| **Auto-classifying the applicant's occupation into a TEER for MEC** | Saves a step. | That's a semantic NOC judgement (see NOC category) — must be human-confirmed. | Consume the *confirmed* TEER/NOC from the vault; unresolved TEER → `AT-RISK unresolved_noc` (already the shipped behavior). |

**AT-RISK / human-confirmation boundary for MEC:** arithmetic and enumerated-threshold criteria (work months, language band vs minimum, ECA recency, age points, 67 sum, funds-vs-LICO) can reach `SUBSTANTIATED`. Anything semantic or discretionary — TEER/NOC fit, arranged-employment validity, substituted evaluation, H&C, admissibility — stays `AT-RISK`/officer-only and blocks a `MEETS`. **Dependencies:** heavy reuse of shipped `decide_language`/`decide_work`/`decide_education`/`aggregate_work` + `within_validity`; new grounded criterion rows in the registry; new roll-up composer. **Complexity: MEDIUM overall** (the deciders exist; the work is grounding the criterion set + the composer + FST's cert-or-offer branch).

---

## Category POLICY — Legacy / physician arranged-employment resolver

**What it is:** A grounded, fail-closed screen for the arranged-employment regime change: the pre-2025-03-25 (ITA-era) legacy points regime vs the repeal, plus the physician temporary public policy. In-window legacy ⇒ `AT-RISK`/manual (never auto-green); post-repeal ⇒ `AT-RISK`/0. Promotes deferred **LATER-01**. **Most of the guard already ships** — v5.0 *extends* it, it does not invent it.

**Shipped baseline (verified):** `crawler/auditors/additional.py::decide_job_offer` delegates to `crawler/crs_audit.py::arranged_employment_guard`, which: returns `N/A` for a zero/unclaimed offer; `AT-RISK`/0 for any non-zero claim citing the current-policy repeal row; and — *only* for a grounded, in-window legacy row — `AT-RISK` with `points is None` (manual legacy resolution), **never** `SUBSTANTIATED`, **never** an auto-award. Both rows exist: `additional.job_offer.current` (grounded from `guidance/job-offer.md`: *"We no longer give points for job offers … As of March 25, 2025"*, `effective_from: 2025-03-25`) and `additional.job_offer.legacy` (grounded from `ministerial-instructions/amendment-2017-2.md`: *"200 points, if the offer is for employment in an occupation contained in Major Group 00"*, `effective_to: 2025-03-25`). The two **never cross-ground** (different families).

### Table Stakes (users expect these)

| Feature | Why Expected | Complexity | Grounding family / span |
|---------|--------------|------------|-------------------------|
| **Preserve the repeal guard exactly** | The single highest-stakes false-green risk. Any regression that auto-awards job-offer CRS is catastrophic. | LOW (already shipped; lock it) | `additional.job_offer.current` + `arranged_employment_guard`; `guidance/job-offer.md#001`. |
| **Legacy window resolved from grounded dates, not prose** | The legacy/repeal boundary must move only when the corpus does. | LOW–MEDIUM | `_in_window(ita_date, legacy.volatility.effective_from, legacy.volatility.effective_to)`; `ministerial-instructions/amendment-2017-2.md`. |
| **No-ITA-date ⇒ fail-closed to current policy** | Without an authoritative ITA date the legacy window can't be evaluated. | LOW (shipped) | `decide_job_offer`: `ita_date is None` → `AT-RISK arranged_employment_current`/0. |

### Differentiators (competitive advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Separation of "valid offer for *program eligibility*" from "CRS *additional points*"** | The repeal removed CRS points but a valid offer still matters for FSW settlement-funds exemption and FST's offer-or-cert branch. Surfacing "your offer gives 0 CRS points (repealed) but may still satisfy the FST offer requirement / FSW funds exemption — verify manually" is genuinely clarifying and groundable. | MEDIUM | Ties POLICY to MEC: the offer feeds FST R87.2(3)(d) and FSW R76(1)(b)(ii) as an `AT-RISK` (human-confirmed valid-offer) input, never a CRS award. Grounded in `definitions` R82(1) arranged-employment definition + `…making-selection-decision.md`. |
| **Physician temporary public-policy edge case, explicitly flagged** | Physicians invited on/after 2023-04-25 with a publicly-funded medical-services offer have a *special* regime (offer valid under FSWP even if not continuous/≥1 yr, and — per the policy text — points for arranged employment/CRS). This is a genuine exception to the repeal narrative that a naive tool would get wrong. | MEDIUM–HIGH | Grounded from `guidance/job-offer.md` (physician temporary public policy, on/after **April 25, 2023**) + `guidance/category-based-selection.md` (physicians categories, NOC 31102 etc.). **Boundary:** this is a public-policy special case with eligibility conditions → always `AT-RISK`/manual with the policy cited; **never** auto-award, even for an in-window physician. |

### Anti-Features (do NOT build)

| Feature | Why Requested | Why Problematic | Instead |
|---------|---------------|-----------------|---------|
| **Auto-awarding legacy 200/50 points for an in-window ITA** | "The MI says 200 points." | The legacy regime requires validating the *offer itself* (LMIA/ESDC, occupation, employer) — semantic + document-heavy; auto-awarding recreates the exact false-green the guard exists to prevent. | `AT-RISK` with `points is None` (manual legacy resolution), citing the legacy row — already shipped; keep it. |
| **Auto-confirming physician public-policy eligibility** | "I'm a physician with an offer." | The policy has conditions (invited on/after 2023-04-25, publicly-funded services, updated valid-job-offer requirements) that require document + policy judgement. | Detect the *signal* (physician NOC + offer + in-window ITA), surface the cited policy, and stop at `AT-RISK`/manual. |
| **Predicting whether the offer is "LMIA-exempt / valid"** | Users want certainty. | Validity of an offer (ESDC assessment, R204/R205 exemptions) is an officer determination; not deterministically groundable to a green. | Present the grounded valid-offer requirements as a human-confirmed checklist; `AT-RISK` until confirmed. |

**AT-RISK / human-confirmation boundary for POLICY:** the arranged-employment *CRS additional-points* factor can **never** be `SUBSTANTIATED` — its only greens are `N/A` (no offer) or the fail-closed `AT-RISK`/0 (repeal). Legacy and physician cases are `AT-RISK`/manual. The *only* thing that can green is the negative case (no offer → `N/A`) or the arithmetic that a repeal means 0. **Dependencies:** `arranged_employment_guard`, `additional.job_offer.*` rows, `_in_window`; new grounded physician-policy row(s) + a legacy/physician *reason-code* expansion; feeds MEC. **Complexity: MEDIUM** (guard exists; new work is the physician row + the eligibility-vs-CRS separation surface).

---

## Category STUDY — DLI / PGWP study evidence for Canadian-education additional points

**What it is:** A grounded screen for the Canadian-study CRS additional points (15 for a 1–2 yr credential, 30 for 3+ yrs — `additional.study`, grounded in `guidance/crs-criteria.md`), gating them on two authoritative facts: (1) the institution was a **Designated Learning Institution (DLI)** during the program, and (2) the credential meets the **"Canadian educational credential"** definition (R73(1)) — using a **pinned local authoritative snapshot** of the DLI list, *not* a live lookup, plus applicant-confirmed evidence. Promotes deferred **LATER-02** (reframed: the deferred item said "live lookup"; the v5.0 decision is explicitly a *pinned snapshot*, per PROJECT.md Key Decision v5.0).

**Shipped baseline (verified):** `additional.study` grounds 15/30 points and `decide_study` maps a confirmed `credential_level` → grounded tier (secondary/ineligible → `GAP`; missing → `GAP`; eligible → `SUBSTANTIATED`). What's missing is the *institution/credential eligibility gate* — today a confirmed `credential_level` alone can green it.

**Critical grounding finding:** The corpus **confirms the DLI requirement** — `pr-pdi/…completeness-check.md`: *"Applicants must provide the Designated Learning Institution (DLI) number of the Canadian Institution where they completed their highest degree to be assigned points for their Canadian educational credentials"*; and `pr-pdi/…assessing-electronic-application-on-section-a11-2.md`: *"if the Canadian educational institution … was a designated learning institution (DLI) during the completion of their program, this is an indication that the credential meets the definition of 'Canadian educational credential' … as in subsection R73(1)"*. **But the DLI *list itself* is a live canada.ca page NOT in the corpus** — so the snapshot is a *new* pinned authoritative artifact this feature must add. PGWP-eligibility (for the CEC Post-Graduation stream credential) is grounded in `pr-pdi/…education-requirement-post-graduation-stream.md`.

### Table Stakes (users expect these)

| Feature | Why Expected | Complexity | Grounding family / span |
|---------|--------------|------------|-------------------------|
| **DLI-number + credential evidence gate on the study points** | The completeness-check PDI makes the DLI number a hard input for Canadian-education points. Greening 15/30 without it is a false-green. | MEDIUM | `pr-pdi/…completeness-check.md` (DLI number required); `pr-pdi/…a11-2.md` + R73(1) (`legislation-irpr`) for "Canadian educational credential". Vault: new confirmed fields `dli_number`, `institution_name`, `study_start`/`study_end` (extraction adds a `proof_of_studies` field group; the proof-of-studies agent already exists). |
| **Pinned local authoritative DLI snapshot (never a live lookup during audit)** | Live lookup breaks the frozen-corpus trust path, offline/PII-safety, and reproducibility; unpinned data could silently green. | MEDIUM–HIGH | New corpus family/snapshot (e.g. `dli-list`) crawled via the shipped `corpus-crawler` from the canada.ca DLI-list page referenced in the completeness-check PDI; carries `crawl_date`/`source_family` for freshness (see SAFE). |
| **Fail-closed on missing/ambiguous DLI match** | If the institution isn't found in the pinned snapshot, or the match is ambiguous, the tool must not green. | LOW–MEDIUM | Deterministic lookup (exact DLI number match preferred); no match / ambiguous → `AT-RISK`; missing evidence → `GAP` (mirrors shipped `missing_evidence`/`below_threshold`). |

### Differentiators (competitive advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **"DLI-during-program" temporal check** | A DLI must have been designated *during* the study period; designation status changes over time. Screening the confirmed study dates against the snapshot's validity is a subtle, high-value correctness point competitors miss. | HIGH | The pinned snapshot may not carry historical designation windows → if the snapshot can't prove designation *during* the program, stop at `AT-RISK` (never assume current==historical). Grounded from the `a11-2` "during the completion of their program" language. |
| **CEC Post-Graduation-stream credential linkage** | For CEC PGWP applicants the Canadian credential is a *membership* criterion (MEC), not just CRS points. Cross-linking STUDY evidence to the CEC MEC card is uniquely useful. | MEDIUM | `pr-pdi/…education-requirement-post-graduation-stream.md` (qualifying credential, ≥2 academic yrs, excluded studies e.g. >50% ESL, award-with-return-condition, distance learning outside Canada). Feeds CEC MEC as `N/A` for non-PGWP stream. |

### Anti-Features (do NOT build)

| Feature | Why Requested | Why Problematic | Instead |
|---------|---------------|-----------------|---------|
| **Live DLI/PGWP web lookup during audit** | "Just check the current list." | Breaks the frozen-corpus trust path, offline PII-safety, reproducibility; unpinned data can green a result. Explicitly the v5.0 Key Decision *against*. | Pinned local snapshot refreshed by the shipped crawler; audit reads the snapshot only. |
| **Inferring DLI/PGWP eligibility from institution *name* fuzzy-match** | Names vary; DLI numbers are annoying. | Fuzzy name matching is a semantic guess → false-green risk (two schools, name changes). | Prefer exact DLI-number match; name-only or ambiguous → `AT-RISK` human-confirm. |
| **Treating "has a Canadian credential" as automatically PGWP-eligible** | Simplifies. | PGWP-eligibility ≠ DLI-eligibility ≠ credential-length tier; conflating them greens wrongly. | Keep three distinct grounded checks (DLI designation, R73(1) credential definition, credential-length tier). |
| **Auto-deciding excluded-studies exceptions (ESL %, award conditions)** | Edge cases. | Requires reading program transcripts / award terms — document + semantic judgement. | Surface the grounded excluded-studies rules; `AT-RISK` for the applicant/representative to confirm. |

**AT-RISK / human-confirmation boundary for STUDY:** credential-length tier arithmetic (1–2 vs 3+ yrs) and an *exact DLI-number match within a fresh pinned snapshot* can reach `SUBSTANTIATED`. Name-only match, ambiguous/absent snapshot entry, unprovable "during-program" designation, or a stale snapshot → `AT-RISK`. **Dependencies:** shipped `additional.study`/`decide_study`, extraction (`credential`/`credential_level`, new DLI fields), the proof-of-studies agent, the crawler (new snapshot), freshness handling (SAFE). **Complexity: MEDIUM–HIGH** (the new pinned-snapshot family + temporal designation check are the hard parts).

---

## Category NOC — Enhanced NOC work-duty review (structured, cited, human-confirmed)

**What it is:** A structured workflow that surfaces the grounded NOC 2021 **lead statement / main duties / employment requirements** for the claimed NOC and lets the human **confirm** whether the claimed work matches — the review that FSW R75(2)(b)/(c), FST R87.2(3)(b), and CEC R87.1(2)(b)/(c) all require (*"performed the actions described in the lead statement … and a substantial number of the main duties, including all of the essential duties"*). Delivered as present-and-confirm, **explicitly NOT** automated semantic entailment. Promotes deferred **LATER-03**.

**Shipped baseline (verified):** `decide_work` aggregates confirmed work periods and returns `AT-RISK unresolved_noc` when a period lacks a resolvable TEER — the correct fail-closed stub. It does **not** yet present duties or capture a duty-match confirmation. The `noc-2021` family has all 376 TEER 0–3 unit groups with the exact structure needed (verified `noc-11100.md`: `## Lead statement`, `## Main duties`, `## Employment requirements`, `## Illustrative example(s)`, `## All examples`).

### Table Stakes (users expect these)

| Feature | Why Expected | Complexity | Grounding family / span |
|---------|--------------|------------|-------------------------|
| **Present the grounded NOC lead statement + main duties + employment requirements for the claimed NOC** | The e-APR reference-letter review *is* a duty-match exercise; a tool that claims NOC support must show the authoritative duties. | LOW–MEDIUM | `noc-2021/noc-<code>.md` sections, retrieved via the shipped `search`→`--cite` path; the 22-agent pack already includes the employment-reference-letter agent. |
| **Structured human confirmation of "lead statement performed?" + "substantial main duties incl. all essential duties?"** | Mirrors the exact IRPR test; captures a confirmed answer rather than guessing. | MEDIUM | Vault confirm/correct/reject on new fields `noc_lead_match`, `noc_main_duties_match` (per claimed NOC/document). Grounded test text from `pr-pdi/…assessing-applications-against-minimum-requirements.md` (R75(2)(b)/(c)), FST + CEC equivalents. |
| **Fail-closed default: unconfirmed / unresolved NOC ⇒ `AT-RISK unresolved_noc`** | Never green a duty match the human didn't confirm. | LOW (extend shipped path) | Extends `decide_work`'s existing `unresolved_noc` branch; no confirmation → `AT-RISK`. |

### Differentiators (competitive advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Cited duty-match worksheet as a review artifact** | A per-NOC worksheet {lead statement, main duties (essential flagged), employment requirements, applicant's confirmed answer, citation} — exactly what an RCIC/lawyer wants and what feeds the review packet. Turns "trust me, it's NOC X" into a grounded, confirmable record. | MEDIUM | Deterministic projection into the vault `output/`; composes with the shipped review-packet allow-list (excludes raw PII by default). |
| **NOC-vs-program-requirement linkage** | The same duty confirmation feeds all three programs' MEC + CRS work factor with subtly different rules (FST needs duties performed *after* qualifying to practise; CEC excludes employment requirements; FSW ignores employment requirements too). Surfacing the program-specific nuance is uniquely valuable. | MEDIUM–HIGH | CEC PDI: *"The employment requirements listed in the NOC description are not applicable."* FSW PDI: *"The applicant does not need to demonstrate that they meet the 'employment requirements'."* FST PDI: employment requirements **do** apply (except the cert-of-qualification). |

### Anti-Features (do NOT build)

| Feature | Why Requested | Why Problematic | Instead |
|---------|---------------|-----------------|---------|
| **Automated semantic entailment ("do these duties match?" answered by a model/NLI/embedding)** | "Just tell me if it matches." | Violates no-model/no-NLI/no-vector/no-cloud; recreates the exact false-confidence risk v4.x excluded; a wrong auto-match greens a refusal-risk factor. | Present the grounded duties; the human confirms; tool stays `AT-RISK` until confirmed. |
| **Auto-classifying free-text job duties into a NOC code** | Saves lookups. | Same semantic-guess problem; NOC selection is the applicant's declared claim to be *verified*, not inferred. | Consume the *claimed* NOC; present its grounded duties for confirmation. |
| **Keyword-overlap "match score" between the letter and the NOC duties** | Feels objective. | A heuristic overlap score is an ungrounded pseudo-semantic judgement that invites false-green. | No score; a binary human confirmation against the cited essential/main duties. |
| **Treating "substantial main duties" as a fixed % threshold** | Wants a number. | IRPR says "a substantial number … including all essential duties" — a judgement, not a percentage. | Present all duties (essential flagged); human judges substantiality; `AT-RISK` otherwise. |

**AT-RISK / human-confirmation boundary for NOC:** this category is *definitionally* human-confirmed — the duty-fit verdict can only become `SUBSTANTIATED` after an explicit operator confirmation against the cited duties; otherwise it stays `AT-RISK unresolved_noc`. The tool never emits the semantic match itself. **Dependencies:** `noc-2021` family, shipped `search`/`--cite`, `decide_work`'s `unresolved_noc` path, vault confirm/correct/reject, review-packet projection; feeds MEC + CRS work factor. **Complexity: MEDIUM** (retrieval + presentation exist; new work is the confirmation fields + the worksheet + program-nuance linkage).

---

## Category SAFE — Cross-cutting effective-date / freshness / drift handling & conformance

**What it is:** The cross-cutting guarantee that a *stale* or *superseded* rule/snapshot can never green a result — surfacing effective dates, superseded rules, and snapshot staleness to the user, and proving it under the continuing SAFE conformance series. This is the milestone's dominant risk (PROJECT.md Key Decision v5.0) because every new domain (MEC thresholds, arranged-employment windows, DLI snapshot, LICO) is date-sensitive.

**Shipped baseline (verified):** the registry already models `volatility` (`effective_from`/`effective_to`/`crawl_date`/`source_family`); `_in_window` gates the legacy/repeal boundary; `within_validity` fail-closes ECA/language freshness from grounded window rows (no window → `False` = no green); `retrieve_what_you_cite` re-selects the cited chunk and drops **superseded amendments** via `deny_families`; `no_inlined_volatile_rules` bans inlined literals; `index_health.py` is a typed read-only preflight that refuses cleanly on a missing/corrupt/drifted index; the SAFE-01..08 gate exists. v5.0 *extends* these to the new surfaces.

### Table Stakes (users expect these)

| Feature | Why Expected | Complexity | Grounding / mechanism |
|---------|--------------|------------|-----------------------|
| **Effective-window gating on every new dated rule** | MEC thresholds, arranged-employment, LICO all change on effective dates; a rule outside its window must not apply. | LOW–MEDIUM | Reuse `_in_window` + `volatility.effective_from/effective_to` on new MEC/policy rows (e.g. CEC's Nov-16-2022 TEER cutover, already visible in the CEC PDIs). |
| **Superseded-rule suppression** | An old MI amendment must not ground a current claim. | LOW (shipped, extend) | `retrieve_what_you_cite` + `deny_families` (superseded amendments/year-end reports already denied); extend deny-lists for any new superseded snapshots. |
| **Snapshot-staleness surfacing (esp. DLI snapshot)** | A pinned DLI/LICO snapshot ages; a stale snapshot greening study points/funds is a silent false-green. | MEDIUM | Compare snapshot `crawl_date` vs a grounded max-age window; stale → `AT-RISK`/refusal, surfaced with the date. New for the DLI/LICO families; mirrors `within_validity` fail-closed pattern. |
| **Clean fail-closed refusal + zero artifacts when a required snapshot/index is missing** | A missing DLI snapshot or corpus index must refuse legibly, not crash or green. | LOW (shipped, extend) | Extend `index_health.py` preflight to cover the new snapshot family; PII-free reason code; non-zero exit; no artifacts. |

### Differentiators (competitive advantage)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **User-visible "as-of" provenance on every screened result** | Each verdict shows the `source_family` + `crawl_date`/`effective_from` behind it, so the user (and reviewer) can see *which vintage* of the rule applied. Builds trust and makes staleness auditable. | MEDIUM | Project existing `volatility` metadata into the report/packet; no new data, new surfacing. |
| **A single v5.0 SAFE release gate proving no stale/superseded rule can green any new screen** | Extends SAFE-01..08 with MEC/POLICY/STUDY/NOC cases: a superseded MEC threshold, an out-of-window arranged-employment claim, a stale DLI snapshot, and an unconfirmed NOC duty each fail-closed. | MEDIUM–HIGH | New conformance tests reusing the shipped gate harness; the milestone's proof of correctness. |

### Anti-Features (do NOT build)

| Feature | Why Requested | Why Problematic | Instead |
|---------|---------------|-----------------|---------|
| **Auto-refreshing snapshots silently on the audit read path** | "Keep it current for me." | Blurs the read/write boundary; a network fetch on audit breaks offline/PII-safety and could inject unpinned data mid-run. | Refresh is an explicit, separate crawler run; audit reads the pinned snapshot and *refuses/flags* if stale. |
| **"Best-effort" applying a superseded rule when no current one is grounded** | Avoids a `GAP`. | A superseded rule greening a result is the dominant milestone risk. | Fail-closed: no in-window grounded rule → `GAP`/`AT-RISK`, never a stale green. |
| **Suppressing the staleness warning to reduce noise** | Cleaner output. | Hiding staleness is exactly how a stale rule silently greens. | Always surface the as-of date; make staleness a first-class `AT-RISK`. |

**AT-RISK / human-confirmation boundary for SAFE:** SAFE never *decides* a factor — it *constrains* the others. Its job is to force `AT-RISK`/refusal whenever a rule is out-of-window, superseded, or snapshot-stale. **Dependencies:** `volatility` model, `_in_window`, `within_validity`, `retrieve_what_you_cite`, `deny_families`, `no_inlined_volatile_rules`, `index_health.py`, SAFE gate. **Complexity: MEDIUM–HIGH** (mechanisms exist; the work is extending them to the DLI/LICO snapshots + the new conformance matrix).

---

## Feature Dependencies

```
SAFE (effective-date / freshness / drift)
  └── constrains ALL of ──> MEC, POLICY, STUDY, NOC   (nothing greens on a stale/superseded/out-of-window rule)

Shipped v4.x substrate (vault, extraction+confirm, CRS rule registry, deciders, remediation, review-packet, SAFE gate)
  └── required by ──> MEC, POLICY, STUDY, NOC, SAFE

NOC (duty-match confirmation)
  └── feeds ──> MEC (FSW/FST/CEC skilled-work criterion)  and  CRS core.work factor

POLICY (arranged-employment resolver, shipped guard + physician row)
  └── feeds ──> MEC (FST offer-or-cert branch, FSW settlement-funds exemption)
  └── never feeds ──> CRS additional job-offer points as a green (repeal: AT-RISK/0 only)

STUDY (DLI/PGWP pinned snapshot + credential gate)
  └── gates ──> CRS additional.study points (15/30)
  └── feeds ──> CEC MEC (Post-Graduation-stream credential criterion)
  └── requires ──> a NEW pinned DLI-list snapshot family (crawler) + SAFE staleness handling

MEC (program-eligibility roll-up)
  └── composes ──> shipped deciders (language/work/education) + NOC confirmation + POLICY + STUDY + new grounded criterion rows
```

### Dependency Notes

- **SAFE is a precondition, not a follow-on.** Because every new domain is date-sensitive, the freshness/effective-window/staleness handling should land *with or before* the rules it guards — a MEC threshold or DLI snapshot shipped without staleness handling is a latent false-green. Roadmap ordering: extend SAFE mechanisms early, prove them in the final SAFE gate.
- **NOC underpins MEC and CRS work.** The duty-match confirmation is the human-confirmed input both the MEC skilled-work criterion and the CRS `core.work` factor need; build NOC's confirmation surface before MEC's roll-up depends on it.
- **POLICY is mostly shipped.** The arranged-employment guard already exists and is correct; POLICY's *new* work is the physician public-policy row + the eligibility-vs-CRS separation feeding MEC — small, high-value, low-risk.
- **STUDY carries the only genuinely new corpus artifact** (the pinned DLI-list snapshot). That crawler+snapshot+staleness work is its long pole and couples STUDY tightly to SAFE.
- **MEC is the integrator** — it composes everything else, so it sequences last among the domain features.

## MVP Definition

### Launch With (v5.0 core — the fail-closed screens that can't be half-built)

- [ ] **SAFE extensions** — effective-window gating on all new dated rows, superseded-rule suppression, snapshot-staleness surfacing, preflight refusal for missing snapshots. *Essential: without it every other feature risks a stale false-green.*
- [ ] **POLICY: physician row + eligibility-vs-CRS separation** — small, grounded, promotes LATER-01; the guard already ships. *Essential + cheap.*
- [ ] **NOC: present-and-confirm duty-match worksheet** — the human-confirmed input MEC/CRS-work depend on; promotes LATER-03. *Essential.*
- [ ] **MEC: three-program minimum-entry-criteria roll-up + FSW 67-grid screen** — the headline capability; promotes LATER-04. *Essential.*

### Add After Validation (within v5.0 if scope allows)

- [ ] **STUDY: DLI/PGWP pinned-snapshot gate** — promotes LATER-02; gated behind the new snapshot family + staleness handling. *Add once SAFE staleness is proven; the snapshot is the long pole.*
- [ ] **Settlement-funds/LICO grounded screen** — high value but depends on a volatile LICO snapshot (same snapshot+staleness machinery as DLI).
- [ ] **Duty-match worksheet → review-packet projection** — reuses the shipped redacted-packet allow-list.

### Future Consideration (deferred / out of scope — do not pull in)

- [ ] **LATER-06** structured recipient-specific export presets — deferred.
- [ ] **LATER-07** encrypted packet bundle — deferred pending a separate key-management threat model.
- [ ] **VAL-02 / any model/NLI/vector** semantic auto-resolution — permanently out of scope for this trust model.
- [ ] **Live DLI/PGWP/LICO web lookup during audit** — explicitly rejected (pinned snapshot only).
- [ ] **Pre-ITA CRS optimization / program recommendation** — out of scope.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| SAFE effective-date / freshness / staleness extensions | HIGH (prevents the dominant false-green risk) | MEDIUM | **P1** |
| MEC three-program roll-up + FSW 67-grid screen | HIGH (headline capability) | MEDIUM–HIGH | **P1** |
| NOC present-and-confirm duty-match worksheet | HIGH (feeds MEC + CRS work; promotes LATER-03) | MEDIUM | **P1** |
| POLICY physician row + eligibility-vs-CRS separation | MEDIUM–HIGH (edge-case correctness; guard already ships) | LOW–MEDIUM | **P1** |
| STUDY DLI/PGWP pinned-snapshot gate | HIGH (correctness on study points; promotes LATER-02) | HIGH (new snapshot family) | **P2** |
| Settlement-funds / LICO grounded screen | MEDIUM (useful; volatile threshold) | MEDIUM (LICO snapshot) | **P2** |
| As-of provenance surfacing on every verdict | MEDIUM (trust/auditability) | MEDIUM | **P2** |
| Duty-match worksheet → review-packet projection | MEDIUM (reviewer value) | LOW–MEDIUM | **P3** |

**Priority key:** P1 = must have for the v5.0 launch; P2 = should have, add when the supporting snapshot/staleness machinery is proven; P3 = nice to have.

## Evidence Inputs by Feature (what each needs from the vault)

| Category | Vault / confirmed inputs required | New extraction fields | Existing fields reused |
|----------|-----------------------------------|-----------------------|------------------------|
| **MEC** | ITA date; confirmed language scores + test type; confirmed work periods (start/end/hours/TEER/NOC); ECA/credential + report date; DOB; intended province; TR-status (CEC); trade cert or offer (FST) | `intended_province`, `tr_status` (CEC), `trade_certificate` (FST) | `test_type`, language abilities, `employment_*`, `teer`, `noc_code`, `credential_level`, `eca_report_date`, `date_of_birth` |
| **POLICY** | ITA date (window); claimed job-offer points; physician-NOC signal; offer document | `physician_offer` flag / policy-signal | `noc_code`, ITA date, `additional.job_offer.*` rows |
| **STUDY** | DLI number; institution; study start/end; credential + length; PGWP-stream flag (CEC) | `dli_number`, `institution_name`, `study_start`, `study_end` | `credential`, `credential_level`, proof-of-studies agent |
| **NOC** | Claimed NOC/TEER per work document; human confirmation of lead-statement + main-duties match | `noc_lead_match`, `noc_main_duties_match` (per doc/NOC) | `noc_code`, `teer`, `employment_*`, employment-reference agent |
| **SAFE** | (No applicant input) — snapshot `crawl_date`s, rule `effective_from/to`, index health | — | `volatility` metadata, `index_health`, `within_validity`, `_in_window` |

## Competitor / Alternative Analysis

| Capability | IRCC pre-ITA tools (CRS calculator, Come-to-Canada) | Third-party CRS blogs / calculators | Generic document managers | **This tool's v5.0 approach** |
|-----------|------------------------------------------------------|--------------------------------------|----------------------------|-------------------------------|
| Program (FSW/FST/CEC) minimum-entry screen | Eligibility questionnaire, not grounded/cited, pre-ITA, not against *your documents* | Ungrounded, often stale, no citations | None | Grounded per-criterion fail-closed roll-up against confirmed vault evidence, cited to PDIs/IRPR/MI |
| Arranged-employment repeal + physician policy | Not surfaced as an edge case | Frequently wrong / outdated | None | Fail-closed guard (shipped) + grounded physician row; eligibility-vs-CRS separation |
| DLI/PGWP study-points eligibility | Points estimate, no DLI verification | Ungrounded | None | Pinned authoritative DLI snapshot + R73(1) credential gate, fail-closed on stale/missing |
| NOC duty-match | Self-declared NOC, no duty review | None | None | Cited present-and-confirm duty worksheet; never auto-entailed |
| Staleness / effective-date safety | N/A | Typically silent/stale | N/A | First-class effective-window + snapshot-staleness fail-closed + as-of provenance |

## Sources

All findings grounded in the local authoritative corpus (curated authoritative source class — HIGH confidence) and the shipped, tested codebase, inspected directly:

- **MEC:** `corpus/pr-pdi/economic-classes-federal-skilled-workers-assessing-applications-against-minimum-requirements.md` (R75(2)(a)/(d)/(e)); `…federal-skilled-workers-making-selection-decision.md` (67 pass mark R76(2); settlement funds R76(1)(b), 50% LICO); `…federal-skilled-workers-selection-criteria.md` (age grid); `…federal-skilled-trades-determining-membership-class.md` + `…assessing-application-against-selection-criteria.md` (R87.2(3), cert-or-offer); `…canadian-experience-class-determining-membership-class.md` + `…experience-qualifying-work-experience.md` (R87.1(2), 12mo/36mo, TEER 0–3) + `…experience-official-language-proficiency.md`; `corpus/ministerial-instructions/current.md` §5(1) eligibility + §2(a)–(c) classes; `corpus/definitions/terms-definitions-related-permanent-residence.md` (TEER); `corpus/legislation-irpr`.
- **POLICY:** `corpus/guidance/job-offer.md` (repeal "As of March 25, 2025"; physician temporary public policy "on or after April 25, 2023"); `corpus/guidance/category-based-selection.md` (physicians categories, NOC 31102); `corpus/ministerial-instructions/amendment-2017-2.md` (legacy 200/50 matrix); shipped `crawler/crs_audit.py::arranged_employment_guard`, `crawler/auditors/additional.py::decide_job_offer`, `crawler/data/crs_rules/additional.yaml` (`additional.job_offer.current`/`.legacy`); `corpus/definitions` R82(1).
- **STUDY:** `corpus/pr-pdi/express-entry-applications-received-on-after-january-1-2016-completeness-check.md` (DLI number required; DLI-list URL); `…express-entry-assessing-electronic-application-on-section-a11-2.md` (DLI ⇒ "Canadian educational credential" R73(1)); `…economic-classes-experience-education-requirement-post-graduation-stream.md`; `corpus/guidance/crs-criteria.md` (`additional.study` 15/30); `corpus/legislation-irpr` R73(1). **Note:** the DLI list itself is NOT in the corpus and must be added as a new pinned snapshot.
- **NOC:** `corpus/noc-2021/noc-11100.md` (verified structure: Lead statement / Main duties / Employment requirements / Illustrative + All examples) representative of all 376 TEER 0–3 groups; R75(2)(b)/(c), R87.2(3)(b), R87.1(2)(b)/(c) from the PDIs above; shipped `crawler/auditors/core.py::decide_work` (`unresolved_noc` path).
- **SAFE:** shipped `crawler/crs_audit.py` (`within_validity`, `_in_window`), `crawler/crs_rules.py` (volatility model, `retrieve_what_you_cite`/`deny_families` superseded suppression), `crawler/index_health.py`, `no_inlined_volatile_rules` scan; PROJECT.md v5.0 Key Decisions.
- **Prior framing reused (not repeated):** `.planning/research/FEATURES-v4.1.md`, `.planning/research/FEATURES-v4.0.md`; `.planning/milestones/v4.1-REQUIREMENTS.md` (LATER-01..04 deferrals, verdict semantics, sibling-evidence pattern).

---
*Feature research for: v5.0 Grounded Eligibility & Policy Edge-Case Screening (categories MEC / POLICY / STUDY / NOC / SAFE)*
*Researched: 2026-07-17*
