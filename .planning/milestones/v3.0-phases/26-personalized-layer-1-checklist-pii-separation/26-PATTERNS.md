# Phase 26: Personalized Layer-1 Checklist + PII Separation - Pattern Map

**Mapped:** 2026-06-21
**Files analyzed:** 7 (3 new, 4 modified) + 1 no-change note
**Analogs found:** 6 / 7 (one synthetic YAML has no code analog)

> **CRITICAL ENV (applies to every plan):** bare `python` is BROKEN in this repo
> (`~/.pyenv/shims/python` → CRLF interpreter error). Run **everything**
> through the venv: `.venv/bin/python -m pytest crawler/tests/test_checklist.py -q`
> (Python 3.10.12). Tests run from the **repo root** (per AGENTS.md / the
> `_REAL_DB = Path("corpus/index.db")` repo-root-relative convention).

---

## File Classification

| New/Modified File | New? | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|------|-----------|----------------|---------------|
| `crawler/checklist.py` | new | service/producer | transform (profile → answer object → gated/rendered) | `crawler/grounding.py` | role-match (sibling compute module, pure-stdlib+searchindex consumer) |
| `crawler/cli.py` (add `_cmd_checklist` + subparser) | modified | controller / CLI dispatch | request-response | `crawler/cli.py` `_cmd_ground` (:431-581) + `_cmd_search` (:294-411) | exact (same file, same dispatch idiom) |
| `crawler/contract.py` (add `"checklist"` command literal) | modified | config/contract | n/a (additive constant) | how `"search"`/`"ground"` were added (:13,:69) | exact |
| `crawler/CONTRACT.md` (add `### checklist`) | modified | docs | n/a | `### ground` (:218-282) / `### search` (:166-217) | exact |
| `personal.example/profile.yaml` | new | config/data (synthetic schema, tracked) | file-I/O (YAML in) | **NO code analog** — model load on `crawler/profile.py` + shape on `crawler/profiles/template.yaml` | no analog (new tracked dir) |
| `crawler/tests/test_checklist.py` | new | test | n/a | `crawler/tests/test_grounding.py` + `test_searchindex.py` | exact (sibling unittest suite) |
| profile loader + `$PR_PERSONAL_DIR` resolution (in `checklist.py` or `cli.py`) | new | utility | file-I/O / env | `crawler/cli.py` `_personal_root()` (:414-428) + `crawler/profile.py` `load_profile` (:142-159) | partial (NO env-var analog exists anywhere) |

---

## Pattern Assignments

### `crawler/checklist.py` (service/producer, transform)

**Primary analog:** `crawler/grounding.py` — the sibling pure-compute module. Copy its
**module shape**: top-of-file design-constraints docstring, `from __future__ import annotations`,
stdlib-only + `from crawler import searchindex`, a domain exception subclass, small pure
functions. The checklist module is the *producer* that ASSEMBLES the answer object that
`grounding.check_answer` / `grounding.render_answer` then gate/render.

**Module header + imports pattern** (`crawler/grounding.py:44-75`):
```python
from __future__ import annotations

import json
import re
from pathlib import Path

from crawler import searchindex

# ... domain constant tuples ...

class InvalidAnswer(ValueError):
    """Raised when the answer object is malformed / missing required shape...."""
```
→ Checklist should define its own analog exception (e.g. `class ProfileError(...)` or reuse
`crawler.profile.ProfileError`) and import BOTH `grounding` and `searchindex`. Per CONTEXT
"stdlib + PyYAML only; NO new deps" — add `import yaml` (already a dependency, see profile.py).

**The answer-object contract this module must EMIT** — exact key set, confirmed from the
tracked eval fixture `crawler/eval/questions.jsonl` (keys: `abstentions, basis, claims,
expect, id, prose, question`) and `grounding.py:6-12`:
```python
{
    "question":   str,
    "claims":     [{"id": str, "text": str, "citations": [str, ...], "quote": str}],
    "basis":      [...],   # profile-derived APPLICABILITY goes HERE — NEVER citation-checked
    "abstentions":[...],
    "prose":      str,
}
```
**SEPARATION-OF-CONCERNS RULE (CHK-01/CHK-02, locked):** requirement text + citation come
from the corpus and live in `claims[]` (gated); profile-derived applicability (countries
lived in, dates) goes in `basis[]` and is NEVER citation-checked. `claims[].text` must
contain **NO PII**. This is the same boundary `grounding._validate_shape` (:149-182) and
`check_answer` (:185-215) enforce — only `claims[]` is inspected; `prose`/`basis`/`abstentions`
are free-form filler.

**How to build a grounded claim (retrieve → cite → quote)** — mirror the resolve/quote
round-trip the gate verifies. Use `searchindex.search` to find the requirement chunk, then
`searchindex.resolve` to get the exact verbatim `text` to quote from:
- `searchindex.search(db, query, limit, family)` returns `{query, db, count, hits}` where each
  hit has `chunk_id = relpath#ordinal` + the 5 citation fields (`crawler/searchindex.py:420-488`).
- `searchindex.resolve(db, chunk_id)` returns `{chunk_id, relpath, source_url, title, section,
  crawl_date, text}` or `None` on miss/drift (`crawler/searchindex.py:502-561`).
- A claim's `quote` MUST be a verbatim (whitespace/case-normalized) substring of the resolved
  chunk's `text`, else the gate fails it `quote_not_in_chunk` (`grounding.check_claim:102-146`,
  `quote_is_grounded:87-99`). Test pattern: `quote = text[:60]` of the resolved chunk
  (`test_grounding.py:82-83`).

**Run the assembled object THROUGH the gate** (do not re-implement gating):
```python
result = grounding.check_answer(answer, db)   # {verdict, total_claims, grounded, ungrounded, violations}
# on pass: rendered = grounding.render_answer(answer, db)
```
(`grounding.check_answer:185-215`, `grounding.render_answer:314-365`.)

---

### `crawler/cli.py` — add `_cmd_checklist` + subparser (controller, request-response)

**Primary analog:** `_cmd_ground` (`crawler/cli.py:431-581`) — it is the render-then-scan-then-write-
to-`personal/output/` verb. Secondary: `_cmd_search` (`:294-411`) for the thin-dispatch +
`--db` validation + envelope idiom.

**Thin-dispatch + lazy-import + `--db` validation** (`_cmd_ground:459-477`):
```python
import json
import re
import sys
from pathlib import Path

from crawler import grounding              # + from crawler import checklist (new)

def _fail(err_type: str, msg: str, code: int) -> int:
    if args.json:
        contract.emit(contract.envelope("checklist", error=(err_type, msg)))
    else:
        print(f"error: {msg}", file=sys.stderr)
    return code

db = Path(args.db)
if not db.is_file():
    return _fail(contract.INVALID_INPUT, f"not a file: {db}", contract.EXIT_INVALID_INPUT)
```

**Repo-anchored PII-boundary containment** — REUSE `_personal_root()` verbatim
(`crawler/cli.py:414-428`); it is already monkeypatched by the grounding CLI tests:
```python
def _personal_root() -> "Path":
    from pathlib import Path
    return (Path(__file__).resolve().parents[1] / "personal").resolve()
```
**Anchored `--out-dir` containment check** (`_cmd_ground:532-538`) — copy exactly so rendered
output can only land under `<repo>/personal`:
```python
out_dir = Path(args.out_dir)
repo_personal = _personal_root()
resolved = out_dir.resolve()
if resolved != repo_personal and repo_personal not in resolved.parents:
    return _fail(contract.INVALID_INPUT,
                 f"--out-dir must resolve under {repo_personal}: {out_dir}",
                 contract.EXIT_INVALID_INPUT)
```

**Render-then-scan-then-write (RPT-03)** — copy the scan-before-write block verbatim
(`_cmd_ground:546-575`). `scripts/` is NOT a package, so use the `sys.path` shim + neutral
scan label (`"answer.md"`/`"checklist.md"`) so the scan is never self-excluded:
```python
_scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)
import check_publish_safe as cps          # RPT-03 share-safety gate

violations = cps.scan_text("checklist.md", rendered_md)   # NEUTRAL label, NOT out_path (WR-01)
if violations:
    msg = f"refusing to write checklist: {len(violations)} publish-safety violation(s)"
    if args.json:
        contract.emit(contract.envelope("checklist", error=(contract.INTERNAL_ERROR, msg)))
    else:
        print(f"error: {msg}", file=sys.stderr)
    return contract.EXIT_INTERNAL_ERROR

out_dir.mkdir(parents=True, exist_ok=True)
out_path.write_text(rendered_md, encoding="utf-8")
```

**Verdict-fail is NOT an execution error** (`_cmd_ground:514-523`): a grounding
`verdict:"fail"` → `ok:true` + `result.verdict:"fail"` + exit `1`, write NOTHING.

**Subparser registration** — mirror the `p_ground` block (`crawler/cli.py:667-682`):
```python
p_checklist = subparsers.add_parser(
    "checklist",
    help="Generate a personalized, fully-cited Layer-1 document checklist from a local profile.")
p_checklist.add_argument("--db", default="corpus/index.db",
                         help="SQLite index path (default: corpus/index.db)")
p_checklist.add_argument("--out-dir", default="personal/output",
                         help="render→scan→write the cited checklist here "
                              "(default: personal/output; must resolve under git-ignored 'personal/')")
# profile path resolution — see $PR_PERSONAL_DIR note below
p_checklist.set_defaults(func=_cmd_checklist)
```
Also add `checklist` to the subparsers `metavar` string (`crawler/cli.py:598`).

**Exit-code mapping (unchanged taxonomy, REUSE constants):** `EXIT_INVALID_INPUT=2`,
`EXIT_MISSING_DEPENDENCY=3`, `EXIT_INTERNAL_ERROR=4` from `contract.py:57-60`; verdict-fail = exit 1.
The `--json` catch-all in `main()` (`cli.py:699-709`) already wraps every verb — no change needed.

---

### `crawler/contract.py` — additive `"checklist"` command literal (config)

**Analog:** how `search`/`ground` were threaded in — additive ONLY, **`SCHEMA_VERSION` stays
`"1.0"`** (`contract.py:41`), 5 envelope keys unchanged (`contract.py:81-87`), `EXIT_*`
unchanged. The only edits are documentation strings listing the command union:
- `contract.py:13` — add `| "checklist"` to the docstring command list.
- `contract.py:69` — add `checklist` to the `envelope()` docstring command list.

`envelope("checklist", result=..., error=...)` already works with zero code change — these are
doc-only edits (the function takes `command: str`).

---

### `crawler/CONTRACT.md` — additive `### checklist` section (docs)

**Analog:** the `### ground` section (`crawler/CONTRACT.md:218-282`) and `### search`
(`:166-217`). Add a parallel `### checklist` under `## Per-command result fields`. Copy these
locked phrasings:
- `schema_version` stays `"1.0"` — "No new error type, exit code, or schema bump is introduced —
  the only additive change is the `checklist` command value and this section." (mirror `:280-282`).
- Reuse the verdict-fail / RPT-03 / publish-safety-refusal / honesty-boundary paragraphs from
  `### ground` (`:251-282`) — the checklist verb shares the exact write-gate semantics.
- Add `checklist` to the command list in the `## The envelope` table area and the parse example
  (`:13` equivalent in the prose).

---

### `personal.example/profile.yaml` (config/data, file-I/O) — **NO CODE ANALOG**

`personal.example/` does NOT exist yet (confirmed: only `personal/output/` exists, git-ignored).
This phase CREATES the synthetic, **tracked** schema file. `.gitignore` is ALREADY correct —
**no edit needed** (confirmed lines): `personal/` (ignored) + `!personal.example/` (un-ignored).

**YAML *shape* analog:** `crawler/profiles/template.yaml` / `crawler/profiles/ircc.yaml` — a
top-level YAML mapping with commented fields. Keep the file SYNTHETIC (zero real PII):
placeholder countries/dates that drive the demo/test end-to-end.

**YAML *loading* analog:** `crawler/profile.py:142-159` — load with **`yaml.safe_load` ONLY**
(never `yaml.load`), wrap errors, assert it is a mapping:
```python
try:
    text = source.read_text(encoding="utf-8")
except OSError as exc:
    raise ProfileError(f"Could not read profile file {source}: {exc}") from exc
try:
    data = yaml.safe_load(text)            # safe_load ONLY — never yaml.load (T-13-01)
except yaml.YAMLError as exc:
    raise ProfileError(f"Invalid YAML in profile {source}: {exc}") from exc
if not isinstance(data, dict):
    raise ProfileError(f"Profile {source} must be a YAML mapping; got {type(data).__name__}.")
```
Also mirror the required-keys/typed-fields validation loop (`profile.py:166-176`).

---

### `crawler/tests/test_checklist.py` (test) — mirror `test_grounding.py` / `test_searchindex.py`

**Module docstring + imports** (`test_grounding.py:1-46`): stdlib `unittest` ONLY (no pytest
fixtures, no network), run-from-repo-root note, synthetic-corpus-in-tempdir pledge:
```python
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from crawler import cli, contract, grounding, searchindex
# Reuse the synthetic-corpus builder — NEVER re-walk the real corpus/.
from crawler.tests.test_searchindex import _make_index_corpus
```

**Synthetic tmp index in `setUp`** (`test_grounding.py:48-59`) — build a real DB in a
`tempfile.TemporaryDirectory`, NEVER the real `corpus/`:
```python
def setUp(self) -> None:
    self._tmp = tempfile.TemporaryDirectory()
    self.root = _make_index_corpus(Path(self._tmp.name))
    self.db = Path(self._tmp.name) / "index.db"
    searchindex.build_index(self.root, self.db)
def tearDown(self) -> None:
    self._tmp.cleanup()
```
Pull a real `(chunk_id, text)` from the built `chunks` table for verbatim quotes
(`test_grounding.py:61-74`, table `pr-pdi/tiny.md`).

**CLI test harness with stdin + monkeypatched `_personal_root`** (`test_grounding.py:500-526`) —
copy `_run` + `_out_dir`. Tempdir-only writes; pin `cli._personal_root` to a `personal/` dir
UNDER the tempdir so the write-gate never touches the real repo tree:
```python
def _run(self, argv, stdin_text=""):
    out, err = io.StringIO(), io.StringIO()
    old_stdin = sys.stdin
    sys.stdin = io.StringIO(stdin_text)
    anchor = (Path(self._tmp.name) / "personal").resolve()
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                mock.patch("crawler.cli._personal_root", return_value=anchor):
            rc = cli.main(argv)
    finally:
        sys.stdin = old_stdin
    return rc, out.getvalue(), err.getvalue()
```

**`@skipUnless` real-corpus guard** (`test_grounding.py:830-853`) — for any end-to-end test
against the live index:
```python
_REAL_DB = Path("corpus/index.db")
@unittest.skipUnless(_REAL_DB.is_file(), "real corpus/index.db not present")
class TestRealCorpusChecklist(unittest.TestCase): ...
```

**PII self-scan assertion (NOT skip-guarded — the rendered/tracked bytes must always scan)**
(`test_grounding.py:856-870`) — the CHK-02 acceptance test over rendered checklist bytes AND the
tracked `personal.example/profile.yaml`:
```python
scripts_dir = str(Path(__file__).resolve().parents[2] / "scripts")
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)
import check_publish_safe as cps
self.assertEqual(cps.scan_text("checklist.md", rendered_md), [])
```
Add an assertion that no PII (countries/dates/names from the profile) appears in
`claims[].text` or in the corpus DB — the core CHK-02 separation guarantee.

---

## Shared Patterns

### PII boundary (render-then-scan, fail-closed)
**Source:** `scripts/check_publish_safe.py` `scan_text` (:115-132) + `CORPORA_PREFIXES`
(:47, includes `personal/`) + `is_excluded` (:104-112); applied via `_cmd_ground:546-575`.
**Apply to:** the `checklist` CLI write-gate AND `test_checklist.py` self-scan.
Pass a **neutral, never-excluded** scan label (`"checklist.md"`), NOT the destination path
(WR-01, `cli.py:553-560`), or an `--out-dir` under `scripts/tests/` self-excludes and SKIPS the scan.
```python
CORPORA_PREFIXES = ("trial/", "personal/", "corpus_new/")   # check_publish_safe.py:47
def scan_text(path: str, text: str) -> list:                # :115
    if is_excluded(path): return []
    ...
```

### Contract envelope + exit codes (frozen, additive-only)
**Source:** `crawler/contract.py` `envelope` (:63-87) / `emit` (:90-96) + `EXIT_*` (:57-60).
**Apply to:** every branch of `_cmd_checklist`. One `contract.emit(contract.envelope("checklist", ...))`
to stdout in `--json` mode; ALL human/progress text to stderr (stdout-purity invariant).
`SCHEMA_VERSION="1.0"` and the 4 exit codes are UNCHANGED.

### Repo-anchored personal/ containment
**Source:** `crawler/cli.py` `_personal_root()` (:414-428) + the anchored containment check
(`_cmd_ground:532-538`).
**Apply to:** `_cmd_checklist` `--out-dir` validation. Reuse the SAME function (tests already
monkeypatch `crawler.cli._personal_root`).

### Safe YAML loading
**Source:** `crawler/profile.py:142-159` (`yaml.safe_load` only, mapping-typed, fail-fast `ProfileError`).
**Apply to:** the profile loader for `profile.yaml` in `checklist.py`.

### Sibling unittest conventions
**Source:** `crawler/tests/test_grounding.py` / `test_searchindex.py`: stdlib `unittest`, synthetic
tempdir corpus, `_make_index_corpus` reuse, `@skipUnless(_REAL_DB.is_file())`, tempdir-only writes,
`mock.patch` for the `personal/` anchor. Run via `.venv/bin/python -m pytest`.

---

## No Analog Found

| File / Concern | Role | Data Flow | Reason / Closest fallback |
|----------------|------|-----------|---------------------------|
| `personal.example/profile.yaml` | config/data | file-I/O | `personal.example/` does not exist; no tracked-profile precedent. Model SHAPE on `crawler/profiles/template.yaml`, LOADING on `crawler/profile.py:142-159`. `.gitignore` already handles tracking (no edit). |
| `$PR_PERSONAL_DIR` env-var + default `./personal/` resolution | utility | env / file-I/O | **NO `os.environ`/`getenv` anywhere in `crawler/` or `scripts/`** (verified). Closest idioms: `_personal_root()` repo-anchored resolve (`cli.py:414-428`) and `BUILTIN_PROFILES_DIR = Path(__file__).parent / "profiles"` anchor-relative default (`profile.py:36`). This is a NEW pattern — planner decides where it lives. |

---

## Decision Points for the Planner

1. **Where does `$PR_PERSONAL_DIR` resolution live?** No env-var analog exists. Options:
   (a) a small helper in `checklist.py` (e.g. `_profile_path()` reading `os.environ.get("PR_PERSONAL_DIR", "./personal")`), or
   (b) a `--profile`/`--personal-dir` CLI flag on the subparser (matches the explicit-flag style of
   `_cmd_crawl --profile`, `cli.py:609-611`). Default must be `./personal/` per success criterion 1.
   Recommend env-var WITH a CLI flag override; keep the default git-ignored.

2. **Profile loader location.** Reuse `crawler.profile.ProfileError` + the `yaml.safe_load` idiom,
   or define a checklist-local `ProfileError`/`load_personal_profile`? The personal profile schema
   is DIFFERENT from a crawl `SiteProfile` (it carries applicability facts, not crawl rules), so a
   dedicated loader in `checklist.py` is cleaner than overloading `crawler/profile.py`.

3. **Does `checklist` write through the SAME render path as `ground`, or its own renderer?**
   `grounding.render_answer` (:314-365) renders a generic answer object claim-by-claim with the
   honesty-boundary footer — it works for the checklist object as-is. Recommend REUSE it (the
   checklist IS a Phase-25 answer object) rather than a bespoke renderer, so the gate/render/scan
   pipeline stays identical and the CHK-01 "every line is a gated cited claim" guarantee holds by
   construction. If a checklist-specific layout is wanted, add a `checklist.render(...)` that still
   only renders gated `claims[]` + `basis[]`.

4. **Applicability → which corpus queries?** The mapping from profile facts (e.g. "lived in
   country X since 18" → "police certificate for X required") to `searchindex.search` queries is
   net-new domain logic with no analog. Keep applicability derivation PURE and in `basis[]`; only
   the resulting requirement text/citation goes through the gate.

5. **CONTRACT.md `result` shape for `checklist`.** Decide whether it returns the raw
   `grounding.check_answer` verdict shape (`{verdict, total_claims, grounded, ungrounded,
   violations, out}`) verbatim — recommended, identical to `ground` (`CONTRACT.md:242-249`) — or a
   richer per-item summary. Reuse keeps the additive-only contract promise trivially true.

---

## Metadata

**Analog search scope:** `crawler/` (cli.py, grounding.py, searchindex.py, contract.py, profile.py,
config.py, profiles/), `crawler/tests/`, `scripts/check_publish_safe.py`, `crawler/CONTRACT.md`,
`crawler/eval/questions.jsonl`, `.gitignore`, `personal/`.
**Files scanned:** ~14 source/doc files read; full reads of grounding.py, contract.py,
check_publish_safe.py, config.py; targeted reads of cli.py / searchindex.py / profile.py /
test_grounding.py.
**Env verified:** bare `python` broken (CRLF shim); `.venv/bin/python` = 3.10.12. No `os.environ`
usage in crawler/scripts. `personal.example/` absent; `.gitignore` already ignores `personal/` +
un-ignores `personal.example/`.
**Pattern extraction date:** 2026-06-21
