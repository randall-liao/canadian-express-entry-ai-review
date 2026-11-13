# Phase 35 — Execution Discoveries

Logged during execution. Items below were initially deferred by individual plan
executors and then resolved by the phase-level integration gate.

## 35-01 (COV-01 first-language pricing)

### Planning research prose triggered the publish-safe scanner

- **Discovered during:** 35-01 Task 2 regression sweep (full audit/language/crs test subset).
- **Failing tests:**
  - `crawler/tests/test_conformance_v40_privacy_containment.py::TestTrackedTreeScansClean::test_publish_safe_main_zero_violations`
  - `crawler/tests/test_full_audit_pii_perimeter.py::TestRepositoryPublishSafe::test_publish_safe_zero_violations`
- **Root cause:** `.planning/research/PITFALLS.md:179` quoted the scanner's own
  absolute-home-directory trigger examples, so the scanner correctly rejected
  its documentation.
- **Resolution:** Phase-level closeout reworded the prose without changing or
  allowlisting the scanner. The tracked-tree publish-safe gate is green.

## 35-04 (COV-04 sibling decider + real seam)

### FieldName completeness pin was not updated for the sibling vocabulary

- **Discovered during:** 35-04 full-suite phase gate (`.venv/bin/python -m pytest crawler/tests -q`).
- **Failing test:** `crawler/tests/test_extraction_store.py::TestModels::test_field_name_vocabulary_is_complete`
- **Root cause:** the test pins `models.FieldName` to a HARD-CODED `expected` set that
  was NOT extended when 35-03 added the four sibling members
  (`sibling_relationship`, `sibling_status`, `sibling_residence`,
  `sibling_date_of_birth`) to the `FieldName` Literal. `allowed` (now includes the
  sibling fields) therefore no longer equals the stale `expected` set.
- **Resolution:** Phase-level closeout added all four sibling members to the
  completeness pin and reran the extraction-store test.

### Prior-plan `.planning/` prose repeated the scanner trigger examples

- **Discovered during:** 35-04 full-suite phase gate.
- **Failing tests:**
  - `crawler/tests/test_conformance_v40_privacy_containment.py::TestTrackedTreeScansClean::test_publish_safe_main_zero_violations`
  - `crawler/tests/test_full_audit_pii_perimeter.py::TestRepositoryPublishSafe::test_publish_safe_zero_violations`
  - `crawler/tests/test_extraction_pii_perimeter.py::TestRealTreeScansClean::test_tracked_tree_is_clean`
- **Root cause:** the discovery log and plan summary repeated the same rejected
  absolute-home-directory examples while documenting the first failure.
- **Resolution:** Phase-level closeout reworded every active planning artifact.
  No scanner exception or allowlist was added.
