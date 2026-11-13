---
title: "Grounded Answer Layer — next milestone"
trigger_condition: "v2.2 is closed and corpus/ is clean & deduped (TRUE now). Start the answer-layer milestone."
planted_date: 2026-06-20
---

# Seed: Grounded Answer Layer (next milestone)

## Why now

Data collection is done — the corpus (16 families, deduped, QC-enforced) and the corpus/QC
pipeline (`corpus-crawler`, `eval_runner`, `completeness`) are complete. But the layer that
actually *answers* an applicant's questions with grounded, cited output — FTS5 search/citation
contract, grounding gate, Layer-1 personalized checklist, document agents — is **not in the repo**
and must be (re)built. See `.planning/notes/answer-layer-gap-and-grounding-bar.md`.

## What to do

Run `/gsd-new-milestone` to scope **"Grounded Answer Layer"** (suggested v2.3 or v3.0). It is
multi-phase scale, so it must be its own milestone — do not append phases to the completed v2.2.

Likely phase shape (for the roadmapper to refine):

1. **FTS5 index + `search` contract** — chunk the clean corpus, build a re-runnable SQLite FTS5
   index with citation metadata (corpus-relative path, source_url, title, section, crawl_date);
   expose a `search` CLI verb returning ranked chunks + resolvable citation IDs (JSON envelope per
   existing `CONTRACT.md`).
2. **Grounding gate + citation resolver** — the fail-closed gate that rejects any output with an
   uncited or unresolvable factual claim. This is the acceptance bar AND the eval harness.
3. **Personalized Layer-1 checklist + document agents** — consume `search` to produce the
   applicant's cited checklist; PII stays local.

## Acceptance bar (locked)

Grounding-by-construction: every factual claim → a citation resolving to a corpus chunk; any
uncited claim fails the whole output (fail-closed).

## Candidate requirements

Captured in `REQUIREMENTS.md` → "Next Milestone (Candidate) — Grounded Answer Layer"
(prefixes RET / GND / CHK).
