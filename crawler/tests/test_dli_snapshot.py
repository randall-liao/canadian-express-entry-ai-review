"""Offline unit tests for ``crawler.dli_snapshot`` (STUDY-01, Phase 41 Plan 01).

Stdlib ``unittest`` run via pytest; **NO network, NO third-party deps, NO
browser**. The network ``fetch`` seam is monkeypatched (a fake opener); every
logic test exercises the pure ``normalize`` / ``write`` functions against the
curated ``fixtures/dli/dli-sample.json`` payload — a faithful verbatim subset of
the authoritative IRCC DLI/PGWP JSON covering every verified data-quality
landmine. Run from the repo root::

    .venv/bin/python -m pytest crawler/tests/test_dli_snapshot.py -x -q
"""

from __future__ import annotations

import inspect
import io
import json
import os
import shutil
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from crawler import dli_snapshot

_FIXTURE = Path(__file__).parent / "fixtures" / "dli" / "dli-sample.json"
_AS_OF = "2026-07-16T18:08:26Z"
_LAST_MODIFIED = "Thu, 16 Jul 2026 18:08:26 GMT"

# Distinct DLI numbers in the curated fixture, and their campus-row counts.
_EXPECTED_DLIS = {
    "O110120953397": 1,
    "O112937696097": 3,
    "O153601941355": 2,
    "O19305471522": 3,
    "O19332746152": 2,
}


def _load_sample() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _valid_row(**overrides) -> dict:
    row = {
        "Province": "Ontario",
        "Institution": "University of Toronto",
        "DLI #": "O19332746152",
        "City": "Toronto",
        "Campus": "Main Campus",
        "Grad Program": "Yes",
        "PGWP": "Yes",
        "HTML": "Yes",
        "Public/Private": "Public institution",
    }
    row.update(overrides)
    return row


class _FakeResp:
    """Minimal stand-in for ``http.client.HTTPResponse`` (context manager)."""

    def __init__(self, body: bytes, last_modified: str | None = _LAST_MODIFIED):
        self._body = body
        self.headers = {"Last-Modified": last_modified}

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            return self._body
        return self._body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeOpener:
    def __init__(self, resp: _FakeResp):
        self._resp = resp
        self.last_req = None

    def open(self, req, timeout=None):  # noqa: A003 - mirrors OpenerDirector.open
        self.last_req = req
        return self._resp


# --------------------------------------------------------------------------- #
# as_of_from — deterministic upstream "data age" (never wall-clock)
# --------------------------------------------------------------------------- #
class TestAsOf(unittest.TestCase):
    def test_as_of_from_parses_rfc1123_to_iso_z(self):
        self.assertEqual(dli_snapshot.as_of_from(_LAST_MODIFIED), _AS_OF)

    def test_as_of_from_none_raises_schema(self):
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.as_of_from(None)

    def test_as_of_from_empty_raises_schema(self):
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.as_of_from("")

    def test_as_of_from_garbage_raises_schema(self):
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.as_of_from("garbage not a date")


# --------------------------------------------------------------------------- #
# fetch — fixed-host network seam, size ceiling, json.loads (never eval)
# --------------------------------------------------------------------------- #
class TestFetch(unittest.TestCase):
    def setUp(self):
        self._saved_opener = dli_snapshot._OPENER
        self._saved_max = dli_snapshot._MAX_BYTES

    def tearDown(self):
        dli_snapshot._OPENER = self._saved_opener
        dli_snapshot._MAX_BYTES = self._saved_max

    def test_fetch_fixed_endpoint_constant(self):
        self.assertEqual(
            dli_snapshot._DLI_URL,
            "https://www.canada.ca/content/dam/ircc/documents/json/dli/dli-full-list.json",
        )
        # The fixed source is structurally enforced: fetch() takes NO caller-
        # overridable ``url`` (only a keyword-only ``timeout``), so there is no
        # arbitrary-URL / initial-request SSRF surface, and the old ``_UA`` constant
        # is gone (no custom identity is sent).
        sig = inspect.signature(dli_snapshot.fetch)
        self.assertNotIn("url", sig.parameters)
        self.assertEqual(set(sig.parameters), {"timeout"})
        self.assertFalse(hasattr(dli_snapshot, "_UA"))

    def test_fetch_builds_request_from_fixed_url_json_accept_no_custom_ua(self):
        # The request is ALWAYS constructed from the fixed _DLI_URL; the code sets
        # NO custom / browser-spoofed User-Agent (stdlib urllib's honest default is
        # what the authoritative endpoint accepts), and advertises Accept: JSON.
        body = json.dumps({"data": [_valid_row()]}).encode("utf-8")
        opener = _FakeOpener(_FakeResp(body))
        dli_snapshot._OPENER = opener
        dli_snapshot.fetch()
        req = opener.last_req
        self.assertIsNotNone(req)
        self.assertEqual(req.full_url, dli_snapshot._DLI_URL)  # exactly the fixed endpoint
        # urllib capitalizes header keys ("User-Agent" -> "User-agent"); the code
        # never sets one, so no custom UA header is present on the request.
        self.assertIsNone(req.get_header("User-agent"))
        self.assertNotIn("User-agent", req.headers)
        self.assertEqual(req.get_header("Accept"), "application/json")

    def test_off_host_redirect_is_rejected(self):
        # SSRF/exfil guard remains intact: any redirect leaving the fixed host
        # raises instead of being followed (initial + redirect surface both fixed).
        handler = dli_snapshot._NoCrossHostRedirect()
        req = urllib.request.Request(dli_snapshot._DLI_URL)
        with self.assertRaises(urllib.error.HTTPError):
            handler.redirect_request(
                req, io.BytesIO(b""), 302, "Found", {},
                "https://evil.example.com/exfil",
            )

    def test_fetch_parses_json_and_returns_last_modified(self):
        body = json.dumps({"data": [_valid_row()]}).encode("utf-8")
        dli_snapshot._OPENER = _FakeOpener(_FakeResp(body))
        payload, last_modified = dli_snapshot.fetch()
        self.assertEqual(last_modified, _LAST_MODIFIED)
        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["data"][0]["DLI #"], "O19332746152")

    def test_fetch_size_ceiling_raises_schema_before_parse(self):
        # Oversized body is refused (DoS guard) before json.loads.
        dli_snapshot._MAX_BYTES = 16
        big = b"x" * 4096
        dli_snapshot._OPENER = _FakeOpener(_FakeResp(big))
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.fetch()

    def test_fetch_non_utf8_body_normalized_to_schema_error(self):
        # A non-UTF-8 body (binary/garbled @ HTTP 200) is a fail-closed refusal,
        # normalized to SchemaError with a stable, PII-free message (CR-01).
        dli_snapshot._OPENER = _FakeOpener(_FakeResp(b"\xff\xfe\x00\x01\x80\x81"))
        with self.assertRaises(dli_snapshot.SchemaError) as ctx:
            dli_snapshot.fetch()
        self.assertIn("not valid UTF-8", str(ctx.exception))

    def test_fetch_non_json_body_normalized_to_schema_error(self):
        # A canada.ca HTML maintenance page served with 200 is not JSON — refused
        # as SchemaError (CR-01), NOT a raw json.JSONDecodeError escaping fetch.
        html = b"<html><body>Service temporarily unavailable</body></html>"
        dli_snapshot._OPENER = _FakeOpener(_FakeResp(html))
        with self.assertRaises(dli_snapshot.SchemaError) as ctx:
            dli_snapshot.fetch()
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_fetch_truncated_json_normalized_to_schema_error(self):
        # A stream dropped mid-payload yields invalid JSON — SchemaError (CR-01).
        dli_snapshot._OPENER = _FakeOpener(_FakeResp(b'{"data": [{"Province": "On'))
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.fetch()

    def test_fetch_schema_error_message_is_pii_free(self):
        # The normalized message must NEVER echo raw payload bytes (stable + PII-
        # free machine/human contract).
        secret = b'{"institution": "University of Toronto SECRET-CAMPUS"'
        dli_snapshot._OPENER = _FakeOpener(_FakeResp(secret))
        with self.assertRaises(dli_snapshot.SchemaError) as ctx:
            dli_snapshot.fetch()
        self.assertNotIn("University of Toronto", str(ctx.exception))
        self.assertNotIn("SECRET-CAMPUS", str(ctx.exception))


# --------------------------------------------------------------------------- #
# normalize — strict closed nine-field schema (fail-closed refusals)
# --------------------------------------------------------------------------- #
class TestSchema(unittest.TestCase):
    def test_schema_empty_data_raises(self):
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize({"data": []}, as_of=_AS_OF)

    def test_schema_non_dict_payload_raises(self):
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize([_valid_row()], as_of=_AS_OF)

    def test_schema_missing_top_level_key_raises(self):
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize({"rows": [_valid_row()]}, as_of=_AS_OF)

    def test_schema_extra_top_level_key_raises(self):
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize(
                {"data": [_valid_row()], "meta": 1}, as_of=_AS_OF
            )

    def test_schema_data_not_a_list_raises(self):
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize({"data": {"nope": 1}}, as_of=_AS_OF)

    def test_schema_missing_row_field_raises(self):
        row = _valid_row()
        del row["City"]
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize({"data": [row]}, as_of=_AS_OF)

    def test_schema_extra_row_field_raises(self):
        row = _valid_row(Extra="tenth key")
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize({"data": [row]}, as_of=_AS_OF)

    def test_schema_non_string_value_raises(self):
        row = _valid_row(PGWP=1)
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize({"data": [row]}, as_of=_AS_OF)

    def test_schema_invalid_pgwp_raises(self):
        row = _valid_row(PGWP="Maybe")
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize({"data": [row]}, as_of=_AS_OF)

    def test_schema_row_not_object_raises(self):
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize({"data": ["not a row"]}, as_of=_AS_OF)

    def test_fixture_schema_valid_groups_five_dlis(self):
        docs = dli_snapshot.normalize(_load_sample(), as_of=_AS_OF)
        self.assertEqual({d.dli_number for d in docs}, set(_EXPECTED_DLIS))
        self.assertEqual({d.dli_number: d.rows for d in docs}, _EXPECTED_DLIS)
        # deterministic ascending DLI# ordering
        self.assertEqual(
            [d.dli_number for d in docs], sorted(_EXPECTED_DLIS)
        )


# --------------------------------------------------------------------------- #
# normalize — a malformed DLI identity aborts the WHOLE refresh (fail-closed)
# --------------------------------------------------------------------------- #
class TestMalformed(unittest.TestCase):
    def test_one_malformed_dli_row_aborts_whole_refresh(self):
        # Contract (must_haves truth #3): ANY malformed row — even a single one
        # among otherwise-valid rows — aborts the whole refresh fail-closed. No
        # partial subset is ever produced (normalize raises before any doc build).
        good = _valid_row(**{"DLI #": "O19332746152"})
        bad = _valid_row(**{"DLI #": "NOT-A-DLI", "Institution": "Bogus"})
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize({"data": [good, bad]}, as_of=_AS_OF)
        # order-independent: a malformed row BEFORE valid rows aborts identically.
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize({"data": [bad, good]}, as_of=_AS_OF)

    def test_trailing_space_dli_is_stripped_not_dropped(self):
        row = _valid_row(**{"DLI #": "O19332746152 "})
        docs = dli_snapshot.normalize({"data": [row]}, as_of=_AS_OF)
        self.assertEqual({d.dli_number for d in docs}, {"O19332746152"})

    def test_all_malformed_rows_raises(self):
        bad = _valid_row(**{"DLI #": "garbage"})
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize({"data": [bad]}, as_of=_AS_OF)


# --------------------------------------------------------------------------- #
# normalize — control characters in ANY free-text field are a fail-closed drift
# (WR-02: a raw newline/CR/NEL survives _nfc().strip() and can forge a
# `DLI number:` marker or a markdown heading into the grounded chunk #000)
# --------------------------------------------------------------------------- #
# Representative control characters spanning the whole rejected block: ASCII C0
# (newline/CR/tab/NUL), DEL, and C1 (NEL). Each MUST abort the whole refresh.
_CONTROL_SAMPLES = {
    "newline_c0": "\n",
    "carriage_return_c0": "\r",
    "tab_c0": "\t",
    "nul_c0": "\x00",
    "unit_separator_c0": "\x1f",
    "del": "\x7f",
    "nel_c1": "\x85",  # C1 Next-Line — a line separator to many processors
}


class TestControlCharRejection(unittest.TestCase):
    def test_predicate_rejects_controls_and_accepts_ordinary_unicode(self):
        # Locks the exact boundary of the explicit-codepoint predicate: every
        # representative control (C0 / DEL / C1) is rejected, while ordinary
        # Unicode letters/punctuation — accents and the curly apostrophe — are
        # accepted (they live above 0x9F and must survive verbatim).
        for name, ch in _CONTROL_SAMPLES.items():
            with self.subTest(control=name):
                self.assertTrue(dli_snapshot._has_control_char(f"Evil U{ch}x"))
        for ok in ("Cestar Coll\u00e8ge", "St. Jerome\u2019s University",
                   "Universit\u00e9 du Qu\u00e9bec", "ASCII only"):
            with self.subTest(accepted=ok):
                self.assertFalse(dli_snapshot._has_control_char(ok))

    def test_embedded_newline_forging_dli_marker_in_institution_raises(self):
        # The exact review scenario: an upstream Institution carrying a raw
        # newline that forges a second `DLI number:` line into chunk #000. It
        # must be refused BEFORE any doc is built (fail-closed), never rendered.
        forged = "Evil U\nDLI number: O00000000\nForged: injected"
        row = _valid_row(**{"DLI #": "O11111111", "Institution": forged})
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize({"data": [row]}, as_of=_AS_OF)

    def test_embedded_newline_forging_dli_marker_in_campus_raises(self):
        forged = "Main\nDLI number: O00000000\nForged: injected"
        row = _valid_row(**{"DLI #": "O11111111", "Campus": forged})
        with self.assertRaises(dli_snapshot.SchemaError):
            dli_snapshot.normalize({"data": [row]}, as_of=_AS_OF)

    def test_each_representative_control_char_aborts_refresh(self):
        # newline, carriage-return, tab, NUL, DEL, and a C1 control each abort.
        for name, ch in _CONTROL_SAMPLES.items():
            with self.subTest(control=name):
                row = _valid_row(Institution=f"Uni{ch}Two")
                with self.assertRaises(dli_snapshot.SchemaError):
                    dli_snapshot.normalize({"data": [row]}, as_of=_AS_OF)

    def test_control_char_is_rejected_in_every_string_field(self):
        # Not just the obvious free-text fields — a control char in ANY of the
        # nine string fields is drift and aborts the whole refresh.
        for field_name in dli_snapshot._FIELDS:
            with self.subTest(field=field_name):
                row = _valid_row(**{field_name: f"bad\nvalue"})
                # Keep PGWP/DLI # otherwise-valid so the control-char guard (not
                # the tri-state / regex guard) is what trips for those fields.
                if field_name == "PGWP":
                    row["PGWP"] = "Ye\ns"
                if field_name == "DLI #":
                    row["DLI #"] = "O1933\n2746152"
                with self.assertRaises(dli_snapshot.SchemaError):
                    dli_snapshot.normalize({"data": [row]}, as_of=_AS_OF)

    def test_single_control_char_row_among_good_rows_aborts_whole_normalize(self):
        # A SINGLE tainted row among otherwise-valid rows aborts fail-closed and
        # returns NO docs — order-independent, mirroring the DLI-identity guard.
        good_a = _valid_row(**{"DLI #": "O19332746152"})
        good_b = _valid_row(**{"DLI #": "O110120953397",
                               "Institution": "Solomon College"})
        bad = _valid_row(**{"DLI #": "O153601941355",
                            "Institution": "Evil U\nDLI number: O00000000"})
        for ordering in ([good_a, good_b, bad], [bad, good_a, good_b]):
            with self.subTest(order=[r["Institution"] for r in ordering]):
                with self.assertRaises(dli_snapshot.SchemaError):
                    dli_snapshot.normalize({"data": ordering}, as_of=_AS_OF)

    def test_control_char_refresh_writes_nothing_and_preserves_prior_family(self):
        # Integration (normalize -> write): a rerun whose payload carries a
        # control-char row aborts in normalize() BEFORE write() runs, so the
        # prior healthy family on disk is preserved byte-for-byte — no doc is
        # emitted, no family swap occurs (must_haves truth #3 + #5, now for
        # content drift as well as identity drift).
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dli"
            dli_snapshot.write(
                dli_snapshot.normalize(_load_sample(), as_of=_AS_OF), out
            )
            before = _read_family(out)

            tainted = _load_sample()
            tainted["data"].append(
                _valid_row(**{"DLI #": "O44444444",
                              "Institution": "Evil U\nDLI number: O00000000"})
            )
            with self.assertRaises(dli_snapshot.SchemaError):
                dli_snapshot.write(
                    dli_snapshot.normalize(tainted, as_of=_AS_OF), out
                )
            after = _read_family(out)
        self.assertEqual(before, after)  # prior family byte-for-byte untouched

    def test_control_char_schema_error_is_pii_free_names_field(self):
        # The refusal names the (fixed, public) schema field key but NEVER echoes
        # the raw offending content — stable + PII-free, mirroring the fetch()
        # decode-refusal contract.
        secret = "SECRET-CAMPUS-NAME\nDLI number: O00000000"
        row = _valid_row(Institution=secret)
        with self.assertRaises(dli_snapshot.SchemaError) as ctx:
            dli_snapshot.normalize({"data": [row]}, as_of=_AS_OF)
        msg = str(ctx.exception)
        self.assertIn("Institution", msg)          # names the field
        self.assertNotIn("SECRET-CAMPUS-NAME", msg)  # never echoes content
        self.assertNotIn("DLI number: O00000000", msg)
        self.assertNotIn("\n", msg)                 # no raw content leaks

    def test_non_ascii_letters_and_punctuation_are_accepted(self):
        # Positive coverage: legitimate accented letters and the curly
        # apostrophe (U+2019) are NOT control characters — they normalize
        # cleanly and survive verbatim (NFC) into the generated body.
        name = "Universit\u00e9 St. Jerome\u2019s Coll\u00e8ge"
        row = _valid_row(**{"DLI #": "O19332746152", "Institution": name})
        docs = dli_snapshot.normalize({"data": [row]}, as_of=_AS_OF)
        self.assertEqual(len(docs), 1)
        self.assertIn("Universit\u00e9 St. Jerome\u2019s Coll\u00e8ge",
                      docs[0].body)


def _docs_by_number(docs) -> dict:
    return {d.dli_number: d for d in docs}


def _read_family(root: Path) -> dict:
    """Return {relative-name: bytes} for every file under *root* (byte-exact)."""
    return {
        p.name: p.read_bytes()
        for p in sorted(root.iterdir())
        if p.is_file()
    }


# --------------------------------------------------------------------------- #
# Per-DLI canonicalization: union of names, per-campus PGWP, current-only markers
# --------------------------------------------------------------------------- #
class TestCanonicalize(unittest.TestCase):
    def setUp(self):
        self.docs = _docs_by_number(
            dli_snapshot.normalize(_load_sample(), as_of=_AS_OF)
        )

    def test_shared_dli_yields_one_doc_with_union_of_names(self):
        doc = self.docs["O19305471522"]
        self.assertEqual(doc.rows, 3)
        for name in (
            "Conrad Grebel University College",
            "St. Jerome\u2019s University (University of Waterloo)",
            "University of Waterloo",
        ):
            self.assertIn(name, doc.body)
        # union listed on a single "Institution names:" line
        names_line = next(
            ln for ln in doc.body.splitlines() if ln.startswith("Institution names:")
        )
        self.assertIn("University of Waterloo", names_line)

    def test_name_whitespace_stripped_and_deduped_in_union(self):
        # "Eastern College" and "Eastern College " collapse to ONE variant.
        doc = self.docs["O112937696097"]
        names_line = next(
            ln for ln in doc.body.splitlines() if ln.startswith("Institution names:")
        )
        self.assertEqual(names_line, "Institution names: Eastern College")

    def test_trailing_space_dli_number_is_clean(self):
        doc = self.docs["O110120953397"]
        self.assertEqual(doc.dli_number, "O110120953397")
        self.assertEqual(doc.path, "O110120953397.md")
        self.assertEqual(doc.front["dli_number"], "O110120953397")
        self.assertIn("DLI number: O110120953397\n", doc.body)

    def test_conflicting_pgwp_preserved_per_campus_verbatim(self):
        doc = self.docs["O153601941355"]
        # both campus PGWP values survive in the per-campus table (never collapsed)
        self.assertIn("| LaSalle | LaSalle | No |", doc.body)
        self.assertIn("| Longueuil | Longueuil | Details |", doc.body)
        # Details preserved verbatim; no sub-page URL followed/emitted
        self.assertIn("Details", doc.body)
        self.assertNotIn("details.html", doc.body)
        self.assertNotIn("<a href", doc.body)

    def test_multicampus_doc_has_exact_dli_number_line_in_chunk_zero(self):
        from crawler import searchindex

        doc = self.docs["O19332746152"]
        self.assertIn("DLI number: O19332746152\n", doc.body)
        chunks = searchindex.chunk(doc.body)
        self.assertIn("DLI number: O19332746152", chunks[0][1])
        # both Toronto campuses present in the PGWP table
        self.assertIn("| Mississauga | Mississauga | Yes |", doc.body)
        self.assertIn("| Toronto | Main Campus, Scarborough Campus | Yes |", doc.body)

    def test_non_ascii_name_is_nfc_and_byte_stable(self):
        import unicodedata

        doc = self.docs["O153601941355"]
        self.assertIn("Cestar Coll\u00e8ge", doc.body)  # NFC 'è'
        self.assertEqual(doc.body, unicodedata.normalize("NFC", doc.body))

    def test_every_doc_carries_current_only_front_matter_and_body_markers(self):
        for doc in self.docs.values():
            self.assertEqual(doc.front["source_type"], "dli")
            self.assertEqual(doc.front["dli_number"], doc.dli_number)
            self.assertEqual(doc.front["crawl_date"], _AS_OF)
            self.assertEqual(doc.front["status_scope"], "current-only")
            self.assertTrue(doc.front["content_sha256"])
            self.assertIn(f"DLI number: {doc.dli_number}\n", doc.body)
            self.assertIn("current status only", doc.body)
            self.assertIn("does NOT establish DLI designation", doc.body)


# --------------------------------------------------------------------------- #
# Provenance hashing: body-only, deterministic, independent of crawl_date
# --------------------------------------------------------------------------- #
class TestHashing(unittest.TestCase):
    def test_content_sha256_hashes_body_only_and_is_deterministic(self):
        a = _docs_by_number(dli_snapshot.normalize(_load_sample(), as_of=_AS_OF))
        b = _docs_by_number(dli_snapshot.normalize(_load_sample(), as_of=_AS_OF))
        for num in a:
            self.assertEqual(a[num].body, b[num].body)
            self.assertEqual(a[num].content_sha256, b[num].content_sha256)

    def test_changing_as_of_does_not_change_body_hash(self):
        a = _docs_by_number(dli_snapshot.normalize(_load_sample(), as_of=_AS_OF))
        other = "2020-01-01T00:00:00Z"
        b = _docs_by_number(dli_snapshot.normalize(_load_sample(), as_of=other))
        for num in a:
            self.assertEqual(a[num].content_sha256, b[num].content_sha256)
            self.assertEqual(a[num].body, b[num].body)
            self.assertNotEqual(a[num].front["crawl_date"], b[num].front["crawl_date"])

    def test_body_sha256_matches_front_matter_value(self):
        docs = dli_snapshot.normalize(_load_sample(), as_of=_AS_OF)
        for doc in docs:
            self.assertEqual(
                doc.front["content_sha256"], dli_snapshot._body_sha256(doc.body)
            )


# --------------------------------------------------------------------------- #
# Atomic full-family write: honors out_dir, idempotent, deletes stale, rolls back
# --------------------------------------------------------------------------- #
class TestWrite(unittest.TestCase):
    def test_write_honors_out_dir_and_is_byte_identical_across_runs(self):
        docs = dli_snapshot.normalize(_load_sample(), as_of=_AS_OF)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dli"
            r1 = dli_snapshot.write(docs, out)
            first = _read_family(out)
            r2 = dli_snapshot.write(
                dli_snapshot.normalize(_load_sample(), as_of=_AS_OF), out
            )
            second = _read_family(out)
        self.assertEqual(first, second)  # byte-identical
        self.assertEqual(r1, r2)
        self.assertEqual(r1["docs"], 5)
        self.assertEqual(r1["rows"], 11)
        self.assertEqual(r1["out"], str(out))
        self.assertTrue(r1["family_sha256"])
        # one .md per distinct DLI + a non-.md manifest
        self.assertEqual(
            {n for n in first if n.endswith(".md")},
            {f"{d}.md" for d in _EXPECTED_DLIS},
        )
        self.assertIn("manifest.json", first)

    def test_rerun_with_removed_institution_deletes_stale_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dli"
            dli_snapshot.write(
                dli_snapshot.normalize(_load_sample(), as_of=_AS_OF), out
            )
            self.assertTrue((out / "O110120953397.md").exists())
            # rerun with Solomon College (O110120953397) removed upstream
            sample = _load_sample()
            sample["data"] = [
                r for r in sample["data"] if r["DLI #"].strip() != "O110120953397"
            ]
            dli_snapshot.write(dli_snapshot.normalize(sample, as_of=_AS_OF), out)
            self.assertFalse((out / "O110120953397.md").exists())  # stale file gone
            self.assertTrue((out / "O19332746152.md").exists())

    def test_write_failure_preserves_prior_family_byte_for_byte(self):
        docs = dli_snapshot.normalize(_load_sample(), as_of=_AS_OF)
        saved = dli_snapshot._write_manifest
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dli"
            dli_snapshot.write(docs, out)
            before = _read_family(out)

            def _boom(*a, **k):
                raise RuntimeError("simulated stage/swap failure")

            dli_snapshot._write_manifest = _boom
            try:
                with self.assertRaises(RuntimeError):
                    dli_snapshot.write(docs, out)
            finally:
                dli_snapshot._write_manifest = saved
            after = _read_family(out)
        self.assertEqual(before, after)  # prior healthy family intact

    def test_malformed_refresh_preserves_prior_family_byte_for_byte(self):
        # Integration of the real refresh flow (normalize -> write): a rerun whose
        # payload carries ANY malformed row aborts in normalize() BEFORE write()
        # runs, so the prior healthy family on disk is preserved byte-for-byte —
        # a partial/garbage family can never replace it (must_haves truth #3 + #5).
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dli"
            dli_snapshot.write(
                dli_snapshot.normalize(_load_sample(), as_of=_AS_OF), out
            )
            before = _read_family(out)

            tainted = _load_sample()
            tainted["data"].append(_valid_row(**{"DLI #": "NOT-A-DLI"}))
            with self.assertRaises(dli_snapshot.SchemaError):
                dli_snapshot.write(
                    dli_snapshot.normalize(tainted, as_of=_AS_OF), out
                )
            after = _read_family(out)
        self.assertEqual(before, after)  # prior family byte-for-byte untouched

    def test_write_contains_output_and_refuses_traversal(self):
        from crawler import paths

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dli"
            dli_snapshot.write(
                dli_snapshot.normalize(_load_sample(), as_of=_AS_OF), out
            )
            root = out.resolve()
            for p in root.iterdir():
                self.assertTrue(paths.is_within(root, p))
            # a crafted DLI value can never traverse out of the family root
            evil = dli_snapshot.DliDoc(
                dli_number="../evil",
                campuses=[],
                front={"x": 1},
                body="body",
                content_sha256="deadbeef",
            )
            with self.assertRaises(paths.PathEscapeError):
                dli_snapshot.write([evil], Path(tmp) / "dli2")


# --------------------------------------------------------------------------- #
# WR-01: crash-window transient dirs live OUTSIDE the indexed family tree, so a
# hard-kill orphan is never enumerated as a duplicate live DLI doc. The frozen
# dupaudit / searchindex are NOT modified — containment moves, not the indexer.
# --------------------------------------------------------------------------- #
class TestCrashOrphanContainment(unittest.TestCase):
    def test_successful_write_leaves_no_transient_dir_in_indexed_tree(self):
        """A normal write leaves ONLY the family under the indexed corpus root —
        no ``.dli.stage-*`` / ``.dli.bak-*`` sibling, and no leftover container."""
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus"
            root = corpus / "dli"
            dli_snapshot.write(
                dli_snapshot.normalize(_load_sample(), as_of=_AS_OF), root)
            # The indexed root (corpus/) holds ONLY the family dir.
            self.assertEqual([p.name for p in corpus.iterdir()], ["dli"])
            # No transient container debris one level up either.
            prefix = dli_snapshot._root_container_prefix(root.resolve())
            self.assertEqual(
                list(root.resolve().parent.parent.glob(f"{prefix}*")), [])

    def test_crash_window_orphan_is_outside_indexed_tree(self):
        """A simulated hard-kill orphan (full family copy in the transient
        container) is NOT enumerated by ``dupaudit.live_docs`` over the corpus
        root — only the canonical family is live (no duplicate DLI markers)."""
        from crawler import dupaudit

        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus"
            root = corpus / "dli"
            dli_snapshot.write(
                dli_snapshot.normalize(_load_sample(), as_of=_AS_OF), root)
            canonical = {f"{d}.md" for d in _EXPECTED_DLIS}
            self.assertEqual(
                {p.name for p, _ in dupaudit.live_docs(corpus)}, canonical)

            # Simulate a SIGKILL in the swap window: a full family copy (valid
            # front-matter .md docs) left behind in a crashed run's container,
            # which lives under root.parent.parent — OUTSIDE the indexed corpus.
            rroot = root.resolve()
            prefix = dli_snapshot._root_container_prefix(rroot)
            orphan_bak = rroot.parent.parent / f"{prefix}999999-deadbeefcafe" / "bak"
            orphan_bak.mkdir(parents=True)
            for md in root.glob("*.md"):
                (orphan_bak / md.name).write_text(
                    md.read_text("utf-8"), encoding="utf-8")

            # The indexed corpus root still sees ONLY the canonical family: the
            # orphan is a sibling of corpus/, never rglob'd, so no duplicate
            # relpaths and no doubled DLI-number markers (WR-01 regression).
            relpaths = [
                str(p.relative_to(corpus)) for p, _ in dupaudit.live_docs(corpus)]
            self.assertEqual(len(relpaths), len(_EXPECTED_DLIS))
            self.assertEqual(len(relpaths), len(set(relpaths)))  # no duplicates
            self.assertTrue(all(r.startswith("dli/") for r in relpaths))
            self.assertEqual(
                {p.name for p, _ in dupaudit.live_docs(corpus)}, canonical)

    def test_write_sweeps_prior_dead_crash_orphan_on_entry(self):
        """``write()`` sweeps a prior crashed run's (dead-PID) container on entry,
        so debris does not accumulate, while a normal write still succeeds."""
        with tempfile.TemporaryDirectory() as tmp:
            root = (Path(tmp) / "corpus" / "dli").resolve()
            root.parent.mkdir(parents=True)
            container_parent = root.parent.parent
            prefix = dli_snapshot._root_container_prefix(root)
            dead = container_parent / f"{prefix}999999-cccccccccccc"
            (dead / "bak").mkdir(parents=True)

            saved = dli_snapshot._pid_alive
            dli_snapshot._pid_alive = lambda pid: False  # treat orphan as dead
            try:
                dli_snapshot.write(
                    dli_snapshot.normalize(_load_sample(), as_of=_AS_OF), root)
            finally:
                dli_snapshot._pid_alive = saved

            self.assertFalse(dead.exists())  # dead-PID orphan swept on entry
            self.assertEqual(list(container_parent.glob(f"{prefix}*")), [])

    def test_sweep_removes_dead_pid_orphan_but_spares_live_concurrent(self):
        """The stale sweep removes a dead-PID container but NEVER a live one — an
        active concurrent refresh of the same family is not destroyed."""
        with tempfile.TemporaryDirectory() as tmp:
            root = (Path(tmp) / "corpus" / "dli").resolve()
            root.parent.mkdir(parents=True)
            container_parent = root.parent.parent
            prefix = dli_snapshot._root_container_prefix(root)
            dead = container_parent / f"{prefix}111111-aaaaaaaaaaaa"
            live = container_parent / f"{prefix}222222-bbbbbbbbbbbb"
            (dead / "bak").mkdir(parents=True)
            (live / "bak").mkdir(parents=True)

            saved = dli_snapshot._pid_alive
            dli_snapshot._pid_alive = lambda pid: pid == 222222
            try:
                dli_snapshot._sweep_stale_containers(container_parent, prefix)
            finally:
                dli_snapshot._pid_alive = saved

            self.assertFalse(dead.exists())  # dead-PID crash-orphan swept
            self.assertTrue(live.exists())   # active concurrent run spared

    def test_rollback_preserves_bytes_and_leaves_no_in_tree_orphan(self):
        """A staging failure restores the prior family byte-for-byte AND leaves no
        transient dir inside the indexed tree (atomic-swap contract preserved)."""
        docs = dli_snapshot.normalize(_load_sample(), as_of=_AS_OF)
        saved = dli_snapshot._write_manifest
        with tempfile.TemporaryDirectory() as tmp:
            corpus = Path(tmp) / "corpus"
            root = corpus / "dli"
            dli_snapshot.write(docs, root)
            before = _read_family(root)

            def _boom(*a, **k):
                raise RuntimeError("simulated swap failure")

            dli_snapshot._write_manifest = _boom
            try:
                with self.assertRaises(RuntimeError):
                    dli_snapshot.write(docs, root)
            finally:
                dli_snapshot._write_manifest = saved

            after = _read_family(root)
            self.assertEqual(before, after)  # prior family byte-for-byte intact
            # corpus/ still holds ONLY the family; no container debris up a level.
            self.assertEqual([p.name for p in corpus.iterdir()], ["dli"])
            prefix = dli_snapshot._root_container_prefix(root.resolve())
            self.assertEqual(
                list(root.resolve().parent.parent.glob(f"{prefix}*")), [])

    def test_container_pid_parses_and_pid_alive_reports_self_alive(self):
        """Sanity: PID parsing round-trips and our own process reads as alive."""
        root = Path("/x/corpus/dli").resolve()
        prefix = dli_snapshot._root_container_prefix(root)
        name = f"{prefix}{os.getpid()}-abcdef012345"
        self.assertEqual(dli_snapshot._container_pid(name, prefix), os.getpid())
        self.assertIsNone(dli_snapshot._container_pid("unrelated", prefix))
        self.assertTrue(dli_snapshot._pid_alive(os.getpid()))


# --------------------------------------------------------------------------- #
# Manifest: non-indexed provenance, never enumerated by dupaudit.live_docs
# --------------------------------------------------------------------------- #
class TestManifest(unittest.TestCase):
    def test_manifest_records_provenance_and_is_non_indexed(self):
        from crawler import dupaudit

        docs = dli_snapshot.normalize(_load_sample(), as_of=_AS_OF)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dli"
            result = dli_snapshot.write(docs, out)
            manifest = json.loads((out / "manifest.json").read_text("utf-8"))
            self.assertEqual(manifest["source_url"], dli_snapshot._DLI_URL)
            self.assertEqual(manifest["as_of"], _AS_OF)
            self.assertEqual(manifest["family_sha256"], result["family_sha256"])
            self.assertEqual(manifest["status_scope"], "current-only")
            files = manifest["files"]
            self.assertEqual(files, sorted(files, key=lambda e: e["file"]))
            self.assertEqual(
                {e["file"] for e in files}, {f"{d}.md" for d in _EXPECTED_DLIS}
            )
            # manifest.json is NOT enumerated into the index (non-.md, no front-matter)
            enumerated = {p.name for p, _ in dupaudit.live_docs(out)}
            self.assertNotIn("manifest.json", enumerated)
            self.assertEqual(enumerated, {f"{d}.md" for d in _EXPECTED_DLIS})


# --------------------------------------------------------------------------- #
# Static self-scan: no inlined volatile rule / max-age literal in the module
# --------------------------------------------------------------------------- #
class TestStaticSelfScan(unittest.TestCase):
    def test_no_inlined_volatile_rules(self):
        from crawler import crs_rules

        self.assertEqual(
            crs_rules.no_inlined_volatile_rules(["crawler/dli_snapshot.py"]), []
        )

    def test_no_max_age_literal_in_module(self):
        src = Path(dli_snapshot.__file__).read_text(encoding="utf-8")
        self.assertNotIn("max_age", src)
        self.assertNotIn("snapshot_max_age", src)

    def test_no_custom_user_agent_header_set_by_code(self):
        # The module must NOT set a custom / browser-spoofed User-Agent header nor
        # define a ``_UA`` constant: the honest stdlib urllib identity is what the
        # authoritative endpoint accepts, and spoofing is explicitly forbidden.
        src = Path(dli_snapshot.__file__).read_text(encoding="utf-8")
        self.assertNotIn('"User-Agent"', src)
        self.assertNotIn("_UA", src)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()