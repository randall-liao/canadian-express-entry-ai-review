# Phase 64 Plan: Observable Synthetic Defect Mutators & Opaque Blind Fixtures Engine

## Goal
Upgrade the synthetic document generator in `crawler/synthetic/` so every defect mutation causes observable document text changes, and save test fixtures as opaque blind files (`case_001.pdf`, `case_002.pdf`) in `crawler/eval/test_data/` with ground truth metadata strictly isolated in `crawler/eval/ground_truth/`.

## Requirements
- `BLIND_DATA-01`: Synthetic generator creates observable document text mutations for all defect categories (`pfl_lump_sum_funds`, `pfl_noc_duty_mismatch`, `pfl_undeclared_refusal`, `pfl_police_cert_gap`, `pfl_incomplete_translation`, `expired_credential`, `missing_mandatory_field`) across all 23 Express Entry document types.
- `BLIND_DATA-02`: Test fixtures use opaque case IDs (`case_001.pdf`, `case_002.pdf`) without revealing defect types in filenames, with ground truth specs stored in separate `crawler/eval/ground_truth/`.

## Tasks
1. Update `crawler/synthetic/generator.py` and `defects.py` to ensure every defect mutation modifies the document raw text and fields deterministically.
2. Update `crawler/synthetic/generate_test_dataset.py` to write opaque blind PDF filenames (`case_001.pdf`, `case_002.pdf`) to `crawler/eval/test_data/` and store paired ground truth specs in `crawler/eval/ground_truth/case_001.json`.
3. Run `generate_test_dataset.py` to generate the blind dataset.
4. Update `crawler/tests/test_multi_case_synthetic.py` and verify all blind fixtures and ground truth specs exist and pass validation.

## Verification
Run `.venv/bin/python -m pytest crawler/tests/test_multi_case_synthetic.py -q`
