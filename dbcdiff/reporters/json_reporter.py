"""
reporters/json_reporter.py
Serialises diff entries to JSON (stdout or file).
"""

from __future__ import annotations
import json
from typing import TextIO
from ..engine import DiffEntry, Severity, max_severity


def write_json(entries: list[DiffEntry], fp: TextIO, pretty: bool = True) -> None:
    payload = {
        "summary": {
            "total_changes": len(entries),
            "max_severity": max_severity(entries).name,
            "breaking":   sum(1 for e in entries if e.severity == Severity.BREAKING),
            "functional":  sum(1 for e in entries if e.severity == Severity.FUNCTIONAL),
            "metadata":   sum(1 for e in entries if e.severity == Severity.METADATA),
        },
        "changes": [e.as_dict() for e in entries],
    }
    indent = 2 if pretty else None
    json.dump(payload, fp, indent=indent, default=str)
    fp.write("\n")
