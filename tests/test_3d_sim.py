"""
tests/test_3d_sim.py
Unit tests for the 3-D Bus Simulation data-building logic that lives in
ThreeSimWidget._build_data().  No QApplication or display required — we test
the pure-Python helpers by reaching into the class directly via a lightweight
mock wrapper.
"""
from __future__ import annotations

import sys
import types
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import cantools

# ---------------------------------------------------------------------------
# Helpers for building synthetic cantools objects
# ---------------------------------------------------------------------------

def _make_signal(name: str, start: int, length: int, is_signed: bool = False):
    """Return a real cantools Signal with the minimum required attributes."""
    return cantools.database.Signal(
        name=name,
        start=start,
        length=length,
        is_signed=is_signed,
    )


def _make_message(frame_id: int, name: str, sigs=(), cycle_time=None, senders=()):
    """Return a real cantools Message."""
    return cantools.database.Message(
        frame_id=frame_id,
        name=name,
        length=8,
        signals=list(sigs),
        cycle_time=cycle_time,
        senders=list(senders) or [],
    )


def _make_db(messages):
    """Return a cantools Database from a list of messages."""
    db = cantools.database.Database()
    for m in messages:
        db.messages.append(m)
    return db


# ---------------------------------------------------------------------------
# Lazy import of ThreeSimWidget without full PySide6 (headless safe)
# ---------------------------------------------------------------------------

def _import_build_data():
    """
    Import just the _build_data static/instance logic by constructing a
    minimal ThreeSimWidget-like object that doesn't need a real QWidget.
    Returns the bound method ready to call.
    """
    # If PySide6 is available, import normally
    try:
        from dbcdiff.gui import ThreeSimWidget  # noqa: PLC0415  (local import OK)

        class _Fake(ThreeSimWidget):
            """Headless subclass that bypasses all Qt widget construction."""
            def __init__(self, db, entries, mode):
                # Skip Qt super().__init__; just set the cache attrs
                self._db = db
                self._entries = entries
                self._sim_mode = mode
                self._view = None   # no WebEngine

        return _Fake

    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Cannot import ThreeSimWidget: {exc}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuildData:
    """Tests for ThreeSimWidget._build_data() correctness."""

    _Fake = None  # populated lazily

    @classmethod
    def setup_class(cls):
        cls._Fake = _import_build_data()

    def _make(self, db, entries, mode="viewer"):
        return self._Fake(db, entries, mode)

    # --- basic structure ---

    def test_returns_dict_with_mode_and_messages(self):
        db = _make_db([_make_message(1, "MSG_A")])
        obj = self._make(db, [])
        result = obj._build_data()
        assert isinstance(result, dict)
        assert "mode" in result
        assert "messages" in result

    def test_mode_propagated(self):
        db = _make_db([])
        for mode in ("viewer", "diff"):
            obj = self._make(db, [], mode)
            assert obj._build_data()["mode"] == mode

    # --- message fields ---

    def test_message_fields_present(self):
        msg = _make_message(0x100, "ENGINE", senders=["ECM"], cycle_time=10)
        db = _make_db([msg])
        obj = self._make(db, [])
        m_data = obj._build_data()["messages"][0]
        assert m_data["name"] == "ENGINE"
        assert m_data["frame_id"] == 0x100
        assert m_data["cycle_time"] == 10
        assert m_data["senders"] == ["ECM"]
        assert m_data["dlc"] == 8

    def test_message_without_cycle_time_defaults_to_zero(self):
        msg = _make_message(1, "NO_CYCLE", cycle_time=None)
        db = _make_db([msg])
        obj = self._make(db, [])
        m_data = obj._build_data()["messages"][0]
        assert m_data["cycle_time"] == 0

    # --- signal fields ---

    def test_signal_start_bit_field_is_integer(self):
        """The critical regression test: s.start must not raise AttributeError."""
        sig = _make_signal("RPM", start=0, length=16, is_signed=False)
        msg = _make_message(1, "ENG", [sig])
        db = _make_db([msg])
        obj = self._make(db, [])
        result = obj._build_data()
        sig_data = result["messages"][0]["signals"][0]
        assert isinstance(sig_data["start_bit"], int), "start_bit must be an int"
        assert sig_data["start_bit"] == 0

    def test_signal_length_and_name(self):
        sig = _make_signal("SPEED", start=16, length=8)
        msg = _make_message(2, "VEHICLE", [sig])
        db = _make_db([msg])
        obj = self._make(db, [])
        s = obj._build_data()["messages"][0]["signals"][0]
        assert s["name"] == "SPEED"
        assert s["length"] == 8

    def test_signal_is_signed_flag(self):
        for signed, expected in [(True, True), (False, False)]:
            sig = _make_signal("V", start=0, length=8, is_signed=signed)
            msg = _make_message(3, "MSG", [sig])
            db = _make_db([msg])
            obj = self._make(db, [])
            s = obj._build_data()["messages"][0]["signals"][0]
            assert s["is_signed"] == expected

    def test_signals_sorted_by_start(self):
        sigs = [
            _make_signal("C", start=16, length=8),
            _make_signal("A", start=0,  length=8),
            _make_signal("B", start=8,  length=8),
        ]
        msg = _make_message(4, "SORTED", sigs)
        db = _make_db([msg])
        obj = self._make(db, [])
        result_sigs = obj._build_data()["messages"][0]["signals"]
        starts = [s["start_bit"] for s in result_sigs]
        assert starts == sorted(starts), "Signals must be sorted by start bit"

    # --- multi-message ---

    def test_multiple_messages_all_included(self):
        db = _make_db([
            _make_message(1, "MSG1"),
            _make_message(2, "MSG2"),
            _make_message(3, "MSG3"),
        ])
        obj = self._make(db, [])
        messages = obj._build_data()["messages"]
        assert len(messages) == 3
        names = {m["name"] for m in messages}
        assert names == {"MSG1", "MSG2", "MSG3"}

    def test_empty_database_produces_empty_messages(self):
        db = _make_db([])
        obj = self._make(db, [])
        assert obj._build_data()["messages"] == []

    # --- severity field in "diff" mode ---

    def test_severity_field_present_in_diff_mode(self):
        from dbcdiff.engine import DiffEntry, Severity
        sig = _make_signal("X", start=0, length=8)
        msg = _make_message(1, "MSG_CHANGED", [sig])
        db = _make_db([msg])
        # simulate a diff entry
        entry = MagicMock()
        entry.is_added = False
        entry.is_removed = False
        entry.message_name = "MSG_CHANGED"
        entry.severity = Severity.BREAKING

        obj = self._make(db, [entry], mode="diff")
        m_data = obj._build_data()["messages"][0]
        assert m_data["severity"] is not None

    def test_severity_none_in_viewer_mode(self):
        db = _make_db([_make_message(1, "MSG_A")])
        obj = self._make(db, [], mode="viewer")
        m_data = obj._build_data()["messages"][0]
        assert m_data["severity"] is None

    # --- no AttributeError regression ---

    def test_no_attribute_error_on_multiple_signals(self):
        """Regression: ensure _build_data() succeeds for many signals."""
        sigs = [_make_signal(f"S{i}", start=i * 8, length=8) for i in range(8)]
        db = _make_db([_make_message(0xAA, "FULL_MSG", sigs)])
        obj = self._make(db, [])
        # Must not raise
        result = obj._build_data()
        assert len(result["messages"][0]["signals"]) == 8


class TestGetTemplate:
    """ThreeSimWidget._get_template() falls back gracefully when HTML missing."""

    def test_fallback_when_resource_missing(self, tmp_path, monkeypatch):
        Fake = _import_build_data()
        # Patch Path.__file__ location so resource won't be found
        monkeypatch.setattr(
            "dbcdiff.gui.Path",
            lambda *args: tmp_path / "nonexistent",
        )
        html = Fake._get_template()
        assert "<html" in html.lower() or html  # some HTML returned
