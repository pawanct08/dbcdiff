"""
reporters/json_reporter.py
Serialises diff entries to JSON (stdout or file).
"""

from __future__ import annotations
import json
from typing import TextIO
from ..engine import DiffEntry, Severity, max_severity


def write_json(entries: list[DiffEntry], fp: TextIO, pretty: bool = True,
               path_a: str = "", path_b: str = "") -> None:
    ms = max_severity(entries)
    payload = {
        "summary": {
            "file_a": path_a,
            "file_b": path_b,
            "total_changes": len(entries),
            "max_severity": ms.name if ms else "IDENTICAL",
            "breaking":   sum(1 for e in entries if e.severity == Severity.BREAKING),
            "functional":  sum(1 for e in entries if e.severity == Severity.FUNCTIONAL),
            "metadata":   sum(1 for e in entries if e.severity == Severity.METADATA),
        },
        "changes": [e.as_dict() for e in entries],
    }
    indent = 2 if pretty else None
    json.dump(payload, fp, indent=indent, default=str)
    fp.write("\n")
