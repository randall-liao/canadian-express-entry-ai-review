"""Default-profile compatibility shim for downstream importers.

Historically this module held the canada.ca/IRCC site rules (exclusion globs,
chrome-stripping regexes, URL normalization). Those constants now live entirely
in the built-in IRCC profile (``crawler/profiles/ircc.yaml``) and the pure,
profile-driven functions in ``crawler.profile`` (GEN-02: no site-specific
constants in engine source).

This file remains as a thin compatibility shim so existing single-arg call
sites keep working unchanged — notably ``completeness.py``'s
``from crawler.config import clean_markdown``. It binds ``clean_markdown`` and
``normalize_url`` to the default built-in IRCC profile, preserving byte-for-byte
behavior. It imports ONLY the standard library and PyYAML (via ``crawler.profile``)
— never ``crawl4ai`` — so it stays importable under a plain Python.
"""

from __future__ import annotations

from crawler.profile import (
    SiteProfile,
    load_profile,
    clean_markdown as _clean,
    normalize_url as _norm,
)

# The default built-in profile, loaded LAZILY (a profile reference, not a site
# constant): all IRCC-specific rules are read from crawler/profiles/ircc.yaml on
# first use. Loading lazily keeps mere import of this module (e.g. by
# completeness.py) free of filesystem/YAML side effects, so a broken ircc.yaml
# fails at the call site with a clear ProfileError rather than at import time.
_DEFAULT: SiteProfile | None = None


def _default() -> SiteProfile:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = load_profile("ircc")
    return _DEFAULT


def clean_markdown(md: str) -> str:
    """Strip site chrome using the default IRCC profile (single-arg shim)."""
    return _clean(md, _default())


def normalize_url(url: str) -> str:
    """Canonicalize a URL using the default IRCC profile (single-arg shim)."""
    return _norm(url, _default())
