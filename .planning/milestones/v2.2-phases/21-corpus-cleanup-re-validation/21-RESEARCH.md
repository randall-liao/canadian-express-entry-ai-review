# Phase 21: Corpus Cleanup & Re-validation - Research

**Researched:** 2026-06-11
**Domain:** Local corpus mutation (safe deletion) + post-deletion QC/completeness re-validation, Python stdlib
**Confidence:** HIGH (all findings grounded in real file reads of this repo; no external packages)

## Summary

Phase 21 *executes* the keep/delete decisions that Phase 20's read-only audit (`crawler/dupaudit.py`)
already computed and serialized to `reports/duplicate-audit.json`. The report names **16 delete
targets across 11 clusters**; the corpus is the local, git-ignored `corpus/` tree (16 families /
752 live docs). The work splits cleanly into: (1) consume the report deterministically, (2) remove
the non-canonical copies from the *live* set safely, (3) refresh the derived artifacts that still
reference the removed files, and (4) re-run the detector to prove the resolved clusters are gone.

The single biggest finding is a **safety fork that the Phase 20 verifier explicitly carried forward**
(`20-VERIFICATION.md:112-116`): of the 16 delete targets, **10 are exact/URL-backed (high-confidence
true duplicates)** but **6 are overlap-only (text-similarity ≥0.95) false positives** — they are
distinct documents that merely share boilerplate. I confirmed by reading the files: the overlap-only
"duplicates" pair *different countries* (`tokelau`→`korea-north`, `guadeloupe`→`french-polynesia`,
`mayotte`→`reunion`) and *different Express Entry rounds* (`invitations-12`→`invitations-20`).
Auto-deleting these would destroy real, distinct content. The second finding is operational: the
repo already has the exact pattern for "delete" — `crawler/apply_verdicts.py` **moves** dropped docs
into a per-family `_dropped/` quarantine, prunes `manifest.json`, and writes an audit log, with a
`--dry-run` flag. Both `dupaudit.live_docs` and `completeness.live_docs` exclude `_dropped/`, so a
move is a true removal from the live set while staying fully recoverable — critical because
`corpus/` is git-ignored and a hard `unlink` is unrecoverable.

**Primary recommendation:** Build a new offline `python -m crawler.dupclean` module that consumes
`reports/duplicate-audit.json`, **moves** (not unlinks) only the **exact + URL-backed** non-canonical
members into their owning family's `_dropped/` (mirroring `apply_verdicts.py`), **dry-run by default**
with an explicit `--apply` flag, and **excludes overlap-only clusters by default** behind a separate
`--include-overlap` gate that requires per-cluster human confirmation. Re-validate by pruning the
affected `manifest.json` files + orphaned `completeness/` artifacts, regenerating each touched
family's `REPORT.md` via `crawler.completeness --report`, and asserting the **exact+URL detectors**
(fast — no `SequenceMatcher`) report zero clusters.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **CLEAN-02** | Delete all non-canonical copies named in the Phase 20 report, leaving exactly one canonical per cluster; re-running the detector then finds zero clusters. | Report schema decoded (§ Report Schema); delete-target inventory enumerated (§ Delete-Target Inventory); safe-removal mechanism = move-to-`_dropped/` reusing `apply_verdicts.py` pattern; zero-cluster re-check scoped to fast exact+URL detectors (§ Pattern 4). |
| **CLEAN-03** | Re-validate corpus after deletion: update live-doc counts, QC/completeness validators pass, no dangling references. | Counts auto-recompute in `completeness.build_report` (reads live glob); dangling-reference inventory computed per target (§ Dangling References); refresh procedure = prune `manifest.json` + orphaned `completeness/` + regen `REPORT.md`. |
</phase_requirements>

## Project Constraints (from PROJECT.md / REQUIREMENTS.md / AGENTS.md)

> No `./copilot-instructions.md` exists; no CONTEXT.md exists for this phase (`skip_discuss: true`).
> These constraints are treated with the same authority as locked decisions.

- **Python + Poetry** for all tooling (`pyproject.toml` + `poetry.lock`, `poetry run`). [VERIFIED: PROJECT.md:99-100,120]
- **Dependency-light**: stdlib + already-present deps only (`pyyaml` is present). **No new packages.** This phase needs nothing beyond `pathlib`, `shutil`, `json`, `argparse`, `difflib` — all stdlib. [VERIFIED: dupaudit.py:21-23 docstring + apply_verdicts.py imports]
- **Offline**: NO `crawl4ai`, NO network, NO browser in the cleanup path or its tests. (Note: `completeness --fetch` *does* need crawl4ai/network — Phase 21 must use `--report` only, which is pure-Python.) [VERIFIED: dupaudit.py:22; completeness.py:88-92]
- **Tests: stdlib `unittest` ONLY** — no pytest, no network, no crawl4ai. Run `python -m unittest crawler.tests.test_dupclean -v` from repo root. Synthetic corpus in a tempdir. [VERIFIED: test_dupaudit.py:1-6 docstring]
- **No PII** may enter the public repo; `corpus/` is git-ignored and must stay so. The cleanup must not commit corpus content. [VERIFIED: .gitignore:8 `corpus/`; `git check-ignore corpus/` → ignored]
- **`--json` agent contract**: any CLI emits exactly one `contract.envelope(...)` line via `contract.emit`. [VERIFIED: contract.py:63-90; dupaudit.py:555,638]
- **Productization is OUT OF SCOPE** (DUP-05/06 deferred). This is a one-time op, but should fit repo conventions (offline module + `--json`). [VERIFIED: REQUIREMENTS.md:36-37,44-45]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Consume keep/delete decisions | Offline analysis module (`crawler.dupclean`) | `reports/duplicate-audit.json` (data) | Decisions are already computed in Phase 20; Phase 21 only reads them — do NOT recompute canonical selection. |
| Remove non-canonical copies from live set | Local filesystem (`corpus/<family>/_dropped/`) | — | "Live" is defined by enumeration filters that exclude `_dropped/`; moving there removes from live without destroying. |
| Refresh derived artifacts | `manifest.json` (per family) + `completeness/` sidecars | — | These are the only files that reference doc paths/URLs; they go stale on deletion. |
| Recompute & record counts | `crawler.completeness --report` → `REPORT.md` | — | `build_report` recomputes `live_docs` live by globbing — it is the count-of-record. |
| Prove zero residual clusters | `crawler.dupaudit` detectors (exact + URL) | — | Re-running the audit's own detectors is the authoritative zero-cluster check. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `pathlib` | 3.10 | path enumeration / resolution | already the repo idiom (`dupaudit`, `apply_verdicts`) [VERIFIED] |
| Python stdlib `shutil` | 3.10 | `shutil.move` files into `_dropped/` | exact precedent in `apply_verdicts.py:52` [VERIFIED] |
| Python stdlib `json` | 3.10 | read `duplicate-audit.json`, rewrite `manifest.json` | repo idiom [VERIFIED] |
| Python stdlib `argparse` | 3.10 | CLI (`--apply`, `--json`, `--include-overlap`) | repo idiom [VERIFIED] |
| `crawler.contract` | repo-internal | `--json` envelope (`envelope`/`emit`, EXIT_* codes) | frozen agent contract [VERIFIED: contract.py] |
| `crawler.dupaudit` | repo-internal | reuse `audit()` / `exact_edges` / `url_edges` for the zero-cluster re-check | keeps "duplicate" definition consistent with Phase 20 [VERIFIED] |
| `crawler.completeness` | repo-internal | `build_report(corpus)` regenerates `REPORT.md` + recomputes live counts | the count-of-record [VERIFIED: completeness.py:188-217,273-274] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `crawler.profile.normalize_url` | repo-internal | normalize a doc's frontmatter URL for manifest pruning | when removing a doc's URL from `manifest.json` [VERIFIED: dupaudit.py:183] |

**Installation:** None. No new dependencies (constraint). Confirm with `poetry run python -m unittest ...`.

**Version verification:** N/A — zero new packages. (Package Legitimacy Audit below records this.)

## Package Legitimacy Audit

> This phase installs **no external packages**. Everything used is Python stdlib or an already-shipped
> repo-internal module. No registry lookups required.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | No new dependencies — constraint satisfied |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Report Schema (what `crawler.dupaudit` produces — the input to Phase 21)

`reports/duplicate-audit.json` is written by `render_json` (dupaudit.py:536-551) and is the
deterministic, machine-readable contract Phase 21 consumes. Top-level keys [VERIFIED: dupaudit.py:544-550 + real file]:

```
{
  "live_docs": 752,
  "exact": 1, "url": 4, "overlap": 8,   # cluster COUNTS per contributing signal
  "total_clusters": 11,
  "clusters": [ <cluster>, ... ]
}
```

Each `<cluster>` (dupaudit.py:408-413) [VERIFIED]:

```
{
  "signals": ["overlap","url"],          # sorted subset of {"exact","url","overlap"}
  "canonical": "guidance/invitations.md", # relpath of the ONE keep
  "size": 7,
  "members": [
    { "relpath": "mi-rounds/invitations-31.md",
      "family": "mi-rounds",
      "url": "https://www.canada.ca/.../invitations.html?q=414",
      "decision": "delete",              # "keep" | "delete"
      "reason": "delete: shorter body" }, ...
  ]
}
```

**Deterministic consumption rules for the deleter:**
- A delete target = any member with `decision == "delete"`. Exactly one member per cluster has `decision == "keep"` and its relpath equals `cluster.canonical` (dupaudit.py:404,410). [VERIFIED]
- Classify each cluster by `signals`: `exact` or `url` present → **high-confidence**; `signals == {"overlap"}` → **overlap-only (risky)**. [VERIFIED — see Pattern 2]
- The richer JSON (vs the human MD) carries `decision`/`reason` per member — **consume the JSON, not the MD** (the MD is for humans, RPT-01/02).
- The `--json` CLI envelope also embeds the same `clusters` under `result.clusters` with `command:"audit-duplicates"` (dupaudit.py:638-647) — but re-reading the persisted file is simpler and avoids re-running the slow audit.

## Delete-Target Inventory (computed from the live report)

**16 delete targets in 11 clusters** [VERIFIED: parsed `reports/duplicate-audit.json`]:

### High-confidence (exact / URL-backed) — 10 targets — SAFE to auto-process
| relpath | signals | canonical kept |
|---------|---------|----------------|
| `police-certificates/police-certificates-1.md` | exact,overlap | `guidance/police-certificates.md` |
| `mi-rounds/invitations-31/-22/-18/-11/-28.md` (5) | overlap,url | `guidance/invitations.md` |
| `mi-rounds/express-entry-rounds.md` | url | `guidance/express-entry-rounds.md` |
| `ministerial-instructions/express-entry-application-management-system.md` | url | `guidance/express-entry-application-management-system.md` |
| `pdi-completeness-check/applications-received-on-after-january-1-2016-completeness-check.md` | url | `pr-pdi/express-entry-...-completeness-check.md` |

*(Note: the 5 `invitations-NN` and `police-certificates-1` carry an `overlap` signal too, but they are
anchored by a strong `url`/`exact` edge — they are genuine duplicates, not overlap-only.)*

### Overlap-ONLY (text ≥0.95, NO url/exact edge) — 6 targets — ⚠️ LIKELY FALSE POSITIVES
| DELETE target | "canonical" it would defer to | Verified distinct? |
|---------------|------------------------------|---------------------|
| `police-certificates/tokelau.md` | `police-certificates/korea-north.md` | **YES — different countries** (Tokelau page body is "Information is unavailable" boilerplate, matching North Korea's) [VERIFIED: read both] |
| `police-certificates/guadeloupe.md` | `police-certificates/french-polynesia.md` | **YES — different French territories** [VERIFIED] |
| `police-certificates/mayotte.md` | `police-certificates/reunion.md` | **YES — different French territories** [VERIFIED] |
| `mi-rounds/invitations-12.md` | `mi-rounds/invitations-20.md` | **YES — different EE rounds** [VERIFIED: distinct round files] |
| `guidance/check-score.md` | `guidance/criteria-comprehensive-ranking-system.md` | LIKELY distinct (CRS tool vs criteria page) [VERIFIED: distinct relpaths/titles] |
| `guidance/grid.md` | `guidance/crs-criteria.md` | LIKELY distinct (CRS grid vs criteria) [VERIFIED] |

**This is the central risk of the phase** and is the verifier's explicit carried-forward gate
(`20-VERIFICATION.md:112-116`): *"Text-overlap ≥0.95 over short, boilerplate-heavy pages can group
distinct logical documents; semantic equivalence cannot be confirmed by grep. This gates safe
deletion in Phase 21."* [VERIFIED]

## Architecture Patterns

### System Architecture Diagram

```
reports/duplicate-audit.json ──(read)──► dupclean.load_plan()
                                              │  parse clusters → {keep, deletes[]}
                                              │  classify each cluster by signals
                                              ▼
                              ┌───────────────────────────────────┐
                              │  partition delete targets          │
                              │   • high-confidence (exact|url)     │──► default scope
                              │   • overlap-only                    │──► EXCLUDED unless
                              └───────────────────────────────────┘     --include-overlap
                                              │ (dry-run by default)
                              ┌───────────────┴────────────────┐
                       --apply absent                     --apply present
                              │                                  │
                              ▼                                  ▼
                   print/emit "would move N"      for each target d:
                   (no fs changes)                  shutil.move(corpus/d →
                                                       corpus/<fam(d)>/_dropped/d)
                                                     append to _dropped/duplicate-clean.log.json
                                                     prune d.url from corpus/<fam>/manifest.json
                                                     remove orphaned completeness/ sidecars
                                              │
                                              ▼
            ┌──────────────────── RE-VALIDATION (CLEAN-03) ───────────────────┐
            │ for each touched family:  completeness.build_report(fam) → REPORT.md │
            │ recompute total live_docs (was 752 → 752 - moved)                   │
            └─────────────────────────────────────────────────────────────────┘
                                              │
                                              ▼
           ZERO-CLUSTER RE-CHECK (CLEAN-02 / SC2):
           re-enumerate live docs → exact_edges() + url_edges() ONLY  ──► assert 0 clusters
           (skip overlap_edges: O(n²) SequenceMatcher, ~9 min on 752 docs)
                                              │
                                              ▼
                       git status corpus/  ──► assert nothing staged (SC5)
```

### Recommended Project Structure
```
crawler/
├── dupclean.py            # NEW: offline cleanup module (this phase)
├── dupaudit.py            # reused: audit(), exact_edges, url_edges for re-check
├── apply_verdicts.py      # PATTERN SOURCE: move-to-_dropped + manifest prune + log
├── completeness.py        # reused: build_report() to regen REPORT.md + counts
├── contract.py            # reused: envelope/emit for --json
└── tests/
    └── test_dupclean.py   # NEW: stdlib unittest, synthetic corpus + report fixture
```

### Pattern 1: "Delete" = move into the owning family's `_dropped/` (NOT hard unlink)
**What:** For each delete target `d`, `shutil.move(corpus/d → corpus/<family(d)>/_dropped/<basename>)`,
plus move its `.eval.json` sibling(s) the same way, and append an audit record.
**When to use:** Always — this is the established repo definition of "remove from live."
**Why it satisfies CLEAN-02:** Both enumerators that define the "live" set explicitly skip `_dropped/`:
```python
# dupaudit.live_docs — dupaudit.py:158-160
if "_dropped" in parts or "completeness" in parts: continue
# completeness.live_docs — completeness.py:67-68
... if p.name not in {"REPORT.md"} and p.parent.name != "_dropped"
```
So a moved file is **gone from every live count and from the detector's input** — exactly "deleted
from the live corpus" — while remaining recoverable. `corpus/` is git-ignored (`git check-ignore
corpus/` → ignored), so a true `os.unlink` would be **unrecoverable**; the move is the safe analog.
**Example (mirrors apply_verdicts.py:30-71):**
```python
# Source: crawler/apply_verdicts.py:49-52,64-68 (proven pattern)
dropped_dir = corpus_root / family / "_dropped"
dropped_dir.mkdir(exist_ok=True)
for src in (corpus_root / relpath, eval_sibling):  # doc + its .eval.json
    if src.is_file():
        shutil.move(str(src), str(dropped_dir / src.name))
# audit log so the op is traceable + reversible
log = dropped_dir / "duplicate-clean.log.json"
existing = json.loads(log.read_text()) if log.is_file() else []
log.write_text(json.dumps(existing + records, indent=2, ensure_ascii=False))
```

### Pattern 2: Treat exact/URL clusters and overlap-only clusters DIFFERENTLY
**What:** Default scope = clusters whose `signals` contain `"exact"` or `"url"` (10 targets).
Overlap-only clusters (`signals == {"overlap"}`, 6 targets) are **excluded by default** and only
processed behind an explicit `--include-overlap` flag that additionally requires per-cluster human
confirmation (or, given the evidence, simply documented as reviewed-and-retained).
**When to use:** Always — overlap-only matches over short boilerplate are demonstrated false positives
here (distinct countries/rounds). [VERIFIED: file reads + 20-VERIFICATION.md:112-116]
**Recommendation:** Do **not** delete the 6 overlap-only targets in this milestone. Record them in the
re-validation output as "reviewed, retained — distinct documents sharing template boilerplate."

### Pattern 3: Dry-run by default, mutate only with `--apply`
**What:** The CLI computes the full plan and prints/emits it without touching the filesystem unless
`--apply` is passed. Mirrors `apply_verdicts.py`'s `--dry-run` (dupaudit/contract idioms), but inverts
the default to fail-safe (no mutation unless explicitly requested).
**Idempotency:** A target already inside `_dropped/` (i.e. its live path no longer exists) is a no-op —
re-running `--apply` must skip missing sources silently (`if src.is_file()`), so the operation is
idempotent. [VERIFIED: apply_verdicts.py:51 guards with `is_file()`]

### Pattern 4: Fast zero-cluster re-check (exact + URL only)
**What:** For SC2, re-enumerate the cleaned live corpus and run **only** `exact_edges` + `url_edges` +
`cluster(...)`, asserting zero components. **Skip `overlap_edges`.**
**Why:** `overlap_edges` is `O(n²)` `difflib.SequenceMatcher` over 752 docs (~9 min) — and after
removing the exact/URL duplicates, the *only* clusters it would still report are the 6 overlap-only
false positives we intentionally retained. Running it would make SC2 fail spuriously. The fast
detectors directly prove "the duplicates we deleted are gone." [VERIFIED: dupaudit.py:242-263 O(n²);
~9-min figure CITED from phase task brief].
**Example:**
```python
# Source: composed from crawler/dupaudit.py:214-239,287-295
from crawler import dupaudit
docs = [dupaudit.parse_doc(p, t, profile, root) for p, t in dupaudit.live_docs(root)]
edges = dupaudit.exact_edges(docs) + dupaudit.url_edges(docs)
assert dupaudit.cluster(len(docs), edges) == []   # zero exact/URL clusters
```

### Anti-Patterns to Avoid
- **Hard `os.unlink`/`os.remove` on corpus files** — unrecoverable (git-ignored), breaks the repo's
  "nothing is silently deleted" invariant (`apply_verdicts.py:6-7`). Use move-to-`_dropped/`.
- **Recomputing canonical selection in Phase 21** — the decisions are frozen in the report; re-deriving
  risks drift. Consume `decision`/`canonical` verbatim.
- **Auto-deleting overlap-only clusters** — destroys distinct country/round pages (demonstrated).
- **Running the full overlap detector for the zero-cluster gate** — slow AND spuriously fails on the
  retained overlap-only set.
- **Editing `crawl_stats.json`'s `recorded`** — that is the historical crawl-time count, intentionally
  distinct from the live count (`REPORT.md` shows both; completeness.py:268 vs :274). Leave it.
- **Committing anything under `corpus/`** — violates the git-ignore / no-PII guarantee.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Quarantine + audit log + manifest prune | Custom move/log code | `crawler.apply_verdicts.apply` pattern (copy its proven move+log+manifest logic) | Already handles `_dropped/` mkdir, `.eval.json` siblings, manifest URL pruning, dry-run [VERIFIED] |
| Re-counting live docs | Custom glob+filter | `crawler.completeness.build_report` (writes REPORT.md, returns counts) | Already excludes `_dropped/`/`REPORT.md`, computes total chars, verdict [VERIFIED:188-217] |
| Re-detecting duplicates | New comparison code | `crawler.dupaudit.exact_edges` / `url_edges` / `cluster` | Keeps "duplicate" definition identical to Phase 20 [VERIFIED] |
| `--json` output shape | Ad-hoc dict | `crawler.contract.envelope` + `emit` | Frozen agent contract, EXIT_* codes [VERIFIED] |
| URL normalization for manifest pruning | Regex | `crawler.profile.normalize_url` | Same normalization the audit + crawler used [VERIFIED] |

**Key insight:** Phase 21 is almost entirely *composition* of existing, tested primitives. The only
genuinely new logic is (a) reading the report, (b) the exact/URL-vs-overlap partition + gate, and
(c) the dry-run/apply orchestration. Resist writing new filesystem or detection code.

## Runtime State Inventory

> This is a deletion/migration-style phase. All five categories answered explicitly.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| **Stored data** | No database. The corpus is flat markdown files per family. The 16 delete targets live as `.md` (+ `.eval.json` sibling) files under `corpus/<family>/`. [VERIFIED: no `*.db`/`*.sqlite` in corpus] | Move each target + its `.eval.json` to `_dropped/`. |
| **Live service config** | None — no external service stores these paths. (The v1.0 SQLite FTS5 index is NOT part of the current v2.1/v2.2 corpus pipeline; no index/db file exists in `corpus/`.) [VERIFIED: `find corpus -name '*.db' -o -name '*.sqlite*'` → empty] | None. No FTS/search index to rebuild this milestone. |
| **OS-registered state** | None — no scheduler/daemon references corpus filenames. | None. |
| **Secrets/env vars** | None — cleanup reads/writes only local files; no secrets involved. | None. |
| **Build artifacts / derived files** | Per-family `manifest.json` (URL→meta), `completeness/sample.json` + `*.check.json` + `*.live.md`, and `REPORT.md` reference doc paths/URLs and go stale on deletion. `crawl_stats.json.recorded` is a historical crawl-time count (NOT live). | Prune manifest URLs; prune/flag orphaned completeness sidecars; regen REPORT.md; leave crawl_stats.json. |

**The canonical question — what still references the old files after the move?** See § Dangling References.

## Dangling References (computed per delete target)

I cross-checked every delete target against the per-family `manifest.json`, `completeness/sample.json`,
and `*.check.json` [VERIFIED: scripted scan]:

| Delete target | In manifest.json | In completeness sample | Has orphaned `.check.json` |
|---------------|:---:|:---:|:---:|
| `mi-rounds/invitations-35.md` | ✔ | ✔ | ✔ |
| `mi-rounds/invitations-11.md` | ✔ | ✔ | ✔ |
| `mi-rounds/invitations-28.md` | ✔ | ✔ | ✔ |
| `guidance/grid.md` (overlap-only) | ✔ | ✔ | ✔ |
| `pdi-completeness-check/...completeness-check.md` | ✔ | ✔ | ✔ |
| `mi-rounds/invitations-31/-22/-18/-12.md`, `mi-rounds/express-entry-rounds.md`, `guidance/check-score.md`, `police-certificates/police-certificates-1.md`, `ministerial-instructions/...management-system.md`, `police-certificates/guadeloupe.md` | ✔ | – | – |
| `police-certificates/tokelau.md`, `police-certificates/mayotte.md` | – | – | – |

**Concrete meaning of "no dangling references":**
1. **`manifest.json`** — most targets' source URL appears here. Prune those URLs (exact pattern:
   `apply_verdicts.py:54-62`). [VERIFIED]
2. **`completeness/` sidecars** — 5 targets were in their family's QC completeness *sample*; their
   `.check.json`/`.live.md` would orphan, AND `build_report`'s readiness check
   `completeness_done = len(checks) >= sampled` (completeness.py:239) would mis-count. For those
   families, either (a) drop the orphaned `sample.json` pair entry + its `.check.json`/`.live.md`,
   keeping `sampled` consistent, or (b) re-sample — but **re-sampling needs `--fetch` (crawl4ai +
   network), which is forbidden offline**, so prefer pruning the orphaned entries. [VERIFIED]
3. **`REPORT.md`** — regenerate via `python -m crawler.completeness --report corpus/<family>`; it
   recomputes `live_docs` by globbing, so counts self-update once files are moved and sidecars pruned.
   [VERIFIED: completeness.py:216,274]

**Families touched by deletions (high-confidence scope):** `police-certificates`, `mi-rounds`,
`ministerial-instructions`, `pdi-completeness-check` (and `guidance`/`pr-pdi` only as canonical-keepers
— no deletions there if overlap-only is excluded). [VERIFIED]

## Common Pitfalls

### Pitfall 1: Deleting overlap-only "duplicates"
**What goes wrong:** Losing distinct documents (Tokelau, Guadeloupe, Mayotte country pages; a distinct
EE round) because they share ≥0.95 boilerplate.
**Why it happens:** `overlap_edges` matches *text*, not *meaning*; short templated pages collide.
**How to avoid:** Exclude overlap-only clusters from the default delete scope (Pattern 2).
**Warning signs:** A cluster's `signals == ["overlap"]`; canonical and target are *different* slugs that
map to *different real-world entities* (different country/round in the relpath).

### Pitfall 2: Spurious zero-cluster failure
**What goes wrong:** Re-running the *full* audit still reports the 6 retained overlap clusters → SC2
"zero clusters" appears to fail.
**Why it happens:** SC2 means "the duplicates we resolved are gone," not "the false-positive detector
output is empty."
**How to avoid:** Scope the re-check to exact+URL detectors (Pattern 4); document overlap-only as
retained-by-design.
**Warning signs:** `total_clusters == 6` after cleanup with all 6 being `signals==["overlap"]`.

### Pitfall 3: Orphaned completeness sidecars break the QC verdict
**What goes wrong:** After moving a doc that was in the completeness sample, `REPORT.md` shows a stale
`sampled` count or an orphaned `.check.json`; `build_report` may flag `incomplete`.
**Why it happens:** `sample.json`/`*.check.json` reference docs by name and aren't auto-pruned.
**How to avoid:** Prune the matching `pairs` entry from `sample.json` and remove the orphaned
`.check.json`/`.live.md` for each moved-and-sampled doc, then regen `REPORT.md`.
**Warning signs:** REPORT.md "Checks completed: N/M" mismatch, or a `.check.json` whose `doc` no longer
exists live.

### Pitfall 4: Unrecoverable hard delete
**What goes wrong:** `os.unlink` on a git-ignored corpus file → no recovery path.
**How to avoid:** Move to `_dropped/` + audit log (Pattern 1).
**Warning signs:** Any `unlink`/`os.remove`/`Path.unlink` call in the cleanup module.

### Pitfall 5: `.eval.json` sibling naming
**What goes wrong:** Moving the `.md` but leaving its eval sibling behind → orphaned eval, and
`build_report` still counts its verdict.
**Why it happens:** Two naming forms exist: `<doc>.md.eval.json` AND `<stem>.eval.json` (handled in
dupaudit.py:191). Observed on disk: `<doc>.md.eval.json` (e.g. `documents.md.eval.json`).
**How to avoid:** When moving `<doc>.md`, also move whichever of `<doc>.md.eval.json` / `<stem>.eval.json`
exists (mirror dupaudit.py:191). [VERIFIED]

## Code Examples

### Load the plan from the report (deterministic, no re-audit)
```python
# Source: schema per crawler/dupaudit.py:536-551 (render_json) + real reports/duplicate-audit.json
import json
from pathlib import Path

def load_plan(report_json: Path, include_overlap: bool = False):
    data = json.loads(report_json.read_text(encoding="utf-8"))
    targets = []
    for c in data["clusters"]:
        sigs = set(c["signals"])
        overlap_only = sigs == {"overlap"}
        if overlap_only and not include_overlap:
            continue  # SAFETY GATE: skip false-positive-prone clusters by default
        for m in c["members"]:
            if m["decision"] == "delete":
                targets.append({"relpath": m["relpath"], "family": m["family"],
                                "url": m["url"], "overlap_only": overlap_only})
    return targets
```

### Move one target + its eval sibling into `_dropped/` (idempotent)
```python
# Source: crawler/apply_verdicts.py:49-52 + dupaudit.py:191 (eval naming)
import shutil
from pathlib import Path

def move_to_dropped(corpus_root: Path, relpath: str) -> bool:
    src = corpus_root / relpath
    if not src.is_file():
        return False  # idempotent: already moved / absent
    dropped = src.parent / "_dropped"
    dropped.mkdir(exist_ok=True)
    shutil.move(str(src), str(dropped / src.name))
    for cand in (src.name + ".eval.json", src.stem + ".eval.json"):
        ev = src.with_name(cand)
        if ev.is_file():
            shutil.move(str(ev), str(dropped / ev.name))
    return True
```

### Regenerate per-family counts/report (offline — `--report`, no network)
```python
# Source: crawler/completeness.py:188 (build_report) — pure-Python, no crawl4ai
from crawler import completeness
summary = completeness.build_report(corpus_root / family)  # writes REPORT.md
# summary["live_docs"] is the refreshed count of record
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Within-run crawler dedup only (URL + sha1) | Cross-family audit (`dupaudit`, Phase 20) → cleanup (Phase 21) | v2.2 | Phase 21 closes the loop the audit opened |
| Hard-delete dropped docs | Move to `_dropped/` + audit log (`apply_verdicts`) | v2.1 | Establishes the recoverable-quarantine convention Phase 21 must follow |
| v1.0 SQLite FTS5 index | Raw markdown families + per-family `manifest.json`/`REPORT.md`; no live index in v2.x corpus | v2.1 | No index rebuild needed this phase |

**Deprecated/outdated:** None relevant. (FTS5 search from v1.0 is not part of the current corpus
artifacts — do not attempt to rebuild it.)

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The full overlap detector takes ~9 min on the 752-doc corpus | Pattern 4 / Pitfall 2 | If faster, the "skip overlap for the gate" optimization is merely nice-to-have, not required — recommendation still holds (it would spuriously fail anyway). [CITED: phase task brief; algorithmic O(n²) basis VERIFIED] |
| A2 | `guidance/check-score.md` and `guidance/grid.md` are distinct from their canonicals | Delete-Target Inventory | If they ARE true duplicates, retaining them is over-cautious (no data loss, just 2 residual overlap clusters). Low risk — fail-safe direction. |
| A3 | Pruning orphaned completeness `pairs`/`.check.json` (vs re-sampling) keeps `build_report` consistent | Dangling References #2 | If `build_report` requires the original `sampled` N to match exactly, a smaller pruned sample is fine (it lowers both `sampled` and `checks` together); verify in Wave-0 test. |

**Confirmation needed before execution:** A1–A3 are low-risk and fail-safe. The one genuine *decision*
(not assumption) is overlap-only handling — see recommendation; treat as locked unless a human overrides.

## Open Questions (RESOLVED)

1. **Should the 6 overlap-only clusters be permanently retained, or revisited with a higher threshold?** — **RESOLVED:** retain all 6 this milestone (verified distinct — different countries/EE rounds); exclude them from deletion by default and document as "reviewed, distinct." A smarter near-dup rule is deferred (DUP-05/06). Implemented across PLAN 21-02 (`--include-overlap` gate) and 21-05 (retention assertion).
   - What we know: They are demonstrably distinct (different countries/rounds). [VERIFIED]
   - Decision rationale: deleting verified-distinct authoritative docs would lose coverage; the false-positive risk is the central hazard of the phase.

2. **Prune-orphaned-sample vs re-sample completeness for touched families?** — **RESOLVED:** prune orphaned `pairs`/`.check.json`/`.live.md` entries offline, then regenerate REPORT.md via `--report`. Re-sampling needs `--fetch` (crawl4ai/network), which is forbidden offline and out of scope. Implemented in PLAN 21-03 (`prune_completeness_orphans` + `revalidate_family`).
   - What we know: Re-sample needs `--fetch` (crawl4ai/network) — forbidden offline.
   - Decision rationale: keeps the cleanup fully offline and dependency-light.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | all tooling | ✓ | 3.10 (`.venv`) | — |
| Poetry | dep mgmt / test run | ✓ (per project) | — | `python -m unittest` directly |
| `pyyaml` | (only if re-parsing frontmatter) | ✓ (installed) | — | — |
| `crawl4ai` | completeness `--fetch` ONLY (NOT used by Phase 21) | not required | — | Use `--report` (pure-Python); never call `--fetch` |
| Network / browser | NOT used | n/a | — | Offline by design |
| `reports/duplicate-audit.json` | the cleanup input | ✓ present (committed) | — | regenerate via `python -m crawler.dupaudit corpus/` |
| `corpus/` (752 live docs) | the target | ✓ present, git-ignored | — | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none blocking — `crawl4ai` is intentionally unused.

## Security Domain

`security_enforcement: true`, ASVS level 1. This phase mutates the local filesystem from a
machine-readable report — the threat model is path traversal and untrusted-input parsing.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (local CLI) |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | **yes** | Validate each `relpath` resolves *inside* `corpus_root` before moving; refuse absolute/`..` paths (path-confinement, carried from threat T-20-01). |
| V6 Cryptography | no | — |
| V12 Files & Resources | **yes** | Only move within `corpus/<family>/_dropped/`; never write outside the resolved corpus root; never follow paths taken from file *content* without re-confinement. |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via a crafted `relpath` in the report JSON | Tampering / Elevation | `target = (corpus_root / relpath).resolve(); assert corpus_root in target.parents` before any move (mirror dupaudit.py:156 confinement, threat T-20-01) [VERIFIED] |
| Malicious YAML frontmatter (if re-parsed) | Tampering | `yaml.safe_load` ONLY — never `yaml.load` (threat T-20-02, dupaudit.py:32-35,178) [VERIFIED] |
| Accidental commit of corpus content / PII | Information Disclosure | SC5 gate: assert `git status --porcelain corpus/` is empty; `corpus/` is git-ignored [VERIFIED] |
| Unrecoverable data loss | Denial (of recovery) | Move-to-`_dropped/` + audit log instead of unlink (Pattern 1) |

## Sources

### Primary (HIGH confidence)
- `crawler/dupaudit.py` (full read) — report schema (`render_json` 536-551), detectors (214-263),
  `live_docs` 752-filter (146-166), canonical/decision (324-352), `--json` envelope (554-665).
- `crawler/apply_verdicts.py` (full read) — the move-to-`_dropped/` + manifest-prune + audit-log +
  dry-run pattern (the "delete" precedent).
- `crawler/completeness.py:60-300` — `live_docs` (65-68), `build_report` (188-217), live count (274),
  completeness readiness (239), `--fetch` needs crawl4ai (88-92).
- `crawler/contract.py:48-95` — envelope/emit, EXIT_* codes.
- `reports/duplicate-audit.json` + `.md` (parsed) — the 16 delete targets, 11 clusters.
- `.planning/phases/20-.../20-VERIFICATION.md:20-21,112-116` — the carried-forward overlap-review gate.
- `corpus/police-certificates/{tokelau,guadeloupe,mayotte}.md` (read) — confirmed distinct countries.
- `crawler/tests/test_dupaudit.py:1-175,263` — stdlib-unittest convention, `_make_dup_corpus` fixture,
  `_snapshot` (size/mtime/sha1) read-only check helper.
- `.gitignore:8` + `git check-ignore corpus/` — corpus is git-ignored.

### Secondary (MEDIUM confidence)
- `.planning/{ROADMAP,REQUIREMENTS,PROJECT}.md` — phase goal, success criteria, constraints.

### Tertiary (LOW confidence)
- ~9-minute full-overlap-detector runtime (phase task brief; not independently timed this session).

## Validation Architecture

Test framework: **stdlib `unittest` only** (no pytest/network/crawl4ai), per repo convention. New
suite `crawler/tests/test_dupclean.py`, run from repo root:
`python -m unittest crawler.tests.test_dupclean -v`.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Python stdlib `unittest` (3.10) |
| Config file | none — discovery via `python -m unittest crawler.tests.<module>` |
| Quick run command | `python -m unittest crawler.tests.test_dupclean -v` |
| Full suite command | `python -m unittest discover -s crawler/tests -v` |

### Fixtures (reuse Phase 20's proven helpers)
- **Synthetic corpus:** extend `crawler.tests.test_dupaudit._make_dup_corpus` (test_dupaudit.py:132) —
  it already plants an EXACT pair, a SAME-URL pair, a NEAR-DUP (overlap-only) pair + negative, a
  singleton, `_dropped/` noise, `completeness/*.live.md`, and `.eval.json` siblings in both naming forms.
- **Report fixture:** run `crawler.dupaudit.audit()` + `render_json()` over that synthetic corpus to
  produce a real `duplicate-audit.json` in the tempdir (no hand-authored JSON — keeps schema in sync).
- **Read-only/no-touch snapshot:** reuse the `_snapshot(root)` `{relpath:(size,mtime_ns,sha1)}` helper
  (test_dupaudit.py:263) to assert dry-run changes nothing.

### Phase Requirements → Test Map
| Req | Behavior | Test type | Automated command | File exists? |
|-----|----------|-----------|-------------------|-------------|
| CLEAN-02 | Each high-confidence delete target leaves the live set; canonical stays | unit | `... test_dupclean.TestApply.test_moves_only_noncanonical -v` | ❌ Wave 0 |
| CLEAN-02 | **Keep-canonical guarantee**: canonical relpath is NEVER moved | unit | `... TestApply.test_canonical_untouched -v` | ❌ Wave 0 |
| CLEAN-02 | Overlap-only clusters excluded by default; included only with `--include-overlap` | unit | `... TestScope.test_overlap_only_excluded_by_default -v` | ❌ Wave 0 |
| CLEAN-02 | Idempotency: second `--apply` is a no-op (sources already gone) | unit | `... TestApply.test_idempotent_reapply -v` | ❌ Wave 0 |
| CLEAN-02 | Dry-run default: filesystem snapshot unchanged | unit | `... TestDryRun.test_default_is_dry_run -v` | ❌ Wave 0 |
| CLEAN-02 | **Zero-cluster re-check**: post-apply, `exact_edges+url_edges → cluster() == []` | unit | `... TestRecheck.test_no_exact_or_url_clusters_after_apply -v` | ❌ Wave 0 |
| CLEAN-03 | Moved doc's URL removed from family `manifest.json` | unit | `... TestRevalidate.test_manifest_pruned -v` | ❌ Wave 0 |
| CLEAN-03 | Orphaned `completeness/*.check.json`/sample pair pruned | unit | `... TestRevalidate.test_completeness_orphans_pruned -v` | ❌ Wave 0 |
| CLEAN-03 | `build_report` regenerates REPORT.md with decremented live count, verdict still pass | unit | `... TestRevalidate.test_report_count_updated -v` | ❌ Wave 0 |
| CLEAN-03 | `.eval.json` sibling moves with its `.md` (both naming forms) | unit | `... TestApply.test_eval_sibling_moved -v` | ❌ Wave 0 |
| SC5 | **Git-status-local guarantee**: `git status --porcelain corpus/` empty after apply (corpus git-ignored) | unit/integration | `... TestGit.test_corpus_changes_stay_ignored -v` | ❌ Wave 0 |
| Security | Path-traversal `relpath` (`../`, absolute) refused before move | unit | `... TestSecurity.test_rejects_escaping_relpath -v` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m unittest crawler.tests.test_dupclean -v`
- **Per wave merge:** `python -m unittest discover -s crawler/tests -v`
- **Phase gate:** full suite green + a real-corpus `--apply` dry-run shows the expected 10
  high-confidence moves and 6 retained overlap-only, before `/gsd-verify-work`.

### Git-status-local test note
The synthetic-corpus tests run in a tempdir (no git), so the SC5 guarantee is best tested two ways:
(1) a unit assertion that the module never writes outside the resolved corpus root, and (2) an
integration check against the **real repo** asserting `git status --porcelain corpus/` is empty after
an `--apply` run (because `corpus/` is git-ignored — `git check-ignore corpus/` confirms). Both are
fast and require no network.

### Wave 0 Gaps
- [ ] `crawler/tests/test_dupclean.py` — new suite (covers CLEAN-02/03 + SC5 + security)
- [ ] Optional `_make_clean_corpus` helper, or reuse/extend `test_dupaudit._make_dup_corpus` +
      `audit()/render_json()` to mint the report fixture in-tempdir
- [ ] No framework install needed (stdlib unittest already used)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all repo-internal modules read in full; zero new deps.
- Architecture (move-to-`_dropped/`, exact/URL vs overlap gate): HIGH — grounded in `apply_verdicts.py`
  precedent + verified file reads of the false-positive targets + the Phase 20 verifier gate.
- Dangling references: HIGH — scripted per-target scan of manifest/completeness.
- Overlap-runtime (~9 min): LOW (cited, not timed) — but the recommendation holds regardless.

**Research date:** 2026-06-11
**Valid until:** 2026-07-11 (stable — local code/data, no fast-moving external deps)
