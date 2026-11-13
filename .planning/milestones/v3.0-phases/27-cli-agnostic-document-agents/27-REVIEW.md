---
phase: 27-cli-agnostic-document-agents
reviewed: 2026-06-21T15:08:45Z
depth: deep
files_reviewed: 10
files_reviewed_list:
  - skills/document-agents/_contract.md
  - skills/document-agents/README.md
  - skills/document-agents/police-certificate.md
  - skills/document-agents/language-test.md
  - skills/document-agents/eca.md
  - skills/document-agents/proof-of-funds.md
  - skills/document-agents/medical.md
  - skills/document-agents/employment-reference-letter.md
  - crawler/eval/document_agents.jsonl
  - crawler/tests/test_document_agents.py
findings:
  critical: 2
  warning: 2
  info: 1
  total: 5
status: resolved
resolved: 2026-06-21T15:52:05Z
resolution:
  fixed: 5
  skipped: 0
  commits:
    CR-01: df21166
    CR-02: 4c05550
    WR-01: 55c9ef9
    WR-02: 3d88804
    IN-01: ed9738e
---

# Phase 27: Code Review Report

**Reviewed:** 2026-06-21T15:08:45Z
**Depth:** deep (cross-file: skills ↔ fixture ↔ harness ↔ live corpus + grounding primitives)
**Files Reviewed:** 10
**Status:** resolved (all 5 findings fixed — 2026-06-21T15:52:05Z)

## Resolution (2026-06-21)

All five findings have been fixed and committed atomically. Verified live against
`corpus/index.db`: the document-agents eval grounds `failed:0` (8/8), the
conformance harness is green (`17 passed, 6 subtests`) including the new
retrieve-what-you-cite proof, and the full `crawler/tests` suite shows no new
failures beyond the pre-existing `test_dupaudit::TestRealCorpus` real-corpus
duplicate-count assertion (unrelated to this phase).

| Finding | Resolution | Commit |
|---|---|---|
| CR-01 | `medical.md` selection rule changed from "take the top `medical/` hit" to **scan the top hits and select the FIRST whose chunk text contains the structural exemption span** (`temporary public policy`). Now lands `medical/requirements-permanent-residents.md#000` (the exemption chunk) and grounds `verdict:pass`. | `df21166` |
| CR-02 | `proof-of-funds.md` worked example changed from blind `hits[0]` to the same **scan-top-N contains-span** rule (marker `equity on real property`). Now lands `guidance/proof-funds.md#007` (the equity rule) and grounds `verdict:pass`. | `4c05550` |
| WR-01 | Added `test_per_agent_retrieves_what_it_cites` to the `@skipUnless(corpus/index.db)` class: for each agent it extracts the baked query from the skill `.md`, applies the documented selection rule against the live index, asserts the selection agrees with the fixture citation, and runs the shipped gate on the re-pointed claims to prove the agent retrieves a chunk that grounds what it cites. Verified to fail under the pre-fix `hits[0]` rule. | `55c9ef9` |
| WR-02 | The grounding-gate skip is now LOUD: an explicit `LOCAL-ONLY GROUNDING GATE` skip reason, a `RuntimeWarning` surfaced in pytest's default warnings summary, and an always-run guard (`TestGroundingGateLocalOnly`) asserting the skip wiring matches corpus presence. The local-only conformance limitation is documented in `README.md`. The corpus is NOT shipped. | `3d88804` |
| IN-01 | The abstention entry shape is unified on the richer object form `{text, reason}` across `_contract.md` and the five abstaining skills, matching the fixture. | `ed9738e` |

## Summary

Phase 27 ships six CLI-agnostic, plain-markdown document agents, a shared
`_contract.md`, a tracked PII-free conformance fixture, and a `unittest`
conformance harness. The trust-path design is sound: the gate (`grounding.py`)
is substring-only and fail-closed, the fixture is genuinely synthetic
(no real names/employers/salaries/machine paths — verified), the police agent
correctly uses `--family guidance` + the country backstop and cites the generic
`guidance/police-certificates.md#002` (not a leaky `police-certificates/<country>`
relpath), the employment agent correctly targets the proof-of-work-experience
letter `...completeness-check.md#019` (not the arranged-employment job-offer
#034/#000), the frozen CONTRACT (`schema_version "1.0"`, exit codes) is unchanged,
and the GSD-managed `AGENTS.md` / `.github/copilot-instructions.md` blocks were not
touched.

**However, two of the six agents steer the agent to the WRONG corpus chunk.**
I ran each skill's baked query against the live `corpus/index.db` and resolved the
chunk each skill's worked example/instruction would actually select:

| Agent | Skill selects | Fixture cites | Selected chunk contains the required quote? |
|---|---|---|---|
| police | `guidance/police-certificates.md#002` | same | ✅ |
| language | `guidance/language-test.md#001` | same | ✅ |
| eca | `eca/educational-credential-assessment.md#014` | same | ✅ |
| **proof-of-funds** | `pr-pdi/...a11-2.md#036` (hits[0]) | `guidance/proof-funds.md#007` (3rd hit) | ❌ **no equity rule in #036** |
| **medical** | `medical/immigration-medical-assessment.md#001` (top `medical/`) | `medical/requirements-permanent-residents.md#000` (3rd hit) | ❌ **no dated exemption in #001** |
| employment | `...completeness-check.md#019` | same | ✅ |

The conformance harness is **green (16 passed)** and the real CLI gate reports
`failed:0` — but that green is misleading: the harness only validates the
fixture's hand-authored citations, and **never runs the agents' baked query +
selection rule**, so it cannot catch that two skills point at chunks that do not
contain the requirement they are built to ground. Because the gate is
substring-only (documented honesty boundary — no entailment check), an agent
following these two skills could pair the intended claim text with an unrelated
verbatim quote from the wrong chunk and **pass the gate with a misleading
"grounded" answer**, or needlessly abstain on a question the corpus answers.

## Critical Issues

### CR-01: medical agent steers to a chunk that lacks the dated exemption it must quote

**File:** `skills/document-agents/medical.md:57-59,90-94`
**Issue:**
The medical agent is the project's "canonical test of the no-inlined-values
rule": its whole job is to quote the dated public-policy IME exemption verbatim
from the corpus. The skill bakes the query `immigration medical examination
permanent residence` and instructs (prose line 57-59) *"This ranks the generic
medical/ family first — the permanent-residence IME-requirement pages whose text
carries the dated public-policy exemption verbatim. Take the top generic
medical/ hit."* The worked example (lines 90-94) implements exactly that:
`generic=[h for h in hits if h['chunk_id'].startswith('medical/')]; print(generic[0]...)`.

Verified against the live index, the top `medical/` hit is
`medical/immigration-medical-assessment.md#001` (about Medical Notification
IMM 5365B / inadmissibility) — it contains **no** `2029` and **no** exemption
language:

```
$ corpus-crawler --json search "immigration medical examination permanent residence" ...
medical/immigration-medical-assessment.md#001      <- skill selects THIS
medical/legal-references-medical.md#000
medical/requirements-permanent-residents.md#000    <- fixture cites THIS (3rd hit)
...
# chunk #001 HAS EXEMPTION QUOTE: False  /  HAS 2029: False
# chunk #000 HAS EXEMPTION QUOTE: True
```

Both the prose AND the worked example deterministically select the wrong chunk;
there is no documented path to the chunk that actually carries the exemption.
Following the skill, the agent either (a) cannot find the exemption span in #001
and abstains on a question the corpus answers, or (b) — worse — copies some other
verbatim span from #001 and grounds the exemption claim against it, producing a
"grounded"-looking answer whose cited quote does not state the exemption. The
substring-only gate cannot catch (b). This directly violates the phase's
grounding-by-construction guarantee.

**Fix:** Make the skill select the chunk that carries the exemption, not "the top
`medical/` hit." Either bake a more specific query that ranks
`medical/requirements-permanent-residents.md` first, or change the selection rule
to filter for the requirements page and assert the exemption span is present
before grounding, e.g.:

```python
# select the permanent-residence requirements page, not hits[0]
target = next((h for h in hits
               if h['chunk_id'].startswith('medical/requirements-permanent-residents')),
              None)
print(target['chunk_id'] if target else 'ABSTAIN: not_in_corpus')
```

and add a harness assertion that the baked query actually surfaces the cited
chunk (see WR-01).

### CR-02: proof-of-funds worked example resolves the wrong chunk (no equity rule)

**File:** `skills/document-agents/proof-of-funds.md:48,83-86`
**Issue:**
The skill claims the baked query `proof settlement funds` *"surfaces the generic
`guidance/proof-funds.md` rule page"* (line 48) and the loop says *"take the top
generic guidance hit"* (line 60). But the worked example (lines 83-86) blindly
takes `hits[0]`:

```python
hits=d['result']['hits']
print(hits[0]['chunk_id'] if hits else 'ABSTAIN: not_in_corpus')
```

Verified against the live index, `hits[0]` is
`pr-pdi/express-entry-assessing-electronic-application-on-section-a11-2.md#036`
(about settlement funds in the CRS/MEC), **not** the guidance page, and it does
**not** contain the equity rule the fixture/skill ground:

```
$ corpus-crawler --json search "proof settlement funds" ...
pr-pdi/...a11-2.md#036                 <- worked example selects THIS (hits[0])
pr-pdi/economic-classes-...#002
guidance/proof-funds.md#007            <- fixture cites THIS (3rd hit)
# #036 HAS "you can't use equity on real property..." : False
# #007 HAS "you can't use equity on real property..." : True
```

The worked example — the concrete snippet an agent copies — contradicts the
skill's own prose and the fixture citation, and lands a chunk from which the
equity claim cannot be grounded. Same failure modes as CR-01 (needless
abstention, or a claim/quote mismatch that the substring-only gate passes). The
ambiguous word "generic" (which elsewhere in the pack means "non-country-specific")
makes it easy to read this as "take the first non-leaky hit" = `#036`.

**Fix:** Make the worked example filter to the `guidance/` family (or assert the
equity span is present) instead of `hits[0]`:

```python
target = next((h for h in hits if h['chunk_id'].startswith('guidance/proof-funds.md')),
              None)
print(target['chunk_id'] if target else 'ABSTAIN: not_in_corpus')
```

and align the prose so "top generic guidance hit" is unambiguous (the
`guidance/proof-funds.md` page, not the first non-country-specific hit).

## Warnings

### WR-01: conformance harness never exercises the agents' baked query — it only validates hand-authored fixture citations

**File:** `crawler/tests/test_document_agents.py:118-152`
**Issue:**
The harness docstring frames the suite as the "per-CLI conformance proof" that
each agent grounds correctly, but `test_per_agent_deterministic_generic_citations`
(lines 127-152) resolves the **fixture's already-hardcoded** `claim["citations"]`
and only checks the resolved family. No test ever calls
`searchindex.search(<baked query>)` to confirm that the query + selection rule an
agent actually runs returns the cited chunk. That gap is precisely why CR-01 and
CR-02 sailed through green: the fixture hand-codes the *correct* `#007`/`#000`
chunks while the skills tell the agent to fetch the *wrong* ones, and nothing
reconciles the two. The suite proves "the fixture grounds," not "the agents
retrieve what they cite."

**Fix:** Add a parametrized test that, for each agent, extracts the skill's baked
query, runs `searchindex.search(_REAL_DB, query, family=...)`, applies the skill's
documented selection rule, and asserts the result equals the fixture's cited
chunk id — closing the skill↔fixture↔index loop. (This test would currently fail
for `medical` and `proof-of-funds`, surfacing CR-01/CR-02.)

### WR-02: the only grounding proof is skip-guarded behind a git-ignored corpus — CI reports green without ever running the gate

**File:** `crawler/tests/test_document_agents.py:108`
**Issue:**
`TestDocumentAgentsConformance` is the only class that runs the real grounding
gate, and it is `@unittest.skipUnless(_REAL_DB.is_file(), ...)` with
`_REAL_DB = Path("corpus/index.db")`. I confirmed `corpus/index.db` is
git-ignored and not tracked (`git check-ignore` → ignored; `git ls-files` → not
tracked). On CI or a fresh clone the corpus is absent, so the entire grounding
proof silently skips and the suite reports all-green from the four always-run
structural/static classes alone — the central "every claim is grounded" guarantee
is never exercised in automation. The guard itself is written correctly (it does
skip rather than error), but the consequence is a false sense of coverage. A
broken/confabulated fixture line would not be caught in CI.

**Fix:** Commit a tiny, purpose-built, PII-free fixture index containing only the
chunks the fixture cites (or add a CI step that builds the corpus before tests),
so the gate actually runs in automation; alternatively emit a loud warning/xfail
when skipping so a green run cannot be mistaken for a passed grounding proof.

## Info

### IN-01: abstention-entry shape is inconsistent across contract, skills, and fixture (no functional impact)

**File:** `skills/document-agents/_contract.md:188-193`, `skills/document-agents/police-certificate.md:121`, `crawler/eval/document_agents.jsonl:8`
**Issue:**
The contract and all five abstaining skill examples emit a **bare string**
abstention (`"abstentions":["not_in_corpus"]`), while the fixture's `must_abstain`
line emits an **object** (`"abstentions":[{"text":"...","reason":"not_in_corpus"}]`).
The grounding gate never inspects `abstentions[]`, so there is no behavioural
impact, but the documented shape disagrees with itself and could lead an agent to
emit a non-conforming abstention object.
**Fix:** Pick one abstention shape and use it consistently across `_contract.md`,
the six skills, and the fixture (the object form `{text, reason}` is the richer
choice).

---

_Reviewed: 2026-06-21T15:08:45Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
