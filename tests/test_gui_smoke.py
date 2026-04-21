"""
tests/test_gui_smoke.py
Headless smoke tests for the GUI compare / visualize flow.

All tests avoid showing windows.  We use a minimal QApplication created
once per session.  PySide6-WebEngine is optional and tests degrade
gracefully when absent.

Run with:
    python -m pytest tests/test_gui_smoke.py -q --tb=short
"""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import cantools

# ── PySide6 availability check ───────────────────────────────────────────────
try:
    from PySide6.QtWidgets import QApplication
    import PySide6  # noqa: F401
    _QT_OK = True
except ImportError:
    _QT_OK = False

if not _QT_OK:
    pytest.skip("PySide6 not installed – GUI smoke tests skipped", allow_module_level=True)

# One QApplication for the whole module (Qt requires exactly one).
import sys as _sys
_app: QApplication | None = None


def _get_app() -> QApplication:
    global _app
    if _app is None:
        _app = QApplication.instance() or QApplication(_sys.argv[:1])
    return _app


# ── Import paths ─────────────────────────────────────────────────────────────
TESTS_DIR = Path(__file__).parent
OLD_DBC = TESTS_DIR / "sample_old.dbc"
NEW_DBC = TESTS_DIR / "sample_new.dbc"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def app():
    return _get_app()


@pytest.fixture()
def main_window():
    """Return a hidden MainWindow, cleaned up after each test."""
    from dbcdiff.gui import MainWindow
    win = MainWindow()
    # Do NOT call win.show()
    yield win
    win.close()
    win.deleteLater()


# ---------------------------------------------------------------------------
# Helper to load cantools db from sample files
# ---------------------------------------------------------------------------

def _load_db(path: Path):
    return cantools.database.load_file(str(path))


# ---------------------------------------------------------------------------
# Smoke tests: _build_data integration via ThreeSimWidget
# ---------------------------------------------------------------------------

class TestThreeSimWidgetIntegration:
    """Integration tests that exercise ThreeSimWidget with real DBC data."""

    def test_load_viewer_does_not_raise(self, main_window):
        """ThreeSimWidget.load() with a real DBC must not raise."""
        db = _load_db(NEW_DBC)
        main_window._three_sim.load(db, [], "viewer")  # must not raise

    def test_load_diff_does_not_raise(self, main_window):
        from dbcdiff.engine import compare_databases
        db_a = _load_db(OLD_DBC)
        db_b = _load_db(NEW_DBC)
        entries = compare_databases(db_a, db_b)
        main_window._three_sim.load(db_b, entries, "diff")

    def test_build_data_no_attribute_error(self, main_window):
        """Regression: _build_data must not raise AttributeError for start_bit."""
        db = _load_db(NEW_DBC)
        main_window._three_sim._db = db
        main_window._three_sim._entries = []
        main_window._three_sim._sim_mode = "viewer"
        result = main_window._three_sim._build_data()  # must not raise
        assert "messages" in result
        assert "mode" in result

    def test_build_data_signal_start_bit_is_int(self, main_window):
        db = _load_db(NEW_DBC)
        main_window._three_sim._db = db
        main_window._three_sim._entries = []
        main_window._three_sim._sim_mode = "viewer"
        data = main_window._three_sim._build_data()
        for msg in data["messages"]:
            for sig in msg["signals"]:
                assert isinstance(sig["start_bit"], int), (
                    f"Signal {sig['name']} has non-int start_bit: {sig['start_bit']!r}"
                )


# ---------------------------------------------------------------------------
# Smoke tests: Compare flow (uses _Worker / QThread)
# ---------------------------------------------------------------------------

class TestCompareFlow:
    """Test that the compare button flow completes and re-enables the button."""

    # ------------------------------------------------------------------
    # Helper: patch every heavy / blocking method called by _on_compare_done
    # so the headless tests finish instantly without hanging.
    # ------------------------------------------------------------------
    @staticmethod
    def _patch_heavy(mw, mp) -> None:
        """Monkeypatch all non-trivial methods invoked by _on_compare_done."""
        mp.setattr(mw, "_build_consistency_records", lambda a, b: [])
        mp.setattr(mw._detail, "set_databases", lambda a, b: None)
        mp.setattr(mw._decoder_tab, "set_database", lambda db: None)
        mp.setattr(mw._summary, "update", lambda entries: None)
        mp.setattr(mw, "_update_sev_chips", lambda: None)
        mp.setattr(mw, "_refresh_all_tabs", lambda: None)
        mp.setattr(mw, "_refresh_header_state", lambda compared=False: None)
        mp.setattr(mw, "_update_msg_type_list", lambda: None)
        mp.setattr(mw, "_update_protocol_list", lambda: None)
        mp.setattr(mw, "_update_ecu_node_list", lambda: None)

    def test_compare_btn_enabled_before_files_dropped(self, main_window):
        """Compare button should be disabled when no files are loaded."""
        # Initially no paths, button disabled
        assert not main_window._compare_btn.isEnabled()

    def test_on_compare_done_reenables_button(self, main_window, monkeypatch):
        """Simulate the worker finish signal: button must become enabled."""
        self._patch_heavy(main_window, monkeypatch)
        from dbcdiff.engine import compare_databases
        db_a = _load_db(OLD_DBC)
        db_b = _load_db(NEW_DBC)
        entries = compare_databases(db_a, db_b)
        # Manually call the slot (bypassing QThread)
        main_window._on_compare_done(entries, db_a, db_b)
        assert main_window._compare_btn.isEnabled()

    def test_on_compare_done_populates_entries(self, main_window, monkeypatch):
        """After _on_compare_done, _entries must be set."""
        self._patch_heavy(main_window, monkeypatch)
        from dbcdiff.engine import compare_databases
        db_a = _load_db(OLD_DBC)
        db_b = _load_db(NEW_DBC)
        entries = compare_databases(db_a, db_b)
        main_window._on_compare_done(entries, db_a, db_b)
        assert main_window._entries is entries

    def test_on_compare_error_reenables_button(self, main_window, monkeypatch):
        """Even on error the compare button must be re-enabled.

        _on_compare_error calls QMessageBox.critical() which would block in
        a headless test environment, so we patch it to a no-op.
        """
        monkeypatch.setattr(main_window, "_refresh_header_state",
                            lambda compared=False: None)
        from PySide6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, "critical",
                            staticmethod(lambda *args, **kwargs: None))
        main_window._compare_btn.setEnabled(False)
        main_window._on_compare_error("simulated error")
        assert main_window._compare_btn.isEnabled()

    def test_compare_done_with_empty_diff(self, main_window, monkeypatch):
        """No diff entries: compare done must still work without exceptions."""
        self._patch_heavy(main_window, monkeypatch)
        db_a = _load_db(OLD_DBC)
        main_window._on_compare_done([], db_a, db_a)  # same db, no differences
        assert main_window._compare_btn.isEnabled()


# ---------------------------------------------------------------------------
# Smoke tests: Worker thread unit
# ---------------------------------------------------------------------------

class TestWorker:
    """Test _Worker in isolation (no real thread, just call .run() directly)."""

    def test_worker_emits_finished(self):
        from dbcdiff.gui import _Worker
        results = {}
        w = _Worker(str(OLD_DBC), str(NEW_DBC))
        w.finished.connect(lambda entries, db_a, db_b: results.update(
            {"entries": entries, "db_a": db_a, "db_b": db_b}
        ))
        w.run()
        assert "entries" in results
        assert isinstance(results["entries"], list)

    def test_worker_emits_error_on_bad_path(self):
        from dbcdiff.gui import _Worker
        errors = []
        w = _Worker("/nonexistent/a.dbc", "/nonexistent/b.dbc")
        w.error.connect(errors.append)
        w.run()
        assert errors  # at least one error message emitted

    def test_worker_same_file_produces_no_entries(self):
        from dbcdiff.gui import _Worker
        results = {}
        w = _Worker(str(OLD_DBC), str(OLD_DBC))
        w.finished.connect(lambda entries, db_a, db_b: results.update({"entries": entries}))
        w.run()
        assert results.get("entries") == []


# ---------------------------------------------------------------------------
# Smoke tests: Visualize flow
# ---------------------------------------------------------------------------

class TestVisualizeFlow:
    """Test _on_visualize does not raise when called with valid data."""

    def test_visualize_opens_and_closes(self, main_window, monkeypatch):
        """Patch ViewerDialog.exec so we don't block on a modal dialog."""
        from dbcdiff.gui import ViewerDialog
        monkeypatch.setattr(ViewerDialog, "exec", lambda self: None)
        # set a path so the method doesn't bail early
        main_window._drop_a._path = str(OLD_DBC)
        main_window._drop_b._path = str(NEW_DBC)
        # Should complete without raising
        main_window._on_visualize()

    def test_visualize_with_no_path_returns_early(self, main_window):
        """When no files are loaded, _on_visualize must be a no-op."""
        main_window._drop_a._path = ""
        main_window._drop_b._path = ""
        main_window._on_visualize()  # must not raise
