"""Config-driven site profile: schema, loader, fail-fast validation, and the
crawl4ai-free pure functions the engine applies (GEN-02 foundation, GEN-04).

A ``SiteProfile`` describes *everything site-specific* about a crawl target —
allowed domains, URL include/exclude globs, chrome-stripping regexes, slug
neutralization, query-param normalization, and the default source label — so an
operator can target their own authoritative source without editing engine
source. ``load_profile`` reads a profile by built-in name or by file path and
fails fast with a clear, actionable error on any invalid/missing input.

This module imports ONLY the standard library and PyYAML — never ``crawl4ai`` —
so it (and the pure functions ``clean_markdown`` / ``is_excluded`` /
``normalize_url``) import and run under a plain Python with no browser stack.

Security: profiles are parsed with ``yaml.safe_load`` ONLY (never ``yaml.load``)
so a profile cannot instantiate arbitrary Python objects (threat T-13-01).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlsplit, urlunsplit

import yaml

# Generic markdown heading detector (NOT site-specific) — used for nav-section
# level tracking in clean_markdown.
_HEADING_RE = re.compile(r"^(#{1,6})\s")

# Where built-in profiles live (e.g. crawler/profiles/ircc.yaml, authored in
# plan 13-2). Resolved relative to this file so it works from any cwd.
BUILTIN_PROFILES_DIR = Path(__file__).parent / "profiles"

# Required top-level keys and their expected (coarse) Python types after parse.
# allowed_domains, slug_substitutions, and strip_query_params are OPTIONAL and
# default to empty (allowed_domains empty == derive from the seed netloc).
_REQUIRED_FIELDS: dict[str, type] = {
    "name": str,
    "exclude_url_patterns": list,
    "footer_patterns": list,
    "nav_section_patterns": list,
    "residual_line_patterns": list,
    "default_source_type": str,
    "default_label": str,
}
_OPTIONAL_LIST_FIELDS = (
    "allowed_domains",
    "slug_substitutions",
    "strip_query_params",
)


class ProfileError(Exception):
    """Raised for every profile load/validation failure with a clear message."""


@dataclass(frozen=True)
class SiteProfile:
    """A fully-resolved, validated crawl target description.

    The ``*_patterns`` fields keep the raw regex strings (for diagnostics /
    round-tripping); the parallel ``*_regexes`` fields hold the compiled
    ``re.Pattern`` objects the engine actually matches against.
    """

    name: str
    allowed_domains: list[str]
    exclude_url_patterns: list[str]
    slug_substitutions: list[tuple[str, str]]
    strip_query_params: list[str]
    footer_patterns: list[str]
    nav_section_patterns: list[str]
    residual_line_patterns: list[str]
    footer_regexes: list[re.Pattern] = field(default_factory=list)
    nav_section_regexes: list[re.Pattern] = field(default_factory=list)
    residual_line_regexes: list[re.Pattern] = field(default_factory=list)
    default_source_type: str = ""
    default_label: str = ""


def _resolve_source(name_or_path: str) -> Path:
    """Resolve the argument to a YAML file path, or fail fast.

    A value that points at an existing file, or ends in ``.yaml``/``.yml``, is
    treated as a path; anything else is treated as a built-in profile name.
    """
    p = Path(name_or_path)
    looks_like_path = p.exists() or name_or_path.endswith((".yaml", ".yml"))
    if looks_like_path:
        if not p.exists():
            raise ProfileError(f"Profile file not found: {name_or_path}")
        return p

    # Built-in NAME branch: must not escape the profiles directory. Reject path
    # separators / parent refs so a malformed name (e.g. '../../foo') produces a
    # clear "Unknown profile" error instead of resolving outside the dir. An
    # explicit file path (e.g. './x.yaml') is handled by the path branch above.
    if os.sep in name_or_path or ".." in name_or_path or (
        os.altsep and os.altsep in name_or_path
    ):
        raise ProfileError(
            f"Unknown profile '{name_or_path}': built-in profile names cannot "
            f"contain path separators or '..'. Pass a path to a .yaml file to "
            f"use your own."
        )

    candidate = BUILTIN_PROFILES_DIR / f"{name_or_path}.yaml"
    if not candidate.exists():
        if BUILTIN_PROFILES_DIR.exists():
            stems = sorted(x.stem for x in BUILTIN_PROFILES_DIR.glob("*.yaml"))
        else:
            stems = []
        raise ProfileError(
            f"Unknown profile '{name_or_path}'. Built-in profiles: {stems}. "
            f"Pass a path to a .yaml file to use your own."
        )
    return candidate


def _compile_list(raw: list, field_name: str) -> list[re.Pattern]:
    """Compile every regex in a list, failing fast and naming the bad pattern."""
    compiled: list[re.Pattern] = []
    for pat in raw:
        if not isinstance(pat, str):
            raise ProfileError(
                f"Field '{field_name}' must contain only strings; got "
                f"{type(pat).__name__}: {pat!r}"
            )
        try:
            compiled.append(re.compile(pat))
        except re.error as exc:
            raise ProfileError(
                f"Invalid regex in field '{field_name}': {pat!r} ({exc})"
            ) from exc
    return compiled


def load_profile(name_or_path: str) -> SiteProfile:
    """Load and validate a profile by built-in name or by file path.

    Fails fast (``ProfileError``) on: unknown built-in name, missing file,
    malformed YAML, missing/mistyped required field, or an uncompilable regex.
    """
    source = _resolve_source(name_or_path)

    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProfileError(f"Could not read profile file {source}: {exc}") from exc

    try:
        # safe_load ONLY — never yaml.load (threat T-13-01: no arbitrary objects).
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ProfileError(f"Invalid YAML in profile {source}: {exc}") from exc

    if not isinstance(data, dict):
        raise ProfileError(
            f"Profile {source} must be a YAML mapping; got {type(data).__name__}."
        )

    # 1) Required keys present and correctly typed (name the FIRST problem).
    for key, expected_type in _REQUIRED_FIELDS.items():
        if key not in data:
            raise ProfileError(
                f"Profile {source} is missing required field '{key}'."
            )
        if not isinstance(data[key], expected_type):
            raise ProfileError(
                f"Field '{key}' in profile {source} must be "
                f"{expected_type.__name__}; got {type(data[key]).__name__}."
            )

    # 2) Optional list fields default to empty and must be lists when present.
    for key in _OPTIONAL_LIST_FIELDS:
        if key in data and not isinstance(data[key], list):
            raise ProfileError(
                f"Field '{key}' in profile {source} must be a list; got "
                f"{type(data[key]).__name__}."
            )

    # 3) Compile every regex list, naming the offending field + pattern.
    footer_regexes = _compile_list(data["footer_patterns"], "footer_patterns")
    nav_section_regexes = _compile_list(
        data["nav_section_patterns"], "nav_section_patterns"
    )
    residual_line_regexes = _compile_list(
        data["residual_line_patterns"], "residual_line_patterns"
    )

    # 4) Coerce slug_substitutions entries to 2-tuples.
    slug_substitutions: list[tuple[str, str]] = []
    for entry in data.get("slug_substitutions") or []:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            raise ProfileError(
                f"Each slug_substitutions entry in profile {source} must be a "
                f"2-item [from, to] pair; got {entry!r}."
            )
        slug_substitutions.append((str(entry[0]), str(entry[1])))

    return SiteProfile(
        name=data["name"],
        allowed_domains=list(data.get("allowed_domains") or []),
        exclude_url_patterns=list(data["exclude_url_patterns"]),
        slug_substitutions=slug_substitutions,
        strip_query_params=list(data.get("strip_query_params") or []),
        footer_patterns=list(data["footer_patterns"]),
        nav_section_patterns=list(data["nav_section_patterns"]),
        residual_line_patterns=list(data["residual_line_patterns"]),
        footer_regexes=footer_regexes,
        nav_section_regexes=nav_section_regexes,
        residual_line_regexes=residual_line_regexes,
        default_source_type=data["default_source_type"],
        default_label=data["default_label"],
    )


def resolve_allowed_domains(profile: SiteProfile, seed: str) -> list[str]:
    """Domains the crawl may follow (config-driven, GEN-01).

    Honors the profile's explicit ``allowed_domains`` list when it is non-empty
    (so a multi-host profile actually spans its hosts); falls back to the seed
    URL's netloc when the list is empty, preserving the single-site default
    behavior the built-in IRCC profile relies on.
    """
    if profile.allowed_domains:
        return list(profile.allowed_domains)
    return [urlparse(seed).netloc]


def clean_markdown(md: str, profile: SiteProfile) -> str:
    """Strip site chrome from extracted markdown, driven by the profile.

    Ports the CURRENT ``crawler.config.clean_markdown`` algorithm verbatim, but
    with the patterns supplied by the profile so behavior is byte-identical to
    the frozen parity baseline.
    """
    lines = md.splitlines()

    # 1) Truncate at the first footer marker.
    end = len(lines)
    for i, ln in enumerate(lines):
        if any(p.match(ln) for p in profile.footer_regexes):
            end = i
            break
    lines = lines[:end]

    # 2) Drop nav sections (heading + body until the next heading of <= level).
    out: list[str] = []
    skip_level: int | None = None
    for ln in lines:
        m = _HEADING_RE.match(ln)
        lvl = len(m.group(1)) if m else None
        if skip_level is not None:
            if lvl is not None and lvl <= skip_level:
                skip_level = None
            else:
                continue
        if any(p.match(ln) for p in profile.nav_section_regexes):
            skip_level = lvl or 6
            continue
        if any(p.match(ln) for p in profile.residual_line_regexes):
            continue
        out.append(ln)

    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    return cleaned + "\n" if cleaned else ""


def is_excluded(url: str, profile: SiteProfile) -> bool:
    """Return True if the URL is out of scope per the profile's exclude globs.

    Lowercases the URL, applies each slug substitution in order (e.g. neutralize
    the department slug so topic globs don't match it), then fnmatches.
    """
    u = url.lower()
    for src, dst in profile.slug_substitutions:
        u = u.replace(src, dst)
    return any(fnmatch(u, pat) for pat in profile.exclude_url_patterns)


def normalize_url(url: str, profile: SiteProfile) -> str:
    """Canonicalize a URL so duplicate variants collapse to one corpus entry.

    Drops the fragment, removes the profile's ``strip_query_params`` by parsing
    and rebuilding the query string (so removing a first-but-not-only param can
    never leave a malformed ``&foo=bar`` query), then strips a trailing slash.
    """
    parts = urlsplit(url.split("#")[0])
    drop = set(profile.strip_query_params)
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in drop
    ]
    url = urlunsplit(parts._replace(query=urlencode(kept)))
    return url.rstrip("/")
