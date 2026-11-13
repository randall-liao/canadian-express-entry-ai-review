# Stack Research

**Domain:** v4.1 CRS Auditor Hardening & Remediation — close fail-closed coverage/operational gaps in the shipped v4.0 substantiation auditor, then derive grounded private remediation checklists + an opt-in, explicitly-redacted lawyer/RCIC review packet inside the local candidate vault
**Researched:** 2026-07-17
**Confidence:** HIGH (this is a hardening milestone over an already-shipped, 714-test stack; every capability maps to existing modules/data — no new library APIs to verify)

## Executive Recommendation

**Add nothing. Ship v4.1 on the exact stack that shipped v4.0.** Every one of the five v4.1 capability areas is pure Python code and/or corpus-grounded YAML data over primitives that already exist, are already tested, and are already inside the PII/publish-safe perimeter:

| v4.1 capability | Realized as | New dependency? |
|-----------------|-------------|-----------------|
| Higher-CLB first-language **points** grounding | New grounded `points_by_level` rows in `crawler/data/crs_rules/core.yaml` (pyyaml + pydantic v2 registry) consumed by `crawler/auditors/core.py::_grounded_points` | **No** |
| Confirmed **sibling-relationship** evidence | Additive `PRAGMA user_version` vault-schema field + extraction field-vocabulary entry (`crawler/testtypes.py` pattern) + `crawler/auditors/additional.py::decide_sibling` | **No** |
| Clean **missing/corrupt-index** refusal surface | Reuse `auditor.AuditGroundingError` + stdlib `sqlite3` read-only preflight; map to a stable fail-closed refusal in `crawler/cli.py` instead of the catch-all `internal_error` | **No** |
| **Example / conformance fixture** alignment | Correct `personal.example/crs-profile.example.yaml`; extend `crawler/tests/test_conformance_v40_*.py` (pytest) | **No** |
| Grounded **remediation checklist** | New `crawler/remediation.py` deriving actions from existing `PrivateFactorCard` verdicts + `rule_citation_ids`, resolving citation text via `searchindex.resolve`, rendered vault-only with f-strings | **No** |
| Opt-in **redacted review packet** | New `crawler/review_packet.py` reusing the two-tier down-projection pattern (`models/audit.py::to_public_envelope`), staged under a new `output/review-packet/` vault subtree, gated by `scripts/check_publish_safe.py:scan_text` | **No** |

The v4.0 milestone already proved the hard parts of this stack (local PDF render/extract, SQLite/FTS5 grounding gate, two-tier PII firewall, publish-safe allow-list, deterministic CRS math). v4.1 is a **coverage + operational + output-surface** milestone, not a new-technology milestone. The single most valuable "stack decision" here is the discipline of **not** adding a PDF engine, a templating engine, a CLI framework, an encryption library, or a PII/NER scrubber — each of which is a plausible-but-wrong instinct for "remediation checklist" and "redacted export packet," and each of which would break a standing constraint.

**Frozen trust path is preserved.** Remediation and the review packet derive **only** from verdicts that were already grounded through the shipped `search` → `--cite` → grounding gate → JSON envelope path. They introduce **no new grounding, no re-scoring, and no second advice path** — they re-render facts the auditor already produced and cited.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | existing `>=3.10,<4.0` | Runtime for all new v4.1 code (registry rows, remediation, packet, refusal hardening) | No capability in this milestone needs a newer floor or a new runtime. |
| SQLite (`sqlite3`) | stdlib; FTS5 already validated | Vault store for the additive sibling-evidence field, audit-trail rows, remediation/packet provenance; corpus index the refusal-hardening preflight probes | Mirrors every prior milestone; local/offline; additive `PRAGMA user_version` migration is the established pattern (schema v2/v3 already shipped). |
| `pydantic` | 2.13.4 (pydantic-core 2.46.4) | Typed boundary models for remediation items and the redacted-packet tier; extends the existing `models/audit.py` two-tier discipline (`extra="forbid"`, `Literal` enums, `ev_`-rejecting validators) | The PII firewall is *structural* here — the packet's redacted tier is a new `extra="forbid"` model that cannot physically hold a raw applicant value or `ev_` pointer, exactly like `PublicAuditEnvelope`. |
| `pyyaml` | 6.0.3 | Source format for the new higher-CLB grounded rule rows and the corrected example profile | The CRS rule registry is already PII-free repo-safe YAML compiled into pydantic rows; higher-CLB points are more rows, not new machinery. |
| `platformdirs` | 4.10.0 | Resolve the vault root for packaged installs so remediation/packet artifacts land under the git-ignored vault, never the CWD/repo | Already the shared `crawler/paths.py` fallback; the new `output/review-packet/` subtree inherits it unchanged. |
| `argparse` | stdlib | New CLI verbs (`vault remediate`, `vault export-review` or equivalent) | **The shipped CLI is a thin stdlib `argparse` tree, not typer.** New verbs must extend the existing `vsub.add_parser(...)` subtree and emit the frozen five-key `--json` envelope. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `hashlib` (`sha256`) | stdlib | Content-addressing / provenance ids for packet + remediation artifacts, staleness keys | Reuse the existing five-key staleness + content-addressing scheme; no new hashing dep. |
| `json` | stdlib | Machine-readable remediation + packet artifacts alongside the human markdown | Matches the shipped `audit_report.py` pattern (`<run_id>.json` + `<run_id>.md`). |
| `pypdfium2` / `Pillow` / `pdfminer.six` | 5.11 / 12.3 / 20260107 (existing `doc-extract` extra) | Only relevant to the *extraction-regression hardening* sub-goal (more adversarial low-quality/ambiguous fixtures) | No version change; add fixtures + tests, not code paths or deps. Stays an OPTIONAL extra. |
| `pytesseract` | 0.3.13 (existing `ocr` extra) | Same — adversarial scan/OCR regression fixtures only | Unchanged; remains behind the `ocr` extra with a local Tesseract binary. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest` (+ `conformance` marker) | Extend the v4.0 release-gate suite (`test_conformance_v40_*.py`) to cover CLB-10 points, sibling evidence, the clean refusal surface, and packet redaction (no PII/`ev_`/raw-doc leakage) | The release gate is `scripts/run_conformance.py`; new proofs must be non-vacuous and marker-registered. No new test dependency. |
| `scripts/check_publish_safe.py` | Extend `VAULT_SUBTREES` with `output/review-packet/` (and `output/remediation/`) so the new artifact types are inside the publish-safe allow-list; gate rendered packet/checklist text through `scan_text` before it is written | This is the RPT-03 share-safety gate already reused by `dupaudit`/`dupclean`/checklist; the packet's redacted body must pass it. |
| `ruff` | Lint/format | Existing; no change. |
| `pre-commit` + `gitleaks` | PII leak prevention on the tracked tree | `personal/` + `*.sqlite*` + vault subtree ignores already block the new artifacts; verify the new subtree names are covered. |

## Installation

**No `poetry add`. No `pyproject.toml` dependency change. No `poetry.lock` churn for a new package.** v4.1 ships on the locked graph as-is:

```bash
# Nothing to install for the core hardening/remediation/packet work.
poetry install

# The extraction-regression sub-goal exercises the ALREADY-DECLARED optional extras:
poetry install --extras "doc-extract"      # pypdfium2 + Pillow + pdfminer.six (existing)
poetry install --extras "ocr"              # pytesseract (existing; needs local Tesseract)
```

The only `pyproject.toml` edits that may be justified are **non-dependency**: registering a new pytest marker if the conformance suite grows a v4.1 sub-marker, and (optionally) a new `[project.scripts]`-adjacent console verb — both are metadata, not packages.

## Integration Points (where v4.1 code lands)

| Capability | Primary module(s) | Data / seam it reuses | Fail-closed guarantee preserved |
|------------|-------------------|-----------------------|---------------------------------|
| Higher-CLB first-language points | `crawler/data/crs_rules/core.yaml` (`core.language.first.points`), `crawler/crs_rules.py` (validation), `crawler/auditors/core.py::_grounded_points` | Grounded `points_by_level` rows with real `chunk_id#ordinal` citations + verbatim quotes; `no_inlined_volatile_rules` static gate | A CLB-10 candidate currently gets `SUBSTANTIATED` with `substantiated_points=None` (fail-closed, never fabricated); grounding the CLB-10 rows makes the points *complete*, not *invented*. |
| Sibling-relationship evidence | vault schema (additive `PRAGMA user_version` bump), `crawler/testtypes.py`-style field vocabulary, `crawler/extraction.py`, `crawler/auditors/additional.py::decide_sibling` | Field-level confirm/correct/reject + five-key staleness; `is_audit_eligible` choke point | Absent/unconfirmed sibling evidence stays a truthful `GAP` (as today); only a confirmed, audit-eligible relationship chain can lift it. |
| Clean missing/corrupt-index refusal | `crawler/searchindex.py` (read-only preflight), `crawler/auditor.py` (`AuditGroundingError`), `crawler/cli.py::_cmd_vault_audit` + `main()` | The shipped `AuditGroundingError` already writes ZERO artifacts (SC5); read-only `mode=ro` open raises an explicit `OperationalError` on a missing DB | Replaces the catch-all `internal_error`/exit 4 with a stable, PII-free refusal (reuse `INVALID_INPUT`/exit 2 or a clearly-labeled grounding-unavailable reason_code); still no partial report. |
| Example/conformance alignment | `personal.example/crs-profile.example.yaml`, `crawler/tests/test_conformance_v40_*.py` | Grid factor-ids used by the auditors; the real extract→confirm→audit seam test | Fixtures must match the real factor grid so the "no false green" proofs stay non-vacuous. |
| Grounded remediation checklist | new `crawler/remediation.py` + `vault remediate` verb | `PrivateAuditReport`/`PrivateFactorCard` (`verdict`, `reason_code`, `rule_citation_ids`), `searchindex.resolve` for cited text | Derives next-actions ONLY from existing grounded verdicts + citations; vault-only markdown/JSON; no new grounding, no legal advice, no volatile-rule inlining. |
| Redacted review packet | new `crawler/review_packet.py` + `vault export-review` verb; new `output/review-packet/` subtree | Two-tier down-projection like `to_public_envelope`; `resolve_within` path guard; `check_publish_safe.scan_text` | Redacted-by-construction tier (`extra="forbid"`, no `ev_`/raw value); **raw documents excluded by default (opt-in flag required)**; staged only inside the git-ignored vault. |

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Markdown + JSON packet (f-string render, like `audit_report.py`) | `reportlab` / `weasyprint` / `pandoc` PDF export | Only if a downstream reviewer contractually requires a signed PDF *and* the operator accepts a heavy/native dependency. A reviewer can convert the redacted markdown themselves; defer PDF to a later opt-in extra if ever demanded. |
| f-string / line-join rendering (shipped pattern) | `jinja2` templating | Never for core — `jinja2` is present in the lock ONLY transitively via the optional `crawl` extra (`litellm`); adopting it promotes a heavy optional extra to a hard runtime requirement. |
| stdlib `argparse` verbs | `typer` / `click` | Never — the shipped CLI is argparse; `typer`/`click` exist in the lock ONLY via the optional `crawl` extra (`crawl4ai`/`huggingface-hub`). Reusing them for core CLI would silently make the crawl extra mandatory. |
| Vault git-ignore + structural redaction | Encrypting the packet (`cryptography` / `age` / `python-gnupg` / `pynacl`) | Only if the operator will transmit the packet OFF-machine through an untrusted channel. Inside the local, git-ignored vault the file is already access-controlled; encryption adds key-management burden and a false sense of "safe to share raw." Keep as a documented future opt-in, not a default. |
| Allow-list redaction + `scan_text` denylist gate | `presidio` / `scrubadub` / spaCy-NER PII scrubbing | Never — NER-based scrubbing is a *model*, violating the no-model/no-vector/no-cloud constraint, and it is *fail-open* (misses become leaks). The redacted tier must be allow-list/`extra="forbid"` (deny-by-default), not detect-and-remove. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| A PDF generation library (`reportlab`, `weasyprint`, `fpdf2`, `pandoc`) as a v4.1 default | Native/heavy dependency for a cosmetic output format; the reviewer can convert markdown | Vault-only markdown + JSON, gated by `check_publish_safe.scan_text` (matches `audit_report.py`). |
| `jinja2` / any templating engine | Only transitively available via the optional `crawl` extra; not a core dep | Existing f-string / `"\n".join(lines)` rendering used by `audit_report._render_factor_card_markdown`. |
| `typer` / `click` for the new CLI verbs | Only transitively available via the optional `crawl` extra; shipped CLI is stdlib argparse | Extend the `argparse` subparser tree (`vsub.add_parser(...)`) and emit the frozen five-key envelope. |
| Encryption / secret-management libs by default (`cryptography`, `age`, `gnupg`, `pynacl`) | Key management + "encrypted so it's safe to include raw docs" is an anti-pattern for this milestone; the packet is redacted-by-construction and vault-local | Structural redaction + `--include-raw` opt-in that is OFF by default and still vault-staged. |
| PII/NER scrubbing libs (`presidio`, `scrubadub`, spaCy) | Requires a model (breaks no-model/no-cloud/no-vector); fail-open detection turns misses into leaks | Deny-by-default allow-list tier (`extra="forbid"`) + the existing `scan_text` denylist as a belt-and-suspenders gate. |
| A new `contract.py` error *type* for grounding failures | The `--json` envelope error-type set (`invalid_input`/`missing_dependency`/`internal_error`) is a stable machine contract | Reuse `INVALID_INPUT` (exit 2) via `AuditGroundingError`, differentiating with a precise, PII-free `reason_code`/message; keep the frozen error-type vocabulary. |
| Storing packet/remediation artifacts anywhere but the vault | Any path outside `candidates/<id>/output/...` risks PII in the repo/corpus | `paths.resolve_within(vault.root, "output", ...)`; extend `VAULT_SUBTREES`. |
| Re-grounding or re-scoring inside remediation/packet code | Would create a second, unaudited trust path | Consume the ALREADY-grounded `PrivateFactorCard` verdicts + `rule_citation_ids`; resolve cited text read-only via `searchindex.resolve`. |
| Cloud OCR / cloud LLM / vector index (any) | Frozen constraints; applicant PII must never leave the machine | Local `pdfminer.six`/`pypdfium2` + optional local Tesseract; SQLite FTS5 keyword grounding only. |

## Stack Patterns by Variant

**If the review packet must exclude raw documents (default):**
- Emit a redacted-tier pydantic model (`extra="forbid"`, no `ev_`, no raw value) + human markdown, gated through `check_publish_safe.scan_text`.
- Because redaction must be deny-by-default and structurally impossible to bypass, not a best-effort scrub.

**If the operator explicitly opts into including raw documents (`--include-raw`):**
- Copy the content-addressed raw files into the packet subtree *inside the vault only*, still git-ignored, still never on stdout.
- Because inclusion is an applicant-controlled exception; it must never widen the public/stdout surface.

**If the corpus index is missing or corrupt at audit/remediation time:**
- Preflight the read-only `mode=ro` open + a cheap `resolve` probe; on failure raise `AuditGroundingError` and refuse with a stable reason_code, writing zero artifacts.
- Because a grounding prerequisite failure is a fail-closed refusal, not an `internal_error` traceback.

**If a CLB-10 (or higher) first-language candidate is audited:**
- Ground the higher-CLB `points_by_level` rows in `core.yaml` with real citations + verbatim quotes; the auditor then returns complete `substantiated_points`.
- Because points must be grounded-or-`None`, never fabricated to fill the gap.

**If sibling evidence is claimed:**
- Require a confirmed, audit-eligible relationship+status+residence chain via the additive vault field; absent it, stay `GAP`.
- Because the `is_audit_eligible` choke point and field-level confirmation must gate every new evidence type identically.

## Version Compatibility

| Package | Version (locked) | Compatible With | Notes |
|---------|------------------|-----------------|-------|
| `pydantic` | 2.13.4 | Python `>=3.10,<4.0`; `pydantic-core` 2.46.4 | New boundary models reuse the shipped v2 idioms (`ConfigDict(extra="forbid")`, `Literal`, `field_validator`). |
| `pyyaml` | 6.0.3 | Python `>=3.10` | Higher-CLB rows + corrected example profile are plain YAML compiled into pydantic rows. |
| `platformdirs` | 4.10.0 | Python `>=3.10` | Vault-root resolution for the new `output/review-packet/` subtree is unchanged. |
| SQLite / `sqlite3` | stdlib (FTS5) | Python `>=3.10` | Additive `PRAGMA user_version` migration for the sibling field follows the shipped schema-v2/v3 pattern. |
| `pypdfium2` / `Pillow` / `pdfminer.six` | 5.11 / 12.3 / 20260107 | project `>=3.10,<4.0` | Unchanged; touched only by extraction-regression fixtures under the `doc-extract` extra. |
| `pytesseract` | 0.3.13 | Python `>=3.8` + local Tesseract | Unchanged; `ocr` extra only. |

**Transitive-only packages that must NOT be treated as available for core runtime:** `typer`, `click`, `jinja2` (via the optional `crawl` extra → `crawl4ai`/`huggingface-hub`/`litellm`), and `cryptography` (via the `doc-extract` extra → `pdfminer.six`/`pyopenssl`). Relying on any of them in core code would silently promote a heavy optional extra to a hard dependency.

## Sources

- Project + milestone context: `.planning/PROJECT.md` (v4.1 goal, constraints, Key Decisions), `.planning/STATE.md` (Phase 29–34 decisions, blockers/concerns, deferred items), `.planning/milestones/v4.0-MILESTONE-AUDIT.md` (tech-debt: CLB-10 points, sibling GAP, missing/corrupt-index `internal_error`, example-profile factor-ids), `.planning/milestones/v4.0-REQUIREMENTS.md` (LATER-05 fix checklist + redacted export), `.planning/research/STACK-v4.0.md` (shipped extraction/vault stack). — HIGH
- Code inspected (integration points + no-new-dep confirmation): `pyproject.toml` + `poetry.lock` (locked graph; transitive-only typer/jinja2/click/cryptography), `crawler/cli.py` (stdlib argparse tree; `_cmd_vault_audit`; `main()` `internal_error` catch-all), `crawler/audit_report.py` (vault-only fail-closed writer; `SCREENING_NOTICE`; f-string rendering), `crawler/models/audit.py` (two-tier PII firewall; `to_public_envelope`; `extra="forbid"`; `ev_`/absolute-path validators), `crawler/auditor.py` (`AuditGroundingError`, zero-artifact ordering), `crawler/searchindex.py` (read-only `mode=ro` open, explicit `OperationalError`, fail-closed `resolve`), `crawler/auditors/core.py` (`_grounded_points`), `crawler/auditors/additional.py` (`decide_sibling` GAP), `crawler/data/crs_rules/core.yaml` (`core.language.first.points` — CLB 9 only), `scripts/check_publish_safe.py` (`VAULT_SUBTREES`/`VAULT_ARTIFACT_EXTS` allow-list). — HIGH
- PyPI/stdlib version cross-check via `poetry.lock`: pydantic 2.13.4 / pydantic-core 2.46.4, pyyaml 6.0.3, platformdirs 4.10.0; project Python floor `>=3.10,<4.0`. — HIGH

---
*Stack research for: v4.1 CRS Auditor Hardening & Remediation (reuse-first; zero new runtime dependencies)*
*Researched: 2026-07-17*
