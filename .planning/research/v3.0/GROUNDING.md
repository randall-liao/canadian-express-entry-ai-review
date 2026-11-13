# v3.0 Research: Grounding Gate, Eval Harness, Personalized Checklist & Document Agents

**Milestone:** v3.0 — Grounded Answer Layer
**Researched:** 2026-06-20
**Scope:** Everything that sits *on top of* retrieval. The sister doc
`.planning/research/v3.0/RETRIEVAL.md` owns the FTS5 `search` verb and the
resolvable citation IDs; **this doc assumes** `search` returns ranked chunks,
each with a stable citation ID, and exposes a `--cite <id>` resolver that
returns the chunk (or "not found").
**Confidence:** HIGH (codebase-grounded; reuses shipped `contract.py`,
`check_publish_safe.py`, `dupaudit` RPT-03, `eval_runner.py`). The only MEDIUM
item is the exact RET citation-ID/resolver signature, deferred to RETRIEVAL.md.

---

## TL;DR (decisive recommendations)

1. **Answer format = structured JSON `{claims:[{id, text, citations[], quote}], ...}`.**
   The agent declares its own claim boundaries. Reject free-text + NLP claim
   extraction — it makes fail-closed unreliable (false negatives let uncited
   claims slip; false positives flag filler).
2. **Gate = pure-Python, deterministic, fail-closed**, mirroring the `dupaudit`
   RPT-03 *render-then-gate* pattern. Reuses `contract.py` (envelope/exit codes)
   and the RET `--cite` resolver. ANY uncited claim or unresolvable citation →
   `verdict:"fail"`, **nothing rendered**, non-zero exit.
3. **Same gate IS the eval harness** — run a tracked, PII-free reference
   question set through agent → gate; mirror `eval_runner.py`'s
   `{total, passed, failed, failures}` shape and exit-1-on-any-fail.
4. **PII lives in the git-ignored `personal/` tree** (already in `.gitignore`),
   resolved via `$PR_PERSONAL_DIR`. Not platformdirs. Add `personal/` to the
   publish-safety tracked-corpora guard as a backstop.
5. **Be honest:** the gate guarantees **resolvability** (every claim → a real
   chunk + a verbatim quote that exists in that chunk). It does **not** prove
   **faithfulness** (that the chunk *entails* the paraphrase). State this limit
   in the plan; do not overpromise.

---

## 1. Answer format contract (recommended)

### Recommendation: a machine-readable structured answer — NOT free text

Every grounded output (a document-agent answer OR a checklist) is **one JSON
object** the agent emits on stdout, wrapped in the existing five-key envelope
from `crawler/contract.py`. The `result` payload:

```json
{
  "question": "Do I need a police certificate, and how recent must it be?",
  "claims": [
    {
      "id": "c1",
      "text": "A police certificate is required for each country where you lived 6 months or more in a row since age 18.",
      "citations": ["ircc-police-certs__who-needs-one__a1b2c3"],
      "quote": "you must provide a police certificate for each country ... where you lived for 6 months or more in a row since the age of 18"
    },
    {
      "id": "c2",
      "text": "A police certificate must be less than 6 months old at the time you submit your application.",
      "citations": ["ircc-police-certs__validity__d4e5f6"],
      "quote": "must have been issued no more than 6 months before"
    }
  ],
  "basis": [
    "profile.countries_lived_since_18 = [CN, CA]  (drives WHICH claims apply; from profile, not corpus)"
  ],
  "abstentions": [
    { "text": "Whether an FBI certificate expires differently for dual citizens", "reason": "not_in_corpus" }
  ],
  "prose": "Here's what you need for police certificates:"
}
```

Field rules the gate enforces:

| Field | Meaning | Gate rule |
|---|---|---|
| `claims[]` | **Factual corpus claims only.** One atomic assertion each. | Every entry MUST have ≥1 `citations` AND each citation MUST resolve AND `quote` MUST be a verbatim substring of the resolved chunk. |
| `claims[].text` | The paraphrased requirement shown to the user. | — |
| `claims[].citations[]` | RET citation IDs from `search`. | Each resolved via RET `--cite`. |
| `claims[].quote` | Verbatim span copied from the cited chunk. | Substring-checked against resolved chunk text (cheap faithfulness signal). |
| `basis[]` | Profile-derived applicability ("you lived in CN+CA"). **PII-adjacent, NOT a corpus fact.** | NOT citation-checked; never written to a tracked path. |
| `abstentions[]` | Explicit "not in corpus" — a first-class, non-penalized outcome. | Not citation-checked; surfaced to user. |
| `prose` | Preamble / transition filler. NOT a factual claim. | **Ignored by the gate** — this is why over-segmentation never happens. |

### Why structured output, not free-text + NLP claim extraction

This is the single most important decision for making fail-closed reliable.

| | Structured `{claim, citations[]}` (RECOMMENDED) | Free text + NLP claim extraction |
|---|---|---|
| **Claim boundary** | Declared by the agent that *wrote* the claim — the only party that knows which sentences are factual assertions. Explicit. | Guessed by a sentence/clause splitter at gate time. |
| **False negatives** (uncited claim slips through) | Impossible by construction: a claim not in `claims[]` is not rendered; a claim in `claims[]` with no citation fails the gate. | Real risk: splitter misses a buried assertion → it's never checked → ungrounded text ships. **This breaks the acceptance bar.** |
| **False positives** (filler flagged) | None: `prose`/preamble lives outside `claims[]`. | Real risk: "Here's your checklist:" gets split into a "claim" demanding a citation. |
| **Determinism** | Total — string presence + substring + resolver lookup. No model, no heuristics. | Depends on the extractor (NLP model or brittle regex); non-deterministic or English-only. |
| **CLI-agnostic** | Yes — "emit one JSON object," identical to `AGENT_SKILL.md`. | Needs an NLP dependency in the gate; contradicts the pure-stdlib convention. |
| **Constraint fit** | Pure stdlib; no vectors; no model. | Pushes toward a model/NLP lib in the trust path. |

Free-text grounding makes fail-closed a *probabilistic* property (we *hope* the
splitter caught every claim). The acceptance bar is *absolute* ("ANY uncited
claim fails the ENTIRE output"). Only a contract where **the generator emits
discrete, pre-segmented claims** can satisfy an absolute bar deterministically.
The burden of "what is a claim" is moved to generation time (where the author
knows) instead of gate time (where it must be guessed). This mirrors how the
codebase already pushes structure to the producer: `eval_runner.py` consumes
agent-authored `must_contain`/`must_not_contain` arrays rather than re-deriving
them, and `contract.py` standardizes one JSON object per invocation.

---

## 2. Grounding gate algorithm + fail-closed behaviour

A new pure-Python module (suggested `crawler/grounding.py`, CLI verb `ground`)
reads the structured answer JSON from **stdin** (or a `--in <file>`), validates
it, and emits the existing envelope. Agents shell out:

```bash
police-cert-agent | corpus-crawler --json ground            # exit 0 ⇒ grounded; non-zero ⇒ refused
```

### Deterministic algorithm

```
1. PARSE the answer JSON.
   - Unparseable / missing required keys (`question`, `claims`) →
     contract.INVALID_INPUT, exit EXIT_INVALID_INPUT (2). FAIL CLOSED.

2. SEGMENT — already explicit. claims = payload["claims"]. No NLP.
   (prose / basis / abstentions are NOT claims and are skipped.)

3. For each claim c in claims:
   a. CITED?  len(c["citations"]) >= 1, else → violation(c.id, "uncited").
   b. RESOLVE each id via the RET resolver (search --cite <id>):
        chunk = resolve_citation(id)
        if chunk is None → violation(c.id, "unresolvable", id).
   c. QUOTE-SUPPORT (deterministic faithfulness floor):
        if normalize(c["quote"]) not in normalize(chunk.text)
            → violation(c.id, "quote_not_in_chunk", id).
      (normalize = collapse whitespace + casefold, à la eval_runner._norm.)

4. GATE:
   if any violations:
       verdict = "fail";  DO NOT render the answer.
       --json: contract.emit(envelope("ground",
                  result={"verdict":"fail","violations":[...]}))   # ok:true
       exit 1.                       # mirrors `report` verdict-fail semantics

5. RENDER the human answer markdown (claims + citations + crawl_date).

6. RPT-03 SHARE-SAFETY GATE (reuse check_publish_safe.scan_text):
        violations = cps.scan_text(out_path, rendered_md)
        if violations:
            --json: envelope("ground", error=(INTERNAL_ERROR, msg))  # ok:false
            exit EXIT_INTERNAL_ERROR (4).   # identical to dupaudit lines 614-629

7. EMIT: write rendered answer to personal/output/ (git-ignored), and
        --json: envelope("ground", result={"verdict":"pass","claims":[...],
                  "citations_resolved": N, "report": "<path>"})
        exit 0.
```

### Exit-code contract (reuses `crawler/contract.py` constants)

| Exit | Envelope | Condition | Meaning |
|---|---|---|---|
| `0` | `ok:true`, `verdict:"pass"` | All claims cited + resolved + quote-checked; render share-safe. | Answer emitted. |
| `1` | `ok:true`, `verdict:"fail"` | ≥1 uncited / unresolvable / quote-mismatch claim. | **Answer refused.** Violations listed. (Same shape as a `report` verdict-fail.) |
| `2` | `ok:false`, `invalid_input` | Answer JSON malformed / missing keys. | Fix the producer. |
| `4` | `ok:false`, `internal_error` | Rendered answer tripped the publish-safety scan (PII/abs-path/secret). | RPT-03 backstop fired. |

**Two distinct fail-closed conditions, two codes:** grounding failure is an
*expected* verdict (`exit 1`, `ok:true` — the gate did its job), exactly like
`report` treating a failing corpus as `verdict:"fail"`, not an error. A PII leak
in the rendered text is a *should-never-happen* condition (`exit 4`,
`ok:false`), exactly like `dupaudit`'s RPT-03 refusal. Both are non-zero and
both emit nothing user-facing — satisfying "non-zero exit, nothing emitted."

**Why render-then-gate (not gate-then-render):** the safety scan must run over
the *exact bytes* the user would see. `dupaudit.main` (lines 604-629) renders
the markdown, scans the rendered string with `cps.scan_text`, and only writes
if clean. Mirror that ordering precisely.

---

## 3. What grounding-by-construction guarantees — and what it does NOT

Be explicit in the plan; this is the honesty boundary the quality gate demands.

**GUARANTEES (resolvability — fully deterministic, no model):**
- Every rendered factual claim carries ≥1 citation ID. **No uncited claims.**
- Every citation ID resolves to a real corpus chunk. **No fabricated/dangling IDs.**
- Every claim carries a `quote` that is a *verbatim substring* of its resolved
  chunk. **No purely decorative citations** (the cited chunk demonstrably
  contains the quoted text).
- The output is **all-or-nothing**: one bad claim → the whole answer is refused.
- No PII reaches a tracked path (RPT-03 backstop + write-to-`personal/` only).

**DOES NOT GUARANTEE (faithfulness / entailment):**
- That the cited chunk **semantically supports** the paraphrased `claim.text`.
  The quote-substring check proves the *quote* is from the chunk; it does **not**
  prove the agent's *paraphrase* of that quote is correct, or that the quote
  (in context) actually entails the claim. A claim could cite a real chunk,
  quote it verbatim, and still mis-paraphrase or quote out of context.
- That the *most authoritative* source was cited (an IRCC guidance page vs. the
  underlying IRPR section).
- That the corpus itself is current (freshness is surfaced via `crawl_date`, not
  proven).

**Why the gap exists in v3.0:** true entailment checking needs NLI / semantic
similarity → a model or embeddings. That violates the *no-vectors / no-cloud /
deterministic* constraints. So v3.0 deliberately stops at **resolvability +
verbatim-quote**, which closes the *cheap* 80% of the faithfulness gap (kills
hallucinated and decorative citations) at zero model cost.

**Pragmatic v3.0 stance (recommended):**
1. Make `quote` a **required** field and the substring check a **hard** gate.
   It is the highest-leverage deterministic control (it is the
   "verify the quoted span is a substring of the chunk" item already on the
   PITFALLS "Looks done but isn't" checklist).
2. Keep claims as **close, atomic paraphrases** of their quote (one fact per
   claim) so the human-judgeable gap between quote and paraphrase stays small.
3. Render quote + claim **side by side** in the human output so the applicant
   can eyeball faithfulness.
4. Document entailment/NLI scoring as a **future** item (alongside VAL-01/02).
   Do **not** claim the gate proves the citation "supports" the claim.

---

## 4. Eval harness (the gate, run over a reference set)

The eval harness is **the same gate** applied to a tracked, PII-free question
set — no separate machinery. This keeps "the bar" and "the test" identical
(the locked requirement: *the gate doubles as the automated eval harness*).

### Reference set (tracked, synthetic, no PII)

`crawler/eval/questions.jsonl` — one record per line:

```json
{ "id": "police-01",
  "question": "How recent must a police certificate be?",
  "expect_families": ["guidance"],
  "expect_terms": ["6 months"],
  "must_abstain": false }
```

Include **adversarial** records (`"must_abstain": true`) whose answer is *not*
in the corpus, to assert the agent abstains instead of confabulating.

### Runner (mirror `eval_runner.py`)

For each question: run the document agent → structured answer → grounding gate.
Aggregate into the same shape `eval_runner.py` already emits, exit 1 if any fail:

```json
{ "total": 24, "passed": 23, "failed": 1,
  "failures": [ { "id": "funds-03", "reasons": ["uncited_claim:c2"] } ] }
```

### Metrics (hard gates vs. soft signals)

| Metric | Definition | Threshold |
|---|---|---|
| **uncited_claim_count** | claims with 0 citations across all answers | **MUST be 0** (hard) |
| **citation_resolution_rate** | citations resolving / total citations | **MUST be 100%** (hard) |
| **quote_substring_rate** | quotes that are verbatim substrings of their chunk | **MUST be 100%** (hard) |
| **abstention_correctness** | adversarial questions correctly abstained | **MUST be 100%** (hard) |
| **retrieval_hit@expected** | answers whose cited chunks include an expected family/section | report % (soft — a different-but-valid chunk is acceptable) |
| **expected_term_present** | answers whose claim text contains the expected fact term | report % (soft sanity signal) |

The first four are *grounding* properties → hard gates (define trustworthiness).
The last two are *retrieval-quality* signals → reported, not enforced, because a
correct answer may legitimately cite a different valid chunk than the one the
fixture author guessed. Keeping them soft avoids brittle, overfit eval failures
while still surfacing recall regressions — consistent with the PITFALLS note
that *recall*, not load, is this project's real risk.

---

## 5. Personalized Layer-1 checklist + PII separation

### Where the profile lives — recommend git-ignored `personal/`, not platformdirs

`.gitignore` **already** encodes the boundary:

```
personal/            # ignored (the user's real data)
!personal.example/   # tracked (synthetic schema only)
```

Recommendation: profile at `personal/profile.yaml`, resolved via
`$PR_PERSONAL_DIR` (default `./personal/`) exactly as `ARCHITECTURE.md`
specifies. All generated output (checklist, answers) to `personal/output/`.

**Why `personal/` over `platformdirs` (`~/.local/share/...`):**
- Already established convention + `.gitignore` rule + the `ARCHITECTURE.md`
  PII-direction invariant; no new pattern to invent.
- The publish-safety scanner is git-tree-pinned (`git -C <root> ls-files`); a
  git-ignored in-tree `personal/` is naturally outside its scan, and a guard
  (below) fails closed the instant it is *ever* tracked. Out-of-tree
  platformdirs data is invisible to that guard.
- Project convention is **pure stdlib** (`contract.py`, `check_publish_safe.py`).
  `platformdirs` is a new dependency for zero benefit here.
- Offer an env override (`PR_PERSONAL_DIR=/abs/path`) for users who *want* their
  data outside the repo tree, but default to in-tree git-ignored `personal/`.

### Tracking guard (extend the shipped scanner — fail closed)

`scripts/check_publish_safe.py` already flags tracked personal corpora purely by
path name via `CORPORA_PREFIXES` and `scan_path_name`:

```python
CORPORA_PREFIXES = ("trial/", "personal/", "corpus_new/")   # add "personal/"
```

Adding `personal/` means: if a profile/output file is *ever* `git add`-ed, the
existing publish-safety check (pre-commit / CI) emits a `TRACKED_CORPORA`
violation and exits non-zero. `personal.example/` (synthetic) stays tracked.

### Keeping the checklist grounded

The checklist is **just another structured answer** that goes through the **same
gate**. Crucial separation of concerns:

- **Profile decides WHICH items appear** (applicability). "You lived in CN and
  CA" → the police-certificate item applies. This lives in the `basis[]` field —
  it is a fact about the *user*, sourced from the profile, **not** citation-checked
  (the corpus does not know the user's countries).
- **Corpus decides the REQUIREMENT TEXT + citation.** "A police certificate is
  required for each country lived in 6+ months since 18" is a `claims[]` entry —
  it MUST carry a resolving, quote-checked citation.

So every "you need document X" *requirement* line is gated; the *applicability*
(why it applies to this user) is profile-derived and stays local. PII (country
names, dates) appears only in `basis[]` and in the rendered file under
`personal/output/` — never in `claims[].text`, never in a tracked path. The
RPT-03 scan over the rendered checklist is the backstop.

---

## 6. Document-agent skill skeleton (portable, CLI-agnostic)

Five agents (police certificate, language test, ECA, proof of funds, medical)
share **one** `crawler/agents/_contract.md` (the answer format + gate rules from
§1-2). Each agent is a thin markdown file: its document-specific queries +
profile slice. Authoring rules mirror `crawler/AGENT_SKILL.md`: **plain
Markdown, no proprietary front-matter, everything is an ordinary shell command +
one JSON object.**

```markdown
# Agent Skill: Police Certificate (grounded, CLI-agnostic)

You answer ONLY from the local corpus via shell commands + JSON. You never
assert immigration facts from memory. Output MUST pass the grounding gate.

## 1. Read the profile slice (LOCAL ONLY — never echo into tracked files)
Read `$PR_PERSONAL_DIR/profile.yaml` (default ./personal/). Use only:
`countries_lived_since_18`, `current_country`, `age`. These drive applicability
(the `basis`), NOT corpus claims.

## 2. Retrieve (RET-02 search contract — one JSON object on stdout)
    corpus-crawler --json search "police certificate who must provide" --top-k 5
    corpus-crawler --json search "police certificate how recent valid 6 months" --top-k 5
Read `result.results[]`; each has a citation `id`, `text`, and `citation`
metadata. Use ONLY these chunks.

## 3. Form claims (from retrieved text ONLY)
For each requirement you state, copy a VERBATIM `quote` from the chunk it comes
from and record that chunk's citation `id`. One atomic fact per claim. If the
search returns nothing relevant, emit ZERO claims with an explicit `abstention`
— "not in corpus" is a correct, expected answer. Never fabricate a citation id.

## 4. Emit the structured answer (the gate's input)
Print ONE JSON object:
    {"question": "...",
     "claims": [{"id":"c1","text":"<requirement>","citations":["<id>"],"quote":"<verbatim span>"}],
     "basis": ["profile.countries_lived_since_18 = [...]"],
     "abstentions": []}

## 5. Gate it (fail-closed)
    <step-4 output> | corpus-crawler --json ground
Exit 0 → grounded, answer rendered under personal/output/. Non-zero → DO NOT
present the answer; read result.violations, retrieve more, or abstain.
```

Each sibling agent (`language_test.md`, `eca.md`, `proof_of_funds.md`,
`medical.md`) changes only the **profile slice** and the **search queries**; the
contract, claim rules, gate call, and fail-closed behaviour are identical.

---

## 7. Pitfalls (ranked, each with a mitigation)

| # | Pitfall | Why it bites | Mitigation (decisive) |
|---|---|---|---|
| **1** | **Fabricated citation IDs that look valid** | LLMs invent plausible IDs and attach them as decoration (PITFALLS Pitfall 2). | RET resolver checks **every** ID against the real index; unresolvable → `verdict:fail`, exit 1 (GND-01). Make RET citation IDs content-hash-derived (opaque), so a guessed ID essentially never collides with a real chunk. |
| **2** | **Partial citation** (some claims cited, some not) | A single "Sources" footer *looks* grounded but doesn't bind to specific claims. | Citations bind **per claim**, never at answer level. Gate iterates **all** `claims[]`; ANY empty `citations` → whole output fails. No answer-level "sources" shortcut. |
| **3** | **Resolves-but-doesn't-support** (faithfulness gap) | A real chunk is cited but doesn't actually entail the claim. The gate's hardest limit. | Hard **verbatim-`quote` substring** check closes the cheap part; render quote beside claim for human review; keep claims atomic paraphrases of the quote. **Acknowledge full entailment is out of scope for v3.0** (no model/NLI). Do not overpromise (§3). |
| **4** | **Over-segmentation flags non-factual filler** | An NLP splitter turns "Here's your checklist:" into a citation-demanding "claim" → false-positive failures. | **Structured contract**: filler lives in `prose`; only `claims[]` is gated. The gate never invents claim boundaries. (This is the decisive reason for §1's recommendation.) |
| **5** | **PII leaks into a shareable answer** | A rendered checklist contains the applicant's countries/dates and someone shares it. | Answers/checklists written **only** to git-ignored `personal/output/`; RPT-03 `scan_text` over the rendered bytes as backstop (exit 4); PII confined to `basis[]`/local files; `claims[].text` is corpus-derived (corpus has no PII). Extend `CORPORA_PREFIXES` with `personal/`. |
| **6** | **Agent-prompt portability drift across CLIs** | "Grounded under Claude, ungrounded under Copilot" — a correctness divergence disguised as a portability nit (PITFALLS Pitfall 9). | All logic in the **Python gate + shell `search`**, not in CLI-native tooling; **one** `_contract.md` source of truth; per-CLI **conformance test**: same question under each CLI must pass the gate with the same resolved citation set. Mirror `AGENT_SKILL.md`'s "one JSON object" invariant. |
| **7** | **Compound claims under-cited** | "X is required AND must be < 6 months old" carries one citation but states two facts; the uncovered fact is effectively ungrounded. | Require **atomic claims** (one assertion each) in `_contract.md`; add a soft eval warning that flags conjunctions / over-long claims for splitting. |

---

## 8. Reuse map (concrete files / functions to build on)

| Need | Reuse | How |
|---|---|---|
| JSON envelope + exit codes | `crawler/contract.py` — `envelope()`, `emit()`, `SCHEMA_VERSION`, `EXIT_INVALID_INPUT` (2), `EXIT_INTERNAL_ERROR` (4) | `ground`/`checklist` verbs emit the same five-key envelope; grounding fail = `verdict:"fail"` (exit 1, `ok:true`), invalid answer = exit 2, PII-in-render = exit 4. |
| Citation resolver | **RET `search --cite <id>`** (sister RETRIEVAL.md) | The gate's `resolve_citation(id)` — single source of truth for "is this citation real" (GND-01). |
| Render-then-gate, fail-closed | `crawler/dupaudit.py` `main()` **lines 604-629** | Copy the order: render markdown → `cps.scan_text(path, rendered)` → refuse + non-zero exit on any violation → only then write. Apply to the answer/checklist render. |
| Publish-safety / PII scan | `scripts/check_publish_safe.py` — `scan_text(path, text)`, `CORPORA_PREFIXES`, `scan_path_name()` | RPT-03 backstop over rendered answer (exit 4); add `personal/` to `CORPORA_PREFIXES` as a tracking guard. |
| Deterministic per-item eval | `crawler/eval_runner.py` — `run()`/`check_doc()`, `_norm()`, `{total,passed,failed,failures}` JSON, exit-1-on-fail | The grounding eval harness mirrors this exact shape and the `_norm` (whitespace-collapse + casefold) used for the quote substring check. |
| Portable agent pattern | `crawler/AGENT_SKILL.md` + `crawler/CONTRACT.md` | Document-agent skills follow the same "ordinary shell command + parse one JSON object, no proprietary tooling" contract. |
| PII boundary | `.gitignore` (`personal/`, `!personal.example/`) + `ARCHITECTURE.md` PII-direction invariant | Profile at `$PR_PERSONAL_DIR` (default `./personal/`); output to `personal/output/`; PII never enters `claims[]` or a tracked path. |

### Suggested phase shape for the planner

1. **Grounding gate + citation resolver** (`crawler/grounding.py`, `ground`
   verb) — GND-01/02. Depends on RET's `--cite` resolver. Ship with the
   structured-answer contract (`_contract.md`) and the verbatim-quote check.
2. **Eval harness** — the gate over a tracked PII-free question set; metrics in
   §4; mirrors `eval_runner.py`. (Same phase or immediately after — it *is* the
   gate, so minimal extra surface.)
3. **Personalized Layer-1 checklist** — CHK-01/02. Profile loader from
   `personal/`, applicability→`basis`, requirement→gated `claims[]`; tracking
   guard added to the publish-safety scanner.
4. **Document agents** — CHK-03. Five thin markdown skills sharing `_contract.md`;
   per-CLI conformance test.

Ordering rationale: the gate is the contract every later phase emits into, so it
must exist first; the eval harness is the gate pointed at fixtures (free once the
gate exists); checklist and agents are *producers* validated by the gate.
