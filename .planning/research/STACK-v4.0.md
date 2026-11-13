# Stack Research

**Domain:** v4.0 CRS Profile ↔ Document Substantiation Auditor — local applicant-document extraction + local candidate vault  
**Researched:** 2026-07-05  
**Confidence:** MEDIUM (library versions and APIs verified; extraction reliability still needs fixture tests on real report/letter/passport samples)

## Executive Recommendation

Keep the shipped v3.x trust path intact: SQLite FTS5 keyword retrieval, cited grounding gate, JSON envelope, Poetry, `pydantic`, `platformdirs`, and PII separation. For v4.0, add only the minimum local document stack needed to (1) render applicant PDFs/images for visual review, (2) extract structured values deterministically where possible, and (3) store raw PII artifacts in a git-ignored vault.

**Recommended additions:** `pypdfium2` + `Pillow` for local PDF-page/image rendering, keep `pdfminer.six` as the first-tier text extractor, and add `pytesseract` only as an optional local OCR fallback. Do **not** make PyMuPDF a default dependency unless the project explicitly accepts its AGPL/commercial license; it is technically excellent, but license-heavy for an MIT public repo. Do **not** use `pdf2image` as the default because it requires a separate Poppler install outside Poetry.

**Vault recommendation:** use a hybrid vault: raw applicant files and rendered page images live as content-addressed files on disk under a git-ignored vault directory; SQLite stores the small index, CRS profile/factor records, document metadata, extraction runs, extracted values, evidence pointers, and confirmation state. Avoid storing raw PDFs/images as SQLite BLOBs by default.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | existing `>=3.10,<4.0` | Runtime for new vault/extraction CLI verbs | All recommended additions support the existing Python floor. No separate service/runtime needed. |
| SQLite (`sqlite3`) | stdlib; FTS5 already validated | Candidate vault DB (`vault.db`) for profile, document metadata, extracted values, confirmations | Mirrors the corpus DB pattern, is local/offline, needs no server, and keeps structured PII queryable without adding Postgres/DuckDB. |
| `pdfminer.six` | 20260107 | First-tier born-digital PDF text extraction | Already in the stack and pure Python. Use `extract_text(..., laparams=LAParams(...))` before OCR; best for selectable-text PDFs. |
| `pypdfium2` | 5.11.0 | Default PDF-page → image renderer | Best fit for Poetry + non-technical install: prebuilt wheels, no Poppler system dependency, liberal BSD/Apache/dependency licensing, and `page.render(...).to_pil()` for page images. |
| `Pillow` | 12.3.0 | Image file loading, normalization, rendered page handling | Standard Python imaging layer. Use for applicant JPG/PNG/TIFF inputs, rendered PDF pages, resizing/grayscale/contrast pre-processing, and OCR handoff. |
| `pydantic` | 2.13.4 | Typed CRS profile, extracted-value, evidence, and rule-registry models | Reuses existing stack discipline: JSON schemas, validation, and explicit contracts for extracted PII values before the auditor consumes them. |
| `platformdirs` | 4.10.0 | Resolve per-user vault paths for installed CLI users | Keeps PII out of the repo by default for packaged use, while still supporting the existing git-ignored `personal/` path for repo-local development. |
| `typer` | 0.26.8 | CLI verbs for `vault`, `extract`, `confirm`, `audit` | Reuse the existing ordinary-shell-command pattern and JSON envelope; no proprietary CLI tooling. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytesseract` | 0.3.13 | Optional local OCR wrapper over a locally installed Tesseract binary | Only when a document page has little/no embedded text or the input is a scan/photo. Keep behind an `ocr` extra and require explicit local Tesseract installation. |
| `pymupdf` / PyMuPDF | 1.28.0 | Optional high-fidelity PDF text/layout/render fallback | Use only if fixture tests prove `pdfminer.six` + `pypdfium2` are insufficient **and** the AGPL/commercial license is acceptable. Technically strong; not the default. |
| `pdf2image` | 1.17.0 | Optional Poppler-backed PDF rendering fallback | Use only for users who already have Poppler installed or if PDFium rendering fails on specific files. Not default because Poppler is a cross-platform install burden. |
| `sqlite-utils` | 3.39 | Dev/inspection helper for SQLite tables and FTS | Optional developer tool for inspecting vault/corpus DBs. Runtime code should use stdlib `sqlite3` to stay dependency-light. |
| `pyyaml` | existing 6.x | Non-PII CRS rule registry YAML | Reuse existing YAML support if CRS factor rules are stored as repo-safe YAML and compiled/validated into `pydantic` models. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest` | Golden extraction fixtures | Add redacted/synthetic PDFs, page images, OCR text, and expected extracted-value JSON. Reliability claims must be fixture-backed per document type. |
| `ruff` | Lint/format | Existing tool; no change. |
| `pre-commit` + `gitleaks` + publish-safe scanner | PII leak prevention | Extend the guard list to the new vault root, `vault.db*`, `files/`, `pages/`, OCR text caches, and extracted-value exports. |
| `tesseract --version` probe | Optional OCR readiness check | If OCR extra is enabled, fail closed with `missing_dependency` when the binary/language data is absent; do not silently skip. |

## Installation

Use Poetry ranges in `pyproject.toml`; `poetry.lock` records the exact resolved versions.

```bash
# Core v4.0 additions
poetry add "pypdfium2>=5.11,<6.0" "Pillow>=12.3,<13.0"

# Keep / update existing structured-data and PDF-text dependencies if not already locked
poetry add "pdfminer.six>=20260107,<20270000" "pydantic>=2.13,<3.0" "platformdirs>=4.10,<5.0" "typer>=0.26,<0.27"

# Optional OCR extra: requires a local Tesseract binary installed by the user/OS
poetry add --optional "pytesseract>=0.3.13,<0.4.0"

# Optional high-fidelity fallback only if license accepted
poetry add --optional "pymupdf>=1.28,<1.29"

# Optional Poppler fallback only for users who already have Poppler installed
poetry add --optional "pdf2image>=1.17,<2.0"
```

Recommended optional extras:

```toml
[project.optional-dependencies]
doc-extract = ["pypdfium2>=5.11,<6.0", "Pillow>=12.3,<13.0"]
ocr = ["pytesseract>=0.3.13,<0.4.0"]
pymupdf = ["pymupdf>=1.28,<1.29"]
poppler = ["pdf2image>=1.17,<2.0"]
```

## Extraction Stack Decision

### Default pipeline

1. **Ingest raw file into vault.** Copy the original PDF/image into `files/` using a SHA-256 content-addressed name. Store original filename only inside the vault DB (PII-safe because vault is git-ignored).
2. **Extract embedded text first.** For PDFs, run `pdfminer.six` and store page-level raw text, extraction method, and low-level diagnostics in SQLite.
3. **Render pages regardless.** Render every PDF page to a PNG (typically 200 DPI for review, 300 DPI when OCR is needed) with `pypdfium2`; store rendered images under `pages/<document_id>/`.
4. **Extract structured values.** Run document-type-specific, deterministic extractors (regex + simple field heuristics) into `pydantic` models. Store value, document pointer, page number, snippet/bbox when available, extraction method, and confidence.
5. **Use OCR only when needed.** If embedded text is empty/too sparse or the input is an image scan, run local `pytesseract` on the rendered page/image. Store OCR text separately and mark values as OCR-derived.
6. **Mandatory confirmation checkpoint.** Before any CRS auditor consumes values, show the user extracted fields alongside the rendered page/snippet and require confirm/edit/reject. The auditor should treat unconfirmed values as `NEEDS_CONFIRMATION` / `AT-RISK`, never as `SUBSTANTIATED`.

This preserves the v3.x guarantee: rule/admissibility verdicts remain cited and fail-closed, while the one non-grounded step (reading applicant documents) is explicitly confirmed before use.

### PDF text extraction tiers: `pdfminer.six` vs PyMuPDF

| Criterion | `pdfminer.six` 20260107 | PyMuPDF 1.28.0 | Recommendation |
|-----------|--------------------------|----------------|----------------|
| Install footprint | Pure Python; already used | Compiled wheel | Keep `pdfminer.six` as default. |
| License fit | Permissive project fit | Dual AGPL-3.0/commercial per PyPI | Avoid default PyMuPDF dependency in an MIT public project unless accepted deliberately. |
| Text extraction | Good for born-digital PDFs; supports `LAParams` layout tuning | Very fast; strong text/block/word extraction | Start with `pdfminer.six`; add PyMuPDF only if fixture failures justify it. |
| Tables/forms | Text order can be imperfect; not visual | Better layout primitives, still not true semantic table understanding | Render pages and require confirmation for table/form values either way. |
| Rendering | None | Excellent via `page.get_pixmap(dpi=...)` | Use `pypdfium2` as default renderer to avoid AGPL; PyMuPDF renderer only in optional fallback. |
| Scanned PDFs | No OCR | No OCR by itself | Use local Tesseract fallback only for scans/photos. |

### PDF → image rendering options

| Option | Current Version | Strengths | Weaknesses | v4.0 Decision |
|--------|-----------------|-----------|------------|---------------|
| `pypdfium2` | 5.11.0 | Local rendering, prebuilt wheels, no Poppler install, liberal licensing, converts to Pillow via `bitmap.to_pil()` | Lower-level API than PyMuPDF; text extraction less central to our plan | **Default renderer.** Best Poetry/non-technical-user fit. |
| PyMuPDF | 1.28.0 | Excellent all-in-one text/layout/render API (`get_text`, `get_pixmap`) | AGPL/commercial license; compiled dependency | Optional fallback only. |
| `pdf2image` + Poppler | 1.17.0 | Simple API (`convert_from_path`, `convert_from_bytes`); battle-tested Poppler renderer | Requires external Poppler binaries and `poppler_path`/PATH troubleshooting; not Poetry-only | Optional fallback for users who already have Poppler. |

### Lightweight local OCR

OCR is warranted, but only as a fallback:

- **Use:** `pytesseract` 0.3.13 + local Tesseract binary for image-only scans/photos, low text density PDFs, and passport/letter screenshots.
- **Do not use OCR by default:** OCR can hallucinate characters, transpose dates, and misread score tables. Embedded text is usually more reliable for born-digital language/ECA PDFs.
- **Always mark OCR-derived values:** store `method="ocr"`, page image path, OCR config/language, raw OCR text, and require confirmation.
- **Keep OCR local:** no cloud OCR, no cloud vision model, no remote LLM image analysis.

## Vault Model

### Recommended layout

Use files-on-disk for raw/derived binary artifacts and SQLite for the small structured index.

```text
personal/candidate-vault/                 # repo-local default; git-ignored
  .gitignore                              # contains "*"
  vault.db                                # SQLite PII index
  vault.db-wal                            # possible WAL sidecar; also ignored
  vault.db-shm                            # possible WAL sidecar; also ignored
  files/
    ab/cd/<sha256>.pdf                    # immutable raw applicant document
  pages/
    <document_id>/page-001.png            # rendered page cache for visual review/OCR
  exports/
    review-packet/                        # optional local-only confirmation views
```

For packaged installs outside a repo, resolve a default root with:

```python
from platformdirs import user_data_path

vault_root = user_data_path(
    "pr-review-agents",
    "pr-review-agents",
    ensure_exists=True,
) / "candidate-vault"
```

Also support `PR_REVIEW_VAULT_DIR` / `--vault-dir`. At startup, fail closed if the chosen vault path is inside the git worktree but not ignored by `.gitignore`, or if any vault file is tracked by git.

### SQLite schema shape

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `candidate_profile` | Applicant CRS profile snapshot | `id`, `created_at`, `source`, `profile_json`, `confirmed_at` |
| `crs_factor_claims` | Claimed CRS factors/points | `factor_key`, `claimed_value_json`, `claimed_points`, `profile_id`, `confirmed_at` |
| `documents` | Logical document records | `id`, `document_type`, `issuer`, `candidate_label`, `raw_file_id`, `status` |
| `files` | Content-addressed raw files | `id`, `sha256`, `vault_relpath`, `media_type`, `size_bytes`, `original_name`, `ingested_at` |
| `document_pages` | Rendered page cache | `document_id`, `page_no`, `image_relpath`, `dpi`, `renderer`, `width`, `height`, `image_sha256` |
| `extraction_runs` | Reproducibility/audit trail | `id`, `document_id`, `tool_versions_json`, `method`, `started_at`, `completed_at`, `status` |
| `extracted_values` | Structured values read from docs | `id`, `document_id`, `factor_key`, `field_name`, `value_json`, `value_type`, `method`, `confidence`, `page_no`, `snippet`, `bbox_json`, `confirmation_status` |
| `confirmations` | Mandatory user checkpoint | `id`, `extracted_value_id`, `decision`, `corrected_value_json`, `confirmed_at`, `notes` |
| `audit_inputs` | Frozen inputs consumed by auditors | `id`, `factor_key`, `extracted_value_id`, `confirmation_id`, `created_at` |

Use `PRAGMA foreign_keys=ON`, a schema `user_version`, and migrations. WAL is fine for local UX, but remember WAL creates PII sidecar files; keep all `vault.db*` under the ignored vault root.

### Why not store raw PDFs/images as SQLite BLOBs?

SQLite's own BLOB guidance says small BLOBs under roughly 100 KB can be faster in-database, while larger BLOBs are faster as separate files. Applicant PDFs, scans, passports, and rendered pages are usually much larger and need direct visual access by the user/agent. Storing them as files keeps the DB small, makes page images easy to display, simplifies backup/export, and avoids bloating `vault.db`/WAL with multi-MB binaries.

Store only these binary-related facts in SQLite: content hash, vault-relative path, MIME/media type, byte size, page count, rendered image metadata, and evidence pointers.

## Reliability by Document Type

| Document Type | Expected Reliability | Best Extraction Path | Confirmation Focus |
|---------------|----------------------|----------------------|-------------------|
| IELTS/CELPIP/TEF/TCF score reports | High for born-digital PDFs; Medium for scans | `pdfminer.six` text + rendered page review; OCR fallback for scans | test type, report/test date, scores per ability, TRF/registration number, name |
| ECA reports | Medium-High | Text extraction + page image review; handle multiple credentials explicitly | organization, report date/number, Canadian equivalency, credential level |
| Passport | Medium | Image/PDF rendering + OCR fallback; regex MRZ/date patterns if visible | name, DOB, passport number, expiry, country; confirm every value |
| Employment reference letters | Medium-Low | Text extraction/OCR can find dates, hours/week, job title/NOC mentions; no semantic duties/NOC entailment | dates, hours/week, employer, title, NOC/TEER claim, full-time equivalence; mark ambiguity `AT-RISK` |
| Provincial nomination letters | Medium | Text extraction + rendered page review | province, nomination certificate/stream, issue/expiry dates, applicant identifiers |
| Job offer / arranged employment letters | Medium-Low | Text extraction + page review; deterministic extraction only for explicit fields | employer, job title, NOC/TEER, start date, hours, duration/indeterminate status |
| Education proof / Canadian study docs | Medium | Text extraction + page review | institution, credential, program length, completion/award date |

The roadmap should include fixture-driven acceptance tests per document family before claiming automation is reliable.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `pypdfium2` for rendering | PyMuPDF | If the project accepts AGPL/commercial licensing and wants a single high-fidelity PDF engine for both text and rendering. |
| `pypdfium2` for rendering | `pdf2image` + Poppler | If a user's environment already has Poppler installed and PDFium fails on a specific PDF. |
| `pdfminer.six` for default text | PyMuPDF text extraction | If real fixtures show pdfminer text order/table extraction is inadequate and license is accepted. |
| `pytesseract` optional OCR | OCRmyPDF | If the goal becomes adding searchable text layers to scanned PDFs, not just extracting fields. Too heavy for the MVP default. |
| stdlib `sqlite3` vault | `sqlite-utils` runtime | Use `sqlite-utils` only for developer inspection/scaffolding; raw `sqlite3` is enough and lighter for shipped CLI. |
| Files-on-disk + SQLite metadata | SQLite BLOBs for raw documents | Only for tiny generated thumbnails/snippets under ~100 KB; not for applicant PDFs/images/pages. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Cloud OCR APIs (Google Vision, Azure Form Recognizer, AWS Textract, Adobe Extract) | Sends applicant PII/documents off-machine and violates the no-cloud constraint. | Local rendering + local `pdfminer.six`; optional local Tesseract fallback. |
| Cloud LLM/vision APIs for reading page images | Same PII leak; also breaks reproducibility and CLI-agnosticism. | Render page images locally and require confirm-what-I-read before audit. |
| Vector DBs / embeddings / local semantic retrieval for the corpus or vault | Explicitly out of scope; adds heavy deps and weakens citation discipline. | Existing SQLite FTS5 keyword retrieval + grounded gate. |
| Heavy ML OCR/layout stacks (`PaddleOCR`, `EasyOCR`, `docTR`, large `opencv` pipelines) | Large installs, model downloads, GPU/CPU surprises, more PII surface. | Optional Tesseract only when text extraction fails. |
| `docling` / PyMuPDF4LLM as default | Powerful but much heavier and aimed at general document conversion/LLM workflows. | Purpose-built extractors per document type using text + rendered page evidence. |
| Raw PDFs/images as SQLite BLOBs | Multi-MB PII bloats DB/WAL and makes visual review/export harder. | Content-addressed files on disk + SQLite metadata. |
| Storing applicant vault data in `corpus/` or the corpus index DB | Mixes PII with shareable authoritative sources and violates the project boundary. | Separate candidate vault directory and `vault.db`. |
| Proprietary per-CLI image/vision tooling as the source of truth | Breaks CLI-agnostic portability. | Ordinary CLI verbs that emit the existing JSON envelope and local file paths. |
| Pre-ITA CRS scoring/optimization engines | v4.0 is substantiation of claimed factors after ITA, not score optimization. | Presence/value/admissibility audit against confirmed extracted values and cited rules. |

## Stack Patterns by Variant

**If the document is a born-digital PDF:**
- Use `pdfminer.six` for text and `pypdfium2` for page images.
- Because embedded text is usually cleaner than OCR, while page images support visual confirmation and table/form review.

**If the document is a scan/photo or embedded text is too sparse:**
- Render/open with `pypdfium2`/`Pillow`, then run optional `pytesseract`.
- Because OCR should be local and explicit, with values marked as OCR-derived and confirmation-required.

**If table/form extraction is unreliable:**
- Do not add heavy table ML. Store rendered page evidence, extract only obvious values, and force confirm/edit.
- Because false confidence is worse than a manual checkpoint for immigration documents.

**If PyMuPDF is accepted later:**
- Use it as a single optional PDF backend (`get_text`, `get_pixmap`) behind a backend interface.
- Because it may simplify difficult PDFs, but the default stack should remain license-light.

**If the vault is used from a packaged install rather than a repo checkout:**
- Resolve the default path with `platformdirs.user_data_path(...)`.
- Because PII should not depend on the current working directory and should never be written into the shareable repo unless explicitly under ignored `personal/`.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `pypdfium2` 5.11.0 | Python `>=3.6`; project `>=3.10,<4.0` | Fits current Python range; recommended default renderer. |
| `Pillow` 12.3.0 | Python `>=3.10` | Fits current Python range; needed by `pypdfium2` image handoff and OCR workflows. |
| `pdfminer.six` 20260107 | Python `>=3.10` | Fits current Python range; pure-Python text extractor. |
| `pytesseract` 0.3.13 | Python `>=3.8` + local Tesseract binary | Python package is light, but OCR will fail unless the system binary/language data are installed. |
| PyMuPDF 1.28.0 | Python `>=3.10`; AGPL/commercial | Technically compatible; license decision required before default use. |
| `pdf2image` 1.17.0 | Poppler `pdftoppm`/`pdftocairo` in PATH or `poppler_path` | Python package is light; system dependency is the support burden. |
| `platformdirs` 4.10.0 | Python `>=3.10` | Use `user_data_path(..., ensure_exists=True)` for non-repo vault roots. |
| `sqlite-utils` 3.39 | Python `>=3.10` | Optional dev dependency only. |

## Sources

- Project context and constraints: `.planning/PROJECT.md`, `.planning/research/STACK.md`, `.planning/notes/crs-claim-substantiation-auditor.md`, `.planning/seeds/crs-claim-substantiation-auditor.md`, `.planning/research/questions.md`, `crawler/CONTRACT.md`.
- PyPI metadata verified 2026-07-05/06: `pypdfium2` 5.11.0, `Pillow` 12.3.0, `pdfminer.six` 20260107, PyMuPDF 1.28.0, `pdf2image` 1.17.0, `pytesseract` 0.3.13, `platformdirs` 4.10.0, `sqlite-utils` 3.39, `pydantic` 2.13.4, `typer` 0.26.8.
- Context7 / official docs fetched: PyMuPDF `get_pixmap` and `get_text`; `pdfminer.six` `extract_text` and `LAParams`; `pdf2image` `convert_from_path` / Poppler wrapper; `pytesseract` `image_to_string` and `tesseract_cmd`; `platformdirs` `user_data_path`; `sqlite-utils` table/FTS helpers; `pypdfium2` `page.render(...).to_pil()`; Pillow image operations.
- SQLite official docs: "Internal Versus External BLOBs in SQLite" and "35% Faster Than The Filesystem" for BLOB/files-on-disk tradeoffs.

---
*Stack research for: v4.0 local applicant-document extraction and candidate vault*
*Researched: 2026-07-05*
