---
title: "Answer Layer Gap + Grounding-by-Construction Bar"
date: 2026-06-20
context: "Captured from /gsd-explore after v2.2 (corpus dedup/cleanup) closed. Decides what 'next' means now that data collection is done."
---

# Answer Layer Gap + Grounding-by-Construction Bar

## Trigger

After v2.2 closed, the question was: *"数据收集完成，下一步做什么"* (data collection done — what's next?).
Data + QC are done; the question is what the next milestone delivers.

## Key finding — only half the system is in the repo

What is actually tracked and runnable today is the **corpus + QC half**:

- `corpus-crawler` CLI subcommands (`crawler/cli.py`): `crawl → apply-verdicts → completeness → report`,
  plus the dedup tools (`dupaudit.py`, `dupclean.py`).
- QC enforcement: `eval_runner.py` (per-doc relevance / `must_contain` / `must_not_contain` /
  `grounding_refs`) and `completeness.py` (guards silent truncation).
- `corpus/` — 16 families of clean, deduped, QC-passed authoritative markdown (local, git-ignored).

The **answer half** that PROJECT.md / the v1.0 ROADMAP describe as "shipped" — the FTS5
search/citation contract, the grounding gate, the Layer-1 personalized checklist, and the 5
document agents — is **NOT present in this repository** (verified: no `search`/`index` CLI
command, no `.db` FTS5 index anywhere, no checklist generator; grep for fts5/checklist/grounding
hits only GSD tooling + incidental mentions). It most likely stayed behind in the untracked
`tools/` + `trial/` tree when the v2.0 productization extracted only the crawler into the
shareable package.

## Decision / direction

The next step is **not** "add tests to an existing system." It is to **(re)build the answer
layer with grounding baked in by construction**, so validation is a property of the design rather
than something bolted on afterward.

## Acceptance bar (user-defined)

**Grounding-by-construction.** Every factual claim in a generated answer/checklist must carry a
citation that resolves to a real corpus chunk. If *any* claim is uncited or its citation does not
resolve, the **entire output fails (fail-closed)**. This hard gate *is* the definition of
"trustworthy enough for an applicant to use on a real application," and it doubles as the automated eval
harness.

## Constraints carried forward (from PROJECT.md / STACK.md)

- Keyword retrieval only — **SQLite FTS5**, no vectors / no embedding APIs.
- All PII (profile, documents, answers) stays in the local git-ignored area — never the repo or
  the corpus DB.
- CLI-agnostic harness — tools are ordinary shell commands emitting the JSON envelope contract;
  no proprietary per-CLI tooling.
- Authoritative-only corpus (IRCC / IRPA / IRPR / PDIs).

## Next action

This is multi-phase / milestone scale — it must be a **new milestone**, not a phase appended to
the completed v2.2. Start with `/gsd-new-milestone` to scope "Grounded Answer Layer".
See seed: `.planning/seeds/grounded-answer-layer.md`. Candidate requirements captured in
`REQUIREMENTS.md` under "Next Milestone (Candidate) — Grounded Answer Layer".
