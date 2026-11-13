# Phase 56 Plan: Agent-Driven Realistic Defective Data Generation Engine

## Goal
Implement an agent-driven realistic defective data generator in `crawler/synthetic/` supporting realistic defect classes: `incomplete_translation`, `no_translation`, `missing_required_info`, `expired_credential`, and `date_mismatch` across all 23 Express Entry document types, outputting paired vector PDFs, 300 DPI scanned PDFs, and ground truth JSON schemas into git-ignored `crawler/eval/test_data/`.

## Requirements
- `AGENT_GEN-01`: Agent-driven synthetic document generator creates realistic defective PDF test fixtures covering incomplete translation, missing translation, missing required info, expired credentials, and date mismatches for all 23 Express Entry document types.
- `AGENT_GEN-02`: All agent-generated test cases produce paired vector PDFs, 300 DPI scanned PDFs, and ground truth JSON schemas stored in git-ignored `crawler/eval/test_data/`.

## Tasks
1. Extend `crawler/synthetic/defects.py` to add new defect categories: `INCOMPLETE_TRANSLATION`, `NO_TRANSLATION`, and `MISSING_REQUIRED_INFO`.
2. Update `crawler/synthetic/generator.py` and `templates.py` to render realistic text layouts for foreign language documents (no translation) and incomplete translator affidavits.
3. Update `crawler/synthetic/generate_test_dataset.py` to generate agent-driven defective fixtures (`defective_translation`, `defective_missing_info`, `defective_expired`) for all 23 document types (vector + 300 DPI scanned).
4. Run `generate_test_dataset.py` to generate the test fixtures in `crawler/eval/test_data/`.
5. Update `crawler/tests/test_multi_case_synthetic.py` and verify all fixtures exist and pass validation.

## Verification
Run `.venv/bin/python -m pytest crawler/tests/test_multi_case_synthetic.py -q`
