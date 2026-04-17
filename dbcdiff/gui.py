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
    QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QSplitter, QStackedWidget, QStatusBar, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

import cantools
from .engine import compare_databases, max_severity, Severity, DiffEntry
from .converter import dbc_to_excel, excel_to_dbc

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
    ("All",        "📋", None),
    ("Messages",   "📨", {"message"}),
    ("Signals",    "📡", {"signal"}),
    ("Nodes",      "🔗", {"node"}),
    ("Attributes", "⚙",  {"attribute"}),
    ("Env Vars",   "🌐", {"envvar"}),
    ("J1939",      "🚛", {"j1939"}),
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


def _esc(s: str) -> str:
    """HTML-escape a string for use in QTextEdit HTML."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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

            # Severity chip – store DiffEntry reference for detail panel
            bg, fg = _sev_colors(e.severity)
            _sev_item = _colored_item(_sev_display(e.severity), bg, fg)
            _sev_item.setData(Qt.ItemDataRole.UserRole, e)
            self.setItem(row, 0, _sev_item)

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

    def current_entry(self) -> Optional[DiffEntry]:
        """Return the DiffEntry for the currently selected row, or None."""
        row = self.currentRow()
        if row < 0:
            return None
        item = self.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None


# ---------------------------------------------------------------------------
# Detail / synopsis panel
# ---------------------------------------------------------------------------

class _DetailPanel(QWidget):
    """Synopsis panel shown below the results table.

    Displays structured, side-by-side detail for the selected DiffEntry,
    including full signal/message metadata looked up from the loaded databases.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        _hdr = QLabel("  \u25c8  Detail \u2014 select a row above")
        _hdr.setStyleSheet(
            "background: #161b22; color: #8b949e; font-size: 11px; "
            "padding: 4px 8px; border-top: 1px solid #30363d;"
        )
        layout.addWidget(_hdr)

        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setStyleSheet(
            "QTextEdit {"
            "  background: #0d1117;"
            "  color: #e6edf3;"
            "  border: none;"
            "  border-top: 1px solid #30363d;"
            "  font-family: 'Courier New', Consolas, monospace;"
            "  font-size: 12px;"
            "  padding: 8px;"
            "}"
        )
        self._text.setHtml(
            "<span style='color:#8b949e; font-style:italic;'>"
            "Select a row to see details\u2026"
            "</span>"
        )
        layout.addWidget(self._text)

        self._db_a = None
        self._db_b = None

    def set_databases(self, db_a, db_b) -> None:
        self._db_a = db_a
        self._db_b = db_b

    def update_entry(self, entry) -> None:
        if entry is None:
            self._text.setHtml(
                "<span style='color:#8b949e; font-style:italic;'>"
                "Select a row to see details\u2026"
                "</span>"
            )
            return
        self._text.setHtml(self._build_html(entry))

    # -----------------------------------------------------------------------
    # HTML builders
    # -----------------------------------------------------------------------

    def _build_html(self, e) -> str:
        kind_color = {
            "added": "#90ee90", "removed": "#ffaaaa", "changed": "#ffff99",
        }.get(e.kind.lower(), "#e6edf3")
        header = (
            f"<p style='margin:0 0 4px 0; font-size:11px;'>"
            f"<b style='color:#58a6ff;'>{_esc(e.path)}</b>"
            f"&nbsp;&nbsp;"
            f"<span style='background:#21262d; padding:1px 6px;"
            f" border-radius:3px; color:#8b949e;'>{_esc(e.entity)}</span>"
            f"&nbsp;"
            f"<span style='color:{kind_color};'>{_esc(e.kind)}</span>"
            f"</p>"
            f"<hr style='border:0; border-top:1px solid #30363d; margin:4px 0;'/>"
        )
        if e.entity == "signal":
            body = self._signal_detail(e)
        elif e.entity == "message":
            body = self._message_detail(e)
        elif e.entity == "node":
            body = self._node_detail(e)
        else:
            body = self._generic_detail(e)
        return header + body

    @staticmethod
    def _row(label: str, val_a, val_b) -> str:
        def _fmt(v, color: str) -> str:
            if v is None:
                return "<span style='color:#555;'>\u2014</span>"
            return f"<span style='color:{color};'>{_esc(str(v))}</span>"

        changed = (
            val_a is not None and val_b is not None
            and str(val_a) != str(val_b)
        )
        bg = " background:#1e1e10;" if changed else ""
        return (
            f"<tr style='{bg}'>"
            f"<td style='color:#8b949e; padding:2px 14px 2px 4px;"
            f" white-space:nowrap; vertical-align:top;'>{_esc(label)}</td>"
            f"<td style='padding:2px 14px 2px 4px; vertical-align:top;'>"
            f"{_fmt(val_a, '#ffaaaa')}</td>"
            f"<td style='padding:2px 4px; vertical-align:top;'>"
            f"{_fmt(val_b, '#90ee90')}</td>"
            f"</tr>"
        )

    @staticmethod
    def _tbl(rows: str) -> str:
        return (
            "<table style='border-collapse:collapse; width:100%; font-size:12px;'>"
            "<tr style='background:#161b22;'>"
            "<th style='text-align:left; padding:3px 14px 3px 4px; color:#6e7681;"
            " font-weight:normal; font-size:11px;'>Field</th>"
            "<th style='text-align:left; padding:3px 14px; color:#ffaaaa;"
            " font-weight:normal; font-size:11px;'>\u25c4 File A</th>"
            "<th style='text-align:left; padding:3px 4px; color:#90ee90;"
            " font-weight:normal; font-size:11px;'>\u25ba File B</th>"
            "</tr>" + rows + "</table>"
        )

    # -----------------------------------------------------------------------

    def _signal_detail(self, e) -> str:
        parts = e.path.split(".")
        if len(parts) < 2:
            return self._generic_detail(e)
        msg_name, sig_name = parts[0], parts[1]
        sig_a = sig_b = msg_a = msg_b = None
        if self._db_a:
            try:
                msg_a = self._db_a.get_message_by_name(msg_name)
                sig_a = msg_a.get_signal_by_name(sig_name)
            except Exception:
                pass
        if self._db_b:
            try:
                msg_b = self._db_b.get_message_by_name(msg_name)
                sig_b = msg_b.get_signal_by_name(sig_name)
            except Exception:
                pass

        def _info(sig, msg):
            if sig is None:
                return {}
            choices_str = (
                ", ".join(f"{k}={v}" for k, v in sig.choices.items())
                if sig.choices else "\u2014"
            )
            return {
                "Parent message": (
                    f"{msg.name} (0x{msg.frame_id:03X})" if msg else "\u2014"
                ),
                "Senders": (
                    ", ".join(msg.senders) if msg and msg.senders else "\u2014"
                ),
                "Receivers": (
                    ", ".join(getattr(sig, "receivers", None) or []) or "\u2014"
                ),
                "Start bit": sig.start,
                "Length (bits)": sig.length,
                "Byte order": (
                    str(getattr(sig, "byte_order", "")).split(".")[-1].lower()
                    or "\u2014"
                ),
                "Scale": sig.scale,
                "Offset": sig.offset,
                "Min": sig.minimum,
                "Max": sig.maximum,
                "Unit": sig.unit or "\u2014",
                "Choices / Values": choices_str,
                "Is multiplexer": getattr(sig, "is_multiplexer", "\u2014"),
                "Mux IDs": str(
                    getattr(sig, "multiplexer_ids", None) or "\u2014"
                ),
                "Comment": (
                    _esc(sig.comment or "").replace("\n", " ") or "\u2014"
                ),
            }

        ia, ib = _info(sig_a, msg_a), _info(sig_b, msg_b)
        if not ia and not ib:
            return "<i style='color:#8b949e;'>Signal not found in loaded files.</i>"
        keys = list(dict.fromkeys(list(ia) + list(ib)))
        rows = "".join(self._row(k, ia.get(k), ib.get(k)) for k in keys)
        return self._tbl(rows)

    def _message_detail(self, e) -> str:
        msg_name = e.path.split(".")[0]
        msg_a = msg_b = None
        if self._db_a:
            try:
                msg_a = self._db_a.get_message_by_name(msg_name)
            except Exception:
                pass
        if self._db_b:
            try:
                msg_b = self._db_b.get_message_by_name(msg_name)
            except Exception:
                pass

        def _info(msg):
            if msg is None:
                return {}
            return {
                "CAN ID (hex)": f"0x{msg.frame_id:03X}",
                "CAN ID (dec)": msg.frame_id,
                "DLC (bytes)": msg.length,
                "Is extended ID": msg.is_extended_id,
                "Is CAN FD": getattr(msg, "is_fd", False),
                "Senders": ", ".join(msg.senders) if msg.senders else "\u2014",
                "Signal count": len(msg.signals),
                "Signals": ", ".join(s.name for s in msg.signals) or "\u2014",
                "Comment": (
                    _esc(msg.comment or "").replace("\n", " ") or "\u2014"
                ),
            }

        ia, ib = _info(msg_a), _info(msg_b)
        if not ia and not ib:
            return "<i style='color:#8b949e;'>Message not found in loaded files.</i>"
        keys = list(dict.fromkeys(list(ia) + list(ib)))
        rows = "".join(self._row(k, ia.get(k), ib.get(k)) for k in keys)
        return self._tbl(rows)

    def _node_detail(self, e) -> str:
        rows = (
            self._row("Path", e.path, e.path)
            + self._row("Value (A)", e.value_a, None)
            + self._row("Value (B)", None, e.value_b)
        )
        if e.detail:
            rows += self._row("Detail", e.detail, None)
        return self._tbl(rows)

    def _generic_detail(self, e) -> str:
        rows = (
            self._row("Path", e.path, e.path)
            + self._row("Value (A)", e.value_a, None)
            + self._row("Value (B)", None, e.value_b)
        )
        if e.detail:
            rows += self._row("Detail", e.detail, None)
        if e.protocol:
            rows += self._row("Protocol", e.protocol, e.protocol)
        return self._tbl(rows)


# ---------------------------------------------------------------------------
# Worker thread
# ---------------------------------------------------------------------------

class _Worker(QObject):
    finished = Signal(list, object, object)   # results, db_a, db_b
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
            self.finished.emit(results, db_a, db_b)
        except Exception as exc:
            self.error.emit(str(exc))


# ---------------------------------------------------------------------------
# License dialog
# ---------------------------------------------------------------------------

_LICENSE_TEXT = """\
MIT License

Copyright (c) 2024  Pawan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""


class LicenseDialog(QDialog):
    """Shown at startup — user must accept before the application opens."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("dbcdiff – License Agreement")
        self.setMinimumSize(640, 480)
        # Disable the ✕ close button so Decline is the only exit path
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── contributor banner ───────────────────────────────────────────────
        contrib = QLabel("Contributor:  <b style='color:#58a6ff;'>Pawan</b>")
        contrib.setStyleSheet("font-size: 15px; padding: 6px 0;")
        layout.addWidget(contrib)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #30363d;")
        layout.addWidget(sep)

        # ── license text ─────────────────────────────────────────────────────
        title_lbl = QLabel("License Agreement")
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #8b949e;")
        layout.addWidget(title_lbl)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText(_LICENSE_TEXT)
        text.setStyleSheet(
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 12px;"
        )
        layout.addWidget(text, stretch=1)

        # ── prompt ───────────────────────────────────────────────────────────
        prompt = QLabel(
            "To use <b>dbcdiff</b> you must accept the terms above."
        )
        prompt.setStyleSheet("font-size: 12px; padding: 4px 0;")
        layout.addWidget(prompt)

        # ── buttons ──────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._decline_btn = QPushButton("✗   Decline")
        self._decline_btn.setFixedHeight(34)
        self._decline_btn.setStyleSheet(
            "QPushButton { background:#da3633; color:#fff; border-radius:6px;"
            "  padding: 0 18px; font-weight:600; }"
            "QPushButton:hover { background:#f85149; }"
        )
        self._decline_btn.clicked.connect(self._on_decline)
        btn_row.addWidget(self._decline_btn)

        btn_row.addSpacing(8)

        self._accept_btn = QPushButton("✓   Accept && Continue")
        self._accept_btn.setFixedHeight(34)
        self._accept_btn.setObjectName("primary")
        self._accept_btn.clicked.connect(self.accept)
        btn_row.addWidget(self._accept_btn)

        layout.addLayout(btn_row)

    def _on_decline(self):
        self.reject()
        sys.exit(0)


# ---------------------------------------------------------------------------
# Converter tab widget
# ---------------------------------------------------------------------------

class ConverterWidget(QWidget):
    """Tab that converts DBC ↔ Excel (.xlsx)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(20, 20, 20, 20)

        # ── title ────────────────────────────────────────────────────────────
        title = QLabel("⟳   DBC  ↔  Excel Converter")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #e6edf3;")
        root.addWidget(title)

        sub = QLabel("Convert a <b>.dbc</b> file to Excel (.xlsx) or an Excel file back to <b>.dbc</b>."
                     "  Direction is detected automatically from the source file extension.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color: #8b949e; font-size: 12px;")
        root.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #30363d;")
        root.addWidget(sep)

        # ── source file ──────────────────────────────────────────────────────
        src_lbl = QLabel("Source file  (.dbc or .xlsx)")
        src_lbl.setStyleSheet("font-weight: 600; color: #e6edf3;")
        root.addWidget(src_lbl)

        src_row = QHBoxLayout()
        self._src_edit = QLineEdit()
        self._src_edit.setPlaceholderText("Path to source file…")
        self._src_edit.textChanged.connect(self._on_src_changed)
        src_row.addWidget(self._src_edit)

        src_btn = QPushButton("Browse…")
        src_btn.setFixedWidth(90)
        src_btn.clicked.connect(self._browse_src)
        src_row.addWidget(src_btn)
        root.addLayout(src_row)

        # ── direction indicator ──────────────────────────────────────────────
        self._dir_lbl = QLabel("")
        self._dir_lbl.setStyleSheet("font-size: 12px; color: #58a6ff; padding: 2px 0;")
        root.addWidget(self._dir_lbl)

        # ── output file ──────────────────────────────────────────────────────
        out_lbl = QLabel("Output file")
        out_lbl.setStyleSheet("font-weight: 600; color: #e6edf3;")
        root.addWidget(out_lbl)

        out_row = QHBoxLayout()
        self._out_edit = QLineEdit()
        self._out_edit.setPlaceholderText("Path to output file (auto-filled)…")
        out_row.addWidget(self._out_edit)

        out_btn = QPushButton("Browse…")
        out_btn.setFixedWidth(90)
        out_btn.clicked.connect(self._browse_out)
        out_row.addWidget(out_btn)
        root.addLayout(out_row)

        # ── convert button ───────────────────────────────────────────────────
        self._convert_btn = QPushButton("⚡   Convert")
        self._convert_btn.setObjectName("primary")
        self._convert_btn.setFixedHeight(38)
        self._convert_btn.setEnabled(False)
        self._convert_btn.clicked.connect(self._do_convert)
        root.addWidget(self._convert_btn)

        # ── log area ─────────────────────────────────────────────────────────
        log_lbl = QLabel("Log")
        log_lbl.setStyleSheet("font-weight: 600; color: #e6edf3;")
        root.addWidget(log_lbl)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setStyleSheet(
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 12px;"
        )
        self._log.setMinimumHeight(120)
        root.addWidget(self._log, stretch=1)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _log_msg(self, text: str):
        self._log.append(text)

    def _src_ext(self) -> str:
        return Path(self._src_edit.text().strip()).suffix.lower()

    def _on_src_changed(self, text: str):
        text = text.strip()
        if not text:
            self._dir_lbl.setText("")
            self._convert_btn.setEnabled(False)
            return
        ext = Path(text).suffix.lower()
        if ext == ".dbc":
            self._dir_lbl.setText("📄 → 📊   Direction: DBC  →  Excel (.xlsx)")
            default_out = str(Path(text).with_suffix(".xlsx"))
        elif ext in (".xlsx", ".xls"):
            self._dir_lbl.setText("📊 → 📄   Direction: Excel  →  DBC (.dbc)")
            default_out = str(Path(text).with_suffix(".dbc"))
        else:
            self._dir_lbl.setText("⚠  Unsupported extension — use .dbc or .xlsx")
            self._convert_btn.setEnabled(False)
            return
        # auto-fill output only when it is still empty / matches old auto value
        current_out = self._out_edit.text().strip()
        if not current_out:
            self._out_edit.setText(default_out)
        self._convert_btn.setEnabled(True)

    def _browse_src(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open source file", "",
            "Supported files (*.dbc *.xlsx *.xls);;DBC files (*.dbc);;Excel files (*.xlsx *.xls);;All files (*)"
        )
        if path:
            self._src_edit.setText(path)
            self._out_edit.clear()   # reset so auto-fill re-runs
            self._on_src_changed(path)

    def _browse_out(self):
        ext = self._src_ext()
        if ext == ".dbc":
            filt = "Excel files (*.xlsx);;All files (*)"
            default_suffix = ".xlsx"
        else:
            filt = "DBC files (*.dbc);;All files (*)"
            default_suffix = ".dbc"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save output file", self._out_edit.text().strip(), filt
        )
        if path:
            if not Path(path).suffix:
                path += default_suffix
            self._out_edit.setText(path)

    def _do_convert(self):
        src = self._src_edit.text().strip()
        out = self._out_edit.text().strip()
        if not src or not out:
            QMessageBox.warning(self, "Missing paths", "Please specify both source and output paths.")
            return
        if not Path(src).is_file():
            QMessageBox.warning(self, "File not found", f"Source file not found:\n{src}")
            return

        self._convert_btn.setEnabled(False)
        self._log.clear()
        ext = self._src_ext()

        try:
            if ext == ".dbc":
                self._log_msg(f"▶  Converting DBC → Excel…\n   Source : {src}\n   Output : {out}")
                dbc_to_excel(src, out)
                self._log_msg("✅  Conversion complete!")
            elif ext in (".xlsx", ".xls"):
                self._log_msg(f"▶  Converting Excel → DBC…\n   Source : {src}\n   Output : {out}")
                excel_to_dbc(src, out)
                self._log_msg("✅  Conversion complete!")
            else:
                self._log_msg("❌  Unsupported source extension.")
        except Exception as exc:  # pylint: disable=broad-except
            self._log_msg(f"❌  Error: {exc}")
            QMessageBox.critical(self, "Conversion Error", str(exc))

        self._convert_btn.setEnabled(True)


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

        # ── converter tab ────────────────────────────────────────────────────
        self._converter_tab = ConverterWidget()
        self._tabs.addTab(self._converter_tab, "🔄  Converter")

        self._tabs.currentChanged.connect(self._on_tab_changed)

        # Wire row-selection in every results table to the detail panel
        for _ti, _t in enumerate(self._view_tables):
            _t.currentItemChanged.connect(
                lambda cur, prev, ti=_ti: self._on_row_selected(ti)
            )

        # Detail / synopsis panel – sits below the results tabs in a splitter
        self._detail = _DetailPanel()
        _splitter = QSplitter(Qt.Orientation.Vertical)
        _splitter.addWidget(self._tabs)
        _splitter.addWidget(self._detail)
        _splitter.setStretchFactor(0, 3)
        _splitter.setStretchFactor(1, 1)
        _splitter.setChildrenCollapsible(False)
        root.addWidget(_splitter, stretch=1)

        # ── status bar ───────────────────────────────────────────────────────
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — drop two DBC files to compare")

        # worker
        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None
        self._db_a = None
        self._db_b = None

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
        self._worker.finished.connect(lambda *_: self._thread.quit())
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _on_compare_done(self, entries: list[DiffEntry], db_a, db_b):
        self._entries = entries
        self._db_a = db_a
        self._db_b = db_b
        self._detail.set_databases(db_a, db_b)
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

    def _on_row_selected(self, table_idx: int) -> None:
        """Update the detail panel when a row is selected in any results table."""
        if 0 <= table_idx < len(self._view_tables):
            entry = self._view_tables[table_idx].current_entry()
            self._detail.update_entry(entry)

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

    # ── License agreement ────────────────────────────────────────────────────
    lic = LicenseDialog()
    lic.setStyleSheet(_QSS_DARK)
    if lic.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())
