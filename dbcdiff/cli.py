"""
dbcdiff/cli.py
Command-line entry point for dbcdiff.

Exit codes:
  0  – files are identical
    1  – metadata-only differences
    2  – functional changes
  3  – breaking changes
"""

from __future__ import annotations
import argparse
import sys
import os

import cantools

from . import __version__
from .engine import (
    compare_databases,
    diff_databases,
    Severity,
    max_severity,
    ADDED,
    REMOVED,
    CHANGED,
    RENAME,
    check_consistency,
    max_consistency_level,
    compute_bus_load,
)


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
    Severity.BREAKING:   "🔴 CRITICAL",
    Severity.FUNCTIONAL: "🟠 WARNING",
    Severity.METADATA:   "🟡 INFO",
}
_KIND_LABEL = {
    ADDED:   "➕ ADDED",
    REMOVED: "➖ REMOVED",
    CHANGED: "✏️  CHANGED",
    RENAME:  "🔄 RENAMED",
}

# Plain-text (ASCII-safe) equivalents used when colour/emoji output is disabled
_SEV_LABEL_PLAIN = {
    Severity.BREAKING:   "CRITICAL",
    Severity.FUNCTIONAL: "WARNING",
    Severity.METADATA:   "INFO",
}
_KIND_LABEL_PLAIN = {
    ADDED:   "ADDED",
    REMOVED: "REMOVED",
    CHANGED: "CHANGED",
    RENAME:  "RENAMED",
}

_CHECK_LEVEL_COLOUR = {
    "ERROR": "red",
    "WARNING": "orange",
    "INFO": "cyan",
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
    2  functional changes
  3  breaking changes

Severity levels:
  breaking    – frame_id, DLC, bit-layout changes that break parsers
  functional  – timing, scale/offset, value range changes
  metadata    – comments, names, units — no parsing impact
""",
    )
    p.add_argument("file_a", metavar="FILE_A.dbc/.arxml",
                   nargs="?", default=None,
                   help="First CAN database file (.dbc or .arxml)")
    p.add_argument("file_b", metavar="FILE_B.dbc/.arxml",
                   nargs="?", default=None,
                   help="Second CAN database file (.dbc or .arxml)")
    p.add_argument("file_c", metavar="FILE_C.dbc/.arxml",
                   nargs="?", default=None,
                   help="Optional third file for three-way merge diff "
                        "(base branch_a branch_b)")
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
    p.add_argument("--git", nargs=3,
                   metavar=("REF_A", "REF_B", "PATH"),
                   help="Load two git revisions of the same file: "
                        "--git HEAD~1 HEAD path/to/can.dbc")
    p.add_argument("--baud-rate", type=int, default=500_000, dest="baud_rate",
                   metavar="BPS",
                   help="CAN baud rate for bus-load annotation (default: 500000)")
    p.add_argument("--bus-load", action="store_true", dest="bus_load",
                   help="Print bus load analysis (total %% and top contributors)")
    p.add_argument("--check", action="store_true",
                   help="Run DBC consistency checks and print the results")
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
    sev_labels  = _SEV_LABEL  if use_colour else _SEV_LABEL_PLAIN
    kind_labels = _KIND_LABEL if use_colour else _KIND_LABEL_PLAIN
    for e in visible:
        sev_lbl = sev_labels.get(e.severity, str(e.severity))
        kind_lbl = kind_labels.get(e.kind, e.kind)
        col = _SEV_COLOUR.get(e.severity, "reset")
        msg_type = e.msg_type or "—"
        line = (
            f"  [{_colour(sev_lbl, col, use_colour)}] "
            f"{_bold(e.entity, use_colour)} · {msg_type} · {e.path}  {kind_lbl}"
        )
        if e.value_a is not None and e.value_b is not None:
            line += (
                f"\n      File A: {_colour(str(e.value_a), 'red', use_colour)}"
                f"  →  File B: {_colour(str(e.value_b), 'green', use_colour)}"
            )
        if e.detail:
            line += f"\n      {e.detail}"
        print(line)


def _print_summary(entries, use_colour: bool) -> None:
    counts: dict[int, int] = {}
    for e in entries:
        counts[e.severity] = counts.get(e.severity, 0) + 1
    total = sum(counts.values())
    if total == 0:
        no_diff_msg = "No differences found — files are identical."
        if use_colour:
            no_diff_msg = "✅  " + no_diff_msg
        print(_colour(no_diff_msg, "green", use_colour))
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


def _print_bus_load(rows: list[dict], baud_rate: int, use_colour: bool) -> None:
    total = sum(r["load_pct"] for r in rows)
    print(_bold(f"\nBus Load Analysis ({baud_rate // 1000} kbps)", use_colour))
    print(f"  Total: {total:.2f}%")
    top = rows[:10]
    if top:
        print(f"  {'Message':<30} {'Frame ID':>8} {'DLC':>4} {'Cycle':>9} {'Load%':>8}")
        print(f"  {'-'*30} {'-'*8} {'-'*4} {'-'*9} {'-'*8}")
        for r in top:
            print(f"  {r['name']:<30} {r['frame_id']:>#8X} {r['dlc']:>4} "
                  f"{r['cycle_ms']:>8.0f}ms {r['load_pct']:>7.3f}%")
    if not rows:
        print("  (No messages with cycle time found)")


def _consistency_exit_code(level: str | None) -> int:
    if level == "ERROR":
        return 3
    if level == "WARNING":
        return 2
    if level == "INFO":
        return 1
    return 0


def _print_consistency_issues(label: str, issues, use_colour: bool) -> None:
    print(_bold(f"\nConsistency Check: {label}", use_colour))
    if not issues:
        no_issue_msg = "  No consistency issues found."
        if use_colour:
            no_issue_msg = "  ✅  No consistency issues found."
        print(_colour(no_issue_msg, "green", use_colour))
        return

    for issue in issues:
        colour = _CHECK_LEVEL_COLOUR.get(issue.level, "reset")
        location = issue.message_name or "(database)"
        if issue.signal_name:
            location = f"{location}.{issue.signal_name}"
        print(
            f"  [{_colour(issue.level, colour, use_colour)}] "
            f"{issue.rule_id}  {_bold(location, use_colour)}"
        )
        print(f"      {issue.description}")
        if issue.fix_hint:
            print(f"      Fix: {issue.fix_hint}")


# ---------------------------------------------------------------------------
# Git integration helper  (Feature #6)
# ---------------------------------------------------------------------------

def _git_load_db(ref: str, path: str):
    """Load a CAN database from a git revision using ``git show``."""
    import subprocess
    import tempfile

    ext = os.path.splitext(path)[1] or ".dbc"
    result = subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode(errors="replace").strip())
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(result.stdout)
        tmp_path = tmp.name
    try:
        return cantools.database.load_file(tmp_path)
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# Three-way terminal renderer  (Feature #1)
# ---------------------------------------------------------------------------

def _print_three_way(result, use_colour: bool, severity_filter: str) -> None:
    """Print a three-way diff result to the terminal."""
    if result.conflict:
        print(_bold(f"\u26a0\ufe0f  CONFLICTS ({len(result.conflict)} change(s)):", use_colour))
        _print_entries(result.conflict, use_colour, severity_filter)
    if result.only_in_a:
        print(_bold(f"\nOnly in Branch A ({len(result.only_in_a)}):", use_colour))
        _print_entries(result.only_in_a, use_colour, severity_filter)
    if result.only_in_b:
        print(_bold(f"\nOnly in Branch B ({len(result.only_in_b)}):", use_colour))
        _print_entries(result.only_in_b, use_colour, severity_filter)
    if result.common:
        print(_bold(f"\nIdentical change in both branches ({len(result.common)}):", use_colour))
        _print_entries(result.common, use_colour, severity_filter)
    total = (
        len(result.conflict) + len(result.only_in_a)
        + len(result.only_in_b) + len(result.common)
    )
    if total == 0:
        print(_colour("\u2705  No differences \u2014 all three files are identical.",
                      "green", use_colour))
    elif result.conflict:
        print(_colour(
            f"\n\u26a0\ufe0f  {len(result.conflict)} conflict(s) require manual resolution.",
            "red", use_colour,
        ))


# ---------------------------------------------------------------------------
# Baseline subcommand  (feature: regression baseline tracking)
# ---------------------------------------------------------------------------

def _main_baseline(argv: list[str]) -> int:
    """Dispatch ``dbcdiff baseline set|check FILE``."""
    import argparse as _ap

    p = _ap.ArgumentParser(
        prog="dbcdiff baseline",
        description="Manage regression baselines for DBC files.",
    )
    sub = p.add_subparsers(dest="action", required=True)

    set_p = sub.add_parser("set", help="Store current DBC as baseline snapshot")
    set_p.add_argument("dbc_file", help="Path to the DBC file")

    chk_p = sub.add_parser("check", help="Compare DBC against stored baseline")
    chk_p.add_argument("dbc_file", help="Path to the DBC file")
    chk_p.add_argument(
        "--severity",
        choices=["breaking", "functional", "metadata", "all"],
        default="all",
        help="Report only changes at or above this severity (default: all)",
    )
    chk_p.add_argument("--json", action="store_true",
                       help="Print JSON report to stdout")
    chk_p.add_argument("--no-color", action="store_true",
                       help="Disable ANSI colour output")

    args = p.parse_args(argv)
    use_colour = not getattr(args, "no_color", False) and sys.stdout.isatty()
    if use_colour and sys.platform == "win32":
        os.system("color")

    from .baseline import set_baseline, check_baseline

    if args.action == "set":
        try:
            stored_path = set_baseline(args.dbc_file)
            print(f"✅  Baseline saved → {stored_path}")
            return 0
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 4

    # action == "check"
    try:
        entries = check_baseline(args.dbc_file)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:
        print(f"Error loading file: {exc}", file=sys.stderr)
        return 4

    sev_filter = getattr(args, "severity", "all")
    print(
        _bold("dbcdiff baseline check", use_colour)
        + f"  {_colour(args.dbc_file, 'cyan', use_colour)}"
    )
    _print_entries(entries, use_colour, sev_filter)
    _print_summary(entries, use_colour)

    if getattr(args, "json", False):
        import io
        from .reporters.json_reporter import write_json
        buf = io.StringIO()
        write_json(entries, buf, pretty=True)
        print(buf.getvalue())

    worst = max_severity(entries)
    if worst == Severity.BREAKING:
        return 3
    if worst == Severity.FUNCTIONAL:
        return 2
    if worst == Severity.METADATA:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Convert subcommand  (DBC ↔ Excel)
# ---------------------------------------------------------------------------

def _main_convert(argv: list[str]) -> int:
    """Dispatch ``dbcdiff convert SOURCE [-o OUTPUT]``."""
    import argparse as _ap
    from pathlib import Path

    p = _ap.ArgumentParser(
        prog="dbcdiff convert",
        description="Convert DBC ↔ Excel.  Direction is auto-detected from the "
                    "source file extension (.dbc → .xlsx, .xlsx/.xls → .dbc).",
    )
    p.add_argument("source",
                   help="Source file to convert (.dbc or .xlsx/.xls)")
    p.add_argument("-o", "--output",
                   help="Output path (default: same name, switched extension)")

    args = p.parse_args(argv)
    src = Path(args.source)
    ext = src.suffix.lower()

    if args.output:
        out = Path(args.output)
    elif ext == ".dbc":
        out = src.with_suffix(".xlsx")
    elif ext in (".xlsx", ".xls"):
        out = src.with_suffix(".dbc")
    else:
        print(f"ERROR: unsupported source extension '{ext}'.  "
              "Expected .dbc, .xlsx, or .xls.", file=sys.stderr)
        return 1

    from .converter import dbc_to_excel, excel_to_dbc

    try:
        if ext == ".dbc":
            print(f"Converting DBC → Excel :  {src}  →  {out}")
            dbc_to_excel(str(src), str(out))
        else:
            print(f"Converting Excel → DBC :  {src}  →  {out}")
            excel_to_dbc(str(src), str(out))
        print("Done.")
        return 0
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Export-matrix subcommand  (DBC → formatted Excel workbook)
# ---------------------------------------------------------------------------

def _main_export_matrix(argv: list[str]) -> int:
    """Dispatch ``dbcdiff export-matrix FILE.dbc --out FILE.xlsx``."""
    import argparse as _ap

    p = _ap.ArgumentParser(
        prog="dbcdiff export-matrix",
        description=(
            "Export a CAN DBC file to a formatted Excel workbook.\n\n"
            "The output contains four sheets:\n"
            "  Messages     – one row per CAN message\n"
            "  Signals      – one row per signal with full attributes\n"
            "  Value Tables – enumeration / choice entries\n"
            "  Nodes        – TX and RX message summary per node"
        ),
        formatter_class=_ap.RawDescriptionHelpFormatter,
    )
    p.add_argument("dbc_file", metavar="FILE.dbc",
                   help="Input DBC file to export")
    p.add_argument("--out", metavar="FILE.xlsx", required=True,
                   help="Output Excel file path (.xlsx)")

    args = p.parse_args(argv)

    try:
        db = cantools.database.load_file(args.dbc_file)
    except FileNotFoundError:
        print(f"Error: file not found – '{args.dbc_file}'", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error loading '{args.dbc_file}': {exc}", file=sys.stderr)
        return 1

    try:
        from .reporters.excel_reporter import write_excel
    except ImportError:
        print(
            "Error: openpyxl is required for export-matrix.\n"
            "Install it with:  pip install openpyxl",
            file=sys.stderr,
        )
        return 1

    try:
        write_excel(db, args.out)
    except Exception as exc:
        print(f"Error writing Excel: {exc}", file=sys.stderr)
        return 1

    msg_count = len(db.messages)
    sig_count = sum(len(m.signals) for m in db.messages)
    print(
        f"Excel \u2192 {args.out}"
        f"  ({msg_count} messages, {sig_count} signals)"
    )
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    # Ensure stdout/stderr use UTF-8 so emoji labels are safe on Windows cp1252 consoles.
    # reconfigure() preserves existing buffering/line-discipline settings.
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass  # stream is not reconfigurable (e.g. already replaced in tests)

    # Fast-path: baseline subcommand is handled by its own parser
    _argv = argv if argv is not None else sys.argv[1:]
    if _argv and _argv[0] == "baseline":
        return _main_baseline(_argv[1:])
    if _argv and _argv[0] == "convert":
        return _main_convert(_argv[1:])
    if _argv and _argv[0] == "export-matrix":
        return _main_export_matrix(_argv[1:])

    parser = _build_parser()
    args = parser.parse_args(argv)

    use_colour = not args.no_color and sys.stdout.isatty()
    # Windows needs this for ANSI to work
    if use_colour and sys.platform == "win32":
        os.system("color")

    # ---- Three-way mode (Feature #1) ----
    if args.file_c is not None:
        from .engine import compare_three_way
        if args.file_a is None or args.file_b is None:
            print("Error: three-way mode requires FILE_A FILE_B FILE_C",
                  file=sys.stderr)
            return 4
        try:
            db_base = cantools.database.load_file(args.file_a)
        except Exception as exc:
            print(f"Error loading base '{args.file_a}': {exc}", file=sys.stderr)
            return 4
        try:
            db_a = cantools.database.load_file(args.file_b)
        except Exception as exc:
            print(f"Error loading branch A '{args.file_b}': {exc}", file=sys.stderr)
            return 4
        try:
            db_b = cantools.database.load_file(args.file_c)
        except Exception as exc:
            print(f"Error loading branch B '{args.file_c}': {exc}", file=sys.stderr)
            return 4
        print(
            _bold("dbcdiff 3-way", use_colour)
            + f"  Base: {_colour(args.file_a, 'cyan', use_colour)}"
            + f"  A: {_colour(args.file_b, 'cyan', use_colour)}"
            + f"  B: {_colour(args.file_c, 'cyan', use_colour)}"
        )
        result = compare_three_way(
            db_base, db_a, db_b,
            path_base=args.file_a,
            path_a=args.file_b,
            path_b=args.file_c,
            baud_rate=args.baud_rate,
        )
        _print_three_way(result, use_colour, args.severity)
        all_entries = (
            result.conflict + result.only_in_a + result.only_in_b + result.common
        )
        if result.conflict:
            return 3
        worst = max_severity(all_entries)
        if worst == Severity.BREAKING:
            return 3
        if worst == Severity.FUNCTIONAL:
            return 2
        if worst == Severity.METADATA:
            return 1
        return 0

    # ---- Single-file consistency mode ----
    if args.check and not args.git and args.file_a is not None and args.file_b is None and args.file_c is None:
        try:
            db_single = cantools.database.load_file(args.file_a)
        except Exception as exc:
            print(f"Error loading '{args.file_a}': {exc}", file=sys.stderr)
            return 4

        issues = check_consistency(db_single)
        print(_bold("dbcdiff consistency", use_colour) + f"  File: {_colour(args.file_a, 'cyan', use_colour)}")
        _print_consistency_issues(args.file_a, issues, use_colour)
        return _consistency_exit_code(max_consistency_level(issues))

    # ---- Git mode (Feature #6) ----
    if args.git:
        ref_a, ref_b, path = args.git
        try:
            db_a = _git_load_db(ref_a, path)
        except Exception as exc:
            print(f"Error checking out '{path}' at '{ref_a}': {exc}",
                  file=sys.stderr)
            return 4
        try:
            db_b = _git_load_db(ref_b, path)
        except Exception as exc:
            print(f"Error checking out '{path}' at '{ref_b}': {exc}",
                  file=sys.stderr)
            return 4
        label_a = f"{path}@{ref_a}"
        label_b = f"{path}@{ref_b}"

    # ---- Standard two-file mode ----
    else:
        if args.file_a is None or args.file_b is None:
            print("Error: provide FILE_A and FILE_B (or use --git)",
                  file=sys.stderr)
            return 4
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
        label_a, label_b = args.file_a, args.file_b

    consistency_code = 0
    if args.check:
        issues_a = check_consistency(db_a)
        issues_b = check_consistency(db_b)
        print(_bold("dbcdiff consistency", use_colour))
        _print_consistency_issues(label_a, issues_a, use_colour)
        _print_consistency_issues(label_b, issues_b, use_colour)
        consistency_code = max(
            _consistency_exit_code(max_consistency_level(issues_a)),
            _consistency_exit_code(max_consistency_level(issues_b)),
        )
        print()

    # --- Diff (git + standard modes) ---
    entries = compare_databases(db_a, db_b, path_a=label_a, path_b=label_b,
                                baud_rate=args.baud_rate)

    # --- Terminal output ---
    print(
        _bold("dbcdiff", use_colour)
        + f"  File A: {_colour(label_a, 'cyan', use_colour)}"
        + f"  File B: {_colour(label_b, 'cyan', use_colour)}"
    )
    _print_entries(entries, use_colour, args.severity)
    _print_summary(entries, use_colour)
    if getattr(args, "bus_load", False):
        _print_bus_load(compute_bus_load(db_b, args.baud_rate), args.baud_rate, use_colour)

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
        print(f"JSON \u2192 {args.json_out}")

    if args.html_out:
        from .reporters.html_reporter import write_html
        with open(args.html_out, "w", encoding="utf-8") as fp:
            write_html(entries, fp, file_a=label_a, file_b=label_b,
                       db_a=db_a, db_b=db_b)
        print(f"HTML \u2192 {args.html_out}")

    if args.csv_out:
        from .reporters.csv_reporter import write_csv
        with open(args.csv_out, "w", encoding="utf-8", newline="") as fp:
            write_csv(entries, fp)
        print(f"CSV  \u2192 {args.csv_out}")

    # --- Exit code ---
    worst = max_severity(entries)
    diff_code = 0
    if worst == Severity.BREAKING:
        diff_code = 3
    elif worst == Severity.FUNCTIONAL:
        diff_code = 2
    elif worst == Severity.METADATA:
        diff_code = 1
    return max(diff_code, consistency_code)


if __name__ == "__main__":
    sys.exit(main())
