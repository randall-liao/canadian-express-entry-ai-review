---
phase: 36-operational-hardening
reviewed: 2026-07-17T11:08:36Z
depth: deep
files_reviewed: 7
files_reviewed_list:
  - crawler/index_health.py
  - crawler/cli.py
  - personal.example/crs-profile.example.yaml
  - crawler/tests/test_index_health.py
  - crawler/tests/test_audit_index_refusal.py
  - crawler/tests/test_example_profile_pinned.py
  - crawler/tests/test_adversarial_extraction_seam.py
findings:
  critical: 0
  warning: 2
  info: 4
  total: 6
status: resolved
resolution:
  warning_fixed: 2
  info_addressed: 0
  note: "WR-01 (pre-open PermissionError/FileNotFoundError) and WR-02 (non-str text cell) fixed in crawler/index_health.py — probe_index now fails closed to index_unreadable/index_corrupt with 3 new regression tests (permission-denied dir, BLOB text, kept row-malformed). Info findings acknowledged as advisory (URI interpolation matches the frozen searchindex read pattern; skip guards are intentional structural-only on a fresh clone)."
---

# Phase 36: Code Review Report

**Reviewed:** 2026-07-17T11:08:36Z
**Depth:** deep (cross-file trace + live execution of all four test files against the real 14 MB `corpus/index.db` and the extraction stack)
**Files Reviewed:** 7
**Status:** issues_found

## Summary

The change set is small, well-targeted, and largely does what it claims. I ran the full Phase‑36 test set in this environment (where `corpus/index.db` and the extraction deps are both present, so **nothing was skipped** — all 24 new tests plus 22 pre-existing audit tests pass), plus adversarial edge-case probes of `probe_index`.

Verified sound (adversarially, not by trust):

- **Read-only / side-effect-free happy path.** `probe_index` never creates a file for a missing path (`test_missing_path...creates_nothing` passes), opens `file:<db>?mode=ro`, and `con.close()` is in a `finally` on every post-connect path — no connection leak.
- **Reason-code classification order is correct:** missing → empty(0-byte) → unreadable → corrupt(non-sqlite / missing tables / row-read DatabaseError) → empty(0 chunks) → drifted → ok. The 0-byte-before-open ordering correctly avoids mislabeling an empty file as corrupt.
- **No drift false-positive on the real index.** The bounded 64-row `chunk_sha` sample passes against the live 14 MB index (both the unit positive control and the full pinned real audit run green). `build_index` stores `chunk_sha(text)` for the exact stored text, so a valid row can never mismatch.
- **Preflight runs before `open_vault` → zero artifacts on refusal.** Wiring at `cli.py:1121-1123` precedes `vault.open_vault`, and `test_audit_index_refusal` confirms `audit_runs` count == 0 and no report files after a refusal. Refusal is `invalid_input` / exit 2, PII-free (echoes only the corpus `--db`, no `ev_`), one envelope only. `refusal is not None` is used (not a truthy check), so an exit code of 0 could not be swallowed.
- **No healthy-index regression.** The 22 existing audit CLI/integration/real-seam tests still pass; the synthetic index they build passes the new preflight.
- **Example profile is pinned and clean.** All six `factor_id`s are members of `auditors.FULL_GRID_FACTORS` and every `factor_group` matches `auditors.FACTOR_GROUP`. `check_publish_safe.py` reports 0 violations across 322 tracked files — no PII introduced, publish-safe.
- **HARD-04 quarantine tests are non-vacuous and key on the correct predicate.** The confirm/correct-cannot-green test keys on `is_audit_eligible` (line 223/226), which gates on `quality_flag == 'ok'` — and `confirm_value` never mutates `quality_flag`, so the lock is real. The rotated-scan test locks the rotation gate via `any(q["rotated"])` *and* `audit_eligible_values(...) == []` *and* `verdict != SUBSTANTIATED`, so it is sound even though a rotated page extracts 0 field values.

Frozen constraints checked: zero new runtime deps (stdlib + reused `searchindex.chunk_sha`) ✅; no second trust path (preflight only) ✅; no new contract error type / exit code (reuses `invalid_input` / exit 2, reason codes are message tokens) ✅.

The two Warnings below are **exception-safety gaps in `probe_index`** that defeat the module's own central promise ("Every post-connect row/column read is wrapped … refuses cleanly as `index_corrupt` instead of re-raising the very traceback this phase kills") and HARD-01 ("*unreadable, corrupt* … → stable PII-free refusal envelope") for two reachable input classes. Neither leaks PII, writes an artifact, or corrupts data — impact is a degraded `internal_error`/exit-4 (json) or raw traceback (human) instead of the intended `invalid_input`/exit-2 refusal — hence Warning, not Critical.

## Warnings

### WR-01: `probe_index` pre-connect filesystem probes are unguarded — a permission-denied directory (or a deletion race) re-raises the exact exit-4 traceback this phase claims to kill

**File:** `crawler/index_health.py:97-103` (specifically `p.is_file()` at :98 and `p.stat()` at :102)

**Issue:** The missing/empty classification runs `p.is_file()` and `p.stat().st_size` outside any `try`. Both call `os.stat`, which re-raises `OSError` subclasses that `Path.is_file()` does *not* swallow — notably `PermissionError` (EACCES). I reproduced this: with the index inside a directory whose traverse permission is removed, `probe_index` raises `PermissionError: [Errno 13] Permission denied: '.../index.db'` instead of returning an `IndexHealth`. A TOCTOU race (file unlinked between `is_file()` returning True and `stat()`) likewise raises `FileNotFoundError`.

This is the *unreadable* case HARD-01 explicitly enumerates, and it is ironic: a permission-denied **file** is handled gracefully (the `mode=ro` connect raises `OperationalError` → `index_unreadable`), but a permission-denied **parent directory** escapes. In `--json` mode `cli.main`'s catch-all (`cli.py:1487-1493`) turns it into `internal_error`/exit-4 with the traceback on stderr; in human mode `main` deliberately does not wrap, so the operator gets a raw traceback. Either way it is the ungraceful outcome this module was written to eliminate. (No artifact is written and no applicant PII leaks — the escaping message carries only the corpus `--db` path — which is why this is Warning, not Critical.)

**Fix:** Wrap the pre-connect probes and classify OSError as a clean refusal:

```python
    p = Path(db)
    try:
        if not p.is_file():
            return IndexHealth(INDEX_MISSING, f"no index file at {p}")
        if p.stat().st_size == 0:
            return IndexHealth(INDEX_EMPTY, f"index file is empty (0 bytes): {p}")
    except FileNotFoundError:
        return IndexHealth(INDEX_MISSING, f"no index file at {p}")
    except OSError:
        return IndexHealth(INDEX_UNREADABLE, "cannot stat index path")
```

### WR-02: drift loop `chunk_sha(text)` raises `AttributeError`/`TypeError` on a NULL or BLOB `text` cell — only `sqlite3.DatabaseError` is caught, so a content-malformed/foreign/legacy-schema DB re-raises instead of refusing as `index_corrupt`

**File:** `crawler/index_health.py:138-147` (the `chunk_sha(text)` call at :141; the guard `except sqlite3.DatabaseError` at :146)

**Issue:** The post-connect body is guarded only by `except sqlite3.DatabaseError`. But `probe_index` validates **table names only**, never the `chunks` column schema or cell types. If the `chunks` table exists with a `text` column that holds a non-`str` value (a `NULL`, or a `BLOB` stored under TEXT affinity), the drift loop calls `chunk_sha(text)` → `text.encode("utf-8")` → `AttributeError: 'NoneType' object has no attribute 'encode'`, which is **not** a `DatabaseError` and is not caught. I reproduced this with a `chunks(chunk_id, text, chunk_sha)` table holding one `NULL` text row: `probe_index` raised `AttributeError` rather than returning `INDEX_CORRUPT`.

This directly contradicts the module docstring's guarantee (lines 17-19) and HARD-01's "corrupt … → stable refusal." The reachable trigger is a DB that is *structurally* valid (right table names, `count(*)` works) but *content*-malformed — e.g. an older/foreign SQLite file the operator accidentally points `--db` at whose `chunks.text` is nullable, or a corrupted page that zeroes a cell without tripping SQLite's structural integrity. Normal truncation corruption raises `DatabaseError` (correctly handled); this specific class does not. As with WR-01 the escape becomes `internal_error`/exit-4 (json) or a traceback (human), no artifact, no PII.

**Fix:** Broaden the guard, or defensively skip non-string rows:

```python
        except (sqlite3.DatabaseError, AttributeError, TypeError):
            return IndexHealth(INDEX_CORRUPT, "index tables unreadable")
```
or, more precisely, inside the loop: `if not isinstance(text, str): return IndexHealth(INDEX_CORRUPT, "non-text chunk body")`.

## Info

### IN-01: `mode=ro` URI is built by naive string interpolation — a `--db` path containing URI-reserved characters mis-parses and can wrongly refuse a healthy index

**File:** `crawler/index_health.py:108` (`sqlite3.connect(f"file:{p}?mode=ro", uri=True)`)

**Issue:** `f"file:{p}?mode=ro"` does not URL-encode `p`. A path containing `?` or `#` (e.g. `/data/foo?bar.db`) mis-parses: SQLite opens a *different* (empty) database, and `probe_index` then reports `index_corrupt` ("missing index tables") for a file that is actually a valid index — reproduced with a `foo?bar.db` path. This is a pre-existing shared idiom (`searchindex.resolve`/`search` build the same URI), the `--db` path is operator-controlled, and the default `corpus/index.db` is safe — so risk is low. Noting because this phase reuses the idiom on a new refusal path. **Fix:** quote the path (`from urllib.request import pathname2url; f"file:{pathname2url(str(p))}?mode=ro"`) or use `p.resolve().as_uri()` + `?mode=ro`.

### IN-02: partially-vacuous recovery-hint assertion in the refusal test

**File:** `crawler/tests/test_audit_index_refusal.py:80` (`self.assertIn("index", msg)`)

**Issue:** The message already contains "corpus **index** unusable" and "reason=**index**_missing", so `assertIn("index", msg)` passes even if the `corpus-crawler … index …` recovery command were removed — it does not actually pin the HARD-02 recovery hint. (`assertIn("doctor", msg)` at :81 is fine — "doctor" appears only in the hint.) **Fix:** assert a token unique to the recovery command, e.g. `self.assertIn("index corpus/", msg)`.

### IN-03: HARD-03/HARD-04 real-path proofs are skip-guarded on the git-ignored `corpus/index.db` — silent SKIP (not fail) on a fresh clone/CI

**File:** `crawler/tests/test_example_profile_pinned.py:59-64` and all of `crawler/tests/test_adversarial_extraction_seam.py:60-64`

**Issue:** The real-audit non-N/A proof (HARD-03) and the entire real-seam quarantine suite (HARD-04) `skipUnless(_REAL_DB.is_file() [and _EXTRACTION_OK])`. Because `corpus/index.db` is git-ignored, on a fresh clone these SKIP silently and a green run is "STRUCTURAL ONLY" (the docstrings say so). I confirmed they **do** run and pass in this environment (index + deps present), so the requirements are genuinely demonstrated here — but the "real CLI path / real seam" guarantee is only enforced where the local artifacts exist. This is an acknowledged trade-off, not a defect; flagging so the release gate (SAFE-08) does not mistake a skip for a pass. Consider committing a tiny fixture index so at least one real-seam case runs in CI.

### IN-04: password-protected quarantine test relies on a mislabeled extraction outcome (out of this diff's scope, but brittle)

**File:** `crawler/tests/test_adversarial_extraction_seam.py:147-152`

**Issue:** The test feeds truncated non-PDF bytes and asserts `q["password_protected"]`, relying on `extraction` mapping any `pdfium.PdfiumError` to the `password_protected` quality flag. The flag is a misnomer for a *truncated/unparseable* file, and the mapping lives in `crawler/extraction.py` (not in this change set). The quarantine assertion is still sound (no eligible value, verdict ≠ SUBSTANTIATED), so this is not a bug in the Phase-36 code — but the test is coupled to an incidental label and would silently stop exercising "password-protected" if extraction later distinguishes the two. Consider a fixture that is genuinely encrypted, or assert on the quarantine outcome rather than the specific flag name.

---

_Reviewed: 2026-07-17T11:08:36Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
