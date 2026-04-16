"""
dbcdiff – PySide6 professional dark-theme GUI
"""
from __future__ import annotations

import html
import sys
import traceback
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    Qt, QThread, QObject, Signal, QMimeData, QSize,
)
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont, QPalette
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QMainWindow, QMessageBox, QPushButton, QSizePolicy, QSplitter,
    QStatusBar, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout,
    QWidget,
)

import cantools

from .engine import compare_databases, max_severity, Severity, DiffEntry
from .protocol import detect_protocol

# ── Dark-theme QSS ────────────────────────────────────────────────────────────
_QSS = """
QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: 'Segoe UI', 'SF Pro Text', 'Consolas', sans-serif;
    font-size: 13px;
}
QMainWindow {
    background-color: #0d1117;
}
QFrame#drop_zone {
    border: 2px dashed #30363d;
    border-radius: 10px;
    background-color: #161b22;
}
QFrame#drop_zone[drag_over="true"] {
    border: 2px dashed #1f6feb;
    background-color: #0d1f3c;
}
QLabel#drop_label {
    color: #8b949e;
    font-size: 14px;
}
QLabel#file_label {
    color: #e6edf3;
    font-size: 13px;
    font-weight: bold;
}
QLabel#proto_badge {
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: bold;
}
QGroupBox {
    border: 1px solid #30363d;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 6px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #8b949e;
    font-size: 11px;
}
QPushButton {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 16px;
    color: #e6edf3;
}
QPushButton:hover {
    background-color: #30363d;
    border-color: #8b949e;
}
QPushButton:pressed { background-color: #161b22; }
QPushButton#compare_btn {
    background-color: #1f6feb;
    border: 1px solid #1f6feb;
    font-weight: bold;
    padding: 8px 24px;
    font-size: 14px;
}
QPushButton#compare_btn:hover { background-color: #388bfd; }
QPushButton#compare_btn:disabled { background-color: #21262d; border-color: #30363d; color: #484f58; }
QTableWidget {
    background-color: #161b22;
    alternate-background-color: #1c2128;
    border: 1px solid #30363d;
    gridline-color: #21262d;
    border-radius: 6px;
}
QTableWidget::item { padding: 4px 8px; }
QTableWidget::item:selected {
    background-color: #1f3a5f;
    color: #e6edf3;
}
QHeaderView::section {
    background-color: #21262d;
    border: none;
    border-bottom: 1px solid #30363d;
    border-right: 1px solid #30363d;
    padding: 6px 8px;
    font-weight: bold;
    color: #8b949e;
    font-size: 12px;
}
QScrollBar:vertical {
    background: #161b22;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #484f58; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QStatusBar { background-color: #161b22; border-top: 1px solid #30363d; color: #8b949e; }
QSplitter::handle { background-color: #30363d; }
"""

# ── Protocol badge colours ─────────────────────────────────────────────────────
_PROTO_COLORS = {
    "J1939":     ("#7ee787", "#0d2911"),
    "CAN FD":    ("#79c0ff", "#0d1f3c"),
    "CAN XL":    ("#d2a8ff", "#2a1f4a"),
    "Basic CAN": ("#ff7b72", "#3d1110"),
    "Unknown":   ("#8b949e", "#21262d"),
}

# ── Severity colours (bg, fg) ────────────────────────────────────────────────
_SEV_COLORS = {
    "BREAKING":    ("#da3633", "#ffd7d5"),
    "FUNCTIONAL":  ("#d29922", "#fde68a"),
    "METADATA":    ("#6ba96b", "#cae8ca"),
    "INFO":        ("#8b949e", "#e6edf3"),
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sev_label(sev: Severity) -> str:
    return sev.name.title() if sev else ""


def _cell_item(text: str, align=Qt.AlignLeft | Qt.AlignVCenter) -> QTableWidgetItem:
    item = QTableWidgetItem(str(text))
    item.setTextAlignment(align)
    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    return item


def _colored_item(text: str, bg: str, fg: str) -> QTableWidgetItem:
    item = _cell_item(text, Qt.AlignCenter)
    item.setBackground(QColor(bg))
    item.setForeground(QColor(fg))
    return item


# ── DBCDropZone ───────────────────────────────────────────────────────────────

class DBCDropZone(QFrame):
    """Drag-and-drop zone with file info panel."""
    file_changed = Signal(str)   # emits path when file is set

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("drop_zone")
        self.setAcceptDrops(True)
        self.setMinimumSize(220, 130)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._path: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Header row: title + browse button
        top = QHBoxLayout()
        title = QLabel(label)
        title.setObjectName("file_label")
        top.addWidget(title, 1)

        browse_btn = QToolButton()
        browse_btn.setText("Browse…")
        browse_btn.setStyleSheet(
            "QToolButton { border:1px solid #30363d; border-radius:4px;"
            " padding:3px 10px; background:#21262d; }"
            "QToolButton:hover { background:#30363d; }"
        )
        browse_btn.clicked.connect(self._browse)
        top.addWidget(browse_btn)
        layout.addLayout(top)

        # Drop hint
        self._hint = QLabel("Drop a .dbc file here")
        self._hint.setObjectName("drop_label")
        self._hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._hint, 1)

        # File info row (hidden until file loaded)
        self._info = QLabel("")
        self._info.setObjectName("drop_label")
        self._info.setWordWrap(True)
        self._info.setAlignment(Qt.AlignCenter)
        self._info.hide()
        layout.addWidget(self._info)

        # Protocol badge
        self._proto_badge = QLabel("")
        self._proto_badge.setObjectName("proto_badge")
        self._proto_badge.setAlignment(Qt.AlignCenter)
        self._proto_badge.hide()
        layout.addWidget(self._proto_badge, 0, Qt.AlignHCenter)

    # ── drag ──────────────────────────────────────────────────────────────────
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()]
            if any(p.lower().endswith(".dbc") for p in paths):
                self.setProperty("drag_over", "true")
                self.style().unpolish(self)
                self.style().polish(self)
                event.acceptProposedAction()
                return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("drag_over", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("drag_over", "false")
        self.style().unpolish(self)
        self.style().polish(self)
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p.lower().endswith(".dbc"):
                self._set_file(p)
                event.acceptProposedAction()
                return
        event.ignore()

    # ── file ops ──────────────────────────────────────────────────────────────
    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open DBC file", "", "DBC files (*.dbc);;All files (*)"
        )
        if path:
            self._set_file(path)

    def _set_file(self, path: str) -> None:
        self._path = path
        fname = Path(path).name
        try:
            db = cantools.database.load_file(path)
            proto = detect_protocol(db).value
            stats = f"{len(db.messages)} msgs · {sum(len(m.signals) for m in db.messages)} signals"
            self._info.setText(f"<b>{html.escape(fname)}</b><br/><span style='font-size:11px;color:#8b949e;'>{stats}</span>")
            self._info.show()
            self._hint.hide()

            bg, fg = _PROTO_COLORS.get(proto, ("#8b949e", "#21262d"))
            self._proto_badge.setText(proto)
            self._proto_badge.setStyleSheet(
                f"QLabel {{ background-color:{bg}; color:{fg};"
                f" border-radius:4px; padding:2px 8px; font-size:11px; font-weight:bold; }}"
            )
            self._proto_badge.show()
        except Exception:
            self._info.setText(f"<b>{html.escape(fname)}</b>")
            self._info.show()
            self._hint.hide()
            self._proto_badge.hide()

        self.file_changed.emit(path)

    def path(self) -> Optional[str]:
        return self._path

    def clear(self) -> None:
        self._path = None
        self._hint.show()
        self._info.hide()
        self._proto_badge.hide()


# ── SummaryBadge ─────────────────────────────────────────────────────────────

class SummaryBadge(QFrame):
    """Coloured count chips for BREAKING / FUNCTIONAL / METADATA / Total."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._chips: dict[str, QLabel] = {}
        for key, label, bg, fg in [
            ("total",      "Total",      "#21262d", "#e6edf3"),
            ("BREAKING",   "Breaking",   "#da3633", "#ffd7d5"),
            ("FUNCTIONAL", "Functional", "#d29922", "#fde68a"),
            ("METADATA",   "Metadata",   "#6ba96b", "#cae8ca"),
        ]:
            chip = QLabel("0")
            chip.setAlignment(Qt.AlignCenter)
            chip.setStyleSheet(
                f"QLabel {{ background:{bg}; color:{fg}; border-radius:5px;"
                f" padding:4px 12px; font-size:12px; font-weight:bold; }}"
            )
            chip.setToolTip(label)
            chip.setMinimumWidth(60)
            self._chips[key] = chip
            col_lbl = QLabel(label)
            col_lbl.setAlignment(Qt.AlignCenter)
            col_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
            grp = QVBoxLayout()
            grp.setSpacing(2)
            grp.addWidget(chip)
            grp.addWidget(col_lbl)
            layout.addLayout(grp)
        layout.addStretch()

    def update(self, entries: list[DiffEntry]) -> None:  # type: ignore[override]
        counts: dict[str, int] = {"total": len(entries), "BREAKING": 0, "FUNCTIONAL": 0, "METADATA": 0}
        for e in entries:
            k = e.severity.name if e.severity else "METADATA"
            if k in counts:
                counts[k] += 1
        for key, chip in self._chips.items():
            chip.setText(str(counts.get(key, 0)))

    def clear_counts(self) -> None:
        for chip in self._chips.values():
            chip.setText("0")


# ── CompareWorker ─────────────────────────────────────────────────────────────

class CompareWorker(QObject):
    finished = Signal(list)       # list[DiffEntry]
    error    = Signal(str)        # error message

    def __init__(self, path_a: str, path_b: str) -> None:
        super().__init__()
        self._path_a = path_a
        self._path_b = path_b

    def run(self) -> None:
        try:
            db_a = cantools.database.load_file(self._path_a)
            db_b = cantools.database.load_file(self._path_b)
            entries = compare_databases(db_a, db_b, path_a=self._path_a, path_b=self._path_b)
            self.finished.emit(entries)
        except Exception as exc:
            self.error.emit(f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}")


# ── ResultsTable ──────────────────────────────────────────────────────────────

_COLUMNS = ["Severity", "Kind", "Entity", "Path", "File A Value", "File B Value", "Protocol", "Detail"]
_COL_WIDTHS = [90, 120, 180, 200, 130, 130, 90, 260]

class ResultsTable(QTableWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, len(_COLUMNS), parent)
        self.setHorizontalHeaderLabels(_COLUMNS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().hide()
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.ExtendedSelection)
        self.setShowGrid(True)
        self.setWordWrap(False)
        for i, w in enumerate(_COL_WIDTHS):
            self.setColumnWidth(i, w)

    def populate(self, entries: list[DiffEntry], severity_filter: str = "ALL") -> None:
        self.setRowCount(0)
        visible = entries if severity_filter == "ALL" else [
            e for e in entries if (e.severity.name if e.severity else "METADATA") == severity_filter
        ]
        self.setRowCount(len(visible))
        for row, e in enumerate(visible):
            sev_name = e.severity.name if e.severity else "METADATA"
            bg, fg = _SEV_COLORS.get(sev_name, ("#21262d", "#e6edf3"))

            sev_item = _colored_item(sev_name.title(), bg, fg)
            self.setItem(row, 0, sev_item)

            kind_item = _cell_item(e.kind or "")
            self.setItem(row, 1, kind_item)

            self.setItem(row, 2, _cell_item(e.entity or ""))
            self.setItem(row, 3, _cell_item(e.path or ""))

            val_a = str(e.value_a) if e.value_a is not None else "—"
            val_b = str(e.value_b) if e.value_b is not None else "—"
            self.setItem(row, 4, _cell_item(val_a))
            self.setItem(row, 5, _cell_item(val_b))
            self.setItem(row, 6, _cell_item(e.protocol or ""))
            self.setItem(row, 7, _cell_item(e.detail or ""))

            self.setRowHeight(row, 26)

    def clear_results(self) -> None:
        self.setRowCount(0)


# ── MainWindow ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("dbcdiff — DBC File Comparator")
        self.resize(1280, 800)
        self._entries: list[DiffEntry] = []
        self._thread: Optional[QThread] = None
        self._active_filter = "ALL"

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)

        # ── Title bar ─────────────────────────────────────────────────────────
        title_lbl = QLabel("dbcdiff")
        title_lbl.setStyleSheet("font-size:22px; font-weight:bold; color:#58a6ff;")
        sub_lbl = QLabel("Professional DBC File Comparator")
        sub_lbl.setStyleSheet("color:#8b949e; font-size:13px;")
        title_row = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)
        title_row.addLayout(title_col)
        title_row.addStretch()
        root.addLayout(title_row)

        # ── Drop zones ────────────────────────────────────────────────────────
        zones_row = QHBoxLayout()
        self._zone_a = DBCDropZone("📁  File A  (reference)")
        self._zone_b = DBCDropZone("📁  File B  (compare to)")
        self._zone_a.file_changed.connect(self._on_file_changed)
        self._zone_b.file_changed.connect(self._on_file_changed)
        zones_row.addWidget(self._zone_a)

        vs_lbl = QLabel("vs")
        vs_lbl.setAlignment(Qt.AlignCenter)
        vs_lbl.setStyleSheet("color:#484f58; font-size:18px; font-weight:bold;")
        vs_lbl.setFixedWidth(30)
        zones_row.addWidget(vs_lbl)

        zones_row.addWidget(self._zone_b)
        root.addLayout(zones_row)

        # ── Compare button ────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._compare_btn = QPushButton("⚡  Compare Files")
        self._compare_btn.setObjectName("compare_btn")
        self._compare_btn.setEnabled(False)
        self._compare_btn.clicked.connect(self._run_compare)
        btn_row.addStretch()
        btn_row.addWidget(self._compare_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(clear_btn)

        export_btn = QPushButton("Export HTML…")
        export_btn.clicked.connect(self._export_html)
        btn_row.addWidget(export_btn)

        btn_row.addStretch()
        root.addLayout(btn_row)

        # ── Summary badges ────────────────────────────────────────────────────
        self._summary = SummaryBadge()
        root.addWidget(self._summary)

        # ── Filter buttons ─────────────────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        filter_lbl = QLabel("Filter:")
        filter_lbl.setStyleSheet("color:#8b949e;")
        filter_row.addWidget(filter_lbl)
        self._filter_btns: dict[str, QPushButton] = {}
        for key, label in [("ALL", "All"), ("BREAKING", "Breaking"),
                            ("FUNCTIONAL", "Functional"), ("METADATA", "Metadata")]:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == "ALL")
            btn.setStyleSheet(
                "QPushButton { border:1px solid #30363d; border-radius:4px; padding:4px 12px; }"
                "QPushButton:checked { background:#1f6feb; border-color:#1f6feb; }"
            )
            btn.clicked.connect(lambda checked, k=key: self._apply_filter(k))
            filter_row.addWidget(btn)
            self._filter_btns[key] = btn
        filter_row.addStretch()
        root.addLayout(filter_row)

        # ── Results table ──────────────────────────────────────────────────────
        self._table = ResultsTable()
        root.addWidget(self._table, 1)

        # ── Status bar ────────────────────────────────────────────────────────
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — drop two DBC files or use Browse…")

    # ── Slots ─────────────────────────────────────────────────────────────────

    def _on_file_changed(self, _path: str) -> None:
        both = self._zone_a.path() and self._zone_b.path()
        self._compare_btn.setEnabled(bool(both))

    def _run_compare(self) -> None:
        path_a = self._zone_a.path()
        path_b = self._zone_b.path()
        if not path_a or not path_b:
            return

        self._compare_btn.setEnabled(False)
        self._status.showMessage("Comparing…")
        self._table.clear_results()
        self._summary.clear_counts()

        worker = CompareWorker(path_a, path_b)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_compare_done)
        worker.error.connect(self._on_compare_error)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._thread = thread
        thread.start()

    def _on_compare_done(self, entries: list[DiffEntry]) -> None:
        self._entries = entries
        self._summary.update(entries)
        self._apply_filter("ALL")
        worst = max_severity(entries)
        sev_str = worst.name.title() if worst else "Identical"
        self._status.showMessage(
            f"Done — {len(entries)} change(s) found · Worst severity: {sev_str}"
        )
        self._compare_btn.setEnabled(True)

    def _on_compare_error(self, msg: str) -> None:
        QMessageBox.critical(self, "Compare Error", msg)
        self._status.showMessage("Error during comparison.")
        self._compare_btn.setEnabled(True)

    def _apply_filter(self, key: str) -> None:
        self._active_filter = key
        for k, btn in self._filter_btns.items():
            btn.setChecked(k == key)
        self._table.populate(self._entries, key)

    def _clear_all(self) -> None:
        self._zone_a.clear()
        self._zone_b.clear()
        self._entries = []
        self._table.clear_results()
        self._summary.clear_counts()
        self._compare_btn.setEnabled(False)
        self._status.showMessage("Cleared.")

    def _export_html(self) -> None:
        if not self._entries:
            QMessageBox.information(self, "Nothing to export", "Run a comparison first.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export HTML Report", "dbcdiff_report.html", "HTML (*.html)"
        )
        if not path:
            return
        from .reporters.html_reporter import write_html
        with open(path, "w", encoding="utf-8") as fp:
            write_html(
                self._entries, fp,
                file_a=self._zone_a.path() or "",
                file_b=self._zone_b.path() or "",
            )
        self._status.showMessage(f"Report exported → {path}")


# ── Entry point ───────────────────────────────────────────────────────────────

def launch_gui() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("dbcdiff")
    app.setApplicationVersion("0.2.0")
    app.setStyleSheet(_QSS)

    # Adjust palette for native widgets
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#0d1117"))
    palette.setColor(QPalette.WindowText, QColor("#e6edf3"))
    palette.setColor(QPalette.Base, QColor("#161b22"))
    palette.setColor(QPalette.AlternateBase, QColor("#1c2128"))
    palette.setColor(QPalette.Text, QColor("#e6edf3"))
    palette.setColor(QPalette.Button, QColor("#21262d"))
    palette.setColor(QPalette.ButtonText, QColor("#e6edf3"))
    palette.setColor(QPalette.Highlight, QColor("#1f6feb"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    launch_gui()
