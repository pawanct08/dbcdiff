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
    RENAME,
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


# ---------------------------------------------------------------------------
# Feature #4 — Value table / choices semantic diff
# ---------------------------------------------------------------------------

# Base: signal with choices {0: "Idle", 1: "Run", 2: "Error"}
MSG_WITH_CHOICES_A = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 300 StatusMsg: 2 Vector__XXX
 SG_ Mode : 0|4@1+ (1,0) [0|15] "" Vector__XXX

VAL_ 300 Mode 0 "Idle" 1 "Run" 2 "Error" ;
"""

# Changed: key 1 renamed Run→Running, key 3 added, key 2 removed
MSG_WITH_CHOICES_B = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 300 StatusMsg: 2 Vector__XXX
 SG_ Mode : 0|4@1+ (1,0) [0|15] "" Vector__XXX

VAL_ 300 Mode 0 "Idle" 1 "Running" 3 "Fault" ;
"""


class TestChoicesSemanticDiff:

    def test_unchanged_key_produces_no_entry(self):
        """Key 0 'Idle' unchanged in both files → must not appear in result."""
        db_a = _load(MSG_WITH_CHOICES_A)
        db_b = _load(MSG_WITH_CHOICES_B)
        from dbcdiff.engine import _expand_choices_diff
        entries = compare_databases(db_a, db_b)
        choices_entries = [e for e in entries if "choices" in e.path.lower()]
        # Key 0 "Idle" unchanged — must not appear as its own row
        key0_entries = [e for e in choices_entries if "[0]" in e.path]
        assert key0_entries == [], f"Unchanged key 0 should not appear, got: {key0_entries}"

    def test_renamed_choice_is_changed(self):
        """Key 1 changes from 'Run' to 'Running' → CHANGED row with [1] in path."""
        db_a = _load(MSG_WITH_CHOICES_A)
        db_b = _load(MSG_WITH_CHOICES_B)
        entries = compare_databases(db_a, db_b)
        changed = _find(entries, kind=CHANGED, path_fragment="[1]")
        assert changed, "Expected a CHANGED entry for choices key 1 (Run→Running)"

    def test_new_choice_key_is_added(self):
        """Key 3 'Fault' exists only in B → ADDED row with [3] in path."""
        db_a = _load(MSG_WITH_CHOICES_A)
        db_b = _load(MSG_WITH_CHOICES_B)
        entries = compare_databases(db_a, db_b)
        added = _find(entries, kind=ADDED, path_fragment="[3]")
        assert added, "Expected an ADDED entry for choices key 3 (Fault)"

    def test_removed_choice_key_is_removed(self):
        """Key 2 'Error' exists only in A → REMOVED row with [2] in path."""
        db_a = _load(MSG_WITH_CHOICES_A)
        db_b = _load(MSG_WITH_CHOICES_B)
        entries = compare_databases(db_a, db_b)
        removed = _find(entries, kind=REMOVED, path_fragment="[2]")
        assert removed, "Expected a REMOVED entry for choices key 2 (Error)"

    def test_expand_choices_diff_direct(self):
        """Unit-test _expand_choices_diff() directly with a synthetic DiffEntry."""
        from dbcdiff.engine import _expand_choices_diff, DiffEntry
        e = DiffEntry(
            entity="Mode",
            kind=CHANGED,
            severity=Severity.METADATA,
            path="StatusMsg.Mode.choices",
            value_a={1: "Idle", 2: "Run"},
            value_b={1: "Idle", 2: "Running", 3: "Error"},
        )
        result = _expand_choices_diff([e])
        paths = [r.path for r in result]
        # Key 1 unchanged → no row
        assert not any("[1]" in p for p in paths), "Key 1 unchanged, should not appear"
        # Key 2 changed
        assert any(r.kind == CHANGED and "[2]" in r.path for r in result), (
            "Key 2 renamed: expected CHANGED row"
        )
        # Key 3 added
        assert any(r.kind == ADDED and "[3]" in r.path for r in result), (
            "Key 3 new: expected ADDED row"
        )


# ---------------------------------------------------------------------------
# Feature #5 — Cycle time / bus-load annotation
# ---------------------------------------------------------------------------

MSG_CYCLE_100 = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 400 BusLoad: 8 Vector__XXX
 SG_ Speed : 0|16@1+ (1,0) [0|300] "km/h" Vector__XXX

BA_DEF_ BO_ "GenMsgCycleTime" INT 0 10000;
BA_DEF_DEF_ "GenMsgCycleTime" 0;
BA_ "GenMsgCycleTime" BO_ 400 100;
"""

MSG_CYCLE_200 = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 400 BusLoad: 8 Vector__XXX
 SG_ Speed : 0|16@1+ (1,0) [0|300] "km/h" Vector__XXX

BA_DEF_ BO_ "GenMsgCycleTime" INT 0 10000;
BA_DEF_DEF_ "GenMsgCycleTime" 0;
BA_ "GenMsgCycleTime" BO_ 400 200;
"""


class TestBusLoadAnnotation:

    def test_cycle_time_change_detected(self):
        """Changing GenMsgCycleTime from 100 to 200 must produce a CHANGED entry."""
        db_a = _load(MSG_CYCLE_100)
        db_b = _load(MSG_CYCLE_200)
        entries = compare_databases(db_a, db_b)
        cycle_entries = _find(entries, kind=CHANGED, path_fragment="cycle_time")
        assert cycle_entries, "Expected a CHANGED entry for cycle_time"

    def test_baud_rate_kwarg_accepted(self):
        """compare_databases() must not raise when baud_rate kwarg is supplied."""
        db_a = _load(MINIMAL_MSG)
        db_b = _load(MSG_SCALE_CHANGED)
        entries = compare_databases(db_a, db_b, baud_rate=250_000)
        assert isinstance(entries, list)

    def test_baud_rate_does_not_affect_non_cycle_entries(self):
        """Changing baud_rate must not change the number of diff entries."""
        db_a = _load(MINIMAL_MSG)
        db_b = _load(MSG_RPM_REMOVED)
        entries_500 = compare_databases(db_a, db_b, baud_rate=500_000)
        entries_250 = compare_databases(db_a, db_b, baud_rate=250_000)
        assert len(entries_500) == len(entries_250), (
            "baud_rate should not change entry count when cycle_time is unchanged"
        )


# ---------------------------------------------------------------------------
# Feature #1 — Three-way merge diff
# ---------------------------------------------------------------------------

# Base: RPM scale = 1.0
THREE_WAY_BASE = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 500 VehicleData: 8 Vector__XXX
 SG_ RPM : 0|16@1+ (1,0) [0|8000] "rpm" Vector__XXX
 SG_ Speed : 16|16@1+ (0.1,0) [0|300] "km/h" Vector__XXX

"""

# Branch A only: RPM scale changed to 0.5
THREE_WAY_BRANCH_A_ONLY = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 500 VehicleData: 8 Vector__XXX
 SG_ RPM : 0|16@1+ (0.5,0) [0|8000] "rpm" Vector__XXX
 SG_ Speed : 16|16@1+ (0.1,0) [0|300] "km/h" Vector__XXX

"""

# Branch B only: Speed scale changed to 0.5
THREE_WAY_BRANCH_B_ONLY = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 500 VehicleData: 8 Vector__XXX
 SG_ RPM : 0|16@1+ (1,0) [0|8000] "rpm" Vector__XXX
 SG_ Speed : 16|16@1+ (0.5,0) [0|300] "km/h" Vector__XXX

"""

# Both branches: RPM scale changed but to *different* values → conflict
THREE_WAY_BRANCH_A_CONFLICT = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 500 VehicleData: 8 Vector__XXX
 SG_ RPM : 0|16@1+ (0.5,0) [0|8000] "rpm" Vector__XXX
 SG_ Speed : 16|16@1+ (0.1,0) [0|300] "km/h" Vector__XXX

"""

THREE_WAY_BRANCH_B_CONFLICT = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 500 VehicleData: 8 Vector__XXX
 SG_ RPM : 0|16@1+ (2,0) [0|8000] "rpm" Vector__XXX
 SG_ Speed : 16|16@1+ (0.1,0) [0|300] "km/h" Vector__XXX

"""


class TestThreeWayDiff:

    def test_only_in_a_when_b_unchanged(self):
        """Change only in branch A: result.only_in_a must be non-empty."""
        from dbcdiff.engine import compare_three_way
        db_base = _load(THREE_WAY_BASE)
        db_a    = _load(THREE_WAY_BRANCH_A_ONLY)   # RPM scale 1→0.5
        db_b    = _load(THREE_WAY_BASE)              # unchanged
        result = compare_three_way(db_base, db_a, db_b)
        assert result.only_in_a, "Expected changes only in branch A"
        assert result.only_in_b == [], "Expected no changes in branch B"
        assert result.conflict  == [], "Expected no conflicts"

    def test_only_in_b_when_a_unchanged(self):
        """Change only in branch B: result.only_in_b must be non-empty."""
        from dbcdiff.engine import compare_three_way
        db_base = _load(THREE_WAY_BASE)
        db_a    = _load(THREE_WAY_BASE)              # unchanged
        db_b    = _load(THREE_WAY_BRANCH_B_ONLY)    # Speed scale 0.1→0.5
        result = compare_three_way(db_base, db_a, db_b)
        assert result.only_in_b, "Expected changes only in branch B"
        assert result.only_in_a == [], "Expected no changes in branch A"
        assert result.conflict  == [], "Expected no conflicts"

    def test_conflict_when_both_change_same_field_differently(self):
        """Both branches change RPM scale to different values → conflict."""
        from dbcdiff.engine import compare_three_way
        db_base = _load(THREE_WAY_BASE)
        db_a    = _load(THREE_WAY_BRANCH_A_CONFLICT)   # RPM scale → 0.5
        db_b    = _load(THREE_WAY_BRANCH_B_CONFLICT)   # RPM scale → 2
        result = compare_three_way(db_base, db_a, db_b)
        assert result.conflict, "Expected conflict when same field changed differently in each branch"

    def test_no_conflict_when_both_make_same_change(self):
        """Both branches make *identical* changes to the same field → no conflict."""
        from dbcdiff.engine import compare_three_way
        db_base = _load(THREE_WAY_BASE)
        db_a    = _load(THREE_WAY_BRANCH_A_CONFLICT)   # RPM scale → 0.5
        db_b    = _load(THREE_WAY_BRANCH_A_CONFLICT)   # RPM scale → 0.5 (same)
        result = compare_three_way(db_base, db_a, db_b)
        assert result.conflict == [], (
            "No conflict expected when both branches make the same change"
        )

    def test_three_way_identical_bases_empty(self):
        """All three DBCs identical → all result lists empty."""
        from dbcdiff.engine import compare_three_way
        db = _load(THREE_WAY_BASE)
        result = compare_three_way(db, db, db)
        assert result.only_in_a == []
        assert result.only_in_b == []
        assert result.conflict  == []
        assert result.common    == []


# ---------------------------------------------------------------------------
# Feature #6 — Semantic rename detection
# ---------------------------------------------------------------------------

# RPM renamed to EngineSpeed (identical geometry: bit 0|16, scale=1, offset=0)
MSG_RPM_RENAMED = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 100 EngineData: 8 Vector__XXX
 SG_ EngineSpeed : 0|16@1+ (1,0) [0|8000] "rpm" Vector__XXX
 SG_ Temp : 16|8@1+ (0.5,-40) [0|150] "degC" Vector__XXX

"""

# RPM scale changed AND renamed → different fingerprint → should NOT produce RENAME
MSG_RPM_RENAMED_DIFF_SCALE = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 100 EngineData: 8 Vector__XXX
 SG_ EngineSpeed : 0|16@1+ (0.5,0) [0|8000] "rpm" Vector__XXX
 SG_ Temp : 16|8@1+ (0.5,-40) [0|150] "degC" Vector__XXX

"""


class TestRenameDetection:

    def test_signal_rename_detected(self):
        """Same geometry, new name → single RENAME, no plain REMOVED/ADDED for that signal."""
        db_a = _load(MINIMAL_MSG)
        db_b = _load(MSG_RPM_RENAMED)
        entries = compare_databases(db_a, db_b)
        renames = _find(entries, kind=RENAME, entity="signal")
        assert len(renames) == 1, f"Expected 1 RENAME, got {renames}"
        assert renames[0].value_a == "RPM"
        assert renames[0].value_b == "EngineSpeed"
        assert renames[0].severity == Severity.METADATA
        assert not _find(entries, kind=REMOVED, path_fragment="RPM"), \
            "Plain REMOVED must not co-exist with RENAME for same signal"
        assert not _find(entries, kind=ADDED, path_fragment="EngineSpeed"), \
            "Plain ADDED must not co-exist with RENAME for same signal"

    def test_different_geometry_not_renamed(self):
        """Different scale → plain REMOVED + ADDED, no RENAME."""
        db_a = _load(MINIMAL_MSG)
        db_b = _load(MSG_RPM_RENAMED_DIFF_SCALE)
        entries = compare_databases(db_a, db_b)
        assert not _find(entries, kind=RENAME), \
            "Scale change should not produce RENAME"
        assert _find(entries, kind=REMOVED, path_fragment="RPM"), \
            "Old RPM must appear as REMOVED"
        assert _find(entries, kind=ADDED, path_fragment="EngineSpeed"), \
            "New EngineSpeed must appear as ADDED"

    def test_partial_rename_and_plain_remove(self):
        """RPM renamed + Temp fully removed → 1 RENAME + 1 REMOVED."""
        MSG_RPM_RENAMED_TEMP_GONE = """\
VERSION ""

NS_ :

BS_:

BU_:

BO_ 100 EngineData: 8 Vector__XXX
 SG_ EngineSpeed : 0|16@1+ (1,0) [0|8000] "rpm" Vector__XXX

"""
        db_a = _load(MINIMAL_MSG)
        db_b = _load(MSG_RPM_RENAMED_TEMP_GONE)
        entries = compare_databases(db_a, db_b)
        renames = _find(entries, kind=RENAME)
        assert len(renames) == 1
        assert renames[0].value_a == "RPM"
        assert renames[0].value_b == "EngineSpeed"
        removed_sigs = _find(entries, kind=REMOVED, entity="signal")
        assert len(removed_sigs) == 1
        assert "Temp" in removed_sigs[0].path


# ---------------------------------------------------------------------------
# Feature #7 — Regression baseline tracking
# ---------------------------------------------------------------------------

class TestBaseline:

    def test_set_creates_pkl_file(self, tmp_path):
        """set_baseline() must write a non-empty .pkl file."""
        from dbcdiff.baseline import set_baseline
        dbc = tmp_path / "test.dbc"
        dbc.write_text(textwrap.dedent(MINIMAL_MSG))
        stored = set_baseline(str(dbc), baseline_dir=tmp_path / "bl")
        assert stored.exists(), "Baseline file should be created"
        assert stored.suffix == ".pkl"
        assert stored.stat().st_size > 0

    def test_check_identical_returns_no_changes(self, tmp_path):
        """Checking an unchanged file returns no ADDED/REMOVED/CHANGED/RENAME entries."""
        from dbcdiff.baseline import set_baseline, check_baseline
        dbc = tmp_path / "test.dbc"
        dbc.write_text(textwrap.dedent(MINIMAL_MSG))
        bl_dir = tmp_path / "bl"
        set_baseline(str(dbc), baseline_dir=bl_dir)
        entries = check_baseline(str(dbc), baseline_dir=bl_dir)
        diff_kinds = {ADDED, REMOVED, CHANGED, RENAME}
        change_entries = [e for e in entries if e.kind in diff_kinds]
        assert change_entries == [], f"Unexpected changes against identical baseline: {change_entries}"

    def test_check_detects_scale_change(self, tmp_path):
        """After changing RPM scale, check_baseline surfaces a CHANGED entry."""
        from dbcdiff.baseline import set_baseline, check_baseline
        dbc = tmp_path / "test.dbc"
        dbc.write_text(textwrap.dedent(MINIMAL_MSG))
        bl_dir = tmp_path / "bl"
        set_baseline(str(dbc), baseline_dir=bl_dir)
        dbc.write_text(textwrap.dedent(MSG_SCALE_CHANGED))
        entries = check_baseline(str(dbc), baseline_dir=bl_dir)
        changed = _find(entries, kind=CHANGED, path_fragment="RPM")
        assert changed, "Expected a CHANGED entry for RPM scale after baseline check"

    def test_check_missing_baseline_raises(self, tmp_path):
        """check_baseline raises FileNotFoundError when no snapshot exists."""
        from dbcdiff.baseline import check_baseline
        dbc = tmp_path / "test.dbc"
        dbc.write_text(textwrap.dedent(MINIMAL_MSG))
        with pytest.raises(FileNotFoundError, match="baseline"):
            check_baseline(str(dbc), baseline_dir=tmp_path / "no_such_dir")
