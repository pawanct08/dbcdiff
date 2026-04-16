"""
dbcdiff/cli.py
Command-line entry point for dbcdiff.

Exit codes:
  0  – files are identical
  1  – metadata-only differences
  2  – functional changes or added/removed entities
  3  – breaking changes
"""

from __future__ import annotations
import argparse
import sys
import os

import cantools

from . import __version__
from .engine import compare_databases, diff_databases, Severity, max_severity, ADDED, REMOVED, CHANGED


# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

_ANSI = {
    "red":    "\033[0;31m",
    "orange": "\033[0;33m",
    "yellow": "\033[1;33m",
    "green":  "\033[0;32m",
    "cyan":   "\033[0;36m",
    "bold":   "\033[1m",
    "reset":  "\033[0m",
}

_SEV_COLOUR = {
    Severity.BREAKING:   "red",
    Severity.FUNCTIONAL: "orange",
    Severity.METADATA:   "yellow",
}
_SEV_LABEL = {
    Severity.BREAKING:   "🔴 BREAKING",
    Severity.FUNCTIONAL: "🟠 FUNCTIONAL",
    Severity.METADATA:   "🟡 METADATA",
}
_KIND_LABEL = {
    ADDED:   "➕ ADDED",
    REMOVED: "➖ REMOVED",
    CHANGED: "✏️  CHANGED",
}


def _colour(text: str, colour: str, use_colour: bool) -> str:
    if not use_colour:
        return text
    return f"{_ANSI[colour]}{text}{_ANSI['reset']}"


def _bold(text: str, use_colour: bool) -> str:
    return _colour(text, "bold", use_colour)


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dbcdiff",
        description="Semantically compare two DBC (CAN database) files.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Exit codes:
  0  identical
  1  metadata-only differences
  2  functional changes / added / removed
  3  breaking changes

Severity levels:
  breaking    – frame_id, DLC, bit-layout changes that break parsers
  functional  – timing, scale/offset, value range changes
  metadata    – comments, names, units — no parsing impact
""",
    )
    p.add_argument("file_a", metavar="FILE_A.dbc", help="First DBC file")
    p.add_argument("file_b", metavar="FILE_B.dbc", help="Second DBC file")
    p.add_argument(
        "--severity",
        choices=["breaking", "functional", "metadata", "all"],
        default="all",
        help="Report only changes at or above this severity (default: all)",
    )
    p.add_argument("--json", action="store_true",
                   help="Print JSON report to stdout")
    p.add_argument("--json-out", metavar="FILE",
                   help="Write JSON report to FILE")
    p.add_argument("--html-out", metavar="FILE",
                   help="Write HTML report to FILE")
    p.add_argument("--csv-out", metavar="FILE",
                   help="Write CSV report to FILE")
    p.add_argument("--no-color", action="store_true",
                   help="Disable ANSI colour output")
    p.add_argument("--version", action="version",
                   version=f"dbcdiff {__version__}")
    return p


# ---------------------------------------------------------------------------
# Terminal renderer
# ---------------------------------------------------------------------------

_SEV_FILTER_MAP = {
    "breaking":   {Severity.BREAKING},
    "functional": {Severity.BREAKING, Severity.FUNCTIONAL},
    "metadata":   {Severity.BREAKING, Severity.FUNCTIONAL, Severity.METADATA},
    "all":        {Severity.BREAKING, Severity.FUNCTIONAL, Severity.METADATA},
}

_SEVERITY_LEVEL = {
    "breaking":   Severity.BREAKING,
    "functional": Severity.FUNCTIONAL,
    "metadata":   Severity.METADATA,
    "all":        Severity.METADATA,   # include everything
}


def _print_entries(entries, use_colour: bool, severity_filter: str) -> None:
    allowed = _SEV_FILTER_MAP[severity_filter]
    visible = [e for e in entries if e.severity in allowed]
    if not visible:
        return
    for e in visible:
        sev_lbl = _SEV_LABEL.get(e.severity, str(e.severity))
        kind_lbl = _KIND_LABEL.get(e.kind, e.kind)
        col = _SEV_COLOUR.get(e.severity, "reset")
        line = f"  [{_colour(sev_lbl, col, use_colour)}] {_bold(e.entity, use_colour)} · {e.path}  {kind_lbl}"
        if e.value_a is not None and e.value_b is not None:
            line += (
                f"\n      File A: {_colour(str(e.value_a), 'red', use_colour)}"
                f"  →  File B: {_colour(str(e.value_b), 'green', use_colour)}"
            )
        if e.protocol:
            line += f"  [{e.protocol}]"
        if e.detail:
            line += f"\n      {e.detail}"
        print(line)


def _print_summary(entries, use_colour: bool) -> None:
    counts: dict[int, int] = {}
    for e in entries:
        counts[e.severity] = counts.get(e.severity, 0) + 1
    total = sum(counts.values())
    if total == 0:
        print(_colour("✅  No differences found — files are identical.", "green", use_colour))
        return
    print(_bold(f"\nSummary: {total} difference(s)", use_colour))
    for sev, lbl, col in [
        (Severity.BREAKING,   "Breaking",   "red"),
        (Severity.FUNCTIONAL, "Functional", "orange"),
        (Severity.METADATA,   "Metadata",   "yellow"),
    ]:
        n = counts.get(sev, 0)
        if n:
            print(f"  {_colour(lbl, col, use_colour)}: {n}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    use_colour = not args.no_color and sys.stdout.isatty()
    # Windows needs this for ANSI to work
    if use_colour and sys.platform == "win32":
        os.system("color")

    # --- Load databases ---
    try:
        db_a = cantools.database.load_file(args.file_a)
    except Exception as exc:
        print(f"Error loading File A '{args.file_a}': {exc}", file=sys.stderr)
        return 4

    try:
        db_b = cantools.database.load_file(args.file_b)
    except Exception as exc:
        print(f"Error loading File B '{args.file_b}': {exc}", file=sys.stderr)
        return 4

    # --- Diff ---
    entries = compare_databases(db_a, db_b, path_a=args.file_a, path_b=args.file_b)

    # --- Terminal output ---
    print(
        _bold("dbcdiff", use_colour)
        + f"  File A: {_colour(args.file_a, 'cyan', use_colour)}"
        + f"  File B: {_colour(args.file_b, 'cyan', use_colour)}"
    )
    _print_entries(entries, use_colour, args.severity)
    _print_summary(entries, use_colour)

    # --- JSON stdout ---
    if args.json:
        import io
        from .reporters.json_reporter import write_json
        buf = io.StringIO()
        write_json(entries, buf, pretty=True)
        print(buf.getvalue())

    # --- File reporters ---
    if args.json_out:
        from .reporters.json_reporter import write_json
        with open(args.json_out, "w", encoding="utf-8") as fp:
            write_json(entries, fp, pretty=True)
        print(f"JSON → {args.json_out}")

    if args.html_out:
        from .reporters.html_reporter import write_html
        with open(args.html_out, "w", encoding="utf-8") as fp:
            write_html(entries, fp, file_a=args.file_a, file_b=args.file_b)
        print(f"HTML → {args.html_out}")

    if args.csv_out:
        from .reporters.csv_reporter import write_csv
        with open(args.csv_out, "w", encoding="utf-8", newline="") as fp:
            write_csv(entries, fp)
        print(f"CSV  → {args.csv_out}")

    # --- Exit code ---
    worst = max_severity(entries)
    if worst == Severity.BREAKING:
        return 3
    if worst == Severity.FUNCTIONAL:
        return 2
    if worst == Severity.METADATA:
        return 1
    return 0   # identical


if __name__ == "__main__":
    sys.exit(main())
