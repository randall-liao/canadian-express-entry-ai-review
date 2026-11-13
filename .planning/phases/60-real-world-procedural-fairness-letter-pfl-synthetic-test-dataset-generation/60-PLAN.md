# Phase 60 Plan: Real-World Procedural Fairness Letter (PFL) Synthetic Test Dataset Generation

## Goal
Implement a real-world Procedural Fairness Letter (PFL) defect generator in `crawler/synthetic/` supporting IRCC refusal classes: `pfl_lump_sum_funds`, `pfl_noc_duty_mismatch`, `pfl_undeclared_refusal`, `pfl_police_cert_gap`, and `pfl_incomplete_translation` across all 23 Express Entry document types, outputting paired vector PDFs, 300 DPI scanned PDFs, and ground truth JSON schemas into git-ignored `crawler/eval/test_data/`.

## Requirements
- `PFL_GEN-01`: Synthetic document generator creates realistic Procedural Fairness Letter (PFL) test cases covering unexplained lump-sum deposits without gift deeds (`pfl_lump_sum_funds`), NOC lead duty mismatches (`pfl_noc_duty_mismatch`), undeclared visa refusals (`pfl_undeclared_refusal`), foreign police cert coverage gaps (`pfl_police_cert_gap`), and incomplete translations (`pfl_incomplete_translation`) across all 23 Express Entry document types.
- `PFL_GEN-02`: All PFL test cases produce paired vector PDFs, 300 DPI scanned PDFs, and ground truth JSON schemas stored in git-ignored `crawler/eval/test_data/`.

## Tasks
1. Extend `crawler/synthetic/defects.py` to add PFL defect categories: `PFL_LUMP_SUM_FUNDS`, `PFL_NOC_DUTY_MISMATCH`, `PFL_UNDECLARED_REFUSAL`, `PFL_POLICE_CERT_GAP`, and `PFL_INCOMPLETE_TRANSLATION`.
2. Update `crawler/synthetic/generate_test_dataset.py` to generate PFL synthetic test cases for all 23 document types (vector + 300 DPI scanned).
3. Execute `generate_test_dataset.py` to generate the PFL test fixtures in `crawler/eval/test_data/`.
4. Update `crawler/tests/test_multi_case_synthetic.py` and verify all fixtures exist and pass validation.

## Verification
Run `.venv/bin/python -m pytest crawler/tests/test_multi_case_synthetic.py -q`
