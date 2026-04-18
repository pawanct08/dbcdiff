"""JSON reporter — writes structured diff output in dbcdiff v0.3 schema."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import TextIO

from ..engine import DiffEntry, Severity, max_severity
from .. import __version__


def _compute_bus_load_delta(entries: list[DiffEntry]) -> dict | None:
    """Aggregate bus-load deltas across all cycle_time CHANGED entries that
    embed a ``bus_load A% → B%`` string in their detail field."""
    _pat = re.compile(r"bus_load\s+([\d.]+)%\s*→\s*([\d.]+)%")
    total_old = total_new = 0.0
    found = False
    for e in entries:
        if e.detail:
            m = _pat.search(e.detail)
            if m:
                total_old += float(m.group(1))
                total_new += float(m.group(2))
                found = True
    if not found:
        return None
    return {
        "old_pct":   round(total_old, 3),
        "new_pct":   round(total_new, 3),
        "delta_pct": round(total_new - total_old, 3),
    }


def write_json(entries: list[DiffEntry], fp: TextIO, pretty: bool = True,
               path_a: str = "", path_b: str = "") -> None:
    """Write a structured JSON diff report in dbcdiff v0.3 schema."""
    ms = max_severity(entries)
    payload = {
        "meta": {
            "tool":      "dbcdiff",
            "version":   __version__,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "file_a":    path_a,
            "file_b":    path_b,
        },
        "summary": {
            "total":      len(entries),
            "breaking":   sum(1 for e in entries if e.severity == Severity.BREAKING),
            "functional": sum(1 for e in entries if e.severity == Severity.FUNCTIONAL),
            "metadata":   sum(1 for e in entries if e.severity == Severity.METADATA),
            "worst":      ms.name if ms else "IDENTICAL",
        },
        "diffs": [e.as_dict() for e in entries],
        "bus_load_delta": _compute_bus_load_delta(entries),
    }
    indent = 2 if pretty else None
    json.dump(payload, fp, indent=indent, default=str)
    fp.write("\n")
