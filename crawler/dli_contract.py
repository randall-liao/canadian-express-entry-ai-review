"""Pure DLI snapshot provenance contract shared by refresh and audit paths."""

from __future__ import annotations

import hashlib
import json
import unicodedata


_DLI_URL = (
    "https://www.canada.ca/content/dam/ircc/documents/json/dli/dli-full-list.json"
)
_PAGE_URL = (
    "https://www.canada.ca/en/immigration-refugees-citizenship/services/"
    "study-canada/study-permit/prepare/designated-learning-institutions-list.html"
)


def _body_sha256(body: str) -> str:
    """SHA-256 over the NFC-normalized body only."""
    normalized = unicodedata.normalize("NFC", body)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _family_sha256(file_hashes: list[dict]) -> str:
    """Stable family hash over sorted per-file hash records."""
    payload = json.dumps(file_hashes, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
