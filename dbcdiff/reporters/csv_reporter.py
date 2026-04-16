"""
reporters/csv_reporter.py
Writes diff entries as CSV.
"""

from __future__ import annotations
import csv
from typing import TextIO
from ..engine import DiffEntry


FIELDNAMES = ["entity", "kind", "severity", "path", "value_a", "value_b", "protocol", "detail"]


def write_csv(entries: list[DiffEntry], fp: TextIO) -> None:
    writer = csv.DictWriter(fp, fieldnames=FIELDNAMES, lineterminator="\n")
    writer.writeheader()
    for e in entries:
        d = e.as_dict()
        writer.writerow({f: d.get(f, "") for f in FIELDNAMES})
