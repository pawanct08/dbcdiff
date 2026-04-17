"""
dbcdiff.baseline
----------------
Regression-baseline tracking for DBC files.

Usage (CLI)::

    dbcdiff baseline set   path/to/can.dbc   # snapshot current state
    dbcdiff baseline check path/to/can.dbc   # diff current vs snapshot

Usage (API)::

    from dbcdiff.baseline import set_baseline, check_baseline

    stored = set_baseline("can.dbc")          # returns Path of snapshot file
    entries = check_baseline("can.dbc")       # returns list[DiffEntry]

The snapshot is keyed by the *resolved absolute path* of the DBC file so
that the same logical file always maps to the same baseline, regardless of
the current working directory.  Snapshots are stored as pickle files under
``~/.dbcdiff/baselines/``.
"""
from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from typing import TYPE_CHECKING

import cantools

from .engine import compare_databases

if TYPE_CHECKING:
    from .engine import DiffEntry

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_DEFAULT_BASELINE_DIR = Path.home() / ".dbcdiff" / "baselines"


def _baseline_path(dbc_path: str, baseline_dir: Path | None = None) -> Path:
    """Return the Path where the baseline snapshot for *dbc_path* is stored."""
    canonical = str(Path(dbc_path).resolve())
    key = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    d = baseline_dir if baseline_dir is not None else _DEFAULT_BASELINE_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.pkl"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def set_baseline(
    dbc_path: str,
    baseline_dir: Path | None = None,
) -> Path:
    """Snapshot *dbc_path* and save it as the regression baseline.

    Parameters
    ----------
    dbc_path:
        Path to the DBC (or ARXML) file to snapshot.
    baseline_dir:
        Directory in which to store the snapshot.  Defaults to
        ``~/.dbcdiff/baselines/``.

    Returns
    -------
    Path
        Location of the saved snapshot file.

    Raises
    ------
    FileNotFoundError
        If *dbc_path* does not exist.
    """
    db = cantools.database.load_file(dbc_path)
    dest = _baseline_path(dbc_path, baseline_dir)
    dest.write_bytes(pickle.dumps(db))
    return dest


def check_baseline(
    dbc_path: str,
    baseline_dir: Path | None = None,
) -> list[DiffEntry]:
    """Compare *dbc_path* against its stored baseline.

    Parameters
    ----------
    dbc_path:
        Path to the DBC (or ARXML) file to check.
    baseline_dir:
        Directory where snapshots are stored.  Defaults to
        ``~/.dbcdiff/baselines/``.

    Returns
    -------
    list[DiffEntry]
        Differences between baseline (File A) and current file (File B).
        An empty list means the file is identical to the baseline.

    Raises
    ------
    FileNotFoundError
        If no baseline exists for *dbc_path*.  Run
        ``dbcdiff baseline set <file>`` first.
    """
    snap = _baseline_path(dbc_path, baseline_dir)
    if not snap.exists():
        raise FileNotFoundError(
            f"No baseline found for {dbc_path!r}.  "
            f"Run 'dbcdiff baseline set {dbc_path}' first."
        )
    db_baseline: cantools.database.Database = pickle.loads(snap.read_bytes())
    db_current: cantools.database.Database = cantools.database.load_file(dbc_path)
    return compare_databases(
        db_baseline,
        db_current,
        path_a="baseline",
        path_b=dbc_path,
    )
