---
phase: 38-redacted-professional-review-packet
reviewed: 2026-07-17T13:33:28Z
depth: deep
files_reviewed: 8
files_reviewed_list:
  - crawler/review_packet.py
  - crawler/remediation.py
  - crawler/vault.py
  - crawler/cli.py
  - scripts/check_publish_safe.py
  - crawler/tests/test_review_packet.py
  - crawler/tests/test_review_packet_cli.py
  - crawler/tests/test_review_packet_conformance.py
findings:
  critical: 1
  warning: 2
  info: 2
  total: 5
status: resolved
resolution:
  blocker_fixed: 1
  warning_fixed: 2
  info_addressed: 0
  note: "CR-01 (per-document staging left a partial packet + abs-path leak on a missing backing file) fixed — all included document bytes are READ before any write and an OSError/PathEscape fails closed as reason=document_unreadable (zero artifacts). WR-01 (missing github_pat/Slack/generic-credential secret shapes) added to _LEAK_PATTERNS. WR-02 (duplicate --include-document double-count/negative excluded) fixed by order-preserving de-dupe. New regression tests: missing-file fail-closed + duplicate-dedupe. Info items advisory."
---

# Phase 38: Code Review Report — Redacted Professional Review Packet

**Reviewed:** 2026-07-17T13:33:28Z
**Depth:** deep (cross-file: review_packet ↔ remediation ↔ vault ↔ cli ↔ paths, plus contract)
**Files Reviewed:** 8 (3 new source, 3 modified source, 2 new test)
**Status:** issues_found

## Summary

The change set for `vault review-packet` is, for the most part, carefully built: the
closed-allowlist models (`PacketFinding`/`PacketCitation`/`ReviewPacket`) enforce the
PKT-02 structural firewall correctly (no `candidate_id`, no `evidence_ids` field,
`extra="forbid"`, `ev_` rejected in `citation_id`); `build_packet` is pure and drops
`ev_`; SQL in `list_candidate_documents`/`get_candidate_document` is parameter-bound and
candidate-scoped (no injection, no cross-candidate resolution); the `_build_checklist_for_run`
refactor is behavior-identical to the old inline path (`_run_row` was unused before and
after); `dry_run` truly writes nothing (verified: no `mkdir`); and the render-then-scan
runs BEFORE any `mkdir`/write, leaving zero artifacts on a `rendered_leak`.

However, the **per-document staging block (PKT-03) is not fail-closed** and breaks two
FROZEN constraints when the opted-in document's physical file is missing/unreadable — it
leaves a partial packet on disk AND leaks an absolute filesystem path to `--json` stdout.
This is confirmed empirically and is a BLOCKER. Two additional WARNING-level defects
(an incomplete secret-leak scan that under-delivers on its own "mirrors check_publish_safe"
claim, and duplicate `--include-document` corrupting the redaction manifest into negative
counts) are also confirmed empirically.

All 27 Phase-38 tests pass — but none exercise the missing-file staging path, so CR-01 is
latent.

## Critical Issues

### CR-01: Document staging writes AFTER the packet and is not exception-safe — leaves a partial artifact and leaks an absolute path to stdout

**File:** `crawler/review_packet.py:314-335` (staging loop 328-335; packet write 320-326)
**Constraints violated:** "fail-closed refusals write zero artifacts" AND "stdout PII-light (no absolute path)" — both FROZEN.

**Issue:**
The order of operations is: render-then-scan (317) → write `pkt_*.json` (323) → write
`pkt_*.md` (325) → THEN loop staging each opted-in document (329-335). The staging read
`src.read_bytes()` (335) is unguarded. `get_candidate_document` only proves the DB *row*
exists; it never verifies the backing file exists or is readable. So if the physical file
was deleted/moved, is on unavailable media, or is permission-denied (an inconsistent-vault
edge case, but a real one), staging raises `FileNotFoundError`/`PermissionError` — which is
neither `RemediationError` nor `PathEscapeError`, so it escapes `_cmd_vault_review_packet`
entirely.

Two frozen constraints break simultaneously (both reproduced empirically):

1. **Partial artifact left behind.** `pkt_*.json` and `pkt_*.md` were already written before
   the staging loop, so a `ok:false` run leaves them on disk:
   `PARTIAL ARTIFACTS LEFT: ['.../output/review-packet/pkt_c990da006b03.json',
   '.../output/review-packet/pkt_c990da006b03.md']`.
   (Note the same partial-artifact outcome occurs even for a *handled* `PathEscapeError` from
   a crafted `storage_relpath` — it is caught in the CLI as a clean `invalid_input`/exit-2
   refusal, yet the packet files are already on disk.)

2. **Absolute path leaked to `--json` stdout.** The uncaught exception hits `main`'s catch-all
   (`cli.py:1627-1633`), which emits `internal_error` with `f"{type(exc).__name__}: {exc}"`.
   For a `FileNotFoundError` that string contains the *resolved absolute* path. Observed stdout:
   `{"...","error":{"type":"internal_error","message":"FileNotFoundError: [Errno 2] No such
   file or directory: '/tmp/.../candidates/pkt/files/raw/<sha>.pdf'"}}` — exit code **4**
   (`internal_error`), not the intended clean `invalid_input`/exit-2 refusal. In production the
   leaked path is `/home/<user>/…/personal/candidates/<id>/files/raw/<sha>.pdf` — exactly the  <!-- # publish-safe: allow -->
   machine-home / abs-path shape the stdout hygiene rule (and `check_publish_safe.py`) forbid.

**Fix:** Resolve + read all staging sources into memory BEFORE the render-then-scan and
before any write, and map read failures onto the fail-closed contract so nothing is written
and no path escapes:

```python
# BEFORE the render/scan/write — resolve + read every opted-in doc up front.
staged: list[tuple[str, bytes]] = []
for row in resolved_docs:
    try:
        src = paths.resolve_within(vault.root, *row["storage_relpath"].split("/"))
        data = src.read_bytes()
    except (OSError, paths.PathEscapeError) as exc:
        raise RemediationError("unknown_document") from exc  # existing code, no abs path
    ext = "".join(src.suffixes) or ".bin"
    staged.append((f"{row['document_id']}{ext}", data))

# ... render-then-scan (unchanged) ...
# ... write packet .json/.md ...
for name, data in staged:                 # writes only after packet, but all reads pre-validated
    dest = paths.resolve_within(out_dir, pkt_id, "documents", name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
```

Even better, treat the whole write set atomically (write packet + docs, and on any write
failure delete the just-created `pkt_id` tree) so a mid-write failure never leaves a partial
packet. At minimum, the read/validation of every source must happen before the first write,
and every failure must surface as `RemediationError` (never a raw `OSError` carrying a path).

## Warnings

### WR-01: `_LEAK_PATTERNS` omits three secret shapes it claims to mirror — the only secret gate on the applicant-facing packet is incomplete

**File:** `crawler/review_packet.py:239-255` (docstring claim at 234-237)
**Issue:** The comment states the scan "Mirrors `scripts/check_publish_safe.py` shapes," but
`_LEAK_PATTERNS` drops three of `check_publish_safe.py`'s `SECRET_PATTERNS`:

- `github_pat_[A-Za-z0-9_]{22,}` (fine-grained GitHub PAT)
- `xox[baprs]-[A-Za-z0-9-]{10,}` (Slack tokens)
- the generic credential assignment `(?i)(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?key|token|password)\s*[:=]\s*['"]?([^'"\s]{12,})['"]?` — the broadest catch-all.

Confirmed empirically: `github_pat_aaaa…`, `xoxb-aaaa…`, `password: "supersecret123"`, and  <!-- # publish-safe: allow -->
`api_key="ABCDEFGHIJKL"` all return `[]` (clean) from `_scan_rendered_bytes`. Because packet  <!-- # publish-safe: allow -->
artifacts live vault-only (`personal/candidates/**`, gitignored/untracked),
`check_publish_safe.py` never scans them, so this render-then-scan is the *only* secret gate
on the packet an applicant hands to a lawyer/RCIC. The docstring parity claim is inaccurate
and the defense-in-depth is weaker than stated. (Practical exploit surface is small — the
free-text fields are corpus `quote`s and templated `action`s — but the belt-and-suspenders
gate should not silently under-deliver on its stated contract.)

**Fix:** Add the three missing patterns to `_LEAK_PATTERNS` (using the same fragment-assembly
trick so the source stays publish-safe), e.g.:

```python
re.compile(r"github" "_pat_[A-Za-z0-9_]{22,}"),
re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
re.compile(r"(?i)(?:api[_-]?key|secret(?:[_-]?key)?|access[_-]?key|token|"
           r"password)\s*[:=]\s*['\"]?[^'\"\s]{12,}"),
```

### WR-02: Duplicate `--include-document` corrupts the redaction manifest (double-counted included, NEGATIVE excluded)

**File:** `crawler/review_packet.py:292-302` (excluded math at 301)
**Issue:** The opt-in loop does not de-duplicate `include_documents`. Passing the same id
twice appends it to `included`/`resolved_docs` twice; `documents_excluded = len(docs) -
len(included)` can then go negative. Confirmed empirically with one total doc opted-in twice:
`documents_included: 2`, `manifest_counts: {... 'documents_excluded': -1, 'documents_included': 2}`.
A negative "excluded" count and an inflated "included" count violate PKT-04's requirement to
accurately record included/excluded documents; the manifest is the auditable redaction record,
so a wrong count is a correctness defect (not cosmetic). The same duplicate also stages the
file twice (idempotent overwrite of the same dest — harmless there, but wasteful).

**Fix:** De-duplicate while preserving order before resolving:

```python
for doc_id in dict.fromkeys(include_documents or []):   # order-preserving dedupe
    row = vault_module.get_candidate_document(vault, vault.candidate_id, doc_id)
    ...
```

(Optionally clamp/validate: `documents_excluded = max(0, len(docs) - len(included))` is a
band-aid but the dedupe is the real fix.)

## Info

### IN-01: Windows-drive leak pattern only matches the JSON-escaped (double-backslash) form, not a raw `.md`

**File:** `crawler/review_packet.py:248`
**Issue:** `re.compile(r"[A-Za-z]:\\\\")` requires *two* literal backslashes, so it matches
`C:\\Users` (JSON-escaped) but not `C:\Users` (single backslash) — confirmed: `scan raw md`
returns `[]` for `r"C:\Users\foo"`, while the JSON form matches. In practice there is **no live
gap**: `packet_json` (scanned via `json.dumps`, which escapes `\`→`\\`) is a content-superset of
`packet_md`, and the scan is `json OR md`, so any Windows path in any field is caught by the JSON
scan and the write (including the `.md`) is refused before it lands. The only concern is that the
pattern's name ("Windows drive path") over-promises — it silently depends on the JSON scan running.
Consider matching `[A-Za-z]:[\\/]` (single separator) so the `.md` scan is independently sound.

### IN-02: `--finding` with a non-matching factor id silently produces an empty (0-finding) packet

**File:** `crawler/review_packet.py:165-167`; `crawler/cli.py:1240`
**Issue:** `selection` filters `checklist.items` by `factor_id`; a `--finding` value that matches
nothing yields `findings=[]` and a written packet with `findings_included: 0` rather than a
refusal or warning. Not a correctness bug (the manifest counts are internally consistent), but a
user who typos a factor id gets a silently empty professional packet. Consider warning to stderr
when a requested `--finding` id matched no checklist item.

---

_Reviewed: 2026-07-17T13:33:28Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: deep_
