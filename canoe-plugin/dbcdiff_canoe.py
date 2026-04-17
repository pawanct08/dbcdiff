#!/usr/bin/env python3
"""
canoe-plugin/dbcdiff_canoe.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
CANoe / CANalyzer integration bridge for dbcdiff.

Usage (from CAPL via system() or from a Python automation script):

  python dbcdiff_canoe.py \
      --base  "C:/Project/can/vehicle_v1.dbc" \
      --head  "C:/Project/can/vehicle_v2.dbc" \
      --html  "C:/Temp/diff.html" \
      --json  "C:/Temp/diff.json" \
      [--open-browser] [--severity FUNCTIONAL]

Exit codes mirror dbcdiff:
  0  identical
  1  metadata changes
  2  functional changes   (properties, values)
  3  BREAKING changes     (removed signals / messages)

Use the exit code in a CAPL pre-start test to decide whether to proceed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import webbrowser
from pathlib import Path


_SEV_LABELS = {0: "IDENTICAL", 1: "METADATA", 2: "FUNCTIONAL", 3: "BREAKING"}
_SEV_COLORS = {0: "green",     1: "yellow",   2: "orange",    3: "red"}


def run_dbcdiff(base: str, head: str, html_out: str, json_out: str) -> int:
    """Invoke dbcdiff; return its exit code."""
    cmd = [
        sys.executable, "-m", "dbcdiff",
        base, head,
        "--html-out", html_out,
        "--json-out", json_out,
        "--no-color",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode


def load_summary(json_path: str) -> dict:
    try:
        return json.loads(Path(json_path).read_text())
    except Exception:
        return {}


def print_canoe_log(data: dict, code: int) -> None:
    """Print output in a format parseable by CANoe's CAPL write() log."""
    s = data.get("summary", {})
    label = _SEV_LABELS.get(code, f"EXIT_{code}")
    print(f"[dbcdiff] severity={label}")
    print(f"[dbcdiff] breaking={s.get('breaking', 0)}")
    print(f"[dbcdiff] functional={s.get('functional', 0)}")
    print(f"[dbcdiff] metadata={s.get('metadata', 0)}")
    print(f"[dbcdiff] total_changes={s.get('total_changes', 0)}")


def check_severity_gate(code: int, min_severity: str) -> bool:
    """Return True if the change severity is BELOW the threshold (pass)."""
    thresholds = {"METADATA": 1, "FUNCTIONAL": 2, "BREAKING": 3}
    gate_code = thresholds.get(min_severity.upper(), 3)
    return code < gate_code


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CANoe/CANalyzer bridge for dbcdiff."
    )
    parser.add_argument("--base", required=True,
                        help="Reference (old) DBC file path.")
    parser.add_argument("--head", required=True,
                        help="New DBC file path.")
    parser.add_argument("--html",
                        help="Path to write the HTML diff report.")
    parser.add_argument("--json",
                        help="Path to write the JSON diff report.")
    parser.add_argument("--open-browser", action="store_true",
                        help="Open the HTML report in the default browser.")
    parser.add_argument(
        "--severity", default="BREAKING",
        choices=["METADATA", "FUNCTIONAL", "BREAKING"],
        help="Block (exit 1) if change severity reaches this level.",
    )
    args = parser.parse_args()

    html_out = args.html or str(
        Path(args.head).with_suffix("") / "_dbcdiff.html"
    )
    json_out = args.json or str(
        Path(args.head).with_suffix("") / "_dbcdiff.json"
    )

    print(f"[dbcdiff] base={args.base}")
    print(f"[dbcdiff] head={args.head}")

    code = run_dbcdiff(args.base, args.head, html_out, json_out)
    data = load_summary(json_out)
    print_canoe_log(data, code)

    if args.open_browser and Path(html_out).exists():
        webbrowser.open(Path(html_out).as_uri())

    # Severity gate: fail with exit code 1 to let CAPL detect the block
    if not check_severity_gate(code, args.severity):
        print(
            f"[dbcdiff] ❌ Gate triggered: {_SEV_LABELS.get(code)} >= {args.severity}"
        )
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
