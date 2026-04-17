"""
dbcdiff – PySide6 professional dark-theme GUI  (v2 – enhanced)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    Qt, QThread, Signal, QObject, QMimeData, QSize,
)
from PySide6.QtGui import (
    QColor, QDragEnterEvent, QDropEvent, QPalette,
    QFont, QIcon,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QSplitter, QStackedWidget, QStatusBar, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

import cantools
from .engine import compare_databases, max_severity, Severity, DiffEntry

# ---------------------------------------------------------------------------
# Severity display map  (enum name → display_label, bg, fg)
# ---------------------------------------------------------------------------
_SEV_MAP: dict[str, tuple[str, str, str]] = {
    "BREAKING":   ("Critical", "#da3633", "#ffd7d5"),
    "FUNCTIONAL": ("Major",    "#d29922", "#fde68a"),
    "METADATA":   ("Minor",    "#1f7a6b", "#b3f0e8"),
    "INFO":       ("Info",     "#8b949e", "#e6edf3"),
}

def _sev_display(sev: Severity) -> str:
    return _SEV_MAP.get(sev.name, (sev.name.title(), "", ""))[0]

def _sev_colors(sev: Severity) -> tuple[str, str]:
    """Return (bg, fg) for the given severity."""
    entry = _SEV_MAP.get(sev.name)
    if entry:
        return entry[1], entry[2]
    return "#21262d", "#e6edf3"

# ---------------------------------------------------------------------------
# Views (tab definitions): name, icon, entity-set (None = all)
# ---------------------------------------------------------------------------
_VIEWS: list[tuple[str, str, Optional[set[str]]]] = [
    ("All",      "📋", None),
    ("Messages", "📨", {"message"}),
    ("Signals",  "📡", {"signal"}),
    ("Nodes",    "🔗", {"node"}),
    ("ECUs",     "💡", {"ecu", "node", "environment_variable"}),
]

# ---------------------------------------------------------------------------
# Protocol colours
# ---------------------------------------------------------------------------
_PROTO_COLORS: dict[str, tuple[str, str]] = {
    "j1939":  ("#1e3a5f", "#7ec8e3"),
    "canopen":("#2d1e5f", "#b8a9e3"),
    "uds":    ("#1e4f1e", "#90ee90"),
    "raw":    ("#21262d", "#8b949e"),
    "":       ("#21262d", "#8b949e"),
}

# ---------------------------------------------------------------------------
# Dark stylesheet
# ---------------------------------------------------------------------------
_QSS_DARK = """
QMainWindow, QWidget {
    background-color: #0d1117;
    color: #e6edf3;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
QLabel {
    color: #e6edf3;
}
QPushButton {
    background-color: #21262d;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 28px;
}
QPushButton:hover {
    background-color: #30363d;
    border-color: #58a6ff;
}
QPushButton:pressed {
    background-color: #161b22;
}
QPushButton#primary {
    background-color: #238636;
    border-color: #2ea043;
    color: #ffffff;
}
QPushButton#primary:hover {
    background-color: #2ea043;
}
QPushButton#active_filter {
    background-color: #1f6feb;
    border-color: #58a6ff;
    color: #ffffff;
}
QTableWidget {
    background-color: #161b22;
    alternate-background-color: #0d1117;
    gridline-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 4px;
    selection-background-color: #1f3a5f;
}
QTableWidget::item {
    padding: 4px 8px;
    border: none;
}
QHeaderView::section {
    background-color: #21262d;
    color: #8b949e;
    border: none;
    border-bottom: 1px solid #30363d;
    padding: 6px 8px;
    font-weight: 600;
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.5px;
}
QScrollBar:vertical {
    background: #161b22;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QFrame#card {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
}
QFrame#drop_zone {
    border: 2px dashed #30363d;
    border-radius: 10px;
    background-color: #161b22;
}
QFrame#drop_zone[drag=true] {
    border-color: #1f6feb;
    background-color: #1c2433;
}
QStatusBar {
    background-color: #161b22;
    border-top: 1px solid #30363d;
    color: #8b949e;
    font-size: 12px;
}
QTabWidget::pane {
    border: 1px solid #30363d;
    background-color: #0d1117;
}
QTabBar::tab {
    background-color: #161b22;
    color: #8b949e;
    border: 1px solid #30363d;
    border-bottom: none;
    padding: 6px 14px;
    border-radius: 4px 4px 0 0;
}
QTabBar::tab:selected {
    background-color: #21262d;
    color: #e6edf3;
    border-bottom-color: #21262d;
}
QTabBar::tab:hover {
    background-color: #21262d;
    color: #e6edf3;
}
QComboBox {
    background-color: #21262d;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px 10px;
    min-height: 26px;
}
QComboBox:hover {
    border-color: #58a6ff;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #21262d;
    color: #e6edf3;
    selection-background-color: #1f3a5f;
    border: 1px solid #30363d;
}
QLineEdit {
    background-color: #21262d;
    color: #e6edf3;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px 8px;
}
"""

# ---------------------------------------------------------------------------
# Light stylesheet
# ---------------------------------------------------------------------------
_QSS_LIGHT = """
QMainWindow, QWidget {
    background-color: #ffffff;
    color: #24292f;
    font-family: "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
}
QLabel {
    color: #24292f;
}
QPushButton {
    background-color: #f6f8fa;
    color: #24292f;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 28px;
}
QPushButton:hover {
    background-color: #eaeef2;
    border-color: #0969da;
}
QPushButton:pressed {
    background-color: #d0d7de;
}
QPushButton#primary {
    background-color: #1a7f37;
    border-color: #1a7f37;
    color: #ffffff;
}
QPushButton#primary:hover {
    background-color: #1c8139;
}
QPushButton#active_filter {
    background-color: #0969da;
    border-color: #0969da;
    color: #ffffff;
}
QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f6f8fa;
    gridline-color: #d0d7de;
    border: 1px solid #d0d7de;
    border-radius: 4px;
    selection-background-color: #dbeafe;
}
QTableWidget::item {
    padding: 4px 8px;
    border: none;
    color: #24292f;
}
QHeaderView::section {
    background-color: #f6f8fa;
    color: #57606a;
    border: none;
    border-bottom: 1px solid #d0d7de;
    padding: 6px 8px;
    font-weight: 600;
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.5px;
}
QScrollBar:vertical {
    background: #f6f8fa;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: #d0d7de;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QFrame#card {
    background-color: #f6f8fa;
    border: 1px solid #d0d7de;
    border-radius: 8px;
}
QFrame#drop_zone {
    border: 2px dashed #d0d7de;
    border-radius: 10px;
    background-color: #f6f8fa;
}
QFrame#drop_zone[drag=true] {
    border-color: #0969da;
    background-color: #dbeafe;
}
QStatusBar {
    background-color: #f6f8fa;
    border-top: 1px solid #d0d7de;
    color: #57606a;
    font-size: 12px;
}
QTabWidget::pane {
    border: 1px solid #d0d7de;
    background-color: #ffffff;
}
QTabBar::tab {
    background-color: #f6f8fa;
    color: #57606a;
    border: 1px solid #d0d7de;
    border-bottom: none;
    padding: 6px 14px;
    border-radius: 4px 4px 0 0;
}
QTabBar::tab:selected {
    background-color: #ffffff;
    color: #24292f;
    border-bottom-color: #ffffff;
}
QTabBar::tab:hover {
    background-color: #eaeef2;
    color: #24292f;
}
QComboBox {
    background-color: #f6f8fa;
    color: #24292f;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 4px 10px;
    min-height: 26px;
}
QComboBox:hover {
    border-color: #0969da;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #24292f;
    selection-background-color: #dbeafe;
    border: 1px solid #d0d7de;
}
QLineEdit {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 4px 8px;
}
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cell_item(text: str, align=Qt.AlignLeft) -> QTableWidgetItem:
    item = QTableWidgetItem(str(text))
    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    item.setTextAlignment(align | Qt.AlignVCenter)
    return item


def _colored_item(text: str, bg: str, fg: str) -> QTableWidgetItem:
    item = _cell_item(text, Qt.AlignCenter)
    item.setBackground(QColor(bg))
    item.setForeground(QColor(fg))
    f = item.font()
    f.setBold(True)
    item.setFont(f)
    return item


# ---------------------------------------------------------------------------
# Drop-zone widget
# ---------------------------------------------------------------------------

class DBCDropZone(QFrame):
    file_chosen = Signal(str)

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setObjectName("drop_zone")
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(120)
        self._path: Optional[str] = None

        self._icon = QLabel("📂", self)
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet("font-size: 28px; background: transparent; border: none;")

        self._hint = QLabel(label, self)
        self._hint.setAlignment(Qt.AlignCenter)
        self._hint.setStyleSheet("color: #8b949e; font-size: 12px; background: transparent; border: none;")

        self._filename = QLabel("", self)
        self._filename.setAlignment(Qt.AlignCenter)
        self._filename.setStyleSheet("color: #58a6ff; font-size: 12px; background: transparent; border: none;")
        self._filename.setVisible(False)

        btn = QPushButton("Browse…", self)
        btn.setFixedWidth(90)
        btn.clicked.connect(self._browse)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.addStretch()
        layout.addWidget(self._icon)
        layout.addWidget(self._hint)
        layout.addWidget(self._filename)
        layout.addWidget(btn, alignment=Qt.AlignCenter)
        layout.addStretch()

    # ------------------------------------------------------------------
    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select DBC file", "", "DBC Files (*.dbc);;All Files (*)"
        )
        if path:
            self._set_path(path)

    def _set_path(self, path: str):
        self._path = path
        name = Path(path).name
        self._filename.setText(name)
        self._filename.setVisible(True)
        self._icon.setText("✅")
        self._hint.setVisible(False)
        self.file_chosen.emit(path)

    @property
    def path(self) -> Optional[str]:
        return self._path

    # ------------------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if any(u.toLocalFile().lower().endswith(".dbc") for u in urls):
                self.setProperty("drag", True)
                self.style().unpolish(self)
                self.style().polish(self)
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        self.setProperty("drag", False)
        self.style().unpolish(self)
        self.style().polish(self)
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p.lower().endswith(".dbc"):
                self._set_path(p)
                break
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self.setProperty("drag", False)
        self.style().unpolish(self)
        self.style().polish(self)


# ---------------------------------------------------------------------------
# Summary badge row
# ---------------------------------------------------------------------------

class SummaryBadge(QWidget):
    _CHIP_DEFS = [
        ("total",      "Total",    "#21262d", "#e6edf3"),
        ("BREAKING",   "Critical", "#da3633", "#ffd7d5"),
        ("FUNCTIONAL", "Major",    "#d29922", "#fde68a"),
        ("METADATA",   "Minor",    "#1f7a6b", "#b3f0e8"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self._chips: dict[str, QLabel] = {}
        for key, label, bg, fg in self._CHIP_DEFS:
            chip = self._make_chip(label, "0", bg, fg)
            self._chips[key] = chip
            layout.addWidget(chip)
        layout.addStretch()

    @staticmethod
    def _make_chip(title: str, count: str, bg: str, fg: str) -> QLabel:
        lbl = QLabel(f"{title}  <b>{count}</b>")
        lbl.setStyleSheet(
            f"background:{bg}; color:{fg}; border-radius:12px;"
            f"padding:4px 12px; font-size:12px; border: none;"
        )
        return lbl

    def update(self, entries: list[DiffEntry]):
        counts: dict[str, int] = {k: 0 for k in self._chips}
        for e in entries:
            counts["total"] += 1
            counts[e.severity.name] = counts.get(e.severity.name, 0) + 1
        for key, _, bg, fg in self._CHIP_DEFS:
            n = counts.get(key, 0)
            label_text = dict((k, l) for k, l, *_ in self._CHIP_DEFS)[key]
            self._chips[key].setText(f"{label_text}  <b>{n}</b>")


# ---------------------------------------------------------------------------
# Table columns
# ---------------------------------------------------------------------------
_COLUMNS = ["Severity", "Entity", "Kind", "Path", "Old Value", "New Value", "Detail", "Protocol"]
_COL_WIDTHS = [80, 80, 80, 220, 130, 130, 200, 80]

# ---------------------------------------------------------------------------
# Results table
# ---------------------------------------------------------------------------

class ResultsTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(_COLUMNS))
        self.setHorizontalHeaderLabels(_COLUMNS)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSortingEnabled(True)
        self.horizontalHeader().setStretchLastSection(True)
        for i, w in enumerate(_COL_WIDTHS):
            self.setColumnWidth(i, w)

    @staticmethod
    def _entry_col_text(e: DiffEntry, col: int) -> str:
        """Return the display text for a given column index."""
        if col == 0:
            return _sev_display(e.severity)
        elif col == 1:
            return e.entity
        elif col == 2:
            return e.kind
        elif col == 3:
            return e.path
        elif col == 4:
            return str(e.value_a) if e.value_a is not None else ""
        elif col == 5:
            return str(e.value_b) if e.value_b is not None else ""
        elif col == 6:
            return e.detail
        elif col == 7:
            return e.protocol
        return ""

    def populate(
        self,
        entries: list[DiffEntry],
        severity_filter: str = "ALL",
        entity_set: Optional[set[str]] = None,
        param_col: Optional[int] = None,
        param_value: str = "",
    ):
        self.setSortingEnabled(False)
        self.setRowCount(0)

        for e in entries:
            # severity filter
            if severity_filter != "ALL" and e.severity.name != severity_filter:
                continue
            # view/entity filter
            if entity_set is not None and e.entity not in entity_set:
                continue
            # parameter column filter
            if param_col is not None and param_value and param_value != "(all)":
                if self._entry_col_text(e, param_col) != param_value:
                    continue

            row = self.rowCount()
            self.insertRow(row)

            # Severity chip
            bg, fg = _sev_colors(e.severity)
            self.setItem(row, 0, _colored_item(_sev_display(e.severity), bg, fg))

            # Entity chip
            proto = e.protocol or ""
            pbg, pfg = _PROTO_COLORS.get(proto.lower(), _PROTO_COLORS[""])
            self.setItem(row, 1, _colored_item(e.entity, pbg, pfg))

            # Kind
            kind_colors = {
                "added":   ("#1f4a1f", "#90ee90"),
                "removed": ("#4a1f1f", "#ffaaaa"),
                "changed": ("#3a3a1a", "#ffff99"),
            }
            kbg, kfg = kind_colors.get(e.kind.lower(), ("#21262d", "#e6edf3"))
            self.setItem(row, 2, _colored_item(e.kind, kbg, kfg))

            self.setItem(row, 3, _cell_item(e.path))
            self.setItem(row, 4, _cell_item(str(e.value_a) if e.value_a is not None else ""))
            self.setItem(row, 5, _cell_item(str(e.value_b) if e.value_b is not None else ""))
            self.setItem(row, 6, _cell_item(e.detail))
            self.setItem(row, 7, _cell_item(e.protocol))
            self.setRowHeight(row, 28)

        self.setSortingEnabled(True)


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

class _Worker(QObject):
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, path_a: str, path_b: str):
        super().__init__()
        self._a = path_a
        self._b = path_b

    def run(self) -> None:
        try:
            db_a = cantools.database.load_file(self._a)
            db_b = cantools.database.load_file(self._b)
            results = compare_databases(db_a, db_b, path_a=self._a, path_b=self._b)
            self.finished.emit(results)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("dbcdiff  |  DBC Diff Analyzer")
        self.setMinimumSize(1100, 700)
        self._entries: list[DiffEntry] = []
        self._dark_theme = True

        # ── central widget ──────────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 12, 16, 8)
        root.setSpacing(10)

        # ── top bar ─────────────────────────────────────────────────────────
        top_bar = QHBoxLayout()
        title = QLabel("🔀  DBC Diff Analyzer")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #58a6ff;")
        top_bar.addWidget(title)
        top_bar.addStretch()

        # theme toggle button
        self._theme_btn = QPushButton("☀  Light")
        self._theme_btn.setFixedWidth(100)
        self._theme_btn.setToolTip("Switch to light theme")
        self._theme_btn.clicked.connect(self._toggle_theme)
        top_bar.addWidget(self._theme_btn)
        root.addLayout(top_bar)

        # ── drop zones ───────────────────────────────────────────────────────
        drop_row = QHBoxLayout()
        drop_row.setSpacing(12)
        self._drop_a = DBCDropZone("Drop Base DBC here\nor click Browse…")
        self._drop_b = DBCDropZone("Drop Compare DBC here\nor click Browse…")
        self._drop_a.file_chosen.connect(self._on_file_chosen)
        self._drop_b.file_chosen.connect(self._on_file_chosen)

        drop_row.addWidget(self._drop_a)
        vs = QLabel("VS")
        vs.setAlignment(Qt.AlignCenter)
        vs.setStyleSheet("font-size: 18px; font-weight: 700; color: #8b949e; min-width: 30px;")
        drop_row.addWidget(vs)
        drop_row.addWidget(self._drop_b)
        root.addLayout(drop_row)

        # ── compare button ───────────────────────────────────────────────────
        self._compare_btn = QPushButton("⚡  Compare Files")
        self._compare_btn.setObjectName("primary")
        self._compare_btn.setEnabled(False)
        self._compare_btn.setFixedHeight(38)
        self._compare_btn.clicked.connect(self._on_compare)
        root.addWidget(self._compare_btn)

        # ── summary row ──────────────────────────────────────────────────────
        summary_card = QFrame()
        summary_card.setObjectName("card")
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(12, 10, 12, 10)
        self._summary = SummaryBadge()
        summary_layout.addWidget(self._summary)
        root.addWidget(summary_card)

        # ── filter + param-dropdown row ──────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        sev_lbl = QLabel("Severity:")
        sev_lbl.setStyleSheet("color: #8b949e; font-size: 12px;")
        filter_row.addWidget(sev_lbl)

        self._filter_btns: dict[str, QPushButton] = {}
        for key, label in [
            ("ALL",        "All"),
            ("BREAKING",   "Critical"),
            ("FUNCTIONAL", "Major"),
            ("METADATA",   "Minor"),
        ]:
            btn = QPushButton(label)
            btn.setFixedHeight(28)
            btn.setCheckable(False)
            btn.setProperty("filter_key", key)
            btn.clicked.connect(self._on_filter_btn)
            self._filter_btns[key] = btn
            filter_row.addWidget(btn)

        # mark "All" active initially
        self._current_filter = "ALL"
        self._filter_btns["ALL"].setObjectName("active_filter")

        filter_row.addSpacing(20)

        # param column selector
        param_lbl = QLabel("Filter by:")
        param_lbl.setStyleSheet("color: #8b949e; font-size: 12px;")
        filter_row.addWidget(param_lbl)

        self._param_combo = QComboBox()
        self._param_combo.setFixedWidth(130)
        self._param_combo.addItem("(none)", None)
        for i, col in enumerate(_COLUMNS):
            self._param_combo.addItem(col, i)
        self._param_combo.currentIndexChanged.connect(self._on_param_col_changed)
        filter_row.addWidget(self._param_combo)

        self._param_value_combo = QComboBox()
        self._param_value_combo.setFixedWidth(180)
        self._param_value_combo.setEditable(True)
        self._param_value_combo.addItem("(all)")
        self._param_value_combo.currentTextChanged.connect(self._on_param_value_changed)
        filter_row.addWidget(self._param_value_combo)

        filter_row.addStretch()
        root.addLayout(filter_row)

        # ── tab widget (views) ───────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._view_tables: list[ResultsTable] = []
        for name, icon, _ in _VIEWS:
            tbl = ResultsTable()
            self._view_tables.append(tbl)
            self._tabs.addTab(tbl, f"{icon}  {name}")

        self._tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self._tabs, stretch=1)

        # ── status bar ───────────────────────────────────────────────────────
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — drop two DBC files to compare")

        # worker
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None

    # -----------------------------------------------------------------------
    # File selection
    # -----------------------------------------------------------------------

    def _on_file_chosen(self, _path: str):
        ready = self._drop_a.path and self._drop_b.path
        self._compare_btn.setEnabled(bool(ready))
        if ready:
            self._status.showMessage(f"Ready: {Path(self._drop_a.path).name}  ↔  {Path(self._drop_b.path).name}")

    # -----------------------------------------------------------------------
    # Compare
    # -----------------------------------------------------------------------

    def _on_compare(self):
        if not self._drop_a.path or not self._drop_b.path:
            return
        self._compare_btn.setEnabled(False)
        self._status.showMessage("⏳  Analysing…")
        for tbl in self._view_tables:
            tbl.setRowCount(0)

        self._worker = _Worker(self._drop_a.path, self._drop_b.path)
        self._thread = QThread()
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_compare_done)
        self._worker.error.connect(self._on_compare_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _on_compare_done(self, entries: list[DiffEntry]):
        self._entries = entries
        self._compare_btn.setEnabled(True)
        self._summary.update(entries)
        self._refresh_all_tabs()
        worst = max((e.severity for e in entries), default=None)
        if entries:
            worst_label = _sev_display(worst) if worst else "None"
            self._status.showMessage(
                f"✅  {len(entries)} difference(s) found  •  Worst severity: {worst_label}"
            )
        else:
            self._status.showMessage("✅  No differences — files are identical")
        self._update_param_value_list(self._param_combo.currentIndex())

    def _on_compare_error(self, msg: str):
        self._compare_btn.setEnabled(True)
        self._status.showMessage(f"❌  Error: {msg}")
        QMessageBox.critical(self, "Compare Error", msg)

    # -----------------------------------------------------------------------
    # Filter helpers
    # -----------------------------------------------------------------------

    def _get_param_col(self) -> Optional[int]:
        idx = self._param_combo.currentIndex()
        data = self._param_combo.itemData(idx)
        return data  # None if "(none)" selected

    def _get_param_value(self) -> str:
        return self._param_value_combo.currentText().strip()

    def _refresh_table(self):
        """Re-populate the currently visible tab."""
        idx = self._tabs.currentIndex()
        if 0 <= idx < len(_VIEWS) and 0 <= idx < len(self._view_tables):
            _, _, entity_set = _VIEWS[idx]
            tbl = self._view_tables[idx]
            tbl.populate(
                self._entries,
                severity_filter=self._current_filter,
                entity_set=entity_set,
                param_col=self._get_param_col(),
                param_value=self._get_param_value(),
            )

    def _refresh_all_tabs(self):
        """Populate every tab."""
        for tab_idx, (_, _, entity_set) in enumerate(_VIEWS):
            if tab_idx < len(self._view_tables):
                self._view_tables[tab_idx].populate(
                    self._entries,
                    severity_filter=self._current_filter,
                    entity_set=entity_set,
                    param_col=self._get_param_col(),
                    param_value=self._get_param_value(),
                )

    def _update_param_value_list(self, combo_idx: int):
        """Populate the param-value combo with distinct values for selected column."""
        col = self._param_combo.itemData(combo_idx)
        self._param_value_combo.blockSignals(True)
        self._param_value_combo.clear()
        self._param_value_combo.addItem("(all)")
        if col is not None and self._entries:
            seen: set[str] = set()
            for e in self._entries:
                val = ResultsTable._entry_col_text(e, col)
                if val and val not in seen:
                    seen.add(val)
                    self._param_value_combo.addItem(val)
        self._param_value_combo.blockSignals(False)

    # -----------------------------------------------------------------------
    # Slots
    # -----------------------------------------------------------------------

    def _on_filter_btn(self):
        btn = self.sender()
        key = btn.property("filter_key")
        self._current_filter = key
        # update button styles
        for k, b in self._filter_btns.items():
            if k == key:
                b.setObjectName("active_filter")
            else:
                b.setObjectName("")
            b.style().unpolish(b)
            b.style().polish(b)
        self._refresh_all_tabs()

    def _on_tab_changed(self, idx: int):
        self._refresh_table()

    def _on_param_col_changed(self, idx: int):
        self._update_param_value_list(idx)
        self._refresh_all_tabs()

    def _on_param_value_changed(self, _text: str):
        self._refresh_all_tabs()

    def _toggle_theme(self):
        app = QApplication.instance()
        self._dark_theme = not self._dark_theme
        if self._dark_theme:
            app.setStyleSheet(_QSS_DARK)
            self._theme_btn.setText("☀  Light")
            self._theme_btn.setToolTip("Switch to light theme")
        else:
            app.setStyleSheet(_QSS_LIGHT)
            self._theme_btn.setText("🌙  Dark")
            self._theme_btn.setToolTip("Switch to dark theme")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def launch_gui():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("dbcdiff")
    app.setStyleSheet(_QSS_DARK)

    # dark system palette
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#0d1117"))
    palette.setColor(QPalette.WindowText, QColor("#e6edf3"))
    palette.setColor(QPalette.Base, QColor("#161b22"))
    palette.setColor(QPalette.AlternateBase, QColor("#0d1117"))
    palette.setColor(QPalette.Text, QColor("#e6edf3"))
    palette.setColor(QPalette.Button, QColor("#21262d"))
    palette.setColor(QPalette.ButtonText, QColor("#e6edf3"))
    palette.setColor(QPalette.Highlight, QColor("#1f6feb"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())
