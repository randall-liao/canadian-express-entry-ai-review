# Phase 20: Cross-Family Duplicate Detection & Audit Report - Research

**Researched:** 2026-06-11
**Domain:** Offline corpus analysis (filesystem walk, content hashing, near-duplicate clustering, deterministic canonical selection, shareable report generation) — pure-Python/stdlib, no network
**Confidence:** HIGH (grounded in direct reads of this codebase + a live duplicate probe over the real 752-doc corpus)

## Summary

This phase builds a **read-only audit tool** that walks all 16 corpus families, finds documents that are duplicates of one another *across* families (which the crawler's within-run dedup never catches), groups them into clusters, names one canonical copy to keep per cluster, and emits a shareable keep/delete report — touching nothing in `corpus/`. Every primitive it needs already exists in this repo and can be reused rather than re-built: the crawler's content-hash definition (`hashlib.sha1` over cleaned markdown, `crawler/pipeline.py:115`), URL canonicalization (`crawler.profile.normalize_url`, `crawler/profile.py:286`), the QC "passed" judgement (`crawler.eval_runner.check_doc`, `crawler/eval_runner.py:66`), the frontmatter-stripping idiom (`crawler/eval_runner.py:43` / `crawler/completeness.py`), the `--json` contract envelope (`crawler/contract.py`), and the publish-safety scanner (`scripts/check_publish_safe.py`).

The single most important fact for getting detection right: **the exact-duplicate hash must be computed over the document body with the YAML frontmatter stripped**, never over the whole file. I verified this directly — the one real cross-family exact duplicate in the corpus (`guidance/police-certificates.md` ≡ `police-certificates/police-certificates-1.md`) has *different* `url` and *different* `crawl_date` in frontmatter but byte-identical bodies. Hashing the whole file would miss it; hashing the body finds it and reproduces the crawler's own `sha1(cleaned_md)` definition exactly. This same example proves all three detectors are needed: those two files have **different** source URLs, so a URL-only detector (DUP-02) would never group them — only the content hash (DUP-01) does.

I ran a live probe over the real corpus to size the work: **752 live docs** (confirmed — the raw `*.md` count is 767, but 15 are generated per-family `REPORT.md` artifacts that must be excluded; 767 − 15 = 752). Exact content-hash duplicates: **1 cross-family cluster**. Same-normalized-URL clusters spanning families: **3** (guidance↔mi-rounds, guidance↔ministerial-instructions, pdi-completeness-check↔pr-pdi). Near-duplicate pairs at ≥0.95 text overlap: **25** (length-blocked, ~23 s) — see the benchmark below.

**Primary recommendation:** Implement a standalone, offline `crawler/dupaudit.py` module (runnable as `python -m crawler.dupaudit corpus/ [--json]`, **not** wired into the `corpus-crawler` subparser — productization is DUP-05/06, explicitly out of scope). It enumerates live docs → reuses the crawler's body-hash + `normalize_url` for exact/URL signals → uses stdlib `difflib.SequenceMatcher` (threshold **0.95**, length-bucket blocking) for text-overlap → unions the three signals into clusters via stdlib union-find → picks the canonical copy (passed-QC first, then longest cleaned body, then lexicographic path tie-break) → writes a markdown report + JSON sidecar whose only sensitive content is corpus-relative paths and public source URLs, validated by reusing `scripts/check_publish_safe.py`'s `scan_text`. No new dependencies (stdlib + already-present `pyyaml`).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DUP-01 | Detect exact (content-hash) duplicates across all 16 families, not just within a run | Hash body-minus-frontmatter with `hashlib.sha1` to match `crawler/pipeline.py:115`; live probe found 1 real cross-family exact cluster. The crawler runs 16 separate `seen_hashes` sets (one per run), which is *why* cross-family exacts survive — see "Why within-run dedup misses cross-family". |
| DUP-02 | Detect near-duplicates across families by shared canonical/source URL | Normalize each doc's frontmatter `url` via `crawler.profile.normalize_url` (drops fragment, `strip_query_params`, trailing slash), group by normalized URL; probe found 3 cross-family URL clusters. |
| DUP-03 | Detect near-duplicates by high text-overlap (substantially identical) | `difflib.SequenceMatcher.ratio()` ≥ 0.95 over bodies, with length-bucket blocking + `real_quick_ratio`/`quick_ratio` prefilters; benchmarked feasible (12,760 comparisons, ~23 s, 25 pairs). |
| DUP-04 | Group duplicates into clusters (one logical doc ↔ ≥2 file copies) | Union-find over the union of all three signal edges → connected components; each component with ≥2 members is a cluster. |
| CLEAN-01 | Select exactly one canonical copy per cluster (most complete; prefer passed-QC) | Rank members by `(passed_qc, cleaned_body_len, -path)`; "passed QC" = `crawler.eval_runner.check_doc(...).passed` on the sibling `.eval.json`; "cleaned content length" = `len(body-minus-frontmatter)` (cross-checks the manifest `chars` field). |
| RPT-01 | Report lists every cluster with each member's path, family, source URL | Member path = corpus-relative; family = first path segment; source URL = frontmatter `url`. |
| RPT-02 | Each cluster states keep/delete decision + reason (completeness / QC) | Emit `keep`/`delete` per member with reason string (e.g. "longest cleaned body (5,605 chars) and passed QC"). |
| RPT-03 | Report safe to share — corpus-relative paths + source URLs only, no PII | Validate generated report via `scripts/check_publish_safe.py:scan_text`; report contains no absolute paths/secrets/PII by construction. |

> CLEAN-02 (delete non-canonical) and CLEAN-03 (re-validate) are **Phase 21**, not this phase. This phase is a strict read-only dry run (Success Criterion 5: corpus live-doc count unchanged after running).
</phase_requirements>

## Architectural Responsibility Map

This is a local offline CLI tool, not a multi-tier web app. "Tier" here = the module/layer that owns each capability. The guiding principle: **reuse the existing crawler primitives; do not re-derive duplicate-detection semantics.**

| Capability | Primary Owner | Secondary | Rationale |
|------------|---------------|-----------|-----------|
| Enumerate live docs (exclude `_dropped/`, `completeness/`, `*.live.md`, `REPORT.md`, non-frontmatter files) | new `dupaudit` enumeration | — | Defines the 752-doc denominator; getting the exclusion set right *is* Success Criterion 5's count. |
| Parse frontmatter (url, title, source_type) + split body | new `dupaudit` (via `pyyaml.safe_load` on the `---` block) | reuse `_strip_frontmatter` idiom | Frontmatter fields key the URL detector & report; `pyyaml` already a dep. |
| Exact content hash | reuse `hashlib.sha1` over body (matches `crawler/pipeline.py:115`) | — | Consistency with the crawler's own dedup definition is required by the phase brief. |
| URL canonicalization | reuse `crawler.profile.normalize_url` | `crawler.profile.load_profile("ircc")` | Same normalization the crawler used to collapse URL variants. |
| Text-overlap near-dup | stdlib `difflib.SequenceMatcher` | — | Dependency-light constraint forbids embeddings/vector DBs. |
| Cluster (connected components) | stdlib union-find (in `dupaudit`) | — | Avoid pulling `networkx`; trivial to hand-write correctly. |
| "Passed QC?" judgement | reuse `crawler.eval_runner.check_doc` | — | The repo's single source of truth for QC pass/fail. |
| Canonical selection | new `dupaudit` ranking | reuse `eval_runner` + body length | Deterministic, no interactive adjudication (out of scope). |
| Report rendering (MD + JSON) | new `dupaudit` | mirror `crawler/completeness.py` REPORT.md style + `crawler.contract` envelope | Fit existing report/JSON conventions. |
| PII / publish-safety scan of report | reuse `scripts/check_publish_safe.py:scan_text` | — | The repo's sanctioned safety gate (STATE.md Phase 15). |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (`hashlib`, `difflib`, `pathlib`, `re`, `json`, `argparse`, `dataclasses`) | 3.10–3.13 | Hashing, near-dup ratio, FS walk, report I/O, CLI, envelopes | Zero install surface; matches the repo's "pure stdlib" ethos for `contract.py`, `check_publish_safe.py`, `eval_runner.py` [VERIFIED: read those files] |
| `pyyaml` | >=6.0,<7.0 | Parse YAML frontmatter robustly (quoted URLs, special chars) | Already the **only** runtime dependency in `pyproject.toml` [VERIFIED: pyproject.toml lines 11-13]; used via `yaml.safe_load` per the security note in `crawler/profile.py:156` |

### Supporting (reused in-repo modules — not new deps)
| Module | Purpose | When to Use |
|--------|---------|-------------|
| `crawler.profile.normalize_url` / `load_profile` | URL canonicalization for DUP-02 | Normalize every doc's frontmatter `url` before grouping |
| `crawler.eval_runner.check_doc` | QC pass/fail for CLEAN-01 tie-break | Determine `passed_qc` per cluster member |
| `crawler.pipeline` (`MIN_CONTENT_CHARS`, classify decision order) | Reference for the exact-dup semantics | Document/confirm the hash definition; do not re-run the classifier |
| `scripts.check_publish_safe.scan_text` | PII/abs-path/secret scan of the report (RPT-03) | Validate the generated report file content |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `difflib.SequenceMatcher` | MinHash/LSH (`datasketch`), SimHash, shingling+Jaccard | Faster at large N and the "right" tool at scale — **rejected**: adds a dependency (violates dependency-light constraint), and at 752 docs with length blocking stdlib difflib finishes in ~23 s. Revisit only if the corpus grows by an order of magnitude. |
| stdlib union-find | `networkx.connected_components` | Cleaner API — **rejected**: ~15 lines of union-find avoids a heavyweight graph dep. |
| Embedding/vector similarity | sentence-transformers + FAISS | Explicitly **out of scope** (REQUIREMENTS.md "Out of Scope": no vector index; PROJECT.md constraint). |
| Line-parsing frontmatter (as `completeness._frontmatter_url` does) | `pyyaml.safe_load` of the `---` block | `pyyaml` handles quoting/escaping correctly and is already installed; prefer it for the URL/title fields. |

**Installation:** None required. Stdlib + already-present `pyyaml`. (`poetry install` already provides everything; `crawl4ai` is **not** needed — this tool is fully offline.)

## Package Legitimacy Audit

> No external packages are installed by this phase. The only runtime dependency touched (`pyyaml`) is already declared in `pyproject.toml` and was shipped in v2.0.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| pyyaml | PyPI | mature (10+ yrs) | very high | github.com/yaml/pyyaml | OK | Already a dependency — no install |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
corpus/ (16 family dirs, git-ignored)
   │
   ▼
[1] ENUMERATE live docs ──── exclude: _dropped/, completeness/, *.live.md,
   │  (yields 752)            REPORT.md, *.eval.json, manifest*.json, files w/o frontmatter
   ▼
[2] PARSE each doc → { path, family, url, title, body, body_hash, body_len, passed_qc }
   │      ├─ body_hash = sha1(body)                 (DUP-01 signal)
   │      ├─ norm_url  = normalize_url(url)          (DUP-02 signal)
   │      └─ passed_qc = eval_runner.check_doc(...)  (CLEAN-01 input)
   ▼
[3] BUILD EDGES (three detectors, each emits (doc_i, doc_j) edges)
   │      ├─ exact:    same body_hash
   │      ├─ url:      same norm_url
   │      └─ overlap:  difflib ratio ≥ 0.95  (length-blocked + quick_ratio prefilter)
   ▼
[4] CLUSTER  union-find over all edges → connected components (≥2 members = a cluster)  (DUP-04)
   ▼
[5] SELECT CANONICAL per cluster  rank by (passed_qc, body_len, -path)  (CLEAN-01)
   │      → 1 keep, rest delete, each with a reason string
   ▼
[6] RENDER  report.md (human) + report.json (sidecar)  (RPT-01/02)
   │      members: corpus-relative path, family, source URL, decision, reason
   ▼
[7] SAFETY SCAN  check_publish_safe.scan_text(report) → must be empty  (RPT-03)
   │
   ▼
[8] ASSERT read-only  live-doc count unchanged; no writes under corpus/  (Success Criterion 5)
```

### Recommended Project Structure
```
crawler/
├── dupaudit.py            # NEW — the audit module; main(argv); offline; --json envelope
└── tests/
    └── test_dupaudit.py   # NEW — stdlib unittest, synthetic tiny corpus in tempfile
reports/                   # NEW (git-tracked) — or write under corpus/ (see Pitfall 6)
├── duplicate-audit.md     # human report (RPT-01/02)
└── duplicate-audit.json   # machine sidecar
```

### Pattern 1: Reproduce the crawler's exact-duplicate definition
**What:** Hash the cleaned body, not the file. The on-disk body (file minus the `---…---` frontmatter block) IS the `cleaned_md` the crawler recorded, so `sha1(body)` equals the crawler's `seen_hashes` digest.
**When to use:** DUP-01.
```python
# Source: mirrors crawler/pipeline.py:115  digest = hashlib.sha1(md.encode("utf-8")).hexdigest()
import hashlib

def body_of(text: str) -> str:
    # same split as crawler/eval_runner.py:43 _strip_frontmatter
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            nl = text.find("\n", end + 1)
            return text[nl + 1:] if nl != -1 else ""
    return text

def body_hash(text: str) -> str:
    return hashlib.sha1(body_of(text).encode("utf-8")).hexdigest()
```

### Pattern 2: URL grouping reuses the crawler's normalizer
**What:** Collapse URL variants exactly as the crawler did, so DUP-02's notion of "same source URL" matches ingestion.
```python
# Source: crawler/profile.py:286 normalize_url ; ircc.yaml strips wbdisable
from crawler.profile import load_profile, normalize_url
profile = load_profile("ircc")          # canada.ca: drops #frag, ?wbdisable, trailing /
norm = normalize_url(url, profile)       # statcan/justice URLs: still drops #frag + trailing /
```
Note: a single profile is fine because `normalize_url` only *adds* normalization (fragment + trailing slash + the profile's `strip_query_params=[wbdisable]`); for non-canada.ca hosts those params simply don't appear.

### Pattern 3: Length-blocked near-dup (the performance-critical pattern)
**What:** Sort by body length; for each doc only compare forward while the partner is within ~6% length (a ratio ≥0.95 is impossible when lengths differ more), and prefilter with `real_quick_ratio`/`quick_ratio` before the O(n·m) `ratio()`.
**When to use:** DUP-03.
```python
# Benchmarked on the real corpus: 282,376 naive pairs → 12,760 blocked comparisons, ~23 s.
from difflib import SequenceMatcher
docs.sort(key=lambda d: len(d.body))
for i in range(len(docs)):
    li = len(docs[i].body)
    for j in range(i + 1, len(docs)):
        if len(docs[j].body) > li * 1.06:   # length block — partners only get longer
            break
        sm = SequenceMatcher(None, docs[i].body, docs[j].body, autojunk=False)
        if sm.real_quick_ratio() < 0.95 or sm.quick_ratio() < 0.95:
            continue
        if sm.ratio() >= 0.95:
            add_edge(i, j)
```

### Pattern 4: Deterministic canonical selection (CLEAN-01)
```python
# passed_qc preferred, then longest cleaned body, then lexicographically smallest path
def rank_key(m):
    return (m.passed_qc, m.body_len, tuple(-ord(c) for c in m.path))  # max() picks canonical
canonical = max(cluster.members, key=rank_key)
```
"passed QC" via the repo's own judge:
```python
# Source: crawler/eval_runner.py:66 check_doc(doc_path, eval_path, min_relevance).passed
from crawler.eval_runner import check_doc
eval_path = doc_path.with_name(doc_path.name + ".eval.json")  # or <stem>.eval.json
passed_qc = eval_path.is_file() and check_doc(doc_path, eval_path, min_relevance=0.4).passed
```
A doc with **no** `.eval.json` ranks as `passed_qc=False` (lower priority than a QC-passed sibling) — make this explicit in the reason string.

### Anti-Patterns to Avoid
- **Hashing the whole file (with frontmatter):** `crawl_date`/`title`/`url` differ per copy → identical content never matches. The real exact-dup pair has different `url` AND `crawl_date`. Always hash body-only.
- **Counting `REPORT.md` / `.live.md` / `_dropped/` as live docs:** inflates 752→767+ and breaks Success Criterion 5's count invariant.
- **Naive O(n²) `difflib.ratio()`:** 282k full-ratio calls on multi-KB strings — minutes and memory churn. Always block by length and prefilter.
- **Treating "same URL" as "exact duplicate":** DUP-02 and DUP-01 are *different signals*. Same-URL docs can have different content (e.g. the `invitations` rounds pages share a base URL family but differ per `?q=`), and exact-content docs can have different URLs (the police-certificates pair). Keep the three edge sets distinct, then union for clustering.
- **Writing anything under `corpus/` during detection:** violates the read-only guarantee. The tool must be pure-read until the (separate) report write, and the report should not go inside a family dir.
- **Pulling a new dependency** (networkx/datasketch/rapidfuzz): violates the dependency-light constraint; stdlib suffices at this scale.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Exact-dup hash semantics | A fresh hashing scheme | `hashlib.sha1(body)` matching `crawler/pipeline.py:115` | Must be consistent with the crawler's own dedup, per the phase brief |
| URL canonicalization | Custom query/fragment stripping | `crawler.profile.normalize_url` | The crawler's exact collapse rules (incl. `wbdisable`) already live here |
| "Did this doc pass QC?" | Re-reading verdict logic | `crawler.eval_runner.check_doc(...).passed` | Single source of truth; encodes verdict + must_contain/relevance contract |
| Frontmatter parsing | A bespoke regex parser | `pyyaml.safe_load` of the `---` block (+ existing `_strip_frontmatter` idiom for body split) | Already-installed, handles quoting; `safe_load` only (security) |
| PII / share-safety scan | A new PII regex set | `scripts/check_publish_safe.py:scan_text` | The repo's sanctioned, tested checker (STATE.md Phase 15 decision) |
| Connected components | A graph library | ~15-line stdlib union-find | Trivial, dependency-free, deterministic |
| Near-dup similarity | Embeddings/vector index | `difflib.SequenceMatcher` | Out-of-scope to add a vector index; corpus is small |

**Key insight:** This phase is overwhelmingly *integration of existing, tested primitives* — the only genuinely new logic is clustering (union-find), canonical ranking, and report rendering. Reusing the crawler's hash + `normalize_url` + `check_doc` is not just convenient; it is **required** for the audit's duplicate definition to be consistent with how the corpus was ingested.

## Runtime State Inventory

> This is an *additive, read-only* analysis phase (it creates a report; it deletes nothing). It is not a rename/refactor/migration. There is no renamed string and no runtime state to migrate.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — the audit only reads `corpus/*.md`; it writes a report outside family dirs. No datastore keys/IDs change. | none |
| Live service config | None — no external service is configured by or affected by this phase. | none |
| OS-registered state | None — no scheduled tasks/daemons. | none |
| Secrets/env vars | None — tool takes a corpus path argument; reads no secrets. | none |
| Build artifacts | None new. (`crawler/dupaudit.py` is a source module; no compiled/installed artifact carries a stale name.) | none |

**Phase-21 note (out of scope here, flagged for the planner):** the per-family `manifest.json` and the FTS index (if any) reference doc paths/URLs; *deletion* in Phase 21 must update those. Phase 20 changes nothing, so no dangling references are introduced here.

## Common Pitfalls

### Pitfall 1: Wrong live-doc denominator (767 vs 752)
**What goes wrong:** Counting/auditing `REPORT.md`, `*.live.md`, `_dropped/`, or eval/manifest files as corpus docs.
**Why it happens:** `corpus.rglob("*.md")` returns 767 — including 15 generated `REPORT.md` files (one per family) and `completeness/*.live.md` ground-truth captures.
**How to avoid:** Exclude paths containing `_dropped/` or `completeness/`, names ending `.live.md`, the literal `REPORT.md`, and any file that doesn't start with `---` (no frontmatter). This yields exactly 752 (verified). Apply the *same* filter for the read-only count assertion.
**Warning signs:** Audited count ≠ 752; clusters containing a `REPORT.md`.

### Pitfall 2: Frontmatter included in the hash
**What goes wrong:** Identical-content copies don't match because `crawl_date`/`url`/`title` differ.
**Why it happens:** Each crawl writes its own timestamp/URL into frontmatter even when bodies are identical.
**How to avoid:** Strip frontmatter before hashing (Pattern 1). Verified against the real exact-dup pair (different `url`+`crawl_date`, identical body).
**Warning signs:** Zero exact clusters found (should be ≥1).

### Pitfall 3: difflib O(n²) blow-up
**What goes wrong:** 752² ≈ 282k full `ratio()` calls → minutes / high CPU.
**Why it happens:** No blocking.
**How to avoid:** Length-bucket blocking + `real_quick_ratio`/`quick_ratio` prefilter (Pattern 3): 12,760 comparisons, ~23 s measured. Set `autojunk=False` for stable ratios on short docs.
**Warning signs:** Audit runtime in minutes; CPU pegged.

### Pitfall 4: Non-deterministic canonical choice
**What goes wrong:** Two members tie on QC + length → run-to-run flip → unstable report → Phase-21 deletes the wrong file.
**Why it happens:** `max()` over an unsorted set with equal keys.
**How to avoid:** Total-order tie-break on corpus-relative path (Pattern 4). Selection must be reproducible (REQUIREMENTS "no interactive adjudication").
**Warning signs:** Diffs in `duplicate-audit.json` across identical runs.

### Pitfall 5: `.eval.json` naming mismatch
**What goes wrong:** QC lookup fails because evals are named `<doc>.md.eval.json` for some and `<doc>.eval.json` for others.
**Why it happens:** `eval_runner.run` resolves the doc from the eval's own `doc` field for exactly this reason (`crawler/eval_runner.py:104-113`). Both forms exist in the corpus.
**How to avoid:** Look for both `doc.name + ".eval.json"` and `stem + ".eval.json"`; treat "no eval" as `passed_qc=False`, not an error.
**Warning signs:** Everything reports `passed_qc=False`.

### Pitfall 6: Report can't be PII-gated where it's written
**What goes wrong:** `check_publish_safe.py` scans only **git-tracked** files (`git ls-files`). A report written into the git-ignored `corpus/` is invisible to the standard gate → RPT-03 can't be satisfied by the existing tool as-is.
**Why it happens:** `corpus/` is git-ignored by design (no corpus content in the public repo).
**How to avoid (recommended):** Write the report to a **git-tracked** location (e.g. `reports/duplicate-audit.md` + `.json`), so the existing publish-safe gate covers it *and* the report itself is shareable. The report's only sensitive content is corpus-relative paths + public source URLs — no abs paths, no secrets, no PII — so it passes by construction. Regardless of location, also call `check_publish_safe.scan_text(rel_path, report_text)` directly in the audit/test to assert zero violations (works even for an untracked path).
**Warning signs:** `check_publish_safe` reports the corpus path scanned 0 of the report; or the report contains a `/home/...`/`/Users/...` absolute path. <!-- # publish-safe: allow -->

## Code Examples

### Enumerate the 752 live docs (verified filter)
```python
from pathlib import Path
def live_docs(corpus: Path):
    for p in corpus.rglob("*.md"):
        parts = set(p.parts)
        if "_dropped" in parts or "completeness" in parts:
            continue
        if p.name == "REPORT.md" or p.name.endswith(".live.md"):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):     # drop generated artifacts w/o frontmatter
            continue
        yield p, text
```

### Union-find clustering (DUP-04)
```python
class UF:
    def __init__(self, n): self.p = list(range(n))
    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]; x = self.p[x]
        return x
    def union(self, a, b): self.p[self.find(a)] = self.find(b)

uf = UF(len(docs))
for i, j in exact_edges + url_edges + overlap_edges:
    uf.union(i, j)
from collections import defaultdict
clusters = defaultdict(list)
for idx in range(len(docs)):
    clusters[uf.find(idx)].append(idx)
clusters = [m for m in clusters.values() if len(m) >= 2]   # ≥2 copies
```

### `--json` envelope (mirror existing contract)
```python
# Source: crawler/contract.py:63 envelope() / :90 emit()
from crawler import contract
payload = {"verdict": "pass", "live_docs": 752, "clusters": [...],
           "exact": n_exact, "url": n_url, "overlap": n_overlap}
contract.emit(contract.envelope("audit-duplicates", result=payload))
```

## State of the Art

| Old Approach | Current Approach | When | Impact |
|--------------|------------------|------|--------|
| `difflib` for fuzzy matching | `rapidfuzz` (C++), MinHash/LSH for big corpora | ongoing | Faster at scale — but adds a dep; **not adopted** (752 docs, dependency-light) |
| Per-run crawler dedup (`seen_urls`/`seen_hashes`) | Cross-corpus offline audit (this phase) | v2.2 | Closes the cross-family gap; the crawler logic is unchanged (REQUIREMENTS out-of-scope) |

**Deprecated/outdated:** Nothing relevant; `difflib` and `hashlib` are stable stdlib. No version churn risk for this phase.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | 0.95 is the right default text-overlap threshold for "substantially identical" (DUP-03). | Patterns/DUP-03 | Too low → false-positive clusters merge distinct docs (e.g. boilerplate-heavy police-cert pages); too high → misses true near-dups. **Recommend** exposing `--overlap-threshold` (default 0.95) and reviewing the 25 flagged pairs before any deletion (Phase 21). [ASSUMED] |
| A2 | The on-disk body (file minus frontmatter) is byte-identical to the `cleaned_md` the crawler hashed (no post-write transformation). | Pattern 1 | If a writer re-wraps/normalizes whitespace on save, `sha1(body)` wouldn't equal the crawler's digest — but exact-dup detection across the *current* corpus still works (consistent within the corpus). Low risk; the 1 found exact cluster confirms bodies match across copies. [ASSUMED] |
| A3 | Loading the `ircc` profile for `normalize_url` is acceptable for non-canada.ca URLs (statcan/justice). | Pattern 2 | `wbdisable` stripping is canada.ca-specific; for other hosts it's a no-op, so normalization reduces to fragment+trailing-slash. Negligible risk. [ASSUMED] |
| A4 | Writing the report to a git-tracked `reports/` dir is the intended "shareable" home. | Pitfall 6 | If the project wants the report kept local (git-ignored) like the corpus, RPT-03 must instead rely on a direct `scan_text` call. This is a **planner/discuss decision** — flag it. [ASSUMED] |
| A5 | Implement as `python -m crawler.dupaudit` (not a registered `corpus-crawler` subcommand). | Summary | If the team wants it wired into the CLI now, that edges toward DUP-05 (out of scope). Confirm scope boundary. [ASSUMED] |

## Open Questions (RESOLVED)

1. **Report location & format split (MD + JSON).** — **RESOLVED:** git-tracked `reports/duplicate-audit.md` + `reports/duplicate-audit.json`, with `scan_text` also called programmatically (fail-closed). Decided in PLAN 20-03 Task 1/Task 2 (A4 accepted).
   - What we know: the repo emits per-family `REPORT.md` (markdown) and uses a stable `--json` envelope; corpus is git-ignored.
   - Decision rationale: a git-tracked `reports/` location makes the publish-safe gate non-vacuous (`reports/` ∉ `EXCLUDE_PREFIXES`) while keeping the corpus itself git-ignored.

2. **DUP-03 threshold & review gate.** — **RESOLVED:** expose `--overlap-threshold` (default 0.95); Phase 20 only *reports*, so near-dup clusters are advisory. Human review of non-exact clusters is surfaced as a `<human-check>` in PLAN 20-03 verification and gates Phase 21 deletion.
   - What we know: 25 pairs at ≥0.95 in the current corpus.
   - Decision rationale: deletion is deferred to Phase 21, so a slightly loose reporting threshold is safe.

3. **Mixed-signal clusters.** — **RESOLVED:** per-component detector signal sets are recorded (`cluster_signals` → `Cluster.signals`) and rendered so reviewers see why members were grouped; exact clusters are kept visually separate from overlap-only clusters in the MD report (PLAN 20-02 Task 3, PLAN 20-03 Task 1).
   - What we know: union-find merges exact + URL + overlap edges.
   - Decision rationale: signal provenance lets a reviewer detect an over-broad overlap edge merging distinct docs.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | everything | ✓ | 3.10–3.13 (`requires-python >=3.10,<4.0`) | — |
| `pyyaml` | frontmatter parse | ✓ | 6.x (declared dep) | line-parse idiom (`completeness._frontmatter_url`) |
| `corpus/` populated (752 docs / 16 families) | the audit input | ✓ | v2.1 shipped | — |
| `crawler.profile` / `crawler.eval_runner` / `scripts.check_publish_safe` | reuse | ✓ | in-repo | — |
| `crawl4ai` | **not needed** | ✗ | — | N/A — tool is fully offline |
| `pytest` | tests | ✗ | — | **Use stdlib `unittest`** (repo convention — see Validation Architecture) |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** `pytest` absent → tests MUST use stdlib `unittest` (this is the established repo convention, not a workaround).

## Security Domain

> `security_enforcement: true`, ASVS level 1. This is a local, offline, read-only analysis CLI with no network, no auth, no user accounts, and only local trusted-ish file input. Most ASVS categories are N/A; the live risk is **output data exposure** (RPT-03) and **safe parsing**.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface |
| V3 Session Management | no | No sessions |
| V4 Access Control | no | Local CLI |
| V5 Input Validation | yes | Parse YAML frontmatter with `yaml.safe_load` ONLY (never `yaml.load`) — matches `crawler/profile.py:156`; decode files with `errors="replace"`; constrain enumeration to the given corpus root. |
| V6 Cryptography | no | `sha1` is used for **dedup identity, not security** — collision-resistance is not a security property here; do not treat it as a security control. |
| V7 Output / Data Protection | yes | The report must contain only corpus-relative paths + public source URLs — validated by reusing `scripts/check_publish_safe.py` (RPT-03). This is the phase's primary security control. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Report leaks an absolute path / PII / secret | Information disclosure | Reuse `check_publish_safe.scan_text` over the report; fail the run if any violation (RPT-03) |
| Path traversal via crafted corpus path arg | Tampering | Resolve the corpus root and only `rglob` within it; never follow paths from file *content* |
| Malicious YAML in a doc's frontmatter | Tampering / RCE | `yaml.safe_load` only — no arbitrary object construction (T-13-01 precedent) |
| Accidental write into `corpus/` | Tampering (integrity of read-only guarantee) | Tool performs zero writes under any family dir; assert live-doc count unchanged (Success Criterion 5) |

## Sources

### Primary (HIGH confidence — direct codebase reads, this session)
- `crawler/pipeline.py:93-123` — `classify()` decision order; `sha1(md)` content-hash dedup; `MIN_CONTENT_CHARS=200`; per-run `seen_urls`/`seen_hashes` (the cross-family gap).
- `crawler/profile.py:286-301` — `normalize_url` (fragment, `strip_query_params`, trailing slash); `:235` `clean_markdown`; `:156` `yaml.safe_load` security note.
- `crawler/eval_runner.py:40-114` — `VALID_VERDICTS`, `check_doc` pass/fail, `_strip_frontmatter`, eval-name resolution via `doc` field.
- `crawler/apply_verdicts.py` — how `drop` verdicts are quarantined (`_dropped/`), audit log, manifest pruning.
- `crawler/completeness.py:1-60` — `.live.md` ground-truth captures, `.check.json`, per-family `REPORT.md` generation.
- `crawler/contract.py` — `--json` envelope (`schema_version`, `ok`, `command`, `result`, `error`), exit-code constants.
- `crawler/cli.py:1-70` — thin subparser dispatch; lazy crawl4ai import; module-`main(argv)` convention.
- `scripts/check_publish_safe.py` — `scan_text`, abs-path/secret patterns, `git ls-files` scope, `# publish-safe: allow` escape hatch.
- `crawler/tests/test_json_contract.py:1-45` — **stdlib `unittest` only, offline** test convention; in-process `cli.main` with redirect capture.
- `pyproject.toml` — single runtime dep `pyyaml`; `crawl4ai` optional `[crawl]` extra; Poetry; `requires-python >=3.10,<4.0`.
- `corpus/**` sampled frontmatter (guidance, police-certificates, noc-2021, legislation) + `manifest.json` (`chars` field) — frontmatter schema.

### Live measurements (HIGH confidence — ran this session against the real corpus)
- Live-doc enumeration: **752** (767 `*.md` − 15 `REPORT.md`).
- Exact cross-family content-hash clusters: **1** (`guidance/police-certificates.md` ≡ `police-certificates/police-certificates-1.md`; different URLs, identical body).
- Same-normalized-URL cross-family clusters: **3**.
- difflib near-dup benchmark: length-blocked → **12,760** comparisons, **25** pairs ≥0.95, **~23 s**.

### Secondary / Tertiary
- General `difflib`/`hashlib` behavior — Python stdlib knowledge [ASSUMED, stable].

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all primitives read directly in-repo; only stdlib + existing `pyyaml`.
- Architecture: HIGH — reuse-driven; clustering/selection are small, well-understood additions; benchmarked.
- Pitfalls: HIGH — each pitfall confirmed by a real codebase fact or a live probe (752 count, body-hash, difflib timing).
- Thresholds (0.95) & report location: MEDIUM — see Assumptions A1/A4 (needs confirmation in planning/discuss).

**Research date:** 2026-06-11
**Valid until:** ~2026-07-11 (stable stdlib + frozen v2.1 corpus; re-probe counts if the corpus is re-ingested).

## Validation Architecture

> `nyquist_validation: true`. Tests use **stdlib `unittest` ONLY** — no pytest (not installed), no crawl4ai, no network (established convention, `crawler/tests/test_json_contract.py:1-12`).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | Python stdlib `unittest` (3.10+) |
| Config file | none — discovered by module path |
| Quick run command | `poetry run python -m unittest crawler.tests.test_dupaudit -v` |
| Full suite command | `poetry run python -m unittest discover -s crawler/tests -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DUP-01 | Two files, identical body, **different** frontmatter (url/date) → one exact cluster; whole-file hash would miss it | unit | `python -m unittest crawler.tests.test_dupaudit.TestExact -v` | ❌ Wave 0 |
| DUP-02 | Two files, different bodies, same `url` (with `#frag`/`wbdisable`/trailing-slash variants) → one URL cluster | unit | `...TestUrl` | ❌ Wave 0 |
| DUP-03 | Two files at ratio ≈0.96 → clustered; a pair at ≈0.90 → NOT clustered (threshold boundary) | unit | `...TestOverlap` | ❌ Wave 0 |
| DUP-04 | Transitive edges (a~b exact, b~c url) → single 3-member cluster; singletons excluded | unit | `...TestCluster` | ❌ Wave 0 |
| CLEAN-01 | Canonical = passed-QC over non-QC; longest body breaks QC ties; path breaks length ties (deterministic across runs) | unit | `...TestCanonical` | ❌ Wave 0 |
| RPT-01/02 | Report (MD+JSON) lists every member's corpus-relative path/family/url + keep/delete + reason | unit | `...TestReport` | ❌ Wave 0 |
| RPT-03 | `check_publish_safe.scan_text(report)` returns 0 violations on a clean report; injecting `/home/u/x` makes it fail | unit | `...TestPublishSafe` | ❌ Wave 0 | <!-- # publish-safe: allow -->
| Success Criterion 5 | Snapshot `{path: (size, mtime, sha)}` of corpus tree before+after a full audit run → unchanged; live-doc count unchanged | unit/integration | `...TestReadOnly` | ❌ Wave 0 |
| Enumeration | Exactly the 752-filter (excludes `_dropped/`, `completeness/`, `*.live.md`, `REPORT.md`, no-frontmatter) on a synthetic corpus | unit | `...TestEnumerate` | ❌ Wave 0 |
| `--json` contract | One JSON object on stdout, `json.loads`-able, `ok:true`, `command=="audit-duplicates"` | unit | `...TestJson` | ❌ Wave 0 |

All unit tests build a **synthetic tiny corpus in `tempfile.TemporaryDirectory`** (mirroring `test_json_contract._make_lean_corpus`) — no dependence on the real `corpus/`. One optional integration test may run against the real `corpus/` *if present*, asserting "no exception + count==752 + ≥1 exact cluster" (skip with `unittest.skipUnless(Path('corpus').is_dir())`).

### Correctness validation strategy (detector + read-only guarantee)
- **Exact (DUP-01):** fixtures with identical bodies but differing frontmatter prove body-only hashing; a negative fixture (same frontmatter, different body) proves no false cluster.
- **Near-dup (DUP-03):** construct strings at known ratios (e.g. change ~4% vs ~10% of characters) to pin the 0.95 boundary; assert length-blocking doesn't drop a true near-dup whose lengths are within the band.
- **Clustering (DUP-04):** assert connected-component count and membership for a hand-built edge set incl. a transitive chain and an isolated singleton.
- **Canonical (CLEAN-01):** three members (QC-pass-short, QC-fail-long, QC-pass-long) → assert QC-pass-long wins; equal-length QC ties → assert lexicographic path winner is stable across 100 shuffled inputs (determinism).
- **Read-only guarantee:** compute a manifest of `(relpath → size, mtime_ns, sha1)` for every file under the temp corpus before the run and after; `assertEqual`. Also assert the audit makes zero writes inside any family dir (report goes to a separate output dir). This is the automated proof of Success Criterion 5.
- **Share-safety (RPT-03):** assert `scan_text` is clean on the generated report, and assert it *fails* on a deliberately poisoned copy (abs path / fake `token=...`) so the test proves the gate actually bites.

### Sampling Rate
- **Per task commit:** `poetry run python -m unittest crawler.tests.test_dupaudit -v` (<5 s on synthetic fixtures).
- **Per wave merge:** `poetry run python -m unittest discover -s crawler/tests -v` (full offline suite).
- **Phase gate:** full suite green + `poetry run python -m crawler.dupaudit corpus/ --json` runs clean against the real corpus + `poetry run python scripts/check_publish_safe.py` green, before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `crawler/tests/test_dupaudit.py` — all detector/cluster/canonical/report/read-only/json tests (covers DUP-01..04, CLEAN-01, RPT-01..03, Criterion 5).
- [ ] A small `_make_dup_corpus(tmp)` fixture helper (synthetic multi-family corpus with planted exact/url/near-dup/singleton docs + matching `.eval.json` siblings) — mirror `test_json_contract._make_lean_corpus`.
- [ ] Framework install: **none** — stdlib `unittest` is present; do NOT add pytest.
