"""
tests/test_engine.py
Unit tests for dbcdiff.engine using in-memory DBC definitions.
"""
from __future__ import annotations

import textwrap
import pytest
import cantools

from dbcdiff.engine import (
    compare_databases,
    Severity,
    ADDED,
    REMOVED,
    CHANGED,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(dbc_text: str):
    """Parse a DBC string into a cantools Database."""
    return cantools.database.load_string(textwrap.dedent(dbc_text))


def _find(entries, kind=None, entity=None, path_fragment=None):
    """Return matching DiffEntry objects from a result list."""
    out = entries
    if kind is not None:
        out = [e for e in out if e.kind == kind]
    if entity is not None:
        out = [e for e in out if e.entity == entity]
    if path_fragment is not None:
        out = [e for e in out if path_fragment in e.path]
    return out


# ---------------------------------------------------------------------------
# Base DBC fragments
# ---------------------------------------------------------------------------

MINIMAL_MSG = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 100 EngineData: 8 Vector__XXX
 SG_ RPM : 0|16@1+ (1,0) [0|8000] "rpm" Vector__XXX
 SG_ Temp : 16|8@1+ (0.5,-40) [0|150] "degC" Vector__XXX

"""

# Same message, signal RPM removed
MSG_RPM_REMOVED = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 100 EngineData: 8 Vector__XXX
 SG_ Temp : 16|8@1+ (0.5,-40) [0|150] "degC" Vector__XXX

"""

# Same message, new signal overlapping RPM bits 0-15
MSG_OVERLAP_ADDED = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 100 EngineData: 8 Vector__XXX
 SG_ Temp : 16|8@1+ (0.5,-40) [0|150] "degC" Vector__XXX
 SG_ EngineLoad : 0|16@1+ (0.1,0) [0|100] "%" Vector__XXX

"""

# Same message, new signal NOT overlapping RPM bits
MSG_NO_OVERLAP_ADDED = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 100 EngineData: 8 Vector__XXX
 SG_ RPM : 0|16@1+ (1,0) [0|8000] "rpm" Vector__XXX
 SG_ Temp : 16|8@1+ (0.5,-40) [0|150] "degC" Vector__XXX
 SG_ FuelRate : 32|8@1+ (0.1,0) [0|25] "L/h" Vector__XXX

"""

# Entirely different message name/ID in B
DIFFERENT_MSG = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 200 TransmData: 8 Vector__XXX
 SG_ Gear : 0|4@1+ (1,0) [0|8] "" Vector__XXX

"""

# RPM scale changed (FUNCTIONAL)
MSG_SCALE_CHANGED = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 100 EngineData: 8 Vector__XXX
 SG_ RPM : 0|16@1+ (0.5,0) [0|8000] "rpm" Vector__XXX
 SG_ Temp : 16|8@1+ (0.5,-40) [0|150] "degC" Vector__XXX

"""

# RPM comment changed (METADATA)
MSG_COMMENT_CHANGED = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 100 EngineData: 8 Vector__XXX
 SG_ RPM : 0|16@1+ (1,0) [0|8000] "rpm" Vector__XXX
 SG_ Temp : 16|8@1+ (0.5,-40) [0|150] "degC" Vector__XXX

CM_ SG_ 100 RPM "Updated engine RPM description";

"""

# Message frame_id changed (BREAKING)
MSG_FRAMEID_CHANGED = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 101 EngineData: 8 Vector__XXX
 SG_ RPM : 0|16@1+ (1,0) [0|8000] "rpm" Vector__XXX
 SG_ Temp : 16|8@1+ (0.5,-40) [0|150] "degC" Vector__XXX

"""


# ---------------------------------------------------------------------------
# Message-level tests
# ---------------------------------------------------------------------------

class TestMessageSeverity:

    def test_message_removed_is_breaking(self):
        """A message present in A but gone in B must be BREAKING."""
        db_a = _load(MINIMAL_MSG)
        db_b = _load(DIFFERENT_MSG)
        entries = compare_databases(db_a, db_b)
        removed = _find(entries, kind=REMOVED, entity="message", path_fragment="EngineData")
        assert removed, "Expected a REMOVED message entry for EngineData"
        assert removed[0].severity == Severity.BREAKING

    def test_message_added_is_breaking(self):
        """A message absent in A but present in B must be BREAKING."""
        db_a = _load(DIFFERENT_MSG)
        db_b = _load(MINIMAL_MSG)
        entries = compare_databases(db_a, db_b)
        added = _find(entries, kind=ADDED, entity="message", path_fragment="EngineData")
        assert added, "Expected an ADDED message entry for EngineData"
        assert added[0].severity == Severity.BREAKING

    def test_frame_id_change_is_breaking(self):
        """
        Changing a message's frame_id produces REMOVED (old id) + ADDED (new id)
        — both must be BREAKING, because the wire identity of the message changed.
        """
        db_a = _load(MINIMAL_MSG)
        db_b = _load(MSG_FRAMEID_CHANGED)
        entries = compare_databases(db_a, db_b)
        # The engine cannot tell "same message, different id" from a removal+addition,
        # so we get two BREAKING message entries.
        removed = _find(entries, kind=REMOVED, entity="message", path_fragment="EngineData")
        added   = _find(entries, kind=ADDED,   entity="message", path_fragment="EngineData")
        assert removed, "Expected REMOVED message entry when frame_id changes"
        assert added,   "Expected ADDED   message entry when frame_id changes"
        assert removed[0].severity == Severity.BREAKING
        assert added[0].severity   == Severity.BREAKING


# ---------------------------------------------------------------------------
# Signal-level tests
# ---------------------------------------------------------------------------

class TestSignalSeverity:

    def test_signal_removed_with_overlap_is_breaking(self):
        """
        RPM removed from A, but EngineLoad (same bits 0-15) present in B
        → overlap → BREAKING.
        """
        db_a = _load(MINIMAL_MSG)
        db_b = _load(MSG_OVERLAP_ADDED)
        entries = compare_databases(db_a, db_b)
        removed = _find(entries, kind=REMOVED, entity="signal", path_fragment="RPM")
        assert removed, "Expected REMOVED signal entry for RPM"
        assert removed[0].severity == Severity.BREAKING, (
            f"Expected BREAKING for overlapping removed signal, got {removed[0].severity}"
        )

    def test_signal_removed_without_overlap_is_functional(self):
        """
        RPM removed from EngineData in B, Temp stays; no other signal uses bits 0-15
        → no overlap → FUNCTIONAL.
        """
        db_a = _load(MINIMAL_MSG)
        db_b = _load(MSG_RPM_REMOVED)
        entries = compare_databases(db_a, db_b)
        removed = _find(entries, kind=REMOVED, entity="signal", path_fragment="RPM")
        assert removed, "Expected REMOVED signal entry for RPM"
        assert removed[0].severity == Severity.FUNCTIONAL, (
            f"Expected FUNCTIONAL for non-overlapping removed signal, got {removed[0].severity}"
        )

    def test_signal_added_with_overlap_is_breaking(self):
        """
        EngineLoad added in B occupying bits 0-15 (same as RPM in A)
        → overlap → BREAKING.
        """
        db_a = _load(MSG_RPM_REMOVED)      # no RPM (bits 0-15 free in A)
        # Actually: A has Temp@16, so adding EngineLoad@0 into B overlaps nothing in A.
        # Re-use the scenario where A *has* RPM and B has EngineLoad instead.
        db_a2 = _load(MINIMAL_MSG)
        db_b2 = _load(MSG_OVERLAP_ADDED)
        entries = compare_databases(db_a2, db_b2)
        added = _find(entries, kind=ADDED, entity="signal", path_fragment="EngineLoad")
        assert added, "Expected ADDED signal entry for EngineLoad"
        assert added[0].severity == Severity.BREAKING, (
            f"Expected BREAKING for overlapping added signal, got {added[0].severity}"
        )

    def test_signal_added_without_overlap_is_functional(self):
        """
        FuelRate added at bits 32-39, no existing signal covers those bits
        → no overlap → FUNCTIONAL.
        """
        db_a = _load(MINIMAL_MSG)
        db_b = _load(MSG_NO_OVERLAP_ADDED)
        entries = compare_databases(db_a, db_b)
        added = _find(entries, kind=ADDED, entity="signal", path_fragment="FuelRate")
        assert added, "Expected ADDED signal entry for FuelRate"
        assert added[0].severity == Severity.FUNCTIONAL, (
            f"Expected FUNCTIONAL for non-overlapping added signal, got {added[0].severity}"
        )

    def test_signal_scale_change_is_functional(self):
        """Changing signal scale (but not bit position) → FUNCTIONAL."""
        db_a = _load(MINIMAL_MSG)
        db_b = _load(MSG_SCALE_CHANGED)
        entries = compare_databases(db_a, db_b)
        changed = _find(entries, kind=CHANGED, entity="signal", path_fragment="RPM")
        scale_entries = [e for e in changed if "scale" in e.path or "factor" in e.path.lower()]
        assert scale_entries, "Expected a CHANGED entry for RPM scale"
        assert scale_entries[0].severity == Severity.FUNCTIONAL

    def test_signal_comment_change_is_metadata(self):
        """Changing a signal comment → METADATA."""
        db_a = _load(MINIMAL_MSG)
        db_b = _load(MSG_COMMENT_CHANGED)
        entries = compare_databases(db_a, db_b)
        changed = _find(entries, kind=CHANGED, entity="signal", path_fragment="RPM")
        comment_entries = [e for e in changed if "comment" in e.path.lower()]
        assert comment_entries, "Expected a CHANGED entry for RPM comment"
        assert comment_entries[0].severity == Severity.METADATA


# ---------------------------------------------------------------------------
# Identical DBCs → empty diff
# ---------------------------------------------------------------------------

class TestIdentical:

    def test_identical_dbs_produce_no_entries(self):
        """Comparing a DBC against itself must return an empty list."""
        db = _load(MINIMAL_MSG)
        entries = compare_databases(db, db)
        # Filter out any summary/info entries if the engine adds them
        diff_entries = [e for e in entries if e.kind in (ADDED, REMOVED, CHANGED)]
        assert diff_entries == [], f"Expected no diff entries, got: {diff_entries}"
