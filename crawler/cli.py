"""Single console entry point for the corpus crawler pipeline (PKG-02).

This module implements the installed ``corpus-crawler`` command (declared in
``[project.scripts]`` as ``crawler.cli:entrypoint``). It is a THIN argparse
sub-parser dispatcher: every subcommand simply translates the parsed CLI
arguments into the argv list the existing module ``main(argv)`` expects and
forwards the call. No module logic is re-implemented here.

Subcommand → module mapping::

    crawl           → crawler.deepcrawl.main           (LAZY crawl4ai import)
    apply-verdicts  → crawler.apply_verdicts.main
    completeness    → crawler.completeness.main --fetch <corpus>
    report          → crawler.completeness.main --report <corpus>
    index           → crawler.searchindex.build_index  (LAZY sqlite3 import)
    search          → crawler.searchindex.search / resolve  (LAZY sqlite3 import)

Graceful degradation (PKG-02 / threat T-14-05): ``crawler.deepcrawl`` imports
``crawl4ai`` at module top, so it is imported LAZILY inside the ``crawl``
handler only. On a lean install (no ``crawl`` extra) the import fails; we catch
it and print an actionable "install the crawl extra" message to stderr and
return a non-zero exit code instead of letting an unhandled ``ImportError``
crash the whole CLI. The lean subcommands (apply-verdicts / completeness /
report) carry no crawl4ai dependency and run on the core install.

Importing ``crawler.cli`` itself never imports crawl4ai.
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from typing import Sequence

from crawler import contract

# Actionable message shown when the optional crawl driver is missing. Names the
# exact step so a user can copy/paste the fix. Parameterized by command name
# (WR-04) so e.g. the `completeness` path does not wrongly claim it is `crawl`.
def _crawl_extra_hint(step: str = "crawl") -> str:
    return (
        f"The '{step}' step requires the optional crawl driver (crawl4ai), "
        "which is not installed. Install it with:\n"
        "    pip install 'corpus-crawler[crawl]'\n"
        "  (or, in a Poetry checkout: poetry install --extras crawl)"
    )


def _cmd_crawl(args: argparse.Namespace) -> int:
    """Dispatch to crawler.deepcrawl.main with a LAZY crawl4ai import.

    deepcrawl imports crawl4ai at module top, so importing it here (not at CLI
    module top) keeps the whole CLI usable on a lean install and lets us turn a
    missing optional dependency into an actionable error + non-zero exit.

    In --json mode the SAME missing-dependency condition becomes a machine-readable
    error envelope on stdout (error.type == "missing_dependency") + exit 3, while
    the human hint still goes to stderr.
    """
    try:
        from crawler import deepcrawl
    except ImportError as exc:  # ModuleNotFoundError is a subclass
        # Only claim "install the crawl extra" when crawl4ai itself is the
        # missing module. deepcrawl also imports crawler.profile / crawler.pipeline
        # transitively; an ImportError from those is a genuine bug that must
        # surface, not be disguised as a missing optional dependency.
        missing = (getattr(exc, "name", "") or "")
        if missing.split(".")[0] == "crawl4ai":
            # Human hint always to stderr (json and non-json alike).
            hint = _crawl_extra_hint("crawl")
            print(hint, file=sys.stderr)
            print(f"(import error: {exc})", file=sys.stderr)
            if args.json:
                contract.emit(contract.envelope(
                    "crawl",
                    error=(contract.MISSING_DEPENDENCY, hint)))
            return contract.EXIT_MISSING_DEPENDENCY
        raise  # genuine import bug — surface it, don't mislabel it

    if args.json:
        # --json mode: call the COMPUTE layer directly (NOT deepcrawl.main, which
        # prints human text to stdout) so stdout stays pure JSON. deepcrawl's own
        # progress goes to stderr already.
        import asyncio
        from pathlib import Path
        from crawler.deepcrawl import load_profile

        # WR-03: source the crawl defaults from deepcrawl's single constants
        # (NOT duplicated literals) so the --json path can never diverge from the
        # default-mode path if a default changes.
        profile_name = args.profile if args.profile is not None else deepcrawl.DEFAULT_PROFILE
        profile = load_profile(profile_name)
        source_type = args.source_type or profile.default_source_type
        label = args.label or profile.default_label
        depth = args.depth if args.depth is not None else deepcrawl.DEFAULT_DEPTH
        max_pages = args.max_pages if args.max_pages is not None else deepcrawl.DEFAULT_MAX_PAGES
        # stdout purity guard (WR-01): crawl4ai's AsyncWebCrawler may log progress
        # to STDOUT by default, which would corrupt the single-JSON-object
        # contract. Redirect ANY stdout writes during the crawl to stderr; the
        # envelope below is then emitted to the REAL stdout.
        with contextlib.redirect_stdout(sys.stderr):
            stats = asyncio.run(deepcrawl.crawl(
                args.seed, depth, max_pages, Path(args.out),
                profile, source_type, label, args.include_pattern))
        result = {
            "recorded": stats["recorded"],
            "skipped_stub": stats["skipped_stub"],
            "skipped_scope": stats["skipped_scope"],
            "skipped_dup": stats["skipped_dup"],
            "out": stats["out"],
            "profile": profile_name,
            "seed": args.seed,
        }
        contract.emit(contract.envelope("crawl", result=result))
        return 0

    # Non-json (default): unchanged — forward only supplied flags so deepcrawl
    # owns its own defaults and the two cannot silently diverge.
    forwarded: list[str] = ["--seed", args.seed, "--out", args.out]
    if args.depth is not None:
        forwarded += ["--depth", str(args.depth)]
    if args.max_pages is not None:
        forwarded += ["--max-pages", str(args.max_pages)]
    if args.profile is not None:
        forwarded += ["--profile", args.profile]
    if args.source_type is not None:
        forwarded += ["--source-type", args.source_type]
    if args.include_pattern is not None:
        forwarded += ["--include", args.include_pattern]
    if args.label is not None:
        forwarded += ["--label", args.label]
    return deepcrawl.main(forwarded)


def _cmd_apply_verdicts(args: argparse.Namespace) -> int:
    from pathlib import Path

    from crawler import apply_verdicts

    if args.json:
        corpus = Path(args.corpus_dir)
        if not corpus.is_dir():
            contract.emit(contract.envelope(
                "apply-verdicts",
                error=(contract.INVALID_INPUT, f"not a directory: {corpus}")))
            return contract.EXIT_INVALID_INPUT
        res = apply_verdicts.apply(corpus, dry_run=args.dry_run)
        result = {
            "dropped": res["dropped"],
            "kept": res["live_remaining"],
            "dry_run": bool(args.dry_run),
            "out": str(corpus),
        }
        contract.emit(contract.envelope("apply-verdicts", result=result))
        return 0

    forwarded: list[str] = [args.corpus_dir]
    if args.dry_run:
        forwarded.append("--dry-run")
    return apply_verdicts.main(forwarded)


def _cmd_completeness(args: argparse.Namespace) -> int:
    from pathlib import Path

    from crawler import completeness

    if args.json:
        corpus = Path(args.corpus_dir)
        if not corpus.is_dir():
            contract.emit(contract.envelope(
                "completeness",
                error=(contract.INVALID_INPUT, f"not a directory: {corpus}")))
            return contract.EXIT_INVALID_INPUT
        try:
            # stdout purity guard (WR-01): the re-fetch path also drives crawl4ai,
            # which may write progress to STDOUT. Keep stdout pure JSON by routing
            # any such writes to stderr for the duration of the fetch.
            with contextlib.redirect_stdout(sys.stderr):
                res = completeness.run_fetch(corpus, args.fraction)
        except completeness.NoLiveDocsError as exc:
            contract.emit(contract.envelope(
                "completeness", error=(contract.INVALID_INPUT, str(exc))))
            return contract.EXIT_INVALID_INPUT
        except ImportError as exc:
            # crawl4ai missing surfaces at asyncio.run time → missing_dependency.
            missing = (getattr(exc, "name", "") or "")
            if missing.split(".")[0] == "crawl4ai":
                hint = _crawl_extra_hint("completeness --fetch")
                print(hint, file=sys.stderr)
                contract.emit(contract.envelope(
                    "completeness",
                    error=(contract.MISSING_DEPENDENCY, hint)))
                return contract.EXIT_MISSING_DEPENDENCY
            raise
        result = {
            "sampled": res["sampled"],
            "total_live": res["total_live"],
            "fraction": res["fraction"],
            "out": res["out"],
        }
        contract.emit(contract.envelope("completeness", result=result))
        return 0

    return completeness.main(["--fetch", args.corpus_dir,
                              "--fraction", str(args.fraction)])


def _cmd_report(args: argparse.Namespace) -> int:
    from pathlib import Path

    from crawler import completeness

    if args.json:
        corpus = Path(args.corpus_dir)
        if not corpus.is_dir():
            contract.emit(contract.envelope(
                "report",
                error=(contract.INVALID_INPUT, f"not a directory: {corpus}")))
            return contract.EXIT_INVALID_INPUT
        summary = completeness.build_report(corpus)
        # A FAIL verdict is NOT an execution error: emit ok:true with
        # result.verdict and preserve the established exit code 1. ``error`` is
        # reserved for execution failures (missing dep / bad input).
        result = {
            "verdict": summary["verdict"],
            "out": summary["out"],
            "recorded": summary["recorded"],
            "live_docs": summary["live_docs"],
            "passed": summary["passed"],
            "failed": summary["failed"],
            "drop": summary["drop"],
            "incomplete": summary["incomplete"],
        }
        contract.emit(contract.envelope("report", result=result))
        # Exit 0 iff verdict == pass; exit 1 for ANY non-pass verdict (fail OR
        # incomplete). The precise verdict is always in result.verdict (WR-02);
        # exit 1 is only a coarse "not pass" signal, never an execution error.
        return 0 if summary["overall_pass"] else 1

    return completeness.main(["--report", args.corpus_dir])


def _cmd_index(args: argparse.Namespace) -> int:
    """Build/rebuild the FTS5 keyword index over the clean corpus.

    Thin dispatcher (no compute here): validate the corpus dir, LAZY-import
    ``searchindex`` (so importing ``crawler.cli`` never drags ``sqlite3``/index
    setup), forward to ``searchindex.build_index``, and emit exactly one CONTRACT
    envelope. ``build_index`` is the compute layer (Plan 02); this handler only
    validates inputs, maps a missing-FTS5 host to a loud non-zero envelope, and
    keeps stdout pure JSON (the human summary always goes to stderr).
    """
    from pathlib import Path

    from crawler import searchindex

    corpus = Path(args.corpus_dir)
    if not corpus.is_dir():
        msg = f"not a directory: {corpus}"
        if args.json:
            contract.emit(contract.envelope(
                "index",
                error=(contract.INVALID_INPUT, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return contract.EXIT_INVALID_INPUT

    try:
        result = searchindex.build_index(corpus, Path(args.db))
    except searchindex.FTS5Unavailable as exc:
        # Host SQLite lacks FTS5 → fail loud, actionable, non-zero (RET-01 SC4 /
        # RETRIEVAL.md §7 P1). The probe message carries the ENABLE_FTS5 remediation.
        if args.json:
            contract.emit(contract.envelope(
                "index",
                error=(contract.MISSING_DEPENDENCY, str(exc))))
        else:
            print(str(exc), file=sys.stderr)
        return contract.EXIT_MISSING_DEPENDENCY

    if args.json:
        contract.emit(contract.envelope("index", result=result))
    else:
        # Human summary to STDERR ONLY (never stdout — RETRIEVAL.md §7 P11).
        print(
            f"indexed {result['docs']} docs → {result['chunks']} chunks "
            f"into {result['db']}",
            file=sys.stderr)
    return 0


def _cmd_refresh_dli(args: argparse.Namespace) -> int:
    """Refresh the pinned IRCC DLI/PGWP snapshot family (STUDY-01 operator surface).

    Thin dispatcher (no compute here): LAZY-import ``dli_snapshot`` (so importing
    ``crawler.cli`` never triggers urllib/network setup), fetch the FIXED IRCC
    endpoint (the network happens ONLY inside ``dli_snapshot.fetch`` — the verb
    exposes NO ``--url``/``--out``/``--from-file``, so there is no SSRF or
    arbitrary-output surface: T-41-02), derive the deterministic ``as_of`` from the
    upstream ``Last-Modified``, strictly validate + canonicalize, then atomically
    (re)write ONLY ``corpus/dli/``.

    A fetch failure (``URLError``/timeout/``OSError``), a ``fetch``-stage refusal
    (the T-41-01 size-ceiling ``SchemaError`` or a decode/JSON fault from a
    non-JSON/truncated CDN response, which ``fetch`` normalizes to ``SchemaError``),
    or an ``as_of``/``normalize`` ``SchemaError`` (empty/truncated/missing-field/
    invalid-PGWP and a missing/unparseable ``Last-Modified``) each becomes a
    machine-readable ``invalid_input`` envelope + exit 2, while the prior healthy
    ``corpus/dli/`` family is preserved byte-for-byte (``dli_snapshot.write`` is
    never reached on a refusal — mirrors ``_cmd_index``'s ``FTS5Unavailable``
    branch). The ``--json`` ``result`` is PII-free provenance ONLY (public counts /
    as_of / family hash).
    """
    import json
    import urllib.error
    from pathlib import Path

    from crawler import dli_snapshot

    try:
        # Fixed authoritative IRCC endpoint; network egress happens ONLY here.
        payload, last_modified = dli_snapshot.fetch()
    except (urllib.error.URLError, TimeoutError, OSError,
            dli_snapshot.SchemaError,
            UnicodeDecodeError, json.JSONDecodeError) as exc:
        # fetch() maps its OWN refusals — the T-41-01 size-ceiling SchemaError and
        # decode/JSON faults from a non-JSON/truncated CDN response — to the SAME
        # invalid_input/exit 2 envelope as a transport failure, so a DoS-guard
        # refusal is never mislabeled internal_error and human mode never crashes
        # with a raw traceback. (UnicodeDecodeError/JSONDecodeError are kept in the
        # tuple as belt-and-suspenders in case a caller bypasses fetch's own
        # normalization.) write() is still never reached, so a prior healthy family
        # is preserved byte-for-byte (CR-01).
        msg = f"could not fetch DLI dataset: {exc}"
        if args.json:
            contract.emit(contract.envelope(
                "refresh-dli",
                error=(contract.INVALID_INPUT, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return contract.EXIT_INVALID_INPUT

    try:
        as_of = dli_snapshot.as_of_from(last_modified)
        docs = dli_snapshot.normalize(payload, as_of=as_of)
    except dli_snapshot.SchemaError as exc:
        # Fail-closed on ANY drift/refusal (mirror _cmd_index FTS5Unavailable branch):
        # invalid_input + exit 2, and write() is never reached so a prior healthy
        # family stays byte-for-byte intact.
        msg = f"DLI dataset failed schema validation: {exc}"
        if args.json:
            contract.emit(contract.envelope(
                "refresh-dli",
                error=(contract.INVALID_INPUT, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return contract.EXIT_INVALID_INPUT

    # Fixed family root; atomic full-family replace + manifest (41-01).
    result = dli_snapshot.write(docs, out_dir=Path("corpus/dli"))
    if args.json:
        contract.emit(contract.envelope("refresh-dli", result={
            "out": "corpus/dli",
            "institutions": result["docs"],
            "campuses": result["rows"],
            "as_of": as_of,
            "family_sha256": result["family_sha256"],  # PII-free provenance only
        }))
    else:
        # Human summary to STDERR ONLY (stdout stays pure JSON when --json).
        print(
            f"dli: {result['docs']} institutions / {result['rows']} campuses "
            f"as_of={as_of} → corpus/dli",
            file=sys.stderr)
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    """BM25-search the FTS5 index, or resolve a citation id with ``--cite``.

    Thin dispatcher (no compute here): validate the ``--db`` path, LAZY-import
    ``searchindex`` (so importing ``crawler.cli`` never drags ``sqlite3``),
    dispatch to ``searchindex.search`` (default ranked mode) or
    ``searchindex.resolve`` (``--cite`` mode), map ``EmptyQuery`` → invalid_input
    (exit 2) and ``FTS5Unavailable`` → missing_dependency (exit 3), and emit
    exactly one CONTRACT envelope. The human summary always goes to stderr; in
    ``--json`` mode stdout stays pure JSON (RETRIEVAL.md §7 P11). All compute lives
    in ``searchindex`` (Plans 01/02); this handler only validates + routes.

    A ``--cite`` miss / stale id is a NORMAL fail-closed result (``result.found =
    false``, ``chunk: null``, exit 0), NOT an execution error — it mirrors the
    ``report`` verdict-fail rule (CONTRACT.md). ``resolve()`` never raises on a miss
    and needs no FTS5, so the ``--cite`` path has no FTS5Unavailable catch.
    """
    from pathlib import Path

    from crawler import searchindex

    db = Path(args.db)
    if not db.is_file():
        msg = f"not a file: {db}"
        if args.json:
            contract.emit(contract.envelope(
                "search",
                error=(contract.INVALID_INPUT, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return contract.EXIT_INVALID_INPUT

    # `query` and --cite are mutually exclusive modes. Supplying both is ambiguous;
    # silently discarding the positional query (the old behavior) can mask an
    # operator mistake, so reject it as invalid_input (IN-02).
    if args.cite is not None and args.query is not None:
        msg = "pass either a query or --cite, not both"
        if args.json:
            contract.emit(contract.envelope(
                "search",
                error=(contract.INVALID_INPUT, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return contract.EXIT_INVALID_INPUT

    # --cite mode: resolve ONE chunk_id to its exact chunk. A miss / content-drifted
    # (stale) id is fail-closed (found:false / chunk:null / exit 0), NOT an error —
    # the Phase-25 grounding gate reads found/chunk to reject ungrounded citations
    # (RET-02 SC2). resolve() never raises on a miss and needs no FTS5 → no catch.
    if args.cite is not None:
        hit = searchindex.resolve(db, args.cite)
        result = {
            "found": hit is not None,
            "chunk_id": args.cite,
            "db": str(db),
            "chunk": hit,
        }
        if args.json:
            contract.emit(contract.envelope("search", result=result))
        else:
            # Human one-line summary to STDERR ONLY (never stdout — RETRIEVAL.md P11).
            print(f"found {args.cite}" if hit is not None
                  else f"not found: {args.cite}", file=sys.stderr)
        return 0

    # default ranked-search mode: argparse makes `query` optional so --cite can omit
    # it; require it here when we are NOT in --cite mode.
    if args.query is None:
        msg = "a query or --cite is required"
        if args.json:
            contract.emit(contract.envelope(
                "search",
                error=(contract.INVALID_INPUT, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return contract.EXIT_INVALID_INPUT

    # --limit feeds SQLite `LIMIT ?`, where a NEGATIVE value means "no limit"
    # (so --limit -1 would silently disable the cap and return every hit). Reject
    # any non-positive limit at the boundary as invalid_input (IN-01).
    if args.limit < 1:
        msg = f"--limit must be a positive integer (got {args.limit})"
        if args.json:
            contract.emit(contract.envelope(
                "search",
                error=(contract.INVALID_INPUT, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return contract.EXIT_INVALID_INPUT

    try:
        result = searchindex.search(db, args.query, args.limit, args.family)
    except searchindex.EmptyQuery as exc:
        # Empty / all-punctuation query (Plan 01) → never run an empty MATCH
        # (RET-02 SC3). Reject at the boundary as invalid_input, exit 2.
        if args.json:
            contract.emit(contract.envelope(
                "search",
                error=(contract.INVALID_INPUT, str(exc))))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return contract.EXIT_INVALID_INPUT
    except searchindex.FTS5Unavailable as exc:
        # Host SQLite lacks FTS5 → fail loud, actionable, non-zero (RETRIEVAL.md P1).
        if args.json:
            contract.emit(contract.envelope(
                "search",
                error=(contract.MISSING_DEPENDENCY, str(exc))))
        else:
            print(str(exc), file=sys.stderr)
        return contract.EXIT_MISSING_DEPENDENCY

    if args.json:
        contract.emit(contract.envelope("search", result=result))
    else:
        # Human summary to STDERR ONLY (never stdout — RETRIEVAL.md §7 P11).
        print(f"{result['count']} hits for {result['query']!r}", file=sys.stderr)
    return 0


def _personal_root() -> "Path":
    """Resolved git-ignored PII-containment boundary: ``<repo-root>/personal``.

    The ``ground`` write-gate confines a passing answer's rendered markdown — which
    embeds VERBATIM corpus chunk text (and, for a personal/trial corpus, potentially
    sensitive content) — to this directory ONLY. Exposed as a module-level function
    so the anchored ``--out-dir`` containment check (CR-03) is testable without ever
    writing under the real repo tree (tests monkeypatch it at a tempdir).

    ``crawler/cli.py`` lives at ``<repo-root>/crawler/cli.py`` so ``parents[1]`` is
    the repo root; ``.resolve()`` collapses symlinks / ``..`` so the containment
    check below compares two fully-resolved absolute paths.

    Centralized (Phase 29): delegates to the shared ``paths.repo_personal_root()``
    — the SAME unconditional ``<repo-root>/personal`` anchor. Kept a module-level
    function so test_grounding/test_checklist can still monkeypatch it. Deliberately
    routed to ``repo_personal_root`` (NOT the env-aware ``personal_root``) so the
    frozen v3.x write-gate stays anchored to ``<repo>/personal`` regardless of
    ``$PR_PERSONAL_DIR``.
    """
    from crawler import paths
    return paths.repo_personal_root()


def _cmd_ground(args: argparse.Namespace) -> int:
    """Fail-closed grounding gate: read one structured answer JSON from stdin (GND-02).

    Thin dispatcher (ALL compute lives in ``crawler.grounding`` — Plan 01): read ONE
    answer object from ``sys.stdin``, validate ``--db``, dispatch to
    ``grounding.check_answer``, and map the outcome to the frozen JSON contract:

    * ``--eval <questions.jsonl>`` (eval-harness mode, Plan 03) runs the SAME per-claim
      gate over each stored answer line in a reference set and emits the locked
      ``eval_runner``-shaped ``{total, passed, failed, failures}`` summary inside a
      ``ground`` envelope (``ok:true``); exits ``1`` if ANY line is ungrounded. This
      branch is checked BEFORE any stdin read (eval mode never blocks on stdin);

    * a grounding ``verdict:"fail"`` (any uncited / unresolvable / quote-mismatch claim)
      is an EXPECTED verdict, NOT an execution error — emit ``ok:true`` with
      ``result.verdict:"fail"`` and exit ``1``, rendering/writing NOTHING (mirrors
      ``_cmd_report`` :223-240 / ``dupclean`` ``return 1 if verdict == "fail" else 0``);
    * a ``verdict:"pass"`` answer is rendered, RPT-03 publish-safety-scanned, and written
      ONLY under git-ignored ``personal/output/`` (exit ``0``). A scan hit is a deliberate
      fail-closed refusal → ``ok:false`` / ``internal_error`` / exit ``4`` (REUSE of the
      existing code, distinguished by the ``refusing to write answer: …`` message — branch
      on ``error.type`` + message, never the bare code), writing NOTHING;
    * malformed stdin / a missing-key answer / a non-file ``--db`` / an ``--out-dir`` outside
      ``personal/`` → ``invalid_input`` / exit ``2``.

    Keeps stdout pure JSON in ``--json`` mode; every human/progress line goes to stderr.
    All compute is LAZY-imported so importing ``crawler.cli`` stays cheap.
    """
    import json
    import re
    import sys
    from pathlib import Path

    from crawler import grounding

    def _fail(err_type: str, msg: str, code: int) -> int:
        # One envelope to stdout in --json mode; the human line goes to stderr only.
        if args.json:
            contract.emit(contract.envelope("ground", error=(err_type, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return code

    db = Path(args.db)
    if not db.is_file():
        return _fail(contract.INVALID_INPUT, f"not a file: {db}",
                     contract.EXIT_INVALID_INPUT)

    # Eval-harness mode (Plan 03): run the SAME per-claim gate over a stored reference
    # set instead of stdin. Checked BEFORE any stdin read (eval mode must never block on
    # stdin). An ungrounded fixture line is a VERDICT (ok:true, in failures, exit 1), not
    # an execution error — same rule as the single-answer verdict-fail path below.
    if args.eval is not None:
        questions = Path(args.eval)
        if not questions.is_file():
            return _fail(contract.INVALID_INPUT, f"not a file: {questions}",
                         contract.EXIT_INVALID_INPUT)
        summary, code = grounding.run_eval(db, questions)
        if args.json:
            contract.emit(contract.envelope("ground", result=summary))
        else:
            print(f"eval: {summary['passed']}/{summary['total']} passed, "
                  f"{summary['failed']} failed", file=sys.stderr)
            for failure in summary["failures"]:
                print(f"  \u2717 {failure['id']}: {', '.join(failure['reasons'])}",
                      file=sys.stderr)
        return code

    # Untrusted structured-answer JSON arrives on stdin. A parse failure is bad input
    # (exit 2), the same shape as the EmptyQuery catch in _cmd_search (:386-395).
    try:
        answer = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _fail(contract.INVALID_INPUT, f"bad stdin JSON: {exc}",
                     contract.EXIT_INVALID_INPUT)

    # A malformed shape (not a dict / missing question / a claim missing a key) is bad
    # input (exit 2); a well-formed-but-ungrounded answer is a verdict (below), not this.
    try:
        result = grounding.check_answer(answer, db)
    except grounding.InvalidAnswer as exc:
        return _fail(contract.INVALID_INPUT, str(exc), contract.EXIT_INVALID_INPUT)

    # A grounding fail is an EXPECTED verdict, NOT an execution error: ok:true +
    # result.verdict:"fail" + exit 1, render/write NOTHING (mirror _cmd_report:223-240).
    if result["verdict"] != "pass":
        if args.json:
            contract.emit(contract.envelope("ground", result=result))
        else:
            print(f"verdict: {result['verdict']} "
                  f"({result['ungrounded']}/{result['total_claims']} ungrounded)",
                  file=sys.stderr)
        return 1

    # verdict == pass → render → RPT-03 scan → write to git-ignored personal/output/ ONLY.
    # CR-03: confine output to the REPO's git-ignored personal/ boundary by ANCHORED
    # containment — the resolved --out-dir must equal or be nested under
    # <repo-root>/personal. The old check only required SOME path component literally
    # named "personal", so /tmp/personal/evil, ~/personal, /var/www/personal/pub all
    # passed and rendered verbatim corpus text could be written OUTSIDE any .gitignore
    # protection. Reject anything not truly contained (invalid_input, exit 2).
    out_dir = Path(args.out_dir)
    repo_personal = _personal_root()
    resolved = out_dir.resolve()
    if resolved != repo_personal and repo_personal not in resolved.parents:
        return _fail(contract.INVALID_INPUT,
                     f"--out-dir must resolve under {repo_personal}: {out_dir}",
                     contract.EXIT_INVALID_INPUT)

    rendered_md = grounding.render_answer(answer, db)

    # Deterministic question-derived filename (cosmetic; containment is the real control).
    slug = re.sub(r"[^a-z0-9]+", "-", str(answer.get("question", "")).lower()).strip("-")
    out_path = out_dir / ((slug[:60] or "answer") + ".md")

    # RPT-03 render-then-gate: scan the EXACT rendered bytes BEFORE any write. scripts/ is
    # NOT a package → sys.path shim then top-level import (mirrors dupclean.py:478-482).
    _scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
    import check_publish_safe as cps  # RPT-03 share-safety gate

    # WR-01: scan under a NEUTRAL, never-excluded label — NOT the destination path.
    # scan_text(path, ...) first calls is_excluded(path) and returns [] for any path
    # under scripts/tests/ or .github/ (the repo-tree publish-scan exclusions). Feeding
    # the destination path in meant an --out-dir like scripts/tests/personal would
    # self-exclude and SKIP the scan entirely. The write-gate must ALWAYS scan the
    # rendered bytes regardless of where they will be written, so we pass a fixed,
    # never-excluded label ("answer.md"); the real out_path is reported separately.
    violations = cps.scan_text("answer.md", rendered_md)
    if violations:
        # A publish-safety hit is a deliberate fail-closed refusal — REUSE the existing
        # internal_error/exit 4 (distinguished by the message), writing NOTHING. Wording
        # is identical to dupaudit/dupclean so agents can grep it.
        msg = f"refusing to write answer: {len(violations)} publish-safety violation(s)"
        if args.json:
            contract.emit(contract.envelope(
                "ground", error=(contract.INTERNAL_ERROR, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return contract.EXIT_INTERNAL_ERROR

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered_md, encoding="utf-8")
    result["out"] = str(out_path)
    if args.json:
        contract.emit(contract.envelope("ground", result=result))
    else:
        # Human summary to STDERR ONLY (never stdout — RETRIEVAL.md §7 P11).
        print(f"verdict: pass → wrote {out_path}", file=sys.stderr)
    return 0


def _cmd_checklist(args: argparse.Namespace) -> int:
    """Personalized, fully-cited Layer-1 document checklist from a local profile (CHK-01).

    Thin dispatcher reusing the EXACT ``_cmd_ground`` trust path (no re-implementation):
    read ``$PR_PERSONAL_DIR/profile.yaml`` (or ``--profile <dir>``), assemble the
    Phase-25 answer object via ``checklist.build_answer`` (PII confined to ``basis[]`` by
    construction), gate it through ``grounding.check_answer``, and map the outcome to the
    frozen JSON contract under the additive ``checklist`` command value:

    * a grounding ``verdict:"fail"`` is an EXPECTED verdict, NOT an execution error —
      emit ``ok:true`` with ``result.verdict:"fail"`` and exit ``1``, writing NOTHING
      (mirrors ``_cmd_ground`` :514-523);
    * a ``verdict:"pass"`` answer is rendered (``grounding.render_answer`` — claims +
      verbatim quote + citation ONLY, never ``basis[]`` → PII-free by construction),
      RPT-03 publish-safety-scanned under a NEUTRAL never-excluded label, and written
      ONLY under the git-ignored, repo-anchored ``personal/output/`` boundary (exit ``0``).
      A scan hit is a deliberate fail-closed refusal → ``ok:false`` / ``internal_error`` /
      exit ``4`` (REUSE of the existing code, distinguished by the
      ``refusing to write checklist: …`` message), writing NOTHING;
    * a missing/non-mapping ``profile.yaml`` / a non-file ``--db`` / an ``--out-dir``
      outside ``<repo>/personal`` → ``invalid_input`` / exit ``2``;
    * ``--emit-answer`` prints the assembled answer JSON to stdout and returns ``0``
      WITHOUT gating/rendering/writing (composability — pipe straight into ``ground``);
      the PII-bearing ``basis[]`` is REDACTED to an empty list first (WR-02) since
      stdout is neither publish-safety-scanned nor confined to ``personal/``.

    Keeps stdout pure JSON in ``--json`` mode; every human/progress line goes to stderr.
    All compute is LAZY-imported so importing ``crawler.cli`` stays cheap.
    """
    import json
    import re
    import sys
    from pathlib import Path

    from crawler import checklist, grounding

    def _fail(err_type: str, msg: str, code: int) -> int:
        # One envelope to stdout in --json mode; the human line goes to stderr only.
        if args.json:
            contract.emit(contract.envelope("checklist", error=(err_type, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return code

    db = Path(args.db)
    if not db.is_file():
        return _fail(contract.INVALID_INPUT, f"not a file: {db}",
                     contract.EXIT_INVALID_INPUT)

    # Resolve the profile root: an explicit --profile dir, else $PR_PERSONAL_DIR /
    # ./personal/ (checklist.personal_dir). load_profile reads <root>/profile.yaml with
    # yaml.safe_load ONLY and fails fast; a missing/non-mapping profile is bad input
    # (exit 2) — mirrors how _cmd_ground maps grounding.InvalidAnswer.
    root = Path(args.profile) if args.profile else checklist.personal_dir()
    try:
        profile = checklist.load_profile(root)
    except checklist.ProfileError as exc:
        return _fail(contract.INVALID_INPUT, str(exc), contract.EXIT_INVALID_INPUT)

    # Assemble + gate-by-construction (PII confined to basis[]; ungroundable items demoted
    # to explicit abstentions). The returned answer always verifies `pass` by design.
    answer = checklist.build_answer(profile, db)

    # Composability escape hatch: emit the raw answer JSON and stop — no gate/render/write.
    # Keeps stdout a single json.loads-able object so it pipes straight into `ground`.
    if getattr(args, "emit_answer", False):
        # WR-02 PII BOUNDARY: --emit-answer streams to UNSCANNED, UNCONTAINED stdout
        # (the doc invites `checklist --emit-answer | ground`). The assembled
        # answer's basis[] is the PII tier (residence countries/counts/etc.), and
        # the downstream `ground` gate inspects claims[] ONLY — basis[] is never
        # citation-checked. So emit a PII-FREE answer: keep question + claims[]
        # (generic labels + verbatim corpus quotes) and the PII-free
        # abstentions/prose, but REDACT basis[] to an empty list. The result still
        # validates against grounding's shape and pipes straight into `ground`,
        # while no profile-derived byte ever reaches stdout.
        safe_answer = dict(answer)
        safe_answer["basis"] = []
        print(json.dumps(safe_answer, ensure_ascii=False))
        return 0

    # Re-run the shipped Phase-25 gate over the assembled answer. A grounding fail is an
    # EXPECTED verdict, NOT an execution error: ok:true + result.verdict:"fail" + exit 1,
    # render/write NOTHING (mirror _cmd_ground:514-523).
    result = grounding.check_answer(answer, db)
    if result["verdict"] != "pass":
        if args.json:
            contract.emit(contract.envelope("checklist", result=result))
        else:
            print(f"verdict: {result['verdict']} "
                  f"({result['ungrounded']}/{result['total_claims']} ungrounded)",
                  file=sys.stderr)
        return 1

    # verdict == pass → render → RPT-03 scan → write to git-ignored personal/output/ ONLY.
    # CR-03: confine output to the REPO's git-ignored personal/ boundary by ANCHORED
    # containment — the resolved --out-dir must equal or be nested under <repo>/personal
    # (reuse _personal_root verbatim). Reject anything not truly contained (exit 2).
    out_dir = Path(args.out_dir)
    repo_personal = _personal_root()
    resolved = out_dir.resolve()
    if resolved != repo_personal and repo_personal not in resolved.parents:
        return _fail(contract.INVALID_INPUT,
                     f"--out-dir must resolve under {repo_personal}: {out_dir}",
                     contract.EXIT_INVALID_INPUT)

    rendered_md = grounding.render_answer(answer, db)

    # Deterministic filename (cosmetic; the anchored containment is the real control).
    out_path = out_dir / "checklist.md"

    # RPT-03 render-then-gate: scan the EXACT rendered bytes BEFORE any write. scripts/ is
    # NOT a package → sys.path shim then top-level import (mirrors _cmd_ground:546-551).
    _scripts_dir = str(Path(__file__).resolve().parents[1] / "scripts")
    if _scripts_dir not in sys.path:
        sys.path.insert(0, _scripts_dir)
    import check_publish_safe as cps  # RPT-03 share-safety gate

    # WR-01: scan under a NEUTRAL, never-excluded label ("checklist.md") — NOT the
    # destination path (an --out-dir under scripts/tests/ would self-exclude and SKIP
    # the scan). The write-gate must ALWAYS scan the rendered bytes.
    violations = cps.scan_text("checklist.md", rendered_md)
    if violations:
        # A publish-safety hit is a deliberate fail-closed refusal — REUSE the existing
        # internal_error/exit 4 (distinguished by the message), writing NOTHING.
        msg = (f"refusing to write checklist: {len(violations)} "
               "publish-safety violation(s)")
        if args.json:
            contract.emit(contract.envelope(
                "checklist", error=(contract.INTERNAL_ERROR, msg)))
        else:
            print(f"error: {msg}", file=sys.stderr)
        return contract.EXIT_INTERNAL_ERROR

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered_md, encoding="utf-8")
    result["out"] = str(out_path)
    if args.json:
        contract.emit(contract.envelope("checklist", result=result))
    else:
        # Human summary to STDERR ONLY (never stdout — RETRIEVAL.md §7 P11).
        print(f"verdict: pass → wrote {out_path}", file=sys.stderr)
    return 0


# --------------------------------------------------------------------------- #
# vault — additive candidate-vault verbs (Phase 29 — VAULT-01/02/03). Every
# --json result is PII-LIGHT (ids/counts/statuses/relative vault paths only);
# detailed values stay in vault.sqlite, never on stdout (locked constraint).
# All compute lives in crawler.vault (LAZY-imported so importing crawler.cli
# stays cheap and never drags pydantic onto a non-vault call).
# --------------------------------------------------------------------------- #
def _vault_fail(args: argparse.Namespace, err_type: str, msg: str, code: int) -> int:
    """Emit ONE PII-safe error envelope to stdout (--json) or a line to stderr."""
    if args.json:
        contract.emit(contract.envelope("vault", error=(err_type, msg)))
    else:
        print(f"error: {msg}", file=sys.stderr)
    return code


def _vault_ok(args: argparse.Namespace, result: dict, human: str) -> int:
    """Emit ONE success envelope to stdout (--json) or a human line to stderr."""
    if args.json:
        contract.emit(contract.envelope("vault", result=result))
    else:
        print(human, file=sys.stderr)
    return 0


def _require_readable_index(args: argparse.Namespace, db) -> "int | None":
    """Preflight the corpus index; return an exit code on refusal, else None (HARD-01/02).

    Reused by every verb that grounds against the corpus index (``vault audit`` now;
    ``remediate`` / ``review-packet`` in Phases 37-38). A missing / empty / unreadable
    / corrupt / content-drifted index becomes ONE PII-free refusal on the frozen
    ``invalid_input`` vocabulary (exit 2 — the same code ``search``/``ground`` return
    for a bad ``--db``) carrying a specific ``reason=<code>`` token and the
    ``index``/``doctor`` recovery hint. Refusing here — BEFORE any ``open_vault`` or
    audit compute — guarantees zero audit / remediation / packet / database artifacts.
    """
    from crawler import index_health
    health = index_health.probe_index(db)
    if health.ok():
        return None
    return _vault_fail(args, contract.INVALID_INPUT, health.message(db),
                       contract.EXIT_INVALID_INPUT)


def _require_readable_snapshot(args: argparse.Namespace, db, family,
                               max_age_days) -> "int | None":
    """Preflight a REQUIRED corpus *family* snapshot; exit code on refusal, else None (SAFE-10).

    A strict additive mirror of :func:`_require_readable_index` for a fresh/consistent
    DLI-style snapshot family. A missing / empty / unreadable / corrupt / content-drifted
    / STALE family becomes ONE PII-free refusal on the frozen ``invalid_input`` vocabulary
    (exit 2 — the same code ``search``/``ground``/``vault audit`` return for a bad ``--db``)
    carrying a stable ``reason=snapshot_<code>`` token. A healthy family returns ``None``
    (permits downstream — SAFE-10 SC4).

    ``max_age_days`` is read by the CALLER from the grounded validity window (via
    ``crs_audit._window_days``) and passed IN — never inlined here; ``index_health`` stays
    literal-free (SAFE-09). ``as_of`` is fixed to today so the freshness delta is deterministic.

    Zero-artifact ordering (frozen invariant, mirrors ``_cmd_vault_audit`` cli.py:1119-1123):
    a future screen handler (Phase 44/45) MUST chain this preflight FIRST — BEFORE any
    ``open_vault`` / compute — so a refusal writes zero audit / report / database artifacts.
    This helper itself only opens the snapshot read-only and emits one envelope; it writes
    nothing. It is defined-only this phase (no user-facing verb; not wired into any decider).
    """
    from datetime import date

    from crawler import index_health
    health = index_health.probe_snapshot(
        db, family, max_age_days=max_age_days, as_of=date.today().isoformat())
    if health.ok():
        return None
    return _vault_fail(args, contract.INVALID_INPUT, health.message(db),
                       contract.EXIT_INVALID_INPUT)


def _cmd_vault_init(args: argparse.Namespace) -> int:
    """`vault init` — create/select a candidate vault under the personal boundary."""
    from crawler import paths, vault
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        existed = vault.select_candidate(v, args.candidate) is not None
        vault.create_candidate(v, args.candidate, label=args.label)
        result = {
            "candidate_id": v.candidate_id,
            "vault_kind": "candidate",
            "created": not existed,
        }
    finally:
        v.con.close()
    return _vault_ok(args, result,
                     f"vault ready: {result['candidate_id']} "
                     f"({'created' if result['created'] else 'exists'})")


def _cmd_vault_profile_set(args: argparse.Namespace) -> int:
    """`vault profile set` — import a factors YAML or upsert one inline factor."""
    import json as _json

    from crawler import paths, vault
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        vault.create_candidate(v, args.candidate)
        if args.factor_file is not None:
            try:
                vault.import_profile_yaml(v, args.candidate, args.factor_file)
            except (vault.VaultError, paths.PathEscapeError) as exc:
                return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                                   contract.EXIT_INVALID_INPUT)
        else:
            if not args.factor_id or not args.group:
                return _vault_fail(
                    args, contract.INVALID_INPUT,
                    "inline factor requires --factor-id and --group "
                    "(or use --factor-file)", contract.EXIT_INVALID_INPUT)
            claimed_value = None
            if args.value_json is not None:
                try:
                    claimed_value = _json.loads(args.value_json)
                except ValueError:
                    # PII boundary: name the field, never echo the bad payload.
                    return _vault_fail(args, contract.INVALID_INPUT,
                                       "--value-json is not valid JSON",
                                       contract.EXIT_INVALID_INPUT)
            try:
                factor = vault.CrsProfileFactor(
                    factor_id=args.factor_id,
                    factor_group=args.group,
                    claimed_points=args.points,
                    claimed_level=args.level,
                    claimed_value=claimed_value,
                    source="user_entry",
                )
            except Exception:  # noqa: BLE001 - pydantic ValidationError, PII-free
                return _vault_fail(args, contract.INVALID_INPUT,
                                   "invalid factor: check --group and --points",
                                   contract.EXIT_INVALID_INPUT)
            vault.upsert_profile_factor(v, factor)
        factor_count = len(vault.load_profile_factors(v, args.candidate))
        result = {"candidate_id": v.candidate_id, "factor_count": factor_count}
    finally:
        v.con.close()
    return _vault_ok(args, result,
                     f"vault profile: {result['factor_count']} factor(s)")


def _cmd_vault_profile_show(args: argparse.Namespace) -> int:
    """`vault profile show` — PII-light summary (counts + groups present, no values)."""
    from crawler import paths, vault
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        summary = vault.summarize_vault(v, args.candidate)
        result = {
            "candidate_id": summary.candidate_id,
            "factor_count": summary.factor_count,
            "ita_round_count": summary.ita_round_count,
            "document_count": summary.document_count,
            "groups_present": summary.groups_present,
        }
    finally:
        v.con.close()
    return _vault_ok(args, result,
                     f"vault {result['candidate_id']}: "
                     f"{result['factor_count']} factor(s), "
                     f"{result['ita_round_count']} ITA round(s), "
                     f"{result['document_count']} document(s)")


def _cmd_vault_ita_set(args: argparse.Namespace) -> int:
    """`vault ita set` — store an ITA round/cutoff; result is PII-light."""
    from crawler import paths, vault
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        vault.create_candidate(v, args.candidate)
        rnd = vault.set_ita_round(
            v, args.candidate, round_label=args.round, round_date=args.date,
            program=args.program, cutoff_score=args.cutoff,
            claimed_score=args.claimed_score,
        )
        result = {
            "round_id": rnd.round_id,
            "has_cutoff": rnd.cutoff_score is not None,
            "program": rnd.program,
        }
    finally:
        v.con.close()
    return _vault_ok(args, result, f"ita round stored: {result['round_id']}")


def _cmd_vault_import(args: argparse.Namespace) -> int:
    """`vault import PATH` — content-addressed ingest; PII-light DocumentSummary."""
    from crawler import paths, vault
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        vault.create_candidate(v, args.candidate)
        try:
            summary = vault.import_document(
                v, args.candidate, args.path, doc_type=args.doc_type,
                mime_type=args.mime_type,
            )
        except (vault.VaultError, paths.PathEscapeError) as exc:
            return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                               contract.EXIT_INVALID_INPUT)
        row = v.con.execute(
            "SELECT file_sha256 FROM documents WHERE document_id = ?",
            (summary.document_id,),
        ).fetchone()
        result = {
            "document_id": summary.document_id,
            "evidence_id": summary.evidence_id,
            "doc_type": summary.doc_type,
            "status": summary.status,
            "sha256_prefix": row["file_sha256"][:12] if row is not None else None,
        }
    finally:
        v.con.close()
    return _vault_ok(args, result,
                     f"imported {result['evidence_id']} ({result['doc_type']})")


def _cmd_vault_list(args: argparse.Namespace) -> int:
    """`vault list` — PII-light document listing (ids/type/status only)."""
    from crawler import paths, vault
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        summary = vault.summarize_vault(v, args.candidate)
        result = {
            "candidate_id": summary.candidate_id,
            "factor_count": summary.factor_count,
            "ita_round_count": summary.ita_round_count,
            "document_count": summary.document_count,
            "documents": [d.model_dump() for d in summary.documents],
        }
    finally:
        v.con.close()
    return _vault_ok(args, result,
                     f"vault {result['candidate_id']}: "
                     f"{result['document_count']} document(s)")


def _cmd_vault_extract(args: argparse.Namespace) -> int:
    """`vault extract` — render+read a document into PII-light pending values.

    Lazy-imports `crawler.extraction`; a missing extraction dependency becomes a
    `missing_dependency`/exit-3 envelope with the install hint (mirrors `_cmd_crawl`).
    The emitted result is PII-LIGHT (document count, pages, pending-value count,
    quality_counts) — never a raw extracted value.
    """
    from crawler import extraction, paths, vault
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        if args.document_id:
            doc_ids = [args.document_id]
        elif args.doc_type:
            rows = v.con.execute(
                "SELECT document_id FROM documents WHERE candidate_id = ? "
                "AND doc_type = ? ORDER BY added_at, document_id",
                (v.candidate_id, args.doc_type)).fetchall()
            doc_ids = [r["document_id"] for r in rows]
        else:
            return _vault_fail(args, contract.INVALID_INPUT,
                               "provide --document-id or --doc-type",
                               contract.EXIT_INVALID_INPUT)
        if not doc_ids:
            return _vault_fail(args, contract.INVALID_INPUT,
                               "no matching documents to extract",
                               contract.EXIT_INVALID_INPUT)
        results = []
        try:
            for did in doc_ids:
                results.append(extraction.extract_document(
                    v, did, factor_override=args.factor))
        except extraction.MissingExtractionDependency as exc:
            # Human hint to stderr always; machine envelope in --json mode.
            print(str(exc), file=sys.stderr)
            return _vault_fail(args, contract.MISSING_DEPENDENCY, str(exc),
                               contract.EXIT_MISSING_DEPENDENCY)
        except (vault.VaultError, paths.PathEscapeError) as exc:
            return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                               contract.EXIT_INVALID_INPUT)
        pages = sum(r.page_count for r in results)
        values_pending = sum(len(r.value_ids) for r in results)
        quality_counts: dict = {}
        for r in results:
            for key, num in r.quality_counts.items():
                quality_counts[key] = quality_counts.get(key, 0) + num
        result = {
            "candidate_id": v.candidate_id,
            "document_id": doc_ids[0] if len(doc_ids) == 1 else None,
            "documents": len(results),
            "pages": pages,
            "values_pending": values_pending,
            "quality_counts": quality_counts,
        }
    finally:
        v.con.close()
    return _vault_ok(args, result,
                     f"extracted {result['documents']} document(s): "
                     f"{result['pages']} page(s), "
                     f"{result['values_pending']} pending value(s)")


def _cmd_vault_fields(args: argparse.Namespace) -> int:
    """`vault fields` — human detail to STDERR; `--json` emits PII-light summaries.

    The human view (raw value, normalized value, source page/crop, affected CRS
    factor, profile claim) is PII and goes ONLY to the local terminal (stderr).
    The `--json` envelope carries the PII-light summaries list only.
    """
    from crawler import confirm, crs_rules, paths, vault
    try:
        registry_snapshot = crs_rules.load_registry_snapshot()
    except crs_rules.RegistryUnavailable:
        return _vault_fail(
            args,
            contract.INVALID_INPUT,
            "rule registry unavailable",
            contract.EXIT_INVALID_INPUT,
        )
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        vals = vault.list_extracted_values(
            v, document_id=args.document_id, status=args.status)
        summaries = [
            confirm.build_field_view_summary(
                v,
                val.value_id,
                registry_fingerprint=registry_snapshot.fingerprint,
            )
            for val in vals
        ]
        if not args.json:
            for val in vals:
                view = confirm.build_field_view(
                    v,
                    val.value_id,
                    registry_fingerprint=registry_snapshot.fingerprint,
                )
                print(confirm.format_field_view_human(view), file=sys.stderr)
        result = {
            "candidate_id": v.candidate_id,
            "count": len(summaries),
            "fields": summaries,
        }
    finally:
        v.con.close()
    return _vault_ok(args, result,
                     f"vault {result['candidate_id']}: {result['count']} field(s)")


def _cmd_vault_confirm(args: argparse.Namespace) -> int:
    """`vault confirm` — confirm/correct/reject ONE field (no bulk confirm-all).

    Acts on a single `--value-id`; emits the PII-light refreshed summary including
    `audit_eligible` and `stale`. A bad decision / missing corrected value / bad
    JSON is `invalid_input` (exit 2), field/type only.
    """
    import json as _json

    from crawler import confirm, crs_rules, paths, vault
    try:
        registry_snapshot = crs_rules.load_registry_snapshot()
    except crs_rules.RegistryUnavailable:
        return _vault_fail(
            args,
            contract.INVALID_INPUT,
            "rule registry unavailable",
            contract.EXIT_INVALID_INPUT,
        )
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        corrected_value = None
        if args.corrected_value is not None:
            try:
                corrected_value = _json.loads(args.corrected_value)
            except ValueError:
                # PII boundary: name the field, never echo the bad payload.
                return _vault_fail(args, contract.INVALID_INPUT,
                                   "--corrected-value is not valid JSON",
                                   contract.EXIT_INVALID_INPUT)
        try:
            result = confirm.apply_decision(
                v, args.value_id, args.decision,
                corrected_value=corrected_value, confirmed_by=args.note,
                registry_fingerprint=registry_snapshot.fingerprint)
        except vault.VaultError as exc:
            return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                               contract.EXIT_INVALID_INPUT)
    finally:
        v.con.close()
    return _vault_ok(args, result,
                     f"{args.decision}: {result['value_id']} "
                     f"(audit_eligible={result['audit_eligible']}, "
                     f"stale={result['stale']})")


def _cmd_vault_audit(args: argparse.Namespace) -> int:
    """`vault audit` — run the CRS auditor slice; emit a PII-light envelope.

    Runs the first-official-language audit and emits ONE five-key envelope with
    `command: "vault"` and a `result` that is the PII-light `PublicAuditEnvelope`
    (run id, per-factor verdicts, counts, generic corpus-cited claims, and the
    vault-RELATIVE private output path) — never applicant values, never `ev_`
    pointers. A grounded GAP/AT-RISK/N/A is `ok:true` (a valid verdict). A
    grounding/system failure (`AuditGroundingError`) is `ok:false` with an error
    object + a non-zero exit, and writes no report (SC5). Human factor-card detail
    (applicant values) routes to STDERR only, exactly like `vault fields`.
    """
    from crawler import audit_report, auditor, crs_rules, paths, vault
    try:
        registry_snapshot = crs_rules.load_registry_snapshot()
    except crs_rules.RegistryUnavailable as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    # HARD-01/02: refuse a missing/empty/unreadable/corrupt/drifted corpus index
    # cleanly, BEFORE opening the vault, so a refusal writes zero artifacts.
    refusal = _require_readable_index(args, args.db)
    if refusal is not None:
        return refusal
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        try:
            if getattr(args, "all", False):
                # Full-grid run: audit every factor, PII-light envelope on stdout.
                report, envelope = audit_report.run_full_audit_report(
                    v, args.db, registry_snapshot.registry,
                    ita_round_id=args.ita_round_id,
                    registry_fingerprint=registry_snapshot.fingerprint)
            else:
                report, envelope = audit_report.run_audit(
                    v, args.factor, args.db, registry_snapshot.registry,
                    ita_round_id=args.ita_round_id,
                    registry_fingerprint=registry_snapshot.fingerprint)
        except auditor.AuditGroundingError as exc:
            # A grounding failure is a loud, PII-free error envelope (rule ids +
            # reasons only) with a non-zero exit and NO report (SC5).
            return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                               contract.EXIT_INVALID_INPUT)
        except audit_report.AuditPersistenceError:
            # Persistence diagnostics may contain private machine paths or vault
            # identifiers.  Keep both machine and human boundaries stable and
            # generic; the global handler must never receive the raw I/O error.
            return _vault_fail(
                args,
                contract.INTERNAL_ERROR,
                "audit report persistence failed",
                contract.EXIT_INTERNAL_ERROR,
            )
        except paths.PathEscapeError as exc:
            return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                               contract.EXIT_INVALID_INPUT)
        # Human factor-card detail (PII) -> STDERR only; stdout stays PII-light.
        if not args.json:
            for card in report.factor_cards:
                print(f"{card.factor_id}: {card.verdict} "
                      f"(reason={card.reason_code}, claimed={card.claimed_value}, "
                      f"confirmed={card.confirmed_value}, "
                      f"delta={card.score_delta}, "
                      f"evidence={', '.join(card.evidence_ids) or '-'})",
                      file=sys.stderr)
        result = envelope.model_dump()
        first = report.factor_cards[0]
        return _vault_ok(args, result,
                         f"vault {v.candidate_id}: {first.verdict} "
                         f"({envelope.run_id})")
    finally:
        v.con.close()


# Fail-closed refusal reasons -> a short recovery hint (PII-free).
_REMEDIATION_HINTS = {
    "no_completed_audit": "run 'corpus-crawler vault audit --all' first",
    "audit_run_not_found": "check the --audit-run-id (must be a completed run)",
    "audit_report_unreadable": "re-run 'corpus-crawler vault audit --all'",
    "registry_drift": "the rule registry changed since the audit — re-run "
                      "'corpus-crawler vault audit --all'",
    "rendered_leak": "the rendered packet failed the redaction leak scan — please "
                     "report this as a bug",
    "unknown_document": "check --include-document (must be a document in this "
                        "candidate's vault)",
    "document_unreadable": "an included document's file is missing or unreadable in "
                           "the vault",
}


def _cmd_vault_remediate(args: argparse.Namespace) -> int:
    """`vault remediate` — project a completed audit into a private fix checklist.

    Loads a selected completed audit run (default: the latest completed run), builds
    the remediation checklist (a pure projection — no re-grounding), writes the full
    PII-bearing JSON + Markdown ONLY under the vault, and emits a PII-light summary.
    A missing / unreadable prerequisite is a clean `invalid_input`/exit-2 refusal with
    a specific `reason=<code>` token and NO artifact written (fail-closed). Human item
    detail (PII) routes to STDERR only.
    """
    from crawler import paths, remediation, vault
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        try:
            checklist, summary = remediation.run_remediation(
                v, args.audit_run_id)
        except remediation.RemediationError as exc:
            reason = str(exc)
            hint = _REMEDIATION_HINTS.get(reason, "re-run the audit")
            return _vault_fail(
                args, contract.INVALID_INPUT,
                f"cannot build remediation (reason={reason}): {hint}",
                contract.EXIT_INVALID_INPUT)
        except paths.PathEscapeError as exc:
            return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                               contract.EXIT_INVALID_INPUT)
        # Human item detail (PII) -> STDERR only; stdout stays PII-light.
        if not args.json:
            for item in checklist.items:
                print(f"{item.factor_id}: {item.verdict} "
                      f"(reason={item.reason_code}, kind={item.finding_kind}) "
                      f"-> {item.action}", file=sys.stderr)
        return _vault_ok(
            args, summary.model_dump(),
            f"vault {v.candidate_id}: {summary.item_count} remediation item(s) "
            f"({summary.run_id})")
    finally:
        v.con.close()


def _cmd_vault_review_packet(args: argparse.Namespace) -> int:
    """`vault review-packet` — produce a redacted lawyer/RCIC review packet.

    Builds a closed-allowlist, redacted packet from a completed audit's findings
    (reusing the Phase-37 checklist), previews a dry-run redaction manifest with
    ``--dry-run``, opts documents in per-document with ``--include-document`` (staged
    vault-only), render-then-scans the bytes for leaks, and writes ONLY under the vault.
    A missing prerequisite / rendered leak / unknown document is a clean
    ``invalid_input``/exit-2 refusal with a ``reason=<code>`` token and NO artifact.
    Human finding detail (PII) routes to STDERR only; stdout stays PII-light.
    """
    from crawler import paths, remediation, review_packet, vault
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        selection = set(args.finding) if args.finding else None
        try:
            packet, summary = review_packet.run_review_packet(
                v, args.audit_run_id, selection=selection,
                include_documents=args.include_document, dry_run=args.dry_run)
        except remediation.RemediationError as exc:
            reason = str(exc)
            hint = _REMEDIATION_HINTS.get(reason, "re-run the audit")
            return _vault_fail(
                args, contract.INVALID_INPUT,
                f"cannot build review packet (reason={reason}): {hint}",
                contract.EXIT_INVALID_INPUT)
        except paths.PathEscapeError as exc:
            return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                               contract.EXIT_INVALID_INPUT)
        if not args.json:
            if args.dry_run:
                print("dry-run — nothing written", file=sys.stderr)
            for finding in packet.findings:
                print(f"{finding.factor_id}: {finding.verdict} "
                      f"(reason={finding.reason_code}, kind={finding.finding_kind}) "
                      f"-> {finding.action}", file=sys.stderr)
        return _vault_ok(
            args, summary.model_dump(),
            f"vault {v.candidate_id}: {summary.findings_included} finding(s) "
            f"({summary.run_id or 'dry-run'})")
    finally:
        v.con.close()


def _cmd_vault_noc_worksheet(args: argparse.Namespace) -> int:
    """`vault noc-worksheet` — generate the grounded, cited NOC duty worksheet (NOC-01).

    Drives the idempotent Plan-01 :func:`crawler.noc_worksheet.generate_worksheet`:
    the cited artifact is written ONLY under the vault, and ``--json`` stdout carries
    ONLY the PII-light summary ``{noc_code, duty_count, value_ids, worksheet_doc_id,
    citations}`` — never raw duty text or an absolute path. Human-readable duty detail
    (the cited worksheet body) routes to STDERR only, mirroring ``vault fields``.

    Zero-artifact ordering (SAFE-10): the corpus index is preflighted FIRST — a
    missing / corrupt / drifted index refuses once on ``invalid_input``/exit-2 BEFORE
    any ``open_vault`` or compute, so a refusal writes zero artifacts. An unresolvable
    / malformed ``--noc-code`` (the generator validates ``\\d{5}`` and fails closed to a
    None-worksheet) is likewise a clean ``invalid_input``/exit-2 refusal with nothing
    written, carrying ``reason=unresolved_noc``. A DISTINCT corpus-integrity fault —
    the index resolves the NOC but its authoritative markdown SOURCE is
    missing/drifted — refuses the SAME way but with ``reason=noc_source_unavailable``
    and a refresh/rebuild-the-corpus hint (never "check the code"), so a slimmed /
    relocated deployment is never misdiagnosed as bad user input (WR-01). This verb
    adds NO idempotency logic of its own and NO new confirmation path — per-duty
    confirm/correct/reject is the shipped per-``--value-id`` ``vault confirm`` verb
    (there is no bulk confirm-all).
    """
    from crawler import noc_worksheet, paths, vault
    # SAFE-10: refuse an unreadable index BEFORE open_vault/compute (zero artifacts).
    refusal = _require_readable_index(args, args.db)
    if refusal is not None:
        return refusal
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        summary = noc_worksheet.generate_worksheet(
            v, args.db, args.candidate, args.noc_code)
        if summary["worksheet_doc_id"] is None:
            # The generator wrote ZERO artifacts and ZERO values; surface it as one
            # PII-free fail-closed refusal, but DISTINGUISH the cause (WR-01) so the
            # operator is pointed at the right fix:
            #   * unresolved_noc         -> bad/absent 5-digit code (check the code);
            #   * noc_source_unavailable -> the index resolved the NOC but its
            #     authoritative corpus SOURCE is missing/drifted (refresh/rebuild
            #     the corpus, NOT the code).
            reason = summary.get("reason") or "unresolved_noc"
            if reason == "noc_source_unavailable":
                msg = ("could not build NOC worksheet "
                       "(reason=noc_source_unavailable); the pinned corpus is "
                       "missing or has drifted the authoritative NOC source — "
                       "refresh or rebuild the authoritative corpus (this is NOT "
                       "a bad --noc-code)")
            else:
                msg = ("could not resolve NOC worksheet (reason=unresolved_noc); "
                       "check the 5-digit --noc-code against the pinned corpus")
            return _vault_fail(
                args, contract.INVALID_INPUT, msg, contract.EXIT_INVALID_INPUT)
        result = {
            "noc_code": summary["noc_code"],
            "duty_count": summary["duty_count"],
            "value_ids": summary["value_ids"],
            "worksheet_doc_id": summary["worksheet_doc_id"],
            "citations": summary["citations"],
        }
        # Human duty detail (the cited worksheet body, PII-adjacent) -> STDERR ONLY;
        # stdout stays PII-light. Mirrors `vault fields` / `vault audit` routing.
        if not args.json:
            artifact = paths.resolve_within(
                v.root, "output", "noc-worksheets", f"noc-{args.noc_code}.md")
            if artifact.is_file():
                print(artifact.read_text(encoding="utf-8"), file=sys.stderr)
        cid = v.candidate_id
    finally:
        v.con.close()
    return _vault_ok(
        args, result,
        f"vault {cid}: NOC {result['noc_code']} worksheet — "
        f"{result['duty_count']} duty item(s), "
        f"{len(result['value_ids'])} pending value(s) captured")


def _cmd_vault_noc_review(args: argparse.Namespace) -> int:
    """`vault noc-review` — inert duty-review roll-up (NOC-02/NOC-03).

    Emits the Plan-02 :func:`crawler.noc_review.review_noc_duties` sidecar's CLOSED
    PII-light dict ``{noc_code, duty_count, confirmed_count, status, reason,
    citations}`` on ``--json`` stdout — a structurally never-green verdict
    (``status`` in ``{AT-RISK, GAP, N/A}``, no score). Human-readable duty detail
    routes to STDERR only; stdout stays PII-light.

    The corpus index is preflighted FIRST (SAFE-10 zero-artifact ordering) — a
    missing / corrupt / drifted index refuses once on ``invalid_input``/exit-2 BEFORE
    any ``open_vault`` or compute. Per-duty confirm/correct/reject is the shipped
    per-``--value-id`` ``vault confirm`` verb (no bulk confirm-all is added here).
    """
    from crawler import noc_review, paths, vault
    # SAFE-10: refuse an unreadable index BEFORE open_vault/compute (zero artifacts).
    refusal = _require_readable_index(args, args.db)
    if refusal is not None:
        return refusal
    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(args, contract.INVALID_INPUT, str(exc),
                           contract.EXIT_INVALID_INPUT)
    try:
        result = noc_review.review_noc_duties(
            v, args.db, args.noc_code, args.candidate)
        # Human review detail -> STDERR ONLY; stdout stays the PII-light closed dict.
        if not args.json:
            print(f"NOC {result['noc_code']} duty review: {result['status']} "
                  f"(reason={result['reason']}, "
                  f"{result['confirmed_count']}/{result['duty_count']} confirmed)",
                  file=sys.stderr)
        cid = v.candidate_id
    finally:
        v.con.close()
    return _vault_ok(
        args, result,
        f"vault {cid}: NOC {result['noc_code']} review — {result['status']}")


def _cmd_vault_study_review(args: argparse.Namespace) -> int:
    """`vault study-review` — preflight-first private Canadian-study review.

    The operational DLI max age is resolved exactly once at this CLI boundary.
    Invalid configuration refuses before either corpus probe, vault creation, or
    report write.  A valid bound then flows unchanged through the index/snapshot
    preflights and into the private sidecar.
    """
    from crawler import paths, snapshot_policy, study_review, vault

    try:
        report_dir = study_review._latest_report_path(
            paths.candidate_root(args.candidate)
        ).parent
        study_review._ensure_study_report_recovered(report_dir)
    except paths.PathEscapeError as exc:
        return _vault_fail(
            args, contract.INVALID_INPUT, str(exc),
            contract.EXIT_INVALID_INPUT)
    except study_review.StudyReportRecoveryError:
        return _vault_fail(
            args,
            contract.INTERNAL_ERROR,
            "study report recovery failed",
            contract.EXIT_INTERNAL_ERROR,
        )

    max_age = snapshot_policy.dli_snapshot_max_age_days(
        args.snapshot_max_age_days)
    if max_age is None:
        return _vault_fail(
            args,
            contract.INVALID_INPUT,
            "DLI snapshot max age must be a positive integer supplied by "
            "--snapshot-max-age-days or PR_DLI_SNAPSHOT_MAX_AGE_DAYS",
            contract.EXIT_INVALID_INPUT,
        )

    refusal = _require_readable_index(args, args.db)
    if refusal is not None:
        return refusal
    refusal = _require_readable_snapshot(args, args.db, "dli", max_age)
    if refusal is not None:
        return refusal

    try:
        v = vault.open_vault(args.candidate)
    except paths.PathEscapeError as exc:
        return _vault_fail(
            args, contract.INVALID_INPUT, str(exc),
            contract.EXIT_INVALID_INPUT)
    try:
        try:
            result = study_review.review_study(
                v,
                args.db,
                candidate_id=args.candidate,
                max_age_days=max_age,
            )
        except study_review.StudyReportRecoveryError:
            return _vault_fail(
                args,
                contract.INTERNAL_ERROR,
                "study report recovery failed",
                contract.EXIT_INTERNAL_ERROR,
            )
    finally:
        v.con.close()

    human = (
        f"study review: {result['status']} "
        f"(reason={result['reason']}, "
        f"{result['confirmed_count']}/{result['required_count']} confirmed, "
        f"{result['eligible_count']} eligible)"
    )
    if getattr(result, "report_created", False):
        human += "; private report: output/study-review/latest.json"
    return _vault_ok(args, result, human)


def _cmd_vault_screen_mec(args: argparse.Namespace) -> int:
    """`vault screen-mec` — preflight, evaluate, durably publish, then emit."""
    import os
    import sqlite3
    from datetime import date

    from pydantic import ValidationError

    from crawler import (
        crs_rules,
        mec_publish,
        mec_screen,
        mecfields,
        paths,
        snapshot_policy,
        study_review,
        vault,
    )

    if args.program == "fsw":
        try:
            report_dir = study_review._latest_report_path(
                paths.candidate_root(args.candidate)
            ).parent
            study_review._ensure_study_report_recovered(report_dir)
        except paths.PathEscapeError:
            return _vault_fail(
                args,
                contract.INVALID_INPUT,
                "candidate vault unavailable",
                contract.EXIT_INVALID_INPUT,
            )
        except study_review.StudyReportRecoveryError:
            return _vault_fail(
                args,
                contract.INTERNAL_ERROR,
                "study report recovery failed",
                contract.EXIT_INTERNAL_ERROR,
            )

    # This required operator policy is resolved exactly once and before every
    # registry/index/vault/database/filesystem read.
    max_age_days = snapshot_policy.mec_rule_max_age_days(args.rule_max_age_days)
    if max_age_days is None:
        return _vault_fail(
            args,
            contract.INVALID_INPUT,
            "MEC rule max age must be a positive integer supplied by "
            "--rule-max-age-days or PR_MEC_RULE_MAX_AGE_DAYS",
            contract.EXIT_INVALID_INPUT,
        )
    try:
        operational_as_of = (
            date.fromisoformat(args.as_of) if args.as_of is not None else date.today()
        )
    except (TypeError, ValueError):
        return _vault_fail(
            args,
            contract.INVALID_INPUT,
            "MEC operational as-of date must be YYYY-MM-DD",
            contract.EXIT_INVALID_INPUT,
        )

    study_max_age_days = None
    if args.program == "fsw":
        raw_study_age = (
            args.snapshot_max_age_days
            if args.snapshot_max_age_days is not None
            else os.environ.get("PR_DLI_SNAPSHOT_MAX_AGE_DAYS")
        )
        if raw_study_age is not None:
            study_max_age_days = snapshot_policy.dli_snapshot_max_age_days(
                args.snapshot_max_age_days
            )
            if study_max_age_days is None:
                return _vault_fail(
                    args,
                    contract.INVALID_INPUT,
                    "DLI snapshot max age must be a positive integer supplied by "
                    "--snapshot-max-age-days or PR_DLI_SNAPSHOT_MAX_AGE_DAYS",
                    contract.EXIT_INVALID_INPUT,
                )

    try:
        registry_snapshot = crs_rules.load_registry_snapshot()
    except (OSError, ValueError, crs_rules.RegistryUnavailable):
        return _vault_fail(
            args,
            contract.INVALID_INPUT,
            "MEC registry unavailable",
            contract.EXIT_INVALID_INPUT,
        )

    refusal = _require_readable_index(args, args.db)
    if refusal is not None:
        return refusal

    if study_max_age_days is not None:
        refusal = _require_readable_snapshot(
            args, args.db, "dli", study_max_age_days
        )
        if refusal is not None:
            return refusal

    try:
        vault_ = vault.open_vault(args.candidate)
    except (OSError, ValueError, sqlite3.Error, paths.PathEscapeError):
        return _vault_fail(
            args,
            contract.INVALID_INPUT,
            "candidate vault unavailable",
            contract.EXIT_INVALID_INPUT,
        )

    try:
        try:
            evidence = mecfields.load_mec_evidence(
                vault_,
                args.candidate,
                registry_snapshot.fingerprint,
            )
            reference_date = mecfields.eligibility_reference_date(evidence)
            context = mec_screen.prepare_mec_gate(
                args.program,
                registry_snapshot,
                args.db,
                reference_date,
                max_age_days,
                as_of=operational_as_of,
            )
            confirmed_inputs = mec_screen.build_confirmed_mec_inputs(
                args.program,
                context,
                evidence,
                vault_,
                args.db,
            )
            private_output_path = f"output/mec/{args.program}/latest.json"
            bundle = mec_screen.screen_mec(
                args.program,
                context,
                evidence,
                confirmed_inputs,
                vault_=vault_,
                db=args.db,
                study_max_age_days=study_max_age_days,
                private_output_path=private_output_path,
            )
            summary = mec_publish.publish_mec_bundle(vault_, bundle)
        except mec_publish.MecPublicationError:
            return _vault_fail(
                args,
                contract.INTERNAL_ERROR,
                "MEC report publication failed",
                contract.EXIT_INTERNAL_ERROR,
            )
        except (
            OSError,
            sqlite3.Error,
            ValueError,
            ValidationError,
            TypeError,
            RuntimeError,
            mec_screen.MecGatePreparationError,
        ):
            return _vault_fail(
                args,
                contract.INTERNAL_ERROR,
                "MEC screening unavailable",
                contract.EXIT_INTERNAL_ERROR,
            )
    finally:
        try:
            vault_.con.close()
        except sqlite3.Error:
            # The stable command refusal above must never be replaced by a
            # database path or driver detail raised while closing the vault.
            pass

    counts = summary.counts
    human = (
        f"MEC {summary.program}: {summary.status} "
        f"(pass={counts.passed}, fail={counts.failed}, "
        f"at-risk={counts.at_risk}, n/a={counts.not_applicable}); "
        f"private report: {summary.private_output_path}"
    )
    return _vault_ok(args, summary.model_dump(mode="json"), human)


def _cmd_doctor(args: argparse.Namespace) -> int:
    """`doctor` — extraction dependency + scan-quality preflight (EXTRACT-05).

    Top-level command (peer of `vault`). Emits a PII-light envelope
    (deps[]/optional[]/quality_counts/overall). A missing REQUIRED dependency is
    `missing_dependency`/exit 3 (never `internal_error`); an absent optional OCR
    stack is a reported warning. Human dep hints go to stderr.
    """
    from crawler import doctor
    report = doctor.run_doctor(candidate=args.candidate,
                               document_id=args.document_id)
    if not args.json:
        for d in report.required + report.optional:
            tag = "ok " if d.present else "MISS"
            suffix = "" if d.present else f"  → {d.hint}"
            kind = "required" if d.required else "optional"
            print(f"[{tag}] {d.name} ({kind}){suffix}", file=sys.stderr)
        if report.quality_counts is not None:
            print(f"scan-quality: {report.quality_counts}", file=sys.stderr)
    if report.overall == "missing_dependency":
        missing = ", ".join(report.missing_required())
        msg = (f"missing required extraction dependencies: {missing}. "
               f"Install with: pip install 'corpus-crawler[doc-extract]'")
        if args.json:
            contract.emit(contract.envelope(
                "doctor", error=(contract.MISSING_DEPENDENCY, msg)))
        else:
            print(f"doctor: {msg}", file=sys.stderr)
        return contract.EXIT_MISSING_DEPENDENCY
    if args.json:
        contract.emit(contract.envelope("doctor", result=report.to_result()))
    else:
        print(f"doctor: {report.overall}", file=sys.stderr)
    return 0


def _add_vault_subparser(subparsers: "argparse._SubParsersAction") -> None:
    """Register the additive `vault` subcommand + its verb sub-subparsers."""
    p_vault = subparsers.add_parser(
        "vault",
        help="Manage the private candidate vault (init / profile / ita / "
             "import / list / extract / fields / confirm / audit / remediate / "
             "review-packet / noc-worksheet / noc-review / study-review / "
             "screen-mec). "
             "All --json output is PII-light.")
    vsub = p_vault.add_subparsers(
        dest="vault_verb", required=True,
        metavar="{init,profile,ita,import,list,extract,fields,confirm,audit,remediate,review-packet,noc-worksheet,noc-review,study-review,screen-mec}")

    # vault init
    p_init = vsub.add_parser("init", help="Create/select a candidate vault.")
    p_init.add_argument("--candidate", default="default",
                        help="candidate id slug (default: default)")
    p_init.add_argument("--label", default=None, help="optional non-PII label")
    p_init.set_defaults(func=_cmd_vault_init)

    # vault profile set|show
    p_profile = vsub.add_parser("profile", help="Set/show CRS profile factors.")
    psub = p_profile.add_subparsers(
        dest="profile_verb", required=True, metavar="{set,show}")
    p_pset = psub.add_parser("set", help="Import a factors YAML or one inline factor.")
    p_pset.add_argument("--candidate", default="default")
    p_pset.add_argument("--factor-file", default=None,
                        help="path to a factors YAML (safe_load only)")
    p_pset.add_argument("--factor-id", default=None, help="inline: factor id")
    p_pset.add_argument("--group", default=None,
                        help="inline: core_human_capital | spouse_common_law | "
                             "skill_transferability | additional_points")
    p_pset.add_argument("--points", type=int, default=None,
                        help="inline: claimed sub-score (private)")
    p_pset.add_argument("--level", default=None, help="inline: claimed level/label")
    p_pset.add_argument("--value-json", default=None,
                        help="inline: JSON-encoded claimed_value")
    p_pset.set_defaults(func=_cmd_vault_profile_set)
    p_pshow = psub.add_parser("show", help="PII-light profile summary (counts only).")
    p_pshow.add_argument("--candidate", default="default")
    p_pshow.set_defaults(func=_cmd_vault_profile_show)

    # vault ita set
    p_ita = vsub.add_parser("ita", help="Store the ITA round/cutoff.")
    isub = p_ita.add_subparsers(dest="ita_verb", required=True, metavar="{set}")
    p_iset = isub.add_parser("set", help="Store one ITA round + cutoff.")
    p_iset.add_argument("--candidate", default="default")
    p_iset.add_argument("--round", required=True, help="round label")
    p_iset.add_argument("--date", default=None, help="round date (YYYY-MM-DD)")
    p_iset.add_argument("--program", default=None, help="program name")
    p_iset.add_argument("--cutoff", type=int, required=True, help="round cutoff score")
    p_iset.add_argument("--claimed-score", type=int, default=None,
                        help="the applicant's claimed CRS score")
    p_iset.set_defaults(func=_cmd_vault_ita_set)

    # vault import
    p_import = vsub.add_parser("import", help="Content-addressed document import.")
    p_import.add_argument("path", help="source document path to import")
    p_import.add_argument("--doc-type", required=True,
                          help="document type (e.g. language_test, eca)")
    p_import.add_argument("--candidate", default="default")
    p_import.add_argument("--mime-type", default=None, help="optional MIME type")
    p_import.set_defaults(func=_cmd_vault_import)

    # vault list
    p_list = vsub.add_parser("list", help="PII-light vault document listing.")
    p_list.add_argument("--candidate", default="default")
    p_list.set_defaults(func=_cmd_vault_list)

    # vault extract — render+read a document into pending values (Phase 30).
    p_extract = vsub.add_parser(
        "extract",
        help="Render+read a document into pending values (requires the "
             "'doc-extract' extra). --json result is PII-light.")
    p_extract.add_argument("--candidate", default="default")
    p_extract.add_argument("--document-id", default=None,
                           help="the document to extract")
    p_extract.add_argument("--doc-type", default=None,
                           help="extract ALL documents of this type instead")
    p_extract.add_argument("--factor", default=None,
                           help="grid factor id to link this document's values to "
                                "(disambiguates e.g. core.language.second)")
    p_extract.set_defaults(func=_cmd_vault_extract)

    # vault fields — review extracted fields (human detail → stderr; --json PII-light).
    p_fields = vsub.add_parser(
        "fields",
        help="Review extracted fields. Human view (raw/normalized/page-crop/"
             "factor/claim) prints to stderr; --json is PII-light.")
    p_fields.add_argument("--candidate", default="default")
    p_fields.add_argument("--document-id", default=None,
                          help="restrict to one document")
    p_fields.add_argument("--status", default=None,
                          help="filter: pending|confirmed|corrected|rejected")
    p_fields.set_defaults(func=_cmd_vault_fields)

    # vault confirm — confirm/correct/reject ONE field (no bulk confirm-all).
    p_confirm = vsub.add_parser(
        "confirm",
        help="Confirm/correct/reject ONE field by --value-id (per-field only; "
             "there is no bulk confirm-all).")
    p_confirm.add_argument("--candidate", default="default")
    p_confirm.add_argument("--value-id", required=True,
                           help="the single value to act on")
    p_confirm.add_argument("--decision", required=True,
                           choices=("confirm", "correct", "reject"))
    p_confirm.add_argument("--corrected-value", default=None,
                           help="JSON corrected value (required for 'correct')")
    p_confirm.add_argument("--note", default=None,
                           help="optional confirmation annotation")
    p_confirm.set_defaults(func=_cmd_vault_confirm)

    # vault audit — run the CRS auditor slice; PII-light envelope on stdout.
    p_audit = vsub.add_parser(
        "audit",
        help="Run the CRS auditor slice for one factor. --json emits a PII-light "
             "envelope (run id, verdicts, counts, corpus-cited claims, vault "
             "report path); applicant detail prints to stderr.")
    p_audit.add_argument("--candidate", default="default")
    p_audit.add_argument("--factor", default="core.language.first",
                         help="the CRS factor to audit (default: core.language.first; "
                              "ignored when --all runs the whole grid)")
    p_audit.add_argument("--all", action="store_true",
                         help="audit every factor on the full CRS grid (one verdict "
                              "per factor) and roll SUBSTANTIATED points up vs the "
                              "ITA cutoff")
    p_audit.add_argument("--db", default="corpus/index.db",
                         help="corpus index db to ground rule claims against")
    p_audit.add_argument("--round", "--ita-round-id", dest="ita_round_id",
                         default=None,
                         help="optional ITA round id (freshness reference date)")
    p_audit.set_defaults(func=_cmd_vault_audit)

    # vault remediate — project a completed audit into a private fix checklist (Phase 37).
    p_remediate = vsub.add_parser(
        "remediate",
        help="Project a completed audit run into a private, corpus-cited remediation "
             "checklist (one item per unresolved finding). --json emits a PII-light "
             "summary; the full checklist stays vault-only.")
    p_remediate.add_argument("--candidate", default="default")
    p_remediate.add_argument(
        "--audit-run-id", default=None,
        help="the completed audit run to remediate (default: the latest completed run)")
    p_remediate.set_defaults(func=_cmd_vault_remediate)

    # vault review-packet — redacted lawyer/RCIC review packet (Phase 38).
    p_packet = vsub.add_parser(
        "review-packet",
        help="Produce an opt-in, explicitly redacted lawyer/RCIC review packet from a "
             "completed audit's findings. --dry-run previews the redaction manifest; "
             "--include-document opts in a document (staged vault-only). --json emits a "
             "PII-light summary; the packet stays vault-only.")
    p_packet.add_argument("--candidate", default="default")
    p_packet.add_argument(
        "--audit-run-id", default=None,
        help="the completed audit run to package (default: the latest completed run)")
    p_packet.add_argument(
        "--finding", action="append", default=None,
        help="restrict to this factor id (repeatable; default: all unresolved findings)")
    p_packet.add_argument(
        "--include-document", action="append", default=None,
        help="opt in a vault document by id (repeatable; staged vault-only)")
    p_packet.add_argument(
        "--dry-run", action="store_true",
        help="preview the redaction manifest without writing the packet")
    p_packet.set_defaults(func=_cmd_vault_review_packet)

    # vault noc-worksheet — generate the grounded, cited NOC duty worksheet (Phase 43).
    p_noc_ws = vsub.add_parser(
        "noc-worksheet",
        help="Generate the grounded, cited NOC-2021 work-duty review worksheet for a "
             "claimed 5-digit NOC. The artifact is written vault-only; --json emits a "
             "PII-light summary (ids/counts/citations); the cited worksheet body "
             "prints to stderr. Per-duty confirm is the shipped 'vault confirm' verb.")
    p_noc_ws.add_argument("--candidate", default="default")
    p_noc_ws.add_argument("--noc-code", required=True,
                          help="the claimed 5-digit NOC-2021 code (validated \\d{5})")
    p_noc_ws.add_argument("--db", default="corpus/index.db",
                          help="corpus index db to resolve the NOC spans against")
    p_noc_ws.set_defaults(func=_cmd_vault_noc_worksheet)

    # vault noc-review — inert never-green duty-review roll-up (Phase 43).
    p_noc_rv = vsub.add_parser(
        "noc-review",
        help="Roll the confirmed/pending NOC duty values into an inert, never-green "
             "{AT-RISK,GAP,N/A} verdict. --json emits the closed PII-light dict; human "
             "detail prints to stderr. Confirm duties one at a time via 'vault confirm'.")
    p_noc_rv.add_argument("--candidate", default="default")
    p_noc_rv.add_argument("--noc-code", required=True,
                          help="the claimed 5-digit NOC-2021 code (validated \\d{5})")
    p_noc_rv.add_argument("--db", default="corpus/index.db",
                          help="corpus index db to rebuild the current worksheet keys")
    p_noc_rv.set_defaults(func=_cmd_vault_noc_review)

    # vault study-review — private, inert Canadian-study review (Phase 44).
    p_study_rv = vsub.add_parser(
        "study-review",
        help="Review confirmed Canadian-study evidence against the pinned local "
             "DLI snapshot. --json emits only the closed public summary; evidence "
             "and citations remain in the candidate vault.")
    p_study_rv.add_argument("--candidate", default="default")
    p_study_rv.add_argument(
        "--db", default="corpus/index.db",
        help="corpus index db containing the pinned DLI snapshot")
    p_study_rv.add_argument(
        "--snapshot-max-age-days",
        default=None,
        help="positive DLI snapshot age bound; overrides "
             "PR_DLI_SNAPSHOT_MAX_AGE_DAYS")
    p_study_rv.set_defaults(func=_cmd_vault_study_review)

    # vault screen-mec — exact FSW/FST/CEC minimum-entry-criteria sidecar.
    p_mec = vsub.add_parser(
        "screen-mec",
        help="Screen one federal program's minimum entry criteria. The complete "
        "report remains private; --json emits only the closed PII-light summary.",
    )
    p_mec.add_argument("--program", required=True, choices=("fsw", "fst", "cec"))
    p_mec.add_argument("--candidate", default="default")
    p_mec.add_argument(
        "--db",
        default="corpus/index.db",
        help="corpus index db used for grounded MEC and optional sidecar reads",
    )
    p_mec.add_argument(
        "--rule-max-age-days",
        default=None,
        help="required positive MEC rule age bound; overrides "
        "PR_MEC_RULE_MAX_AGE_DAYS",
    )
    p_mec.add_argument(
        "--snapshot-max-age-days",
        default=None,
        help="optional positive DLI snapshot age bound consumed only by FSW study "
        "composition; overrides PR_DLI_SNAPSHOT_MAX_AGE_DAYS",
    )
    p_mec.add_argument(
        "--as-of",
        default=None,
        help="optional operational rule-freshness date (YYYY-MM-DD); applicant "
        "effectivity and lookbacks always use confirmed vault evidence",
    )
    p_mec.set_defaults(func=_cmd_vault_screen_mec)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="corpus-crawler",
        description="Authoritative-source corpus crawler pipeline: "
    )
    # GLOBAL --json flag, parsed BEFORE the subcommand (e.g.
    # `corpus-crawler --json report <corpus>`). One consistent flag owned by the
    # dispatcher so the underlying module main(argv) functions and their human-text
    # default behavior stay UNCHANGED (preserving the 37 tests + degradation).
    parser.add_argument(
        "--json", action="store_true",
        help="emit one machine-readable JSON object on stdout (human text → stderr)")
    subparsers = parser.add_subparsers(dest="command", required=True,
                                       metavar="{crawl,apply-verdicts,completeness,report,index,refresh-dli,search,ground,checklist,vault,doctor}")

    # crawl — mirrors crawler.deepcrawl flags; forwarded verbatim (lazy import).
    p_crawl = subparsers.add_parser(
        "crawl", help="Deep-crawl a content tree (requires the optional 'crawl' extra).")
    p_crawl.add_argument("--seed", required=True, help="seed URL to crawl from")
    p_crawl.add_argument("--depth", type=int, default=None,
                         help="BFS depth (default: deepcrawl's default, currently 2)")
    p_crawl.add_argument("--max-pages", type=int, default=None,
                         help="max pages to record (default: deepcrawl's default, currently 40)")
    p_crawl.add_argument("--out", required=True, help="output corpus directory")
    p_crawl.add_argument("--profile", default=None,
                         help="built-in profile name or path to a .yaml profile "
                              "(default: deepcrawl's default, currently 'ircc')")
    p_crawl.add_argument("--source-type", default=None,
                         help="override the profile's default source_type")
    p_crawl.add_argument("--include", dest="include_pattern", default=None,
                         help="glob the crawl must stay within (default: seed's parent dir)")
    p_crawl.add_argument("--label", default=None,
                         help="override the profile's default source label")
    p_crawl.set_defaults(func=_cmd_crawl)

    # apply-verdicts — quarantine drop-verdict docs.
    p_apply = subparsers.add_parser(
        "apply-verdicts", help="Quarantine 'drop'-verdict documents out of the live corpus.")
    p_apply.add_argument("corpus_dir", help="corpus directory to apply verdicts to")
    p_apply.add_argument("--dry-run", action="store_true",
                         help="report what would be dropped without moving anything")
    p_apply.set_defaults(func=_cmd_apply_verdicts)

    # completeness — re-fetch a sample at full fidelity (--fetch path).
    p_complete = subparsers.add_parser(
        "completeness",
        help="Sample ~fraction of live docs and re-fetch them at full fidelity.")
    p_complete.add_argument("corpus_dir", help="corpus directory to sample")
    p_complete.add_argument("--fraction", type=float, default=0.1,
                            help="fraction of live docs to sample (default: 0.1)")
    p_complete.set_defaults(func=_cmd_completeness)

    # report — aggregate stats/evals/completeness into REPORT.md (--report path).
    p_report = subparsers.add_parser(
        "report", help="Aggregate crawl stats, evals, and completeness into REPORT.md.")
    p_report.add_argument("corpus_dir", help="corpus directory to report on")
    p_report.set_defaults(func=_cmd_report)

    # index — build/rebuild the FTS5 keyword index over the clean corpus.
    p_index = subparsers.add_parser(
        "index", help="Build/rebuild the FTS5 keyword index over the clean corpus.")
    p_index.add_argument("corpus_dir", help="corpus directory to index")
    p_index.add_argument("--db", default="corpus/index.db",
                         help="output SQLite index path (default: corpus/index.db)")
    p_index.set_defaults(func=_cmd_index)

    # refresh-dli — regenerate the pinned IRCC DLI/PGWP snapshot family (STUDY-01).
    # TOP-LEVEL verb registered directly on `subparsers` (beside index/crawl); there
    # is NO `corpus` parent subcommand. Network happens ONLY at refresh time, inside
    # dli_snapshot.fetch. Exposes NO --url/--out/--from-file: it fetches the fixed
    # IRCC endpoint and writes only corpus/dli/ (SSRF + accidental-publication guard
    # T-41-02). The global `--json` flag (parsed on the main parser) precedes it.
    p_refresh = subparsers.add_parser("refresh-dli",
        help="Refresh the pinned IRCC DLI/PGWP snapshot family (network at refresh only).")
    p_refresh.set_defaults(func=_cmd_refresh_dli)

    # search — BM25-search the FTS5 index, or resolve a citation id with --cite.
    p_search = subparsers.add_parser(
        "search", help="BM25-search the FTS5 index, or resolve a citation id with --cite.")
    p_search.add_argument("query", nargs="?", default=None,
                          help="search query (omit when using --cite)")
    p_search.add_argument("--db", default="corpus/index.db",
                          help="SQLite index path (default: corpus/index.db)")
    p_search.add_argument("--cite", default=None,
                          help="resolve a single chunk_id to its exact chunk")
    p_search.add_argument("--limit", type=int, default=10,
                          help="max ranked hits (default: 10)")
    p_search.add_argument("--family", default=None,
                          help="restrict to a corpus family (e.g. pr-pdi)")
    p_search.set_defaults(func=_cmd_search)

    # ground — fail-closed grounding gate over ONE structured answer read from stdin.
    p_ground = subparsers.add_parser(
        "ground",
        help="Fail-closed grounding gate: check a structured answer's claims[] cite "
             "real, un-drifted chunks (reads the answer JSON from stdin).")
    p_ground.add_argument("--db", default="corpus/index.db",
                          help="SQLite index path (default: corpus/index.db)")
    p_ground.add_argument("--eval", default=None,
                          help="run the gate over a questions.jsonl reference set "
                               "instead of stdin (eval harness): emits the "
                               "eval_runner {total,passed,failed,failures} summary "
                               "and exits 1 if any answer line is ungrounded")
    p_ground.add_argument("--out-dir", default="personal/output",
                          help="on a pass, render→scan→write the cited answer here "
                               "(default: personal/output; must resolve under a "
                               "git-ignored 'personal/' path — render-then-scan, RPT-03)")
    p_ground.set_defaults(func=_cmd_ground)

    # checklist — personalized, fully-cited Layer-1 document checklist from a local
    # profile (CHK-01). Reuses the `ground` render→scan→write-to-personal/output/ path.
    p_checklist = subparsers.add_parser(
        "checklist",
        help="Generate a personalized, fully-cited Layer-1 document checklist "
             "from a local profile.")
    p_checklist.add_argument("--db", default="corpus/index.db",
                             help="SQLite index path (default: corpus/index.db)")
    p_checklist.add_argument("--out-dir", default="personal/output",
                             help="on a pass, render→scan→write the cited checklist "
                                  "here (default: personal/output; must resolve under "
                                  "a git-ignored 'personal/' path — render-then-scan, "
                                  "RPT-03)")
    p_checklist.add_argument("--profile", default=None,
                             help="profile directory holding profile.yaml "
                                  "(default: $PR_PERSONAL_DIR or ./personal/)")
    p_checklist.add_argument("--emit-answer", action="store_true",
                             help="print the assembled answer JSON to stdout and exit "
                                  "WITHOUT gating/rendering/writing (pipe into `ground`)")
    p_checklist.set_defaults(func=_cmd_checklist)

    # vault — additive private candidate-vault verbs (Phase 29). PII-light --json.
    _add_vault_subparser(subparsers)

    # doctor — extraction dependency + scan-quality preflight (Phase 30). PII-light.
    p_doctor = subparsers.add_parser(
        "doctor",
        help="Report extraction dependency + per-document scan-quality status "
             "(EXTRACT-05). PII-light --json envelope.")
    p_doctor.add_argument("--candidate", default=None,
                          help="candidate id (with --document-id) for scan-quality")
    p_doctor.add_argument("--document-id", default=None,
                          help="report scan-quality flags for this vault document")
    p_doctor.set_defaults(func=_cmd_doctor)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "json", False):
        # Non-json (human) mode is unchanged: let exceptions surface normally.
        return args.func(args)
    # --json mode is a STABLE MACHINE CONTRACT: stdout must always be exactly one
    # json.loads-able object, even when an UNEXPECTED exception escapes the
    # compute layer (e.g. a corrupt crawl_stats.json / dropped.log.json inside
    # the corpus). Wrap the dispatch in a last-resort catch-all that converts any
    # otherwise-unhandled exception into a machine-readable ok:false envelope.
    # A generic path-free diagnostic goes to stderr; stdout stays pure JSON.
    try:
        return args.func(args)
    except (SystemExit, KeyboardInterrupt, GeneratorExit):
        raise
    except Exception:  # noqa: BLE001 - stable last-resort machine boundary
        # Unexpected exception text and tracebacks can carry private vault paths,
        # evidence ids, or applicant values. Keep both public JSON and the generic
        # human diagnostic stable and path-free.
        print("unexpected internal error", file=sys.stderr)
        contract.emit(contract.envelope(
            args.command,
            error=(contract.INTERNAL_ERROR, "unexpected internal error")))
        return contract.EXIT_INTERNAL_ERROR


def entrypoint() -> int:
    """Run the installed command without rendering private control-flow payloads."""
    try:
        return main()
    except KeyboardInterrupt:
        return 130
    except GeneratorExit:
        return 1
    except SystemExit as exc:
        # Setuptools ultimately calls sys.exit() with this return value. Preserve
        # numeric argparse/application outcomes, but never let sys.exit render a
        # string or arbitrary object that may contain a private path or evidence id.
        if exc.code is None:
            return 0
        if isinstance(exc.code, int):
            return exc.code
        return 1


if __name__ == "__main__":
    raise SystemExit(entrypoint())
