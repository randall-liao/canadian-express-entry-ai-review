# Phase 41 — Deferred / Blocked Items

## RESOLVED (2026-07-18) — 41-04 real-refresh closeout gate

**Plan:** 41-04 — Phase-41 conformance + real end-to-end DLI closeout
**Gate:** Task 2, step 1 — the REQUIRED real out-of-band refresh
(`.venv/bin/python -m crawler.cli --json refresh-dli`)
**Status:** ✅ RESOLVED. The maintainer compatibility/security fix landed in
`crawler/dli_snapshot.py` (commit `c6a0d65`, plan 41-01 scope) and the required
live refresh now SUCCEEDS: **exit 0**, `ok:true`, 1136 institutions / 1454
campuses, `as_of=2026-07-16T18:08:26Z`, real git-ignored `corpus/dli/` written
(1136 `.md` + `manifest.json`), PII-free five-key envelope, and `corpus/index.db`
byte-for-byte unchanged (real index rebuild + chained conformance/full gates are
owned by the resumed **41-04**, not run here).

### Resolution (decision + rationale — factual)

The confirmed root cause below was **not** an endpoint outage and **not** IPv6/
proxy/cold-connection: the upstream Akamai CDN deterministically blackholes the
one specific custom `User-Agent` string the shipped seam sent. The fix is a
maintainer compatibility/security correction, applied autonomously per the
governance decision to treat it as a product defect (the tool's custom identifier
is filtered by the real endpoint's CDN), **not** identity evasion:

- **Dropped the custom `_UA`** and set **no** `User-Agent` header — stdlib
  `urllib` sends its own standard, truthful client identity (`Python-urllib/…`),
  which the official endpoint accepts. **No browser-spoofed UA was substituted**
  (explicitly forbidden). Kept `Accept: application/json` (verified compatible).
- **Hardened the fixed-source boundary:** `fetch(*, timeout=60)` no longer takes
  a caller-overridable `url`; the request is ALWAYS built from the fixed
  `_DLI_URL`, eliminating the initial-request SSRF surface. Off-host redirects are
  still rejected (`_NoCrossHostRedirect`); the `_MAX_BYTES` ceiling, `Last-Modified`
  derivation, containment guard, and fail-closed schema parsing are all preserved.
- **Tests:** `test_dli_snapshot.py` 39 → **42** (added: `fetch` has no `url` param
  and no `_UA`; request URL is exactly `_DLI_URL`; no custom User-Agent set by
  code; Accept is JSON; off-host-redirect rejection; static self-scan forbids a
  custom UA). `test_dli_refresh_cli.py` + `test_dli_grounding.py` remain green.

Commit: `c6a0d65` (source + test atomic). SUMMARY updated: `41-01-SUMMARY.md`
Deviation #3.

### Observable behavior (historical — the blocked symptom, now fixed)

Before the fix, the shipped verb returned a clean fail-closed refusal every time:

```
{"schema_version": "1.0", "ok": false, "command": "refresh-dli", "result": null,
 "error": {"type": "invalid_input",
           "message": "could not fetch DLI dataset: The read operation timed out"}}
exit 2
```

Consistent across 12+ invocations (initial + an 8-attempt bounded retry loop +
targeted probes).

### Root cause (diagnosed — NOT an endpoint outage, NOT caused by 41-04)

The IRCC endpoint is **UP and reachable**. The failure is that the upstream
Akamai CDN **blackholes the shipped verb's honest `User-Agent`** over HTTP/1.1
from this environment's egress:

- `curl` (HTTP/2 and forced `--http1.1`) with the same custom UA → `HTTP 200`,
  432,580 bytes in ~0.24 s, `Last-Modified: Thu, 16 Jul 2026 18:08:26 GMT`.
- Plain `urllib.request.urlopen` (default `Python-urllib` UA) → succeeds in ~2–3 s.
- Controlled isolation (`crawler/dli_snapshot.py` fetch seam):
  - `_OPENER` + **no** UA → OK (432,580 b)
  - `_OPENER` + `Accept` only → OK
  - `_OPENER` + custom `_UA` only → **read timeout (fail)**
  - default opener + custom `_UA` only → **read timeout (fail)**
  - i.e. the request hangs (no response) **iff** the header
    `User-Agent: pr-review-agents DLI snapshot generator (personal, non-commercial)`
    is sent over HTTP/1.1. It is the exact `_UA` string
    (`crawler/dli_snapshot.py:88`) that is filtered, not IPv6, not a proxy, not
    a cold connection, not the audit path.

The verb's fail-closed contract worked perfectly: **no partial `corpus/dli/`
family was written, and `corpus/index.db` is byte-for-byte identical to its
pre-phase state** (verified via `cmp`). No dli-less index was rebuilt. No
full-suite / conformance "green" is claimed on a dli-less index.

### The data + mechanism + test are all PROVEN (only the verb's UA path is blocked)

Fetching the **same live payload** through the working default-UA path, running
the shipped generator, and building a real dli-bearing index in a throwaway temp
dir (NOT `corpus/`) grounds the row end-to-end with the REAL current upstream
data:

- live payload: 1,454 rows → 1,136 institutions, `as_of=2026-07-16T18:08:26Z`
- `retrieve_what_you_cite(...)['study.dli.designation']`: selected
  `dli/O19332746152.md#000`, `agrees_with_citation=True`, `grounds=True`
- `validate_registry` → zero violations for the row
- resolved chunk `source_type='dli'`

So the offline suite (41-01/02/03 + 41-04 Task 1) and the skip-guarded
live-grounding test (41-04 Task 2) are complete and correct; the live-grounding
class **would pass** the moment a real dli-bearing `corpus/index.db` exists.

### Why it was initially escalated (superseded by the maintainer decision above)

The original triage deferred rather than auto-fixing because changing the shipped
seam is (1) outside the 41-04 file scope (41-04 owns only
`crawler/tests/test_dli_conformance.py`; `dli_snapshot.py` shipped in 41-01),
(2) a change to a security-relevant SSRF-guarded network seam, and (3) possibly an
environment artifact (Akamai bot-management often filters datacenter egress IPs).

That framing is now corrected and superseded: the maintainer decision authorized
the fix as a compatibility/security correction under plan 41-01's scope. A key
factual correction to the original wording — **stdlib `urllib`'s default
`Python-urllib` identity IS the standard, honest client identity**; it is the
*custom* `_UA` string that the CDN filters. Removing the custom `_UA` therefore
adopts the truthful standard identity — it is **not** identity evasion, and no
browser-spoofed UA is used. Whether the filtering is also an egress-IP artifact is
moot: the standard identity is compatible with the official endpoint here, and the
`fetch` `url`-parameter removal is a pure security hardening independent of network.

### Resolution paths — DONE

- **Applied:** removed the custom `_UA` (standard urllib identity) + removed the
  `fetch` `url` parameter — commit `c6a0d65`, and the live
  `.venv/bin/python -m crawler.cli --json refresh-dli` now returns exit 0 with a
  real git-ignored `corpus/dli/` family (evidence above).
- **Remaining (owned by resumed 41-04, NOT run here):** the chained real index
  rebuild + full-suite + publish-safe + conformance gates —
  `.venv/bin/python -m crawler.cli index corpus/ --db corpus/index.db`
  `&& .venv/bin/python -m pytest crawler/tests -q`
  `&& .venv/bin/python scripts/check_publish_safe.py`
  `&& .venv/bin/python scripts/run_conformance.py`

Once the resumed 41-04 rebuilds a real dli-bearing `corpus/index.db`, STUDY-01
closes: the whole-registry conformance and the skip-guarded live-grounding test
both ground `study.dli.designation` against the real refreshed index.
