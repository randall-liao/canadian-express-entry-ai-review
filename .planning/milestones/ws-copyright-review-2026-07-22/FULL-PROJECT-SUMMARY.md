# Project-Wide Copyright & Licensing Audit Summary

**Workstream:** `copyright-review`
**Date:** July 21, 2026
**Model Used:** Gemini 3.6 Flash (`gemini-3.6-flash`, long_context)
**Scope:** Full Project Repository (`corpus/`, `crawler/`, `skills/`, `.github/`, `.planning/`, `reports/`, `scripts/`, root files)

---

## Executive Summary

A comprehensive, multi-agent parallel audit of all repository files was conducted using 9 parallel Gemini 3.6 Flash long-context subagents across two phases (Corpus Audit + Full Codebase Audit).

**Overall Audit Result:** **PASS / CLEAN**

---

## Audit Phase 1: Corpus Audit (`corpus/`)

| Agent | Target Scope | Files Audited | Findings & Status |
| :--- | :--- | :---: | :--- |
| `police-copyright-agent` | `corpus/police-certificates` | 229 | **PASS** — 100% IRCC `canada.ca` guidance with Crown Copyright frontmatter attribution. |
| `dli-copyright-agent` | `corpus/dli` | 1,137 | **PASS** — Official IRCC Designated Learning Institutions list & manifest. |
| `noc-copyright-agent` | `corpus/noc-2021` | 376 | **PASS** — Statistics Canada NOC 2021 V1.0 records under StatCan Open Licence. |
| `pdi-guidance-copyright-agent` | `corpus/pr-pdi`, `guidance`, `medical`, `ministerial-instructions` | 115 | **PASS** — IRCC Operational Instructions and guidance; external images hosted on `canada.ca`. |
| `legislation-misc-copyright-age` | `legislation-irpa`, `legislation-irpr`, `biometrics`, `language`, `mi-rounds`, etc. | 22 | **PASS** — Public federal statutes under *Reproduction of Federal Law Order* (SI/97-5) and official PDIs. |

---

## Audit Phase 2: Full Codebase Audit (Non-Corpus)

| Agent | Target Scope | Files Audited | Findings & Status |
| :--- | :--- | :---: | :--- |
| `crawler-copyright-agent` | `crawler/` Python modules, rules, tests, fixtures | ~680 | **PASS with 1 Advisory** — Code & rules 100% MIT/clean. Synthetic downloader has fallback generator for official marks. |
| `skills-github-copyright-agent` | `skills/` & `.github/` agent skills, workflows, definitions | ~478 | **PASS** — Vendor-neutral, open Markdown agent skills and Node.js stdlib gsd-core scripts. |
| `planning-docs-copyright-agent` | `.planning/` & `reports/` planning docs, research, reports | ~425 | **PASS** — Design documents & research. Compliant AGPL quarantine for optional `PyMuPDF`. |
| `root-scripts-copyright-agent` | Project root files, `scripts/`, `dist/`, `build/` | ~25 | **PASS** — Standard MIT License & `NOTICE` file. 0 publish-safety violations on 505 scanned files. |

---

## Conclusion & Actionable Items

1. **Licensing Architecture:** Software code is covered under the permissive **MIT License** (`LICENSE`), while crawled corpus materials are governed by Crown Copyright non-commercial reproduction terms as declared in `NOTICE`.
2. **Publish Safety:** Automated scan via `scripts/check_publish_safe.py` confirmed 0 violations across tracked repository files.
3. **Synthetic Assets Recommendation:** Default to using the offline placeholder generator (`create_placeholder_image` in `crawler/synthetic/downloader.py`) to avoid using real government coat-of-arms images in synthetic test fixtures.
