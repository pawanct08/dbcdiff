"""
reporters/csv_reporter.py
Writes diff entries as CSV.
"""

from __future__ import annotations
import csv
from typing import Optional, TextIO
from ..engine import DiffEntry, Severity


FIELDNAMES = ["entity", "kind", "severity", "path", "value_a", "value_b", "protocol", "detail"]


def write_csv(
    entries: list[DiffEntry],
    fp: TextIO,
    min_severity: Optional[Severity] = None,
) -> None:
    filtered = [
        e for e in entries
        if min_severity is None or e.severity >= min_severity
    ]
    sorted_entries = sorted(filtered, key=lambda e: -e.severity)
    writer = csv.DictWriter(fp, fieldnames=FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    for e in sorted_entries:
        d = e.as_dict()
        writer.writerow({f: d.get(f, "") for f in FIELDNAMES})
