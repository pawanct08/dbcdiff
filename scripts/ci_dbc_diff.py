#!/usr/bin/env python3
"""
scripts/ci_dbc_diff.py
~~~~~~~~~~~~~~~~~~~~~~
CI helper: detects modified .dbc files in a PR, runs *dbcdiff* on each one,
writes per-file HTML/JSON reports, and produces a Markdown summary consumed
by the GitHub Actions workflow.

Exit code mirrors the worst dbcdiff severity across all changed files:
  0 – identical / no changes detected
  1 – metadata changes only
  2 – functional changes
  3 – BREAKING changes  (workflow blocks the merge)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# ── Severity labels ───────────────────────────────────────────────────────────

_ICON: dict[int, str] = {
    0: "🟢 identical",
    1: "🟡 metadata",
    2: "🟠 functional",
    3: "🔴 **BREAKING**",
}
_BADGE: dict[int, str] = {
    0: "🟢 IDENTICAL",
    1: "🟡 METADATA",
    2: "🟠 FUNCTIONAL",
    3: "🔴 BREAKING",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def changed_dbc_files(base_ref: str) -> list[str]:
    """Return relative paths of .dbc files modified in HEAD vs *base_ref*."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=M",
         f"{base_ref}...HEAD", "--", "*.dbc"],
        capture_output=True, text=True, check=True,
    )
    return [f.strip() for f in result.stdout.splitlines() if f.strip()]


def diff_one(rel_path: str, base_ref: str, report_dir: Path) -> int:
    """
    Run ``dbcdiff --git <base_ref> HEAD <rel_path>``  and write HTML + JSON
    reports.  Returns the dbcdiff exit code for this file.
    """
    stem = Path(rel_path).stem
    json_out = str(report_dir / f"{stem}.json")
    html_out = str(report_dir / f"{stem}.html")

    r = subprocess.run(
        [sys.executable, "-m", "dbcdiff",
         "--git", base_ref, "HEAD", rel_path,
         "--json-out", json_out,
         "--html-out", html_out,
         "--no-color"],
        capture_output=True, text=True,
    )
    return r.returncode


def _load_summary_json(report_dir: Path, stem: str) -> dict:
    """Parse the JSON report for a single file; return empty dict on error."""
    try:
        p = report_dir / f"{stem}.json"
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}


def write_summary_md(report_dir: Path, results: dict[str, int]) -> None:
    """Write a Markdown summary for the GitHub PR comment."""
    lines: list[str] = ["## 🚗 DBC Semantic Diff\n"]

    if not results:
        lines.append("_No `.dbc` files were modified in this PR._")
    else:
        for rel_path, code in sorted(results.items()):
            badge = _BADGE.get(code, f"exit {code}")
            stem = Path(rel_path).stem
            data = _load_summary_json(report_dir, stem)
            s = data.get("summary", {})

            breaking   = s.get("breaking",   0)
            functional = s.get("functional",  0)
            metadata   = s.get("metadata",    0)
            total      = s.get("total_changes", breaking + functional + metadata)

            lines.append(f"### `{rel_path}`  —  {badge}")
            if total:
                lines.append(
                    f"- Breaking: **{breaking}**  |  "
                    f"Functional: **{functional}**  |  "
                    f"Metadata: **{metadata}**  |  "
                    f"Total: **{total}**"
                )
            else:
                lines.append("- No differences found.")
            lines.append("")

        lines.append(
            "> 📎 Download the **dbc-diff-reports** artifact for full HTML reports."
        )

    (report_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diff all changed .dbc files between a base ref and HEAD."
    )
    parser.add_argument(
        "--base-ref", required=True,
        help="Git ref for the base branch, e.g. origin/main",
    )
    parser.add_argument(
        "--report-dir", required=True,
        help="Directory where HTML/JSON reports and summary.md are written.",
    )
    args = parser.parse_args()

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    changed = changed_dbc_files(args.base_ref)
    if not changed:
        print("ℹ  No modified .dbc files detected.")
        write_summary_md(report_dir, {})
        sys.exit(0)

    print(f"Found {len(changed)} modified .dbc file(s):")
    results: dict[str, int] = {}

    for rel_path in changed:
        print(f"  • diffing {rel_path} …", end=" ", flush=True)
        code = diff_one(rel_path, args.base_ref, report_dir)
        results[rel_path] = code
        print(_ICON.get(code, f"exit {code}"))

    write_summary_md(report_dir, results)

    worst = max(results.values(), default=0)
    print(f"\nOverall severity: {_BADGE.get(worst, str(worst))}")
    sys.exit(worst)


if __name__ == "__main__":
    main()
