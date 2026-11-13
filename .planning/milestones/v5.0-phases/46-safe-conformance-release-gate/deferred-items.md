# Deferred Items

- **Pre-existing Phase 46-01 collection regression:** `crawler/tests/test_conformance_v5_mec_no_false_meets.py` imports `_MEC_MODULES` from `crawler/tests/test_crs_no_inlined_rules.py`, but commit `f5a4185` removed that exported name. The Plan 46-02 independent matrix passes; the unchanged donor-suite verification cannot collect until the Phase 46-01 owner restores or updates the compatibility contract.
