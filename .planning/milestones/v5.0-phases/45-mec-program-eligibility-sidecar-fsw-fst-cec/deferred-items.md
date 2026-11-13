# Deferred Items

- `crawler/tests/test_conformance_v5_study_no_false_green.py::TestRuntimeReadOnlyAndFrozenPins::test_source_dependency_lock_and_network_surfaces_are_frozen`
  still pins the pre-45-02 SHA-256 for `crawler/study_review.py`. Plan 45-02
  intentionally added injected-snapshot read-only composition to that file. The
  stale Phase-44 source pin is outside Plan 45-03's file surface and should be
  advanced by the Phase 45 conformance plan after its frozen-surface review.
