# Phase 46: Safe Conformance Release Gate - Pattern Map

**Mapped:** 2026-07-20  
**Files analyzed:** 9 target paths  
**Analogs found:** 9 / 9

## Scope Reconciliation

`46-RESEARCH.md` is the authoritative create/modify/freeze contract. `46-VALIDATION.md`
uses the older split names `test_conformance_v5_release_matrix.py` and
`test_conformance_v5_privacy_release.py`; these are pattern-equivalent partitions of
the research file `test_conformance_v5_release_flow.py`. If the planner keeps the
validation split, apply the matrix patterns to the former and privacy/frozen/E2E
patterns to the latter. Do not create both the combined and split forms.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `crawler/tests/test_conformance_v5_grounding.py` | test/static analysis | batch/transform | `crawler/tests/test_conformance_v40_retrieve_what_you_cite.py` | exact |
| `crawler/tests/test_conformance_v5_release_flow.py` | integration/E2E test | request-response + file-I/O | Existing four `test_conformance_v5_*` screen suites | exact composite |
| `crawler/tests/test_conformance_v5_release_matrix.py` (validation split) | integration test | batch matrix | `crawler/tests/test_conformance_v5_mec_no_false_meets.py` | exact |
| `crawler/tests/test_conformance_v5_privacy_release.py` (validation split) | integration/static test | file-I/O + transform | `crawler/tests/test_conformance_v40_privacy_containment.py` | exact |
| `crawler/tests/test_conformance_v5_release_gate.py` | runner self-test | subprocess/request-response | `crawler/tests/test_conformance_v41_release_gate.py` | exact |
| `scripts/run_conformance.py` | CLI/config | subprocess/batch | existing `scripts/run_conformance.py` | exact in-place |
| `crawler/tests/test_crs_no_inlined_rules.py` | static-analysis test | discovery/transform | existing `_MEC_MODULES` enrollment | exact in-place |
| `pyproject.toml` | config | declarative | existing pytest marker at line 40 | exact in-place |
| `crawler/tests/test_conformance_v5_mec_no_false_meets.py` | frozen-contract test | hashing/transform | existing `TestFrozenMecSurfaces` | exact in-place |

## Pattern Assignments

### `crawler/tests/test_conformance_v5_grounding.py`

**Primary analogs:**
- `crawler/tests/test_conformance_v40_retrieve_what_you_cite.py`
- `crawler/tests/test_crs_no_inlined_rules.py`

**Imports and marker pattern** — copy the stdlib `unittest` plus module-level marker
style from `crawler/tests/test_conformance_v41_grounding.py:9-21`.

```python
import ast
import unittest
from pathlib import Path

import pytest

from crawler import auditors, crs_rules, remediation, review_packet

pytestmark = pytest.mark.conformance
```

**Real-index grounding sweep** — copy
`crawler/tests/test_conformance_v40_retrieve_what_you_cite.py:100-130`, but first
assert exact MEC/POLICY/STUDY/DLI rule-id manifests rather than relying on aggregate
counts.

```python
@unittest.skipUnless(_REAL_DB.is_file(), "...")
class TestRetrieveWhatYouCiteWholeRegistry(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = crs_rules.load_registry(_DATA_DIR)
        cls.nongap = [r for r in cls.reg.rows if not r.gap]

    def test_every_non_gap_rule_agrees_and_grounds(self) -> None:
        report = crs_rules.retrieve_what_you_cite(self.reg, _REAL_DB)
        covered: set[str] = set()
        for row in self.nongap:
            with self.subTest(rule_id=row.rule_id):
                entry = report[row.rule_id]
                self.assertTrue(entry["agrees_with_citation"], row.rule_id)
                self.assertTrue(entry["grounds"], row.rule_id)
                covered.add(row.rule_id)
        self.assertEqual(covered, {r.rule_id for r in self.nongap})
```

Under `PR_CONFORMANCE_RUNNER=1`, replace the local-only skip with a failing setup
assertion. Normal focused/full-suite execution may retain the honest skip.

**Non-vacuous grounding negative** — use the paired bad/good pattern from
`crawler/tests/test_conformance_v40_retrieve_what_you_cite.py:463-482`.

```python
row = _syn_row("wrong.family", family="legislation-irpr")
entry = self._entry(row)
self.assertFalse(entry["agrees_with_citation"])
self.assertFalse(entry["grounds"])

mirror = _syn_row("wrong.family.mirror", family="pr-pdi", marker=_TINY_QUOTE)
m = self._entry(mirror)
self.assertTrue(m["agrees_with_citation"])
self.assertTrue(m["grounds"])
```

**Exact scanner enrollment** — copy the exact-set assertion from
`crawler/tests/test_conformance_v5_mec_no_false_meets.py:1135-1143`. The v5 set must
explicitly include `policy_offer.py` and `dli_snapshot.py`; do not merely assert that
the files happen to appear in a broad recursive glob.

### `crawler/tests/test_conformance_v5_release_flow.py`

This combined research target owns independent matrices, privacy/frozen checks, and
the confirmed-vault E2E. If using validation's split, put the first subsection in
`test_conformance_v5_release_matrix.py` and the remaining subsections in
`test_conformance_v5_privacy_release.py`.

#### Independent matrix pattern

Copy the table-driven `subTest` structure, not donor fixture helpers.

**MEC unwired/stale matrix:** `crawler/tests/test_conformance_v5_mec_no_false_meets.py:212-282`

```python
cases = {
    "missing": complete[1:],
    "unwired": [
        item.model_copy(update={"wired": False, "rule_ids": []})
        if item.criterion_id == first.criterion_id else item
        for item in complete
    ],
    "duplicate": complete + [first],
}
for name, criteria in cases.items():
    with self.subTest(program=program, case=name):
        self.assertEqual(
            mec_screen.rollup_program_status(program, criteria), "AT-RISK")
```

**POLICY cross-window sweep:** `crawler/tests/test_conformance_v5_policy_no_job_offer_green.py:177-199`

```python
for label, by_field, factor, ita_date, registry in self._cases():
    with self.subTest(case=label):
        res = ad.decide_job_offer(_ctx(...))
        self.assertNotEqual(res.verdict, "SUBSTANTIATED")
        self.assertIn(res.substantiated_points, (None, 0))
        self.assertIn(res.verdict, ("AT-RISK", "N/A"))
```

**NOC state matrix:** `crawler/tests/test_conformance_v5_noc_no_auto_green.py:311-352`
shows the required assertions beyond “not green”: closed status, no score-bearing
keys, exact public-field set, bounded confirmation count, and pole spot-checks.

**Independent fixture rule:** unlike the existing focused NOC suite, Phase 46 must
not import helpers from another test module. Seed raw vault/SQLite rows locally,
prove one valid positive reaches the intended branch, apply one mutation, then call
only the public production entry point.

#### Snapshot provenance and fingerprint pattern

Use independent copied-index mutation from
`crawler/tests/test_conformance_v5_study_no_false_green.py:816-876`.

```python
with sqlite3.connect(db) as con:
    con.execute(
        "UPDATE chunks SET crawl_date = ? WHERE relpath = ?",
        (replacement, relpath),
    )
seen = searchindex.canonical_rows_for_relpath(db, relpath)
self.assertGreaterEqual(len(seen), 2)  # mutation is non-vacuous

result = self._review(v, label, db)
self.assertEqual(
    (result["status"], result["reason"], result["as_of"]),
    ("AT-RISK", "snapshot_provenance_mismatch", None),
)
self.assertFalse(self._report(v).exists())
```

For registry drift, preserve snapshot A's fingerprint in confirmed evidence and
sidecars, independently construct snapshot B, rerun MEC/POLICY/STUDY/NOC composition,
and assert each refuses. Do not calculate the expected fingerprint using a second
test-only canonicalizer.

#### Privacy and publish-safe pattern

Use canaries across both streams and every public projection, following
`crawler/tests/test_conformance_v40_privacy_containment.py:137-180`.

```python
rc, out, err = self._run_cli([...])
self.assertEqual(rc, 0, out + err)
dumped = json.dumps(json.loads(out)["result"])
for sentinel in self._sentinels():
    self.assertNotIn(sentinel, out)
    self.assertNotIn(sentinel, dumped)
self.assertNotIn("ev_", out)
self.assertNotIn(self._tmp.name, out)
```

Also copy the refusal-path scan from lines 182-206 and public-model negative
construction from lines 213-232. Scan the whole tracked tree through the shipped
scanner exactly as in lines 340-348:

```python
cps = _load_cps()
out = io.StringIO()
with contextlib.redirect_stdout(out):
    rc = cps.main()
self.assertEqual(rc, 0, out.getvalue())
```

#### Dependency/network AST pattern

Copy `crawler/tests/test_conformance_v5_mec_no_false_meets.py:1088-1124` for the
transitive enrolled screen surface: parse imports/calls, reject network packages and
alternate loaders, and assert the expected loader count.

At runtime, deny sockets as in lines 1126-1133:

```python
with mock.patch.object(
    socket, "socket", side_effect=AssertionError("network forbidden")
):
    run_real_composite_flow()
```

Freeze the exact dependency set and lock hash using
`crawler/tests/test_conformance_v5_study_no_false_green.py:1306-1341`.

#### Frozen envelope and CRS pattern

Copy `crawler/tests/test_conformance_v5_mec_no_false_meets.py:1019-1064`:

```python
self.assertEqual(
    tuple(PublicAuditEnvelope.model_fields),
    ("run_id", "factor_id", "verdicts", "claims", "counts",
     "private_output_path"),
)
self.assertEqual(FULL_GRID_FACTORS, EXPECTED_FULL_GRID)
self.assertFalse(
    any("program" in factor or "mec" in factor for factor in FULL_GRID_FACTORS))
```

Hash named contractual files individually. Do not replace this with one broad,
brittle hash over all production files.

#### Confirmed-vault E2E fixture pattern

Use `crawler/tests/test_full_audit_integration.py:38-120` as the base shape:
temporary `PR_PERSONAL_DIR`, real `corpus/index.db`, shipped vault APIs, imported
synthetic documents, extracted values, confirmations, and explicit cleanup.

```python
def setUp(self) -> None:
    self._tmp = tempfile.TemporaryDirectory()
    self._env = mock.patch.dict(
        os.environ, {"PR_PERSONAL_DIR": self._tmp.name})
    self._env.start()
    self.db = str(_REAL_DB)
    self.registry = crs_rules.load_registry()

def tearDown(self) -> None:
    self._env.stop()
    self._tmp.cleanup()
```

For five-key evidence, follow the shipped API sequence at
`crawler/tests/test_conformance_v5_study_no_false_green.py:220-269`:
`create_candidate` → `upsert_profile_factor` → `import_document` →
`record_extraction_run` → `add_document_page` → `add_extracted_value` →
`confirm_value`. Distinct evidence IDs/file/render hashes must be used for separate
fields.

Release mode must fail—not skip—when the real index, DLI family/manifest, or required
confirmed fixture is absent. Error text must be stable and PII-free.

### `crawler/tests/test_conformance_v5_release_gate.py`

**Analog:** `crawler/tests/test_conformance_v41_release_gate.py`

Copy its constants/marker/guard pattern from lines 16-40 and its four-test structure
from lines 43-73:

```python
pytestmark = pytest.mark.conformance
_RUNNER = _REPO_ROOT / "scripts" / "run_conformance.py"
_GUARD_ENV = "PR_CONFORMANCE_RUNNER"

env = dict(os.environ)
env[_GUARD_ENV] = "1"
proc = subprocess.run(
    [sys.executable, str(_RUNNER), "--collect-only", "-q"],
    cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True)
self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
for criterion, module in _V5_MODULES:
    self.assertIn(module, proc.stdout, f"{criterion} not collected")
```

Assert:
1. bounded discovery contains every required v4 and v5 module;
2. collect-only node IDs contain the hard required-module subset;
3. every selected module carries `pytest.mark.conformance`;
4. the self-test is marked;
5. collect-only does not set up a recursive real release run.

### `scripts/run_conformance.py`

**Analog:** existing file, especially lines 34-54 and 57-91.

Change the one `_GLOB` to a bounded tuple and deduplicate:

```python
_GLOBS = (
    "crawler/tests/test_conformance_v4[01]_*.py",
    "crawler/tests/test_conformance_v5_*.py",
)

def conformance_modules() -> list[Path]:
    return sorted({
        path for pattern in _GLOBS for path in _REPO_ROOT.glob(pattern)
    })
```

Preserve unchanged:
- `argparse.parse_known_args` passthrough (`scripts/run_conformance.py:57-72`);
- guard only on real execution (lines 74-77);
- list-form `subprocess.run`, repository `cwd`, copied environment (line 83);
- exact pytest return code (lines 84-91);
- `--collect-only`/`--list` behavior.

Update the banner/criteria to SAFE-01..12. Never use an unbounded
`test_conformance_v*.py` glob or marker-only discovery.

### `crawler/tests/test_crs_no_inlined_rules.py`

**Analog:** existing exact enrollment at lines 42-74.

Add `crawler/policy_offer.py` and `crawler/dli_snapshot.py` to named v5 source
collections, retain existence filtering, and add an exact-set test. Keep all current
positive controls (`test_positive_control_gate_bites`,
`test_positive_control_python_literal_bites`, and MEC category controls); they prove
the scanner is wired even when a path/glob is empty.

### `pyproject.toml`

**Analog:** line 40.

Change only the marker description:

```toml
markers = [
    "conformance: v5 release-gate safety conformance suite (SAFE-01..12)",
]
```

Do not change `[project].dependencies`, optional dependencies, build configuration,
or `poetry.lock`.

### `crawler/tests/test_conformance_v5_mec_no_false_meets.py`

**Analog:** `TestFrozenMecSurfaces._HASHES` at lines 1000-1025.

After reviewing the exact diffs, roll only the expected SHA-256 values for:

```python
"pyproject.toml": "...",
"scripts/run_conformance.py": "...",
```

All production, lock, envelope, CRS guard, auditor grid, model, and registry hashes
remain unchanged.

## Shared Patterns

### Screening Notices and Release Docs

**Tests:** `crawler/tests/test_conformance_v40_screening_framing.py:89-181`  
**Canonical prose:** `crawler/README.md:202-219`, `SCREENING.md:1-59`

For every rendered MEC/STUDY/NOC/public artifact, assert:
- “screening” and “not legal advice”/“not a substitute” are present;
- grounded/cited and audit-eligible threshold framing is present;
- semantic fit, NOC-duty fit, and officer discretion stay human-review/`AT-RISK`;
- affirmative eligibility/outcome phrases are absent.

Keep the denylist non-vacuous with a crafted bad sentence before scanning real
artifacts. POLICY is inert and need not render its own notice; test it through the
containing MEC/public artifact.

Release docs are validation targets, not default edit targets. Their existing text is
the copy source:

```markdown
The CRS auditor produces a **substantiation screening**, **not legal advice** and
**not a substitute** for a licensed immigration consultant or lawyer.
```

Run the shipped `check_publish_safe.scan_text` over `SCREENING.md` and the README
screening section as in `test_conformance_v40_screening_framing.py:161-181`.

### Assertions and Cleanup

- Use stdlib `unittest.TestCase`, `subTest`, and module-level
  `pytestmark = pytest.mark.conformance`.
- Prefer stable status/reason/output assertions over broad `assertFalse`.
- Pair every negative with a positive branch-reachability control.
- Use `try/finally`, `tearDown`, or context managers to close vault/SQLite handles and
  temporary directories.
- There is no authentication layer in this local CLI phase.

## No Analog Found

None. Every target has a current repository analog. The composite E2E is new only in
its breadth; its fixture, privacy, provenance, and screen-specific pieces all have
exact local sources above.

## Metadata

**Analog search scope:** `scripts/`, `crawler/tests/`, `crawler/README.md`,
`SCREENING.md`, `pyproject.toml`  
**Primary analogs read:** 14  
**Pattern extraction date:** 2026-07-20
