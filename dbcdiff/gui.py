"""
dbcdiff – PySide6 professional dark-theme GUI  (v2 – enhanced)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    Qt, QThread, Signal, QObject, QMimeData, QSize, QRect, QPoint,
    QRectF, QPointF, QTimer,
)
from PySide6.QtGui import (
    QColor, QDragEnterEvent, QDropEvent, QPalette,
    QFont, QIcon, QPainter, QPen, QBrush, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFrame,
    QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QProgressBar, QSlider, QSplitter, QStackedWidget, QStatusBar, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
    QToolTip,
    QGraphicsScene, QGraphicsView, QGraphicsRectItem,
)

# Optional: PySide6-WebEngine for 3-D simulation (pip install PySide6-WebEngine)
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView as _QWebEngineView  # type: ignore[import]
    _WEB_ENGINE_OK = True
except ImportError:
    _QWebEngineView = None   # type: ignore[assignment, misc]
    _WEB_ENGINE_OK  = False

import cantools
from . import __version__
from .engine import (
    compare_databases,
    max_severity,
    Severity,
    DiffEntry,
    check_consistency,
    BAUD_RATES,
    compute_bus_load,
)
from .converter import excel_to_dbc
from .reporters.csv_reporter import write_csv
from .reporters.excel_reporter import write_excel
from .reporters.html_reporter import write_html
from .reporters.json_reporter import write_json

# ---------------------------------------------------------------------------
# Severity display map  (enum name → display_label, bg, fg)
# ---------------------------------------------------------------------------
_SEV_MAP: dict[str, tuple[str, str, str]] = {
    "BREAKING":   ("Breaking",   "#ff453a18", "#ff453a"),
    "FUNCTIONAL": ("Functional", "#ff9f0a18", "#ff9f0a"),
    "METADATA":   ("Metadata",   "#bf5af218", "#bf5af2"),
    "INFO":       ("Info",       "#a1a1a618", "#a1a1a6"),
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
    ("All changes",   "#a1a1a6", None),
    ("Breaking only", "#ff453a", {"__BREAKING__"}),
    ("Messages",      "#32d4d4", {"message"}),
    ("Signals",       "#3478f6", {"signal"}),
    ("Nodes / ECUs",  "#bf5af2", {"node"}),
    ("Attributes",    "#ff9f0a", {"attribute"}),
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


_STYLE_PATH = Path(__file__).resolve().parent.parent / "resources" / "style.qss"


def _load_app_stylesheet() -> str:
    try:
        return _STYLE_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def _apply_app_theme(app: QApplication) -> None:
    app.setFont(QFont("DM Sans", 10))
    app.setStyleSheet(_load_app_stylesheet())

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor("#0a0a0a"))
    palette.setColor(QPalette.WindowText, QColor("#f5f5f7"))
    palette.setColor(QPalette.Base, QColor("#0a0a0a"))
    palette.setColor(QPalette.AlternateBase, QColor("#111111"))
    palette.setColor(QPalette.Text, QColor("#f5f5f7"))
    palette.setColor(QPalette.Button, QColor("#111111"))
    palette.setColor(QPalette.ButtonText, QColor("#f5f5f7"))
    palette.setColor(QPalette.Highlight, QColor("#3478f6"))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)


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
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.setMinimumHeight(100)
        self.setMaximumHeight(140)
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
    _CARD_DEFS = [
        ("BREAKING",   "BREAKING",   "#ff453a"),
        ("FUNCTIONAL", "FUNCTIONAL", "#ff9f0a"),
        ("added",      "ADDED",      "#30d158"),
        ("removed",    "REMOVED",    "#3478f6"),
        ("METADATA",   "METADATA",   "#bf5af2"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self._cards: dict[str, tuple[QFrame, QLabel]] = {}
        for key, label, accent in self._CARD_DEFS:
            card, value = self._make_card(label, accent)
            self._cards[key] = (card, value)
            layout.addWidget(card)

    @staticmethod
    def _make_card(title: str, accent: str) -> tuple[QFrame, QLabel]:
        frame = QFrame()
        frame.setObjectName("statCard")
        frame.setMinimumHeight(84)
        frame.setStyleSheet(f"QFrame#statCard {{ border-top: 2px solid {accent}; }}")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("statTitle")
        value_lbl = QLabel("0")
        value_lbl.setObjectName("statValue")
        layout.addWidget(title_lbl)
        layout.addWidget(value_lbl)
        layout.addStretch()
        return frame, value_lbl

    def update(self, entries: list[DiffEntry]):
        counts: dict[str, int] = {k: 0 for k in self._cards}
        for e in entries:
            counts[e.severity.name] = counts.get(e.severity.name, 0) + 1
            counts[e.kind] = counts.get(e.kind, 0) + 1
        for key, (_, value_lbl) in self._cards.items():
            value_lbl.setText(str(counts.get(key, 0)))


# ---------------------------------------------------------------------------
# Table columns
# ---------------------------------------------------------------------------
_COLUMNS = ["Severity", "Protocol", "Message type", "Path", "Old", "→", "New"]
_COL_WIDTHS = [90, 90, 110, 220, 140, 30, 140]

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
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setSortingEnabled(True)
        self.horizontalHeader().setStretchLastSection(True)
        for i, w in enumerate(_COL_WIDTHS):
            self.setColumnWidth(i, w)

    def populate(self, entries: list[DiffEntry]) -> None:
        self.setSortingEnabled(False)
        self.setRowCount(0)

        mono = QFont("Courier New", 9)
        mono.setStyleHint(QFont.StyleHint.Monospace)

        for e in entries:
            row = self.rowCount()
            self.insertRow(row)
            self.setRowHeight(row, 40)

            # Col 0: Severity chip — stores DiffEntry for detail panel
            bg, fg = _sev_colors(e.severity)
            sev_item = _colored_item(_sev_display(e.severity), bg, fg)
            sev_item.setData(Qt.ItemDataRole.UserRole, e)
            self.setItem(row, 0, sev_item)

            # Col 1: Protocol
            proto = e.protocol or ""
            pbg, pfg = _PROTO_COLORS.get(proto.lower(), _PROTO_COLORS[""])
            self.setItem(row, 1, _colored_item(proto, pbg, pfg) if proto else _cell_item(""))

            # Col 2: Message type
            self.setItem(row, 2, _cell_item(e.msg_type or ""))

            # Col 3: Path widget — message name bold + signal/attr muted monospace
            parts = e.path.split(".", 1)
            path_w = QWidget()
            path_lay = QVBoxLayout(path_w)
            path_lay.setContentsMargins(8, 4, 8, 4)
            path_lay.setSpacing(1)
            msg_lbl = QLabel(parts[0])
            msg_lbl.setStyleSheet("color: #f5f5f7; font-weight: bold; background: transparent;")
            path_lay.addWidget(msg_lbl)
            if len(parts) > 1:
                sig_lbl = QLabel(parts[1])
                sig_lbl.setStyleSheet(
                    "color: #a1a1a6; font-family: 'Courier New'; font-size: 11px; background: transparent;"
                )
                path_lay.addWidget(sig_lbl)
            self.setItemWidget(row, 3, path_w)

            # Col 4: Old value — red strikethrough monospace
            old_text = str(e.value_a) if e.value_a is not None else ""
            old_item = QTableWidgetItem(old_text)
            old_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            old_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if old_text:
                old_font = QFont("Courier New", 9)
                old_font.setStrikeOut(True)
                old_item.setFont(old_font)
                old_item.setForeground(QColor("#ff453a"))
            self.setItem(row, 4, old_item)

            # Col 5: Arrow — centered muted
            arr_item = _cell_item("\u2192", Qt.AlignCenter)
            arr_item.setForeground(QColor("#636366"))
            self.setItem(row, 5, arr_item)

            # Col 6: New value — green monospace
            new_text = str(e.value_b) if e.value_b is not None else ""
            new_item = QTableWidgetItem(new_text)
            new_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            new_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if new_text:
                new_item.setFont(mono)
                new_item.setForeground(QColor("#30d158"))
            self.setItem(row, 6, new_item)

        self.setSortingEnabled(True)


    def current_entry(self) -> Optional[DiffEntry]:
        """Return the DiffEntry for the currently selected row, or None."""
        row = self.currentRow()
        if row < 0:
            return None
        item = self.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None


class ConsistencyTable(QTableWidget):
    _COLUMNS = ["File", "Level", "Rule", "Message", "Signal", "Description", "Fix Hint"]
    _WIDTHS = [70, 90, 90, 180, 180, 360, 260]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(len(self._COLUMNS))
        self.setHorizontalHeaderLabels(self._COLUMNS)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setSortingEnabled(False)
        self.horizontalHeader().setStretchLastSection(True)
        for index, width in enumerate(self._WIDTHS):
            self.setColumnWidth(index, width)

    def populate(self, records: list[dict]) -> None:
        self.setRowCount(0)
        level_colors = {
            "ERROR":   ("#ff453a18", "#ff453a"),
            "WARNING": ("#ff9f0a18", "#ff9f0a"),
            "INFO":    ("#bf5af218", "#bf5af2"),
        }

        for record in records:
            issue = record["issue"]
            row = self.rowCount()
            self.insertRow(row)
            self.setItem(row, 0, _cell_item(record["source"]))
            bg, fg = level_colors.get(issue.level, ("#21262D", "#E6EDF3"))
            self.setItem(row, 1, _colored_item(issue.level, bg, fg))
            self.setItem(row, 2, _cell_item(issue.rule_id))
            self.setItem(row, 3, _cell_item(issue.message_name or "—"))
            self.setItem(row, 4, _cell_item(issue.signal_name or "—"))
            self.setItem(row, 5, _cell_item(issue.description or ""))
            self.setItem(row, 6, _cell_item(issue.fix_hint or ""))
            self.setRowHeight(row, 28)

    def current_entry(self):
        return None


# ---------------------------------------------------------------------------
# Detail / synopsis panel
# ---------------------------------------------------------------------------

class _DetailPanel(QWidget):
    """Rich detail rail for the selected diff row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("detailPanel")
        self.setFixedWidth(300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        header_col = QVBoxLayout()
        header_col.setSpacing(2)
        self._header = QLabel("Select a frame")
        self._header.setObjectName("detailHeader")
        self._subheader = QLabel("Frame ID and signal geometry appear here")
        self._subheader.setObjectName("detailSubheader")
        header_col.addWidget(self._header)
        header_col.addWidget(self._subheader)
        top_row.addLayout(header_col, 1)

        self._proto_badge = QLabel("RAW")
        self._proto_badge.setObjectName("detailBadge")
        top_row.addWidget(self._proto_badge, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addLayout(top_row)

        bit_wrap = QFrame()
        bit_wrap.setObjectName("previewCard")
        bit_layout = QVBoxLayout(bit_wrap)
        bit_layout.setContentsMargins(12, 12, 12, 12)
        bit_layout.setSpacing(8)
        bit_title = QLabel("Bit Layout")
        bit_title.setObjectName("previewTitle")
        bit_layout.addWidget(bit_title)
        bit_caption = QLabel("8 × 8 occupancy map")
        bit_caption.setObjectName("bitCaption")
        bit_layout.addWidget(bit_caption)

        self._bit_grid = BitGridWidget()
        bit_layout.addWidget(self._bit_grid, alignment=Qt.AlignmentFlag.AlignLeft)

        self._bit_legend = QVBoxLayout()
        self._bit_legend.setSpacing(6)
        bit_layout.addLayout(self._bit_legend)
        layout.addWidget(bit_wrap)

        kv_wrap = QFrame()
        kv_wrap.setObjectName("previewCard")
        kv_outer = QVBoxLayout(kv_wrap)
        kv_outer.setContentsMargins(12, 12, 12, 12)
        kv_outer.setSpacing(8)
        kv_title = QLabel("Attributes")
        kv_title.setObjectName("previewTitle")
        kv_outer.addWidget(kv_title)
        self._kv_rows = QVBoxLayout()
        self._kv_rows.setSpacing(6)
        kv_outer.addLayout(self._kv_rows)
        layout.addWidget(kv_wrap)

        preview = QFrame()
        preview.setObjectName("previewCard")
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_layout.setSpacing(8)
        preview_glyph = QLabel("◫")
        preview_glyph.setObjectName("previewGlyph")
        preview_layout.addWidget(preview_glyph)
        preview_title = QLabel("Selection Summary")
        preview_title.setObjectName("previewTitle")
        preview_layout.addWidget(preview_title)
        self._preview_text = QLabel("Select a message or signal to inspect its impact, mapping, and current change context.")
        self._preview_text.setWordWrap(True)
        self._preview_text.setObjectName("previewText")
        preview_layout.addWidget(self._preview_text)
        layout.addWidget(preview)
        layout.addStretch()

        self._db_a = None
        self._db_b = None

    def set_databases(self, db_a, db_b) -> None:
        self._db_a = db_a
        self._db_b = db_b

    def update_entry(self, entry) -> None:
        if entry is None:
            self._header.setText("Select a frame")
            self._subheader.setText("Frame ID and signal geometry appear here")
            self._proto_badge.setText("RAW")
            self._preview_text.setText("Select a message or signal to inspect its impact, mapping, and current change context.")
            self._set_kv_rows([])
            self._update_bit_grid(None, None)
            return
        data = self._entry_data(entry)
        self._header.setText(data["title"])
        self._subheader.setText(data["subtitle"])
        self._proto_badge.setText(data["badge"])
        self._preview_text.setText(data["preview"])
        self._set_kv_rows(data["rows"])
        self._update_bit_grid(data["message"], data["signal"])

    def _set_kv_rows(self, rows: list[tuple[str, str]]) -> None:
        while self._kv_rows.count():
            item = self._kv_rows.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not rows:
            rows = [("State", "No selection")]

        for key, value in rows[:9]:
            row = QFrame()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            key_lbl = QLabel(key)
            key_lbl.setObjectName("kvKey")
            val_lbl = QLabel(value)
            val_lbl.setObjectName("kvValue")
            val_lbl.setWordWrap(True)
            row_layout.addWidget(key_lbl)
            row_layout.addStretch()
            row_layout.addWidget(val_lbl, 1)
            self._kv_rows.addWidget(row)
        self._kv_rows.addStretch()

    def _update_bit_grid(self, message, signal) -> None:
        self._bit_grid.load_message(message)
        self._set_bit_legend(self._bit_grid.legend_items(), signal.name if signal is not None else "")

    def _set_bit_legend(self, items: list[tuple[str, str]], selected_signal: str = "") -> None:
        while self._bit_legend.count():
            item = self._bit_legend.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not items:
            empty = QLabel("No signals mapped")
            empty.setObjectName("bitCaption")
            self._bit_legend.addWidget(empty)
            return

        rows = QHBoxLayout()
        rows.setSpacing(6)
        for idx, (name, color) in enumerate(items):
            chip = QFrame()
            chip.setObjectName("legendItem")
            chip_layout = QHBoxLayout(chip)
            chip_layout.setContentsMargins(0, 0, 0, 0)
            chip_layout.setSpacing(6)

            swatch = QLabel()
            swatch.setObjectName("legendSwatch")
            swatch.setFixedSize(12, 12)
            swatch.setStyleSheet(f"background:{color}; border-radius:6px;")
            chip_layout.addWidget(swatch)

            label = QLabel(name)
            label.setObjectName("kvValue" if name == selected_signal else "bitCaption")
            chip_layout.addWidget(label)
            rows.addWidget(chip)

            if (idx + 1) % 2 == 0:
                rows.addStretch()
                self._bit_legend.addLayout(rows)
                rows = QHBoxLayout()
                rows.setSpacing(6)

        if rows.count():
            rows.addStretch()
            self._bit_legend.addLayout(rows)

    def _message_name_from_path(self, entry) -> str:
        path = entry.path or ""
        if path.startswith("message."):
            fragment = path.split(".", 1)[1]
            return fragment.split("(", 1)[0]
        return path.split(".", 1)[0]

    def _signal_name_from_path(self, entry) -> str:
        parts = (entry.path or "").split(".")
        if parts and parts[0] == "message" and len(parts) > 2:
            return parts[2].split("(", 1)[0]
        if len(parts) > 1:
            return parts[1].split("(", 1)[0]
        return ""

    def _find_message(self, entry):
        msg_name = self._message_name_from_path(entry)
        for db in (self._db_b, self._db_a):
            if db is None:
                continue
            try:
                return db.get_message_by_name(msg_name)
            except Exception:
                continue
        return None

    def _find_signal(self, entry, message):
        if message is None:
            return None
        sig_name = self._signal_name_from_path(entry)
        if not sig_name:
            return None
        try:
            return message.get_signal_by_name(sig_name)
        except Exception:
            return None

    def _entry_data(self, entry) -> dict:
        message = self._find_message(entry)
        signal = self._find_signal(entry, message) if entry.entity == "signal" else None
        frame_id = f"0x{message.frame_id:03X}" if message is not None else "No frame"
        title = f"{frame_id} · {message.name}" if message is not None else entry.path
        subtitle = f"{entry.entity.title()} • {entry.kind.title()} • {_sev_display(entry.severity)}"
        badge = (entry.protocol or entry.msg_type or "RAW").upper()
        rows = [
            ("Path", entry.path or "—"),
            ("Old", str(entry.value_a) if entry.value_a is not None else "—"),
            ("New", str(entry.value_b) if entry.value_b is not None else "—"),
            ("Message Type", entry.msg_type or "—"),
        ]
        if message is not None:
            rows.extend([
                ("Frame ID", frame_id),
                ("DLC", str(message.length)),
                ("Senders", ", ".join(message.senders) if message.senders else "—"),
            ])
        if signal is not None:
            rows.extend([
                ("Signal", signal.name),
                ("Start Bit", str(signal.start)),
                ("Length", str(signal.length)),
                ("Unit", signal.unit or "—"),
            ])
        if entry.detail:
            rows.append(("Change Impact", entry.detail))

        preview = entry.detail or (
            f"{entry.msg_type or entry.entity.title()} change in a frame with "
            f"{len(getattr(message, 'signals', [])) if message is not None else 0} mapped signals."
        )
        return {
            "title": title,
            "subtitle": subtitle,
            "badge": badge,
            "rows": rows,
            "preview": preview,
            "message": message,
            "signal": signal,
        }


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
Apache License
Version 2.0, January 2004
http://www.apache.org/licenses/

Copyright (c) 2024  Pawan

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this software except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

---

TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

1. Definitions. "License" means the terms and conditions for use as
   defined by Sections 1 through 9 of this document.

2. Grant of Copyright License. Each Contributor grants you a perpetual,
   worldwide, non-exclusive, no-charge, royalty-free, irrevocable
   copyright license to reproduce, prepare Derivative Works of, publicly
   display, publicly perform, sublicense, and distribute the Work.

3. Grant of Patent License. Each Contributor grants you a perpetual,
   worldwide, non-exclusive, no-charge, royalty-free, irrevocable patent
   license to make, use, offer to sell, sell, import the Work.

4. Redistribution. You may reproduce and distribute copies of the Work
   provided that you meet the conditions stated in the License.

5. Submission of Contributions. Any Contribution submitted for inclusion
   in the Work shall be under the terms and conditions of this License.

6. Trademarks. This License does not grant permission to use the trade
   names or trademarks of the Licensor.

7. Disclaimer of Warranty. The Work is provided on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND.

8. Limitation of Liability. In no event shall any Contributor be liable
   for any damages arising as a result of this License.

9. Accepting Warranty or Additional Liability. You may offer and charge
   a fee for acceptance of support, warranty, or indemnity obligations.

END OF TERMS AND CONDITIONS
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
                db = cantools.database.load_file(src)
                write_excel(db, out)
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
# Bit-layout helpers
# ---------------------------------------------------------------------------

def _motorola_bits(start_bit: int, length: int) -> set[int]:
    """Return the set of DBC bit positions occupied by a Motorola (big-endian) signal.

    In DBC files the *start_bit* of a Motorola signal is its MSB position.
    Traversal goes right within the byte (bit-in-byte decrements) then
    wraps to the MSB of the next byte — identical to cantools' convention.

    Verification: start=7, length=16
        → {7,6,5,4,3,2,1,0, 15,14,13,12,11,10,9,8}  (bytes 0 and 1 fully covered) ✓
    """
    bits: set[int] = set()
    b = start_bit
    for _ in range(length):
        bits.add(b)
        if b % 8 == 0:   # reached the LSB of the current byte
            b += 15      # jump to MSB of the *next* byte
        else:
            b -= 1
    return bits


def _motorola_start_bit(sig) -> int:
    """Return cantools' byte-aligned Motorola start bit when available."""
    try:
        return int(cantools.database.can.signal.start_bit(sig))
    except Exception:
        return int(sig.start)


def _signal_bits(sig) -> set[int]:
    """Return DBC bit positions for *sig* regardless of byte order."""
    if getattr(sig, "byte_order", "little_endian") == "big_endian":
        start_bit = _motorola_start_bit(sig)
        return set(range(start_bit, start_bit + int(sig.length)))
    return set(range(int(sig.start), int(sig.start) + int(sig.length)))


_BIT_GRID_COLORS = [
    "#58A6FF",
    "#3FB950",
    "#D29922",
    "#F85149",
    "#8957E5",
    "#39D0D8",
    "#FF7B72",
    "#FFA657",
]


class BitGridWidget(QWidget):
    """64-cell bit layout widget using QLabel cells."""

    def __init__(self, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(4)
        self._cells: list[QLabel] = []
        self._legend: list[tuple[str, str]] = []
        self._color_map: dict[int, str] = {}
        self._message = None

        for row in range(8):
            for col in range(8):
                bit_index = (row * 8) + col
                cell = QLabel(str(bit_index))
                cell.setObjectName("bitCell")
                cell.setFixedSize(22, 22)
                cell.setToolTip(f"Bit {bit_index}")
                grid.addWidget(cell, row, col)
                self._cells.append(cell)

    def legend_items(self) -> list[tuple[str, str]]:
        return list(self._legend)

    def load_message(self, msg) -> None:
        self._message = msg
        self._legend = []
        color_map: dict[str, str] = {}
        occupied: dict[int, tuple[str, object]] = {}

        if msg is not None:
            signals = sorted(msg.signals, key=lambda sig: sig.name)
            for idx, sig in enumerate(signals):
                color = _BIT_GRID_COLORS[idx % len(_BIT_GRID_COLORS)]
                color_map[sig.name] = color
                self._legend.append((sig.name, color))
                for bit in _signal_bits(sig):
                    if 0 <= bit < 64:
                        occupied[bit] = (color, sig)

        self._color_map = {bit: color for bit, (color, _) in occupied.items()}
        for bit_index, cell in enumerate(self._cells):
            if bit_index in occupied:
                color, sig = occupied[bit_index]
                cell.setStyleSheet(
                    f"background:{color}; color:#0A0A0A; border:1px solid {color}; border-radius:7px;"
                )
                cell.setText(sig.name[:2].upper())
                cell.setToolTip(f"{sig.name}\nstart_bit={sig.start}\nlength={sig.length}")
            else:
                cell.setStyleSheet(
                    "background:#4A515B; color:#D4D9E0; border:1px solid #5A6370; border-radius:7px;"
                )
                cell.setText(str(bit_index % 8))
                cell.setToolTip(f"Bit {bit_index}")

    def set_bytes(self, data: bytes) -> None:
        """Re-colour cells based on which bits are set in *data*."""
        if self._message is None:
            return
        set_bits: set[int] = set()
        for bi, bv in enumerate(data[: self._message.length]):
            for bp in range(8):
                if bv & (1 << bp):
                    set_bits.add(bi * 8 + bp)
        for bit_index, cell in enumerate(self._cells):
            if bit_index in self._color_map:
                color = self._color_map[bit_index]
                if bit_index in set_bits:
                    cell.setStyleSheet(
                        f"background:{color}; color:#0A0A0A;"
                        " border:2px solid #FFFFFF; border-radius:7px;"
                    )
                else:
                    cell.setStyleSheet(
                        f"background:#1c2128; color:{color};"
                        " border:1px solid #30363d; border-radius:7px;"
                    )
            else:
                cell.setStyleSheet(
                    "background:#4A515B; color:#D4D9E0;"
                    " border:1px solid #5A6370; border-radius:7px;"
                )


# ---------------------------------------------------------------------------
# Interactive bit-grid canvas
# ---------------------------------------------------------------------------

class _BitGridCanvas(QWidget):
    """Custom QWidget that paints a DBC-compliant 8×8 bit-layout grid.

    Layout (matches standard CAN / DBC tooling convention):
        • Rows  = byte index 0 … 7   (top = byte 0)
        • Cols  = bit within byte     (left-col = bit 7, right-col = bit 0)
        • DBC bit number = row × 8 + (7 − col)

    Features
    --------
    * Correct Motorola (big-endian) *and* Intel (little-endian) bit mapping
    * Each signal gets a unique hue; filled cells show the abbreviated name
    * Hover → cell highlight + QToolTip with signal name, unit and
      physical-value formula  ``physical = raw × scale + offset``
    * Responsive cell sizes (fills available width)
    """

    # Minimum cell geometry (pixels)
    _MIN_CW = 44
    _MIN_CH = 28
    _HDR_H  = 20   # column-header row height
    _HDR_W  = 50   # row-header (byte label) column width

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(
            self._HDR_W + 8 * self._MIN_CW,
            self._HDR_H + 8 * self._MIN_CH,
        )
        self._signals: list = []
        # (row, col) → (signal, QColor)
        self._cell_map: dict[tuple[int, int], tuple] = {}
        self._hover_rc: tuple[int, int] | None = None

    # ── public API ──────────────────────────────────────────────────────────

    def set_message(self, msg) -> None:
        """Populate the canvas from a *cantools* message object (or None)."""
        self._signals.clear()
        self._cell_map.clear()
        self._hover_rc = None
        if msg is None:
            self.update()
            return
        sigs = sorted(msg.signals, key=lambda s: s.name)
        n = max(len(sigs), 1)
        colors = [QColor.fromHsv(int(i * 360 / n), 165, 205) for i in range(n)]
        for idx, sig in enumerate(sigs):
            color = colors[idx]
            for bit in _signal_bits(sig):
                row, col = bit // 8, 7 - (bit % 8)
                if 0 <= row < 8 and 0 <= col < 8:
                    self._cell_map[(row, col)] = (sig, color)
        self._signals = sigs
        self.update()

    def get_signal_color_map(self) -> dict:
        """Return ``{signal_name: QColor}`` for every signal in the current message."""
        result: dict = {}
        for sig, color in self._cell_map.values():
            result[sig.name] = color
        return result

    # ── geometry helpers ────────────────────────────────────────────────────

    def _cell_w(self) -> int:
        return max(self._MIN_CW, (self.width() - self._HDR_W) // 8)

    def _cell_h(self) -> int:
        return max(self._MIN_CH, (self.height() - self._HDR_H) // 8)

    def sizeHint(self) -> QSize:
        return QSize(self._HDR_W + 8 * 58, self._HDR_H + 8 * 32)

    def _cell_rect(self, row: int, col: int) -> QRect:
        cw, ch = self._cell_w(), self._cell_h()
        return QRect(self._HDR_W + col * cw, self._HDR_H + row * ch, cw, ch)

    def _rc_from_pos(self, x: float, y: float) -> tuple[int, int] | None:
        cw, ch = self._cell_w(), self._cell_h()
        col = int(x - self._HDR_W) // cw
        row = int(y - self._HDR_H) // ch
        if 0 <= row < 8 and 0 <= col < 8:
            return (row, col)
        return None

    # ── painting ────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        C_BG         = QColor("#0a0a0a")
        C_HDR        = QColor("#111111")
        C_BORDER     = QColor("#2a2a2e")
        C_HOVER_BORD = QColor("#3478f6")
        C_EMPTY      = QColor("#1c1c1e")
        C_HDR_TXT    = QColor("#8b949e")
        C_CELL_TXT   = QColor("#0d1117")

        p.fillRect(self.rect(), C_BG)

        cw, ch = self._cell_w(), self._cell_h()

        # ── small fonts ──
        f_hdr = QFont()
        f_hdr.setPointSize(7)
        f_hdr.setBold(True)
        f_cell = QFont()
        f_cell.setPointSize(7)

        # ── column headers  (bit-in-byte 7 … 0) ──
        p.setFont(f_hdr)
        p.setPen(C_HDR_TXT)
        for col in range(8):
            r = QRect(self._HDR_W + col * cw, 0, cw, self._HDR_H)
            p.fillRect(r, C_HDR)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(7 - col))

        # ── row headers  (Byte 0 … 7) ──
        for row in range(8):
            r = QRect(0, self._HDR_H + row * ch, self._HDR_W, ch)
            p.fillRect(r, C_HDR)
            p.setPen(C_HDR_TXT)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, f"B{row}")

        # ── cells ──
        p.setFont(f_cell)
        for row in range(8):
            for col in range(8):
                r = self._cell_rect(row, col)
                entry = self._cell_map.get((row, col))
                is_hover = (row, col) == self._hover_rc

                if entry:
                    sig, base_color = entry
                    fill = base_color.lighter(125) if is_hover else base_color
                    p.fillRect(r, fill)
                    # abbreviated signal name (up to 9 chars)
                    abbr = sig.name if len(sig.name) <= 9 else sig.name[:8] + "…"
                    p.setPen(C_CELL_TXT)
                    p.drawText(
                        r.adjusted(1, 1, -1, -1),
                        Qt.AlignmentFlag.AlignCenter,
                        abbr,
                    )
                else:
                    p.fillRect(r, C_EMPTY)

                # border
                bord_pen = QPen(C_HOVER_BORD if is_hover else C_BORDER)
                bord_pen.setWidth(2 if is_hover else 1)
                p.setPen(bord_pen)
                p.drawRect(r.adjusted(0, 0, -1, -1))

        p.end()

    # ── interaction ─────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position()
        rc = self._rc_from_pos(pos.x(), pos.y())
        if rc != self._hover_rc:
            self._hover_rc = rc
            self.update()
        if rc and rc in self._cell_map:
            sig, _ = self._cell_map[rc]
            scale  = getattr(sig, "scale",  1)
            offset = getattr(sig, "offset", 0)
            unit   = getattr(sig, "unit",   "") or ""
            # Build formula line
            if scale == 1 and offset == 0:
                formula = "physical = raw"
            else:
                sc_part = f"raw × {scale}" if scale != 1 else "raw"
                if offset > 0:
                    formula = f"physical = {sc_part} + {offset}"
                elif offset < 0:
                    formula = f"physical = {sc_part} − {abs(offset)}"
                else:
                    formula = f"physical = {sc_part}"
            unit_part = f"  [{unit}]" if unit else ""
            tip = f"{sig.name}{unit_part}\n{formula}"
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, _event) -> None:  # noqa: N802
        if self._hover_rc is not None:
            self._hover_rc = None
            self.update()
        QToolTip.hideText()


# ---------------------------------------------------------------------------
# Single-file viewer dialog
# ---------------------------------------------------------------------------

class ViewerDialog(QDialog):
    """Tabbed viewer for a single DBC file (Messages / Signals / Bit Layout / Nodes)."""

    _CELL_COLORS: list[tuple[str, str]] = [
        ("#1e4f1e", "#90ee90"), ("#1e3a5f", "#7ec8e3"),
        ("#4f1e1e", "#ee9090"), ("#3a1e5f", "#c87ee3"),
        ("#4f3a1e", "#e3c87e"), ("#1e4f4f", "#7ee3e3"),
        ("#3f1e4f", "#d07ee3"), ("#1e3f1e", "#7ee3a0"),
        ("#4f4f1e", "#e3e37e"), ("#1e4f3a", "#7ee3c8"),
    ]

    def __init__(self, db, filename: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"🔍  Viewer — {filename}")
        self.setMinimumSize(1000, 680)
        self._db = db

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        tabs = QTabWidget()
        tabs.addTab(self._build_messages_tab(),   "📨  Messages")
        tabs.addTab(self._build_signals_tab(),    "📡  Signals")
        tabs.addTab(self._build_bit_layout_tab(),    "🔢  Bit Layout")
        tabs.addTab(self._build_nodes_tab(),         "🔗  Nodes")
        tabs.addTab(self._build_consistency_tab(),   "⚠️  Consistency")
        tabs.addTab(self._build_timing_tab(),        "⏱️  Timing")
        tabs.addTab(self._build_timeline_tab(),       "📊  Timeline")
        root.addWidget(tabs, stretch=1)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    # ── Messages ──────────────────────────────────────────────────────────────

    def _build_messages_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        fr = QHBoxLayout()
        fr.addWidget(QLabel("Filter by sender:"))
        sender_cb = QComboBox()
        sender_cb.addItem("(All senders)")
        senders = sorted({s for m in self._db.messages for s in (m.senders or [])})
        sender_cb.addItems(senders)
        fr.addWidget(sender_cb)
        fr.addStretch()
        lay.addLayout(fr)

        cols = ["Frame ID", "Name", "DLC", "Cycle Time (ms)", "Signals", "Comment"]
        tbl = QTableWidget(0, len(cols))
        tbl.setHorizontalHeaderLabels(cols)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.setSortingEnabled(True)
        tbl.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(tbl)

        def _fill(sender_filter: str = "") -> None:
            msgs = sorted(self._db.messages, key=lambda m: m.frame_id)
            if sender_filter and sender_filter != "(All senders)":
                msgs = [m for m in msgs if sender_filter in (m.senders or [])]
            tbl.setSortingEnabled(False)
            tbl.setRowCount(len(msgs))
            for row, m in enumerate(msgs):
                cycle = str(m.cycle_time) if m.cycle_time else ""
                for col, val in enumerate([
                    f"0x{m.frame_id:X}",
                    m.name,
                    str(m.length),
                    cycle,
                    str(len(m.signals)),
                    m.comment or "",
                ]):
                    it = QTableWidgetItem(val)
                    it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    tbl.setItem(row, col, it)
            tbl.setSortingEnabled(True)
            tbl.resizeColumnsToContents()

        _fill()
        sender_cb.currentTextChanged.connect(_fill)
        return w

    # ── Signals ───────────────────────────────────────────────────────────────

    def _build_signals_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        fr = QHBoxLayout()
        fr.addWidget(QLabel("Filter by message:"))
        msg_cb = QComboBox()
        msg_cb.addItem("(All messages)", "")
        for m in sorted(self._db.messages, key=lambda m: m.name):
            msg_cb.addItem(f"{m.name}  (0x{m.frame_id:X})", m.name)
        fr.addWidget(msg_cb)
        fr.addStretch()
        lay.addLayout(fr)

        cols = ["Signal", "Message", "Start Bit", "Length", "Byte Order",
                "Scale", "Offset", "Unit", "Min", "Max", "Comment"]
        tbl = QTableWidget(0, len(cols))
        tbl.setHorizontalHeaderLabels(cols)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.setSortingEnabled(True)
        tbl.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(tbl)

        def _fill(_idx: int = 0) -> None:
            filter_name: str = msg_cb.currentData() or ""
            rows: list[tuple] = []
            for m in sorted(self._db.messages, key=lambda m: m.name):
                if filter_name and m.name != filter_name:
                    continue
                for s in sorted(m.signals, key=lambda s: s.name):
                    bo = "Intel" if "little" in str(s.byte_order).lower() else "Motorola"
                    rows.append((
                        s.name, m.name, str(s.start), str(s.length), bo,
                        str(s.scale), str(s.offset), s.unit or "",
                        str(s.minimum) if s.minimum is not None else "",
                        str(s.maximum) if s.maximum is not None else "",
                        s.comment or "",
                    ))
            tbl.setSortingEnabled(False)
            tbl.setRowCount(len(rows))
            for row, vals in enumerate(rows):
                for col, val in enumerate(vals):
                    it = QTableWidgetItem(val)
                    it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                    tbl.setItem(row, col, it)
            tbl.setSortingEnabled(True)
            tbl.resizeColumnsToContents()

        _fill()
        msg_cb.currentIndexChanged.connect(_fill)
        return w

    # ── Bit Layout ────────────────────────────────────────────────────────────

    def _build_bit_layout_tab(self) -> QWidget:
        """Bit Layout tab — interactive DBC grid with correct Motorola mapping.

        Rows = bytes 0–7, columns = bit-in-byte 7 (left) → 0 (right).
        Signals rendered via :class:`_BitGridCanvas`; hover shows tooltip with
        physical-value formula.  Legend below lists each signal's colour.
        """
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # ── top control row ──────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Message:"))
        msg_cb = QComboBox()
        msgs = sorted(self._db.messages, key=lambda m: m.name)
        for m in msgs:
            msg_cb.addItem(f"{m.name}   0x{m.frame_id:X}  (DLC={m.length})", m)
        ctrl.addWidget(msg_cb, stretch=1)
        lay.addLayout(ctrl)

        # ── hint label ───────────────────────────────────────────────────────
        hint = QLabel(
            "ℹ  Hover a cell for signal name and physical-value formula.  "
            "Rows = bytes, columns = bit-in-byte (7 left → 0 right).  "
            "Motorola (big-endian) and Intel (little-endian) both mapped correctly."
        )
        hint.setStyleSheet("color: #8b949e; font-size: 11px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        # ── canvas inside a scroll area ──────────────────────────────────────
        canvas = _BitGridCanvas()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(canvas)
        scroll.setStyleSheet("QScrollArea { border: 1px solid #30363d; }")
        lay.addWidget(scroll, stretch=1)

        # ── legend strip ─────────────────────────────────────────────────────
        legend = QLabel()
        legend.setWordWrap(True)
        legend.setStyleSheet("font-size: 11px; padding: 4px 0;")
        lay.addWidget(legend)

        # ── refresh helper ───────────────────────────────────────────────────
        def _refresh(idx: int) -> None:
            msg = msg_cb.itemData(idx)
            if msg is None:
                return
            canvas.set_message(msg)
            color_map = canvas.get_signal_color_map()
            if color_map:
                badges = "  ".join(
                    f'<span style="background:{c.name()}; color:#0d1117;'
                    f' border-radius:3px; padding:2px 8px;">'
                    f'{_esc(name)}</span>'
                    for name, c in sorted(color_map.items())
                )
                legend.setText(f"<html><body>{badges}</body></html>")
            else:
                legend.setText(
                    '<span style="color:#8b949e;">No signals in this message.</span>'
                )

        msg_cb.currentIndexChanged.connect(_refresh)
        if msgs:
            _refresh(0)

        return w

    # ── Nodes ─────────────────────────────────────────────────────────────────

    def _build_nodes_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)

        cols = ["Name", "Comment", "TX Messages", "RX Signals"]
        tbl = QTableWidget(0, len(cols))
        tbl.setHorizontalHeaderLabels(cols)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(True)
        lay.addWidget(tbl)

        nodes = sorted(self._db.nodes or [], key=lambda n: n.name)
        node_tx: dict[str, list[str]] = {}
        for m in self._db.messages:
            for s in (m.senders or []):
                node_tx.setdefault(s, []).append(m.name)
        node_rx: dict[str, int] = {}
        for m in self._db.messages:
            for sig in m.signals:
                for r in (sig.receivers or []):
                    node_rx[r] = node_rx.get(r, 0) + 1

        tbl.setRowCount(len(nodes))
        for row, n in enumerate(nodes):
            for col, val in enumerate([
                n.name,
                n.comment or "",
                str(len(node_tx.get(n.name, []))),
                str(node_rx.get(n.name, 0)),
            ]):
                it = QTableWidgetItem(val)
                it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if col >= 2:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tbl.setItem(row, col, it)
        tbl.resizeColumnsToContents()
        return w

    # ── Consistency checks ────────────────────────────────────────────────────

    def _build_consistency_tab(self) -> QWidget:  # noqa: PLR0912
        """Run all 8 automatic consistency checks and render results."""

        # ── Internal data class ───────────────────────────────────────────
        class Finding:
            __slots__ = ("sev", "check", "entity", "detail", "hint")

            def __init__(self, sev: str, check: str, entity: str,
                         detail: str, hint: str) -> None:
                self.sev    = sev
                self.check  = check
                self.entity = entity
                self.detail = detail
                self.hint   = hint

        findings: list[Finding] = []
        db      = self._db
        KNODES  = {n.name for n in (db.nodes or [])}

        # ── Helper: physical bit positions ────────────────────────────────
        def _bits_of(s) -> set[int]:
            start, length = int(s.start), int(s.length)
            if "little" in str(s.byte_order).lower():       # Intel LE
                return set(range(start, start + length))
            # Motorola BE: start = MSB in DBC vector notation;
            # walk downward in-byte then wrap to MSB of next byte.
            bits: set[int] = set()
            cur  = start
            for _ in range(length):
                bits.add(cur)
                cur = (cur // 8 + 1) * 8 + 7 if cur % 8 == 0 else cur - 1
            return bits

        # ── Check 1: Duplicate frame IDs ──────────────────────────────────
        seen_ids: dict[int, str] = {}
        for m in db.messages:
            if m.frame_id in seen_ids:
                findings.append(Finding(
                    "Error", "Duplicate Frame ID",
                    f"0x{m.frame_id:X}",
                    f"'{m.name}' and '{seen_ids[m.frame_id]}' share"
                    f" frame ID 0x{m.frame_id:X}.",
                    "Assign a unique frame ID to every message.",
                ))
            else:
                seen_ids[m.frame_id] = m.name

        for m in db.messages:
            dlc_bits = m.length * 8
            pref     = m.name

            # ── Check 2: Undefined sender ──────────────────────────────────
            for sender in (m.senders or []):
                if sender and sender not in KNODES:
                    findings.append(Finding(
                        "Warning", "Undefined Sender",
                        pref,
                        f"Sender '{sender}' is not listed in BU_.",
                        "Add the node to the BU_ declaration or correct"
                        " the sender name.",
                    ))

            # ── Check 3: Cycle time = 0 ────────────────────────────────────
            ct = m.cycle_time
            if ct == 0:
                findings.append(Finding(
                    "Error", "Cycle Time = 0",
                    pref,
                    f"'{pref}' has GenMsgCycleTime = 0;"
                    " a cyclic message would fire continuously.",
                    "Set GenMsgCycleTime to the intended period in ms"
                    " (e.g. 10 or 100).",
                ))

            # ── Check 4: Multiplexer switch with no muxed signals ──────────
            has_mux_sw = any(getattr(s, "is_multiplexer", False)
                             for s in m.signals)
            has_muxed  = any(bool(getattr(s, "multiplexer_ids", None))
                             for s in m.signals)
            if has_mux_sw and not has_muxed:
                sw_name = next(
                    s.name for s in m.signals
                    if getattr(s, "is_multiplexer", False)
                )
                findings.append(Finding(
                    "Warning", "Mux Without Signals",
                    pref,
                    f"Multiplexer switch '{sw_name}' is declared but no"
                    " signals reference any mux ID.",
                    "Add multiplexed signals (M0, M1 …) or remove the"
                    " mux switch.",
                ))

            # ── Per-signal checks + bit collection ────────────────────────
            sig_bits: dict[str, set[int]] = {}
            for s in m.signals:
                bits = _bits_of(s)
                sig_bits[s.name] = bits

                # Check 5: Scale = 0
                try:
                    if float(s.scale) == 0.0:
                        findings.append(Finding(
                            "Warning", "Scale = 0",
                            f"{pref}.{s.name}",
                            f"Scale is 0 — physical value will always equal"
                            f" offset ({s.offset}) regardless of raw data.",
                            "Set a meaningful scale factor (e.g. 0.001, 0.1, 1.0).",
                        ))
                except (TypeError, ValueError):
                    pass

                # Check 6: No receivers
                receivers = getattr(s, "receivers", None) or []
                if not receivers:
                    findings.append(Finding(
                        "Info", "No Receivers",
                        f"{pref}.{s.name}",
                        "Signal has no receiver nodes; routing is undefined.",
                        "Add receiving node(s) or use"
                        " VECTOR__INDEPENDENT_SIG_MSG.",
                    ))
                else:
                    # Check 7: Undefined receiver(s)
                    for r in receivers:
                        if r and r not in KNODES:
                            findings.append(Finding(
                                "Warning", "Undefined Receiver",
                                f"{pref}.{s.name}",
                                f"Receiver '{r}' is not listed in BU_.",
                                "Add the node to the BU_ declaration or"
                                " correct the receiver name.",
                            ))

                # Check 8: DLC undersize
                if bits:
                    max_bit = max(bits)
                    if max_bit >= dlc_bits:
                        findings.append(Finding(
                            "Error", "DLC Undersize",
                            f"{pref}.{s.name}",
                            f"Signal reaches bit {max_bit} but DLC={m.length}"
                            f" only covers bits 0\u2013{dlc_bits - 1}.",
                            f"Increase DLC to at least {max_bit // 8 + 1}"
                            " bytes.",
                        ))

            # ── Check 1b: Bit overlap (pairwise) ──────────────────────────
            snames = list(sig_bits)
            for i in range(len(snames)):
                for j in range(i + 1, len(snames)):
                    overlap = sig_bits[snames[i]] & sig_bits[snames[j]]
                    if overlap:
                        ovs = sorted(overlap)
                        rng = (str(ovs[0]) if len(ovs) == 1
                               else f"{ovs[0]}\u2013{ovs[-1]}")
                        findings.append(Finding(
                            "Error", "Bit Overlap",
                            pref,
                            f"'{snames[i]}' and '{snames[j]}' share"
                            f" {len(ovs)} bit(s) at position(s) {rng}.",
                            "Correct the start bit or length of one of the"
                            " conflicting signals.",
                        ))

        # ── Build UI ───────────────────────────────────────────────────────
        SEV_ORDER  = {"Error": 0, "Warning": 1, "Info": 2}
        SEV_COLORS = {
            "Error":   ("#3d1a1a", "#f85149"),
            "Warning": ("#3d2e0a", "#e3b341"),
            "Info":    ("#0d2645", "#58a6ff"),
        }
        findings.sort(key=lambda f: SEV_ORDER.get(f.sev, 9))

        n_err  = sum(1 for f in findings if f.sev == "Error")
        n_warn = sum(1 for f in findings if f.sev == "Warning")
        n_info = sum(1 for f in findings if f.sev == "Info")

        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Summary bar
        summary_row = QHBoxLayout()
        if not findings:
            ok_lbl = QLabel("\u2705  No issues found")
            ok_lbl.setStyleSheet(
                "background:#1a3d1a; color:#3fb950;"
                " padding:2px 10px; border-radius:4px; font-weight:600;"
            )
            summary_row.addWidget(ok_lbl)
        else:
            for label, count, sev_key in [
                (f"\u26d4  {n_err} Error{'s' if n_err   != 1 else ''}", n_err,  "Error"),
                (f"\u26a0\ufe0f  {n_warn} Warning{'s' if n_warn != 1 else ''}", n_warn, "Warning"),
                (f"\u2139\ufe0f  {n_info} Info",                              n_info, "Info"),
            ]:
                if count > 0:
                    lbl = QLabel(label)
                    bg, fg = SEV_COLORS[sev_key]
                    lbl.setStyleSheet(
                        f"background:{bg}; color:{fg};"
                        " padding:2px 10px; border-radius:4px;"
                        " font-weight:600; margin-right:4px;"
                    )
                    summary_row.addWidget(lbl)

        total_lbl = QLabel(
            f"  {len(findings)} finding{'s' if len(findings) != 1 else ''} total"
        )
        total_lbl.setStyleSheet("color:#8b949e;")
        summary_row.addWidget(total_lbl)
        summary_row.addStretch()
        summary_row.addWidget(QLabel("Filter:"))
        filter_cb = QComboBox()
        filter_cb.addItems(["Show all", "Errors only",
                            "Warnings only", "Info only"])
        summary_row.addWidget(filter_cb)
        lay.addLayout(summary_row)

        # Table
        COLS = ["Severity", "Check", "Entity", "Detail", "Fix Hint"]
        tbl = QTableWidget(0, len(COLS))
        tbl.setHorizontalHeaderLabels(COLS)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(False)
        tbl.setSortingEnabled(True)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setWordWrap(True)
        lay.addWidget(tbl, stretch=1)

        def _populate(show_filter: str = "Show all") -> None:
            visible = [
                f for f in findings
                if show_filter == "Show all"
                or (show_filter == "Errors only"   and f.sev == "Error")
                or (show_filter == "Warnings only" and f.sev == "Warning")
                or (show_filter == "Info only"     and f.sev == "Info")
            ]
            tbl.setSortingEnabled(False)
            tbl.setRowCount(len(visible))
            for row, f in enumerate(visible):
                bg, fg = SEV_COLORS.get(f.sev, ("#21262d", "#c9d1d9"))
                for col, val in enumerate(
                    [f.sev, f.check, f.entity, f.detail, f.hint]
                ):
                    it = QTableWidgetItem(val)
                    it.setFlags(
                        Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                    )
                    if col == 0:
                        it.setBackground(QColor(bg))
                        it.setForeground(QColor(fg))
                        it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    tbl.setItem(row, col, it)
            tbl.setSortingEnabled(True)
            tbl.resizeColumnsToContents()
            tbl.horizontalHeader().setStretchLastSection(True)

        _populate()
        filter_cb.currentTextChanged.connect(_populate)
        return w

    def _build_timing_tab(self) -> QWidget:
        """6th tab: per-message CAN bus-load estimation with visual gauge."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # ── Controls row ──────────────────────────────────────────────────
        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel("Baud Rate:"))
        baud_cb = QComboBox()
        baud_cb.addItems(list(BAUD_RATES.keys()))
        baud_cb.setCurrentText("500k")
        baud_cb.setFixedWidth(90)
        ctrl_row.addWidget(baud_cb)
        ctrl_row.addSpacing(16)

        total_lbl = QLabel("Total bus load:")
        total_lbl.setStyleSheet("color:#8b949e;")
        ctrl_row.addWidget(total_lbl)
        load_val_lbl = QLabel("—")
        load_val_lbl.setStyleSheet("font-weight:700; min-width:60px;")
        ctrl_row.addWidget(load_val_lbl)
        ctrl_row.addStretch()

        skipped_lbl = QLabel("")
        skipped_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
        ctrl_row.addWidget(skipped_lbl)
        lay.addLayout(ctrl_row)

        # ── Gauge bar ─────────────────────────────────────────────────────
        gauge = QProgressBar()
        gauge.setRange(0, 100)
        gauge.setValue(0)
        gauge.setFixedHeight(18)
        gauge.setTextVisible(True)
        gauge.setFormat("%p%")
        lay.addWidget(gauge)

        # ── Table ─────────────────────────────────────────────────────────
        COLS = ["Message", "Frame ID", "DLC", "Cycle (ms)", "Frame Bits", "Load %"]
        tbl = QTableWidget(0, len(COLS))
        tbl.setHorizontalHeaderLabels(COLS)
        tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        tbl.setAlternatingRowColors(False)
        tbl.setSortingEnabled(True)
        tbl.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(tbl, stretch=1)

        def _refresh(baud_key: str = "500k") -> None:
            baud = BAUD_RATES.get(baud_key, 500_000)
            records = compute_bus_load(self._db, baud)

            total_msgs = len(self._db.messages)
            skipped = total_msgs - len(records)
            skipped_lbl.setText(
                (f"({skipped} message{'s' if skipped != 1 else ''} skipped "
                 "\u2014 no cycle time)")
                if skipped else ""
            )

            total_load = sum(r["load_pct"] for r in records)
            load_val_lbl.setText(f"{total_load:.2f}%")

            clamped = min(int(total_load), 100)
            gauge.setValue(clamped)
            if total_load > 100:
                gauge.setStyleSheet("QProgressBar::chunk { background:#da3633; }")
            elif total_load > 70:
                gauge.setStyleSheet("QProgressBar::chunk { background:#d29922; }")
            else:
                gauge.setStyleSheet("QProgressBar::chunk { background:#238636; }")

            tbl.setSortingEnabled(False)
            tbl.setRowCount(len(records))
            for row, r in enumerate(records):
                lp = r["load_pct"]
                if lp > 70:
                    row_bg = QColor("#3d1a1a")
                elif lp > 30:
                    row_bg = QColor("#3d2e0a")
                else:
                    row_bg = QColor("#1a2d1a")

                vals = [
                    r["name"],
                    f"0x{r['frame_id']:X}",
                    str(r["dlc"]),
                    str(r["cycle_ms"]),
                    str(r["frame_bits"]),
                    f"{lp:.4f}%",
                ]
                for col, val in enumerate(vals):
                    it = QTableWidgetItem(val)
                    it.setFlags(
                        Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                    )
                    it.setBackground(row_bg)
                    tbl.setItem(row, col, it)
            tbl.setSortingEnabled(True)
            tbl.resizeColumnsToContents()
            tbl.horizontalHeader().setStretchLastSection(True)

        _refresh("500k")
        baud_cb.currentTextChanged.connect(_refresh)
        return w


    def _build_timeline_tab(self) -> QWidget:
        """7th tab: temporal bus heatmap — cyclic message transmission timeline."""
        return TemporalHeatmapWidget(self._db)


# ---------------------------------------------------------------------------
# Temporal Bus Heatmap Widget
# ---------------------------------------------------------------------------


class TemporalHeatmapWidget(QWidget):
    """Interactive timeline showing when each cyclic message fires.

    - X-axis: 0 → window_ms (selectable: 100/500/1000/5000 ms)
    - Each row: one cyclic message; vertical bars at t=0, cycle_time, 2×, …
    - Bar height scales with DLC; unique colour per message
    - Overlap detection: two messages in the same ms bucket → red indicator
    - Tooltip on hover: name, frame_id, cycle_time, DLC, sender
    """

    _LABEL_W = 140      # Fixed-width label column (px)
    _ROW_H   = 22       # Pixels per message row
    _BAR_W   = 5        # Width of each transmission bar (px)
    _H_PAD   = 6        # Vertical padding inside a row
    _ZOOM_OPTIONS = [100, 500, 1000, 5000]   # window sizes in ms

    # 10-colour palette — matches ViewerDialog._CELL_COLORS accents
    _PALETTE = [
        "#90ee90", "#7ec8e3", "#ee9090", "#c87ee3",
        "#e3c87e", "#7ee3e3", "#d07ee3", "#7ee3a0",
        "#e3e37e", "#7ee3c8",
    ]

    def __init__(self, db, parent=None):
        super().__init__(parent)
        self._db = db
        self._window_ms = 500

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Controls row ──────────────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Window:"))
        self._zoom_cb = QComboBox()
        for v in self._ZOOM_OPTIONS:
            self._zoom_cb.addItem(f"{v} ms", v)
        self._zoom_cb.setCurrentIndex(1)   # 500 ms default
        self._zoom_cb.setFixedWidth(100)
        self._zoom_cb.currentIndexChanged.connect(self._on_zoom_changed)
        ctrl.addWidget(self._zoom_cb)
        ctrl.addSpacing(12)
        self._info_lbl = QLabel()
        self._info_lbl.setStyleSheet("color:#8b949e; font-size:11px;")
        ctrl.addWidget(self._info_lbl)
        ctrl.addStretch()
        root.addLayout(ctrl)

        # ── Two-panel layout: fixed label column + scrollable scene ───────
        h_split = QHBoxLayout()
        h_split.setSpacing(0)

        # Left: label panel
        self._label_scene = QGraphicsScene(self)
        self._label_view  = QGraphicsView(self._label_scene)
        self._label_view.setFixedWidth(self._LABEL_W)
        self._label_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._label_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._label_view.setStyleSheet("background:#0d1117; border:none; border-right:1px solid #30363d;")
        h_split.addWidget(self._label_view)

        # Right: main timeline scene
        self._scene = QGraphicsScene(self)
        self._view  = QGraphicsView(self._scene)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._view.setStyleSheet("background:#0d1117; border:none;")
        self._view.setMouseTracking(True)
        self._view.viewport().installEventFilter(self)
        h_split.addWidget(self._view, stretch=1)

        # Sync vertical scrollbars
        self._view.verticalScrollBar().valueChanged.connect(
            self._label_view.verticalScrollBar().setValue
        )

        root.addLayout(h_split, stretch=1)

        self._rebuild()

    # ── Helpers ───────────────────────────────────────────────────────────

    def _msg_color(self, idx: int) -> str:
        return self._PALETTE[idx % len(self._PALETTE)]

    def _cyclic_messages(self):
        """Return sorted list of (index, message) for cyclic messages."""
        result = []
        for m in sorted(self._db.messages, key=lambda x: x.name):
            ct = getattr(m, "cycle_time", None) or 0
            if ct > 0:
                result.append(m)
        return result

    # ── Rebuild ───────────────────────────────────────────────────────────

    def _rebuild(self) -> None:
        self._scene.clear()
        self._label_scene.clear()

        msgs = self._cyclic_messages()
        if not msgs:
            no_msg = self._scene.addText("No cyclic messages found in this DBC file.")
            no_msg.setDefaultTextColor(Qt.GlobalColor.gray)
            no_msg.setPos(20, 20)
            self._info_lbl.setText("")
            return

        win = self._window_ms
        row_h = self._ROW_H
        bar_w = self._BAR_W
        h_pad = self._H_PAD
        label_w = self._LABEL_W - 8   # slight inner margin

        # Width of the graphics scene in pixels — 1px per ms, min 600
        scene_w = max(win, 600)
        scene_h = len(msgs) * row_h

        self._scene.setSceneRect(0, 0, scene_w, scene_h)
        self._label_scene.setSceneRect(0, 0, label_w, scene_h)

        # ── Overlap detection: bucket ms → list of (row, name) ────────────
        buckets: dict[int, list] = {}
        for row_idx, m in enumerate(msgs):
            ct = int(round(getattr(m, "cycle_time", 0) or 0))
            if ct <= 0:
                continue
            t = 0
            while t <= win:
                buckets.setdefault(t, []).append(row_idx)
                t += ct

        overlap_rows: set[tuple[int, int]] = set()   # (row_idx, t_ms)
        for t_ms, rows in buckets.items():
            if len(rows) > 1:
                for r in rows:
                    overlap_rows.add((r, t_ms))

        total_overlaps = len({t for t, rs in buckets.items() if len(rs) > 1})

        # ── Draw rows ────────────────────────────────────────────────────
        from PySide6.QtGui import QColor, QFont, QPen, QBrush  # noqa: PLC0415

        axis_pen   = QPen(QColor("#30363d"))
        axis_pen.setWidth(1)

        for row_idx, m in enumerate(msgs):
            y0 = row_idx * row_h
            color_hex = self._msg_color(row_idx)
            color = QColor(color_hex)
            ct_ms = int(round(getattr(m, "cycle_time", 0) or 0))
            dlc = getattr(m, "length", 1) or 1           # bytes
            bar_h = min(max(dlc * 2 + 2, 4), row_h - h_pad * 2)
            bar_y = y0 + (row_h - bar_h) / 2
            sender = ", ".join(m.senders) if m.senders else "—"

            # Row separator
            sep = self._scene.addLine(0, y0 + row_h - 1, scene_w, y0 + row_h - 1, axis_pen)
            sep.setZValue(0)

            # Label (left panel)
            lbl_sep = self._label_scene.addLine(0, y0 + row_h - 1, label_w, y0 + row_h - 1, axis_pen)
            lbl_sep.setZValue(0)
            lbl_txt = self._label_scene.addText(m.name)
            lbl_txt.setDefaultTextColor(color)
            fnt = QFont("Consolas", 8)
            lbl_txt.setFont(fnt)
            lbl_txt.setPos(4, y0 + (row_h - 14) / 2)
            # Clip text width
            if lbl_txt.boundingRect().width() > label_w - 6:
                lbl_txt.setTextWidth(label_w - 6)

            if ct_ms <= 0:
                continue

            # ── Draw transmission bars ───────────────────────────────────
            t = 0
            brush_normal  = QBrush(color)
            brush_overlap = QBrush(QColor("#da3633"))
            pen_none = QPen(Qt.PenStyle.NoPen)

            while t <= win:
                x = t   # 1 px per ms
                is_overlap = (row_idx, t) in overlap_rows
                rect_item = self._scene.addRect(
                    QRectF(x, bar_y, bar_w, bar_h),
                    pen_none,
                    brush_overlap if is_overlap else brush_normal,
                )
                rect_item.setZValue(1)

                # Tooltip data stored via setData
                tip = (
                    f"<b>{m.name}</b><br/>"
                    f"Frame ID: 0x{m.frame_id:X}<br/>"
                    f"Cycle: {ct_ms} ms<br/>"
                    f"DLC: {dlc} bytes<br/>"
                    f"Sender: {sender}<br/>"
                    f"t = {t} ms"
                    + ("<br/><span style='color:#da3633'>⚠ Overlap!</span>" if is_overlap else "")
                )
                rect_item.setToolTip(tip)
                rect_item.setAcceptHoverEvents(True)

                t += ct_ms

        # ── X-axis tick labels ────────────────────────────────────────────
        tick_pen = QPen(QColor("#58a6ff"))
        tick_font = QFont("Consolas", 7)
        tick_interval = win // 10 or 1
        for t in range(0, win + 1, tick_interval):
            tick_lbl = self._scene.addText(f"{t}")
            tick_lbl.setDefaultTextColor(QColor("#58a6ff"))
            tick_lbl.setFont(tick_font)
            tick_lbl.setPos(t, scene_h + 2)
            tick_lbl.setZValue(2)

        # Extend scene height to accommodate tick labels
        self._scene.setSceneRect(0, 0, scene_w, scene_h + 16)

        # ── Info label ────────────────────────────────────────────────────
        skip = len(self._db.messages) - len(msgs)
        parts = [f"{len(msgs)} cyclic message(s)"]
        if skip:
            parts.append(f"{skip} skipped (no cycle time)")
        if total_overlaps:
            parts.append(f"⚠ {total_overlaps} overlap slot(s) (red)")
        self._info_lbl.setText("  ·  ".join(parts))

    # ── Zoom ─────────────────────────────────────────────────────────────

    def _on_zoom_changed(self, _idx: int) -> None:
        self._window_ms = self._zoom_cb.currentData()
        self._rebuild()

    # ── Event filter for tooltip support on QGraphicsView ────────────────

    def eventFilter(self, obj, event):   # noqa: N802
        from PySide6.QtCore import QEvent  # noqa: PLC0415
        if obj is self._view.viewport() and event.type() == QEvent.Type.ToolTip:
            pos = event.pos()
            scene_pos = self._view.mapToScene(pos)
            item = self._scene.itemAt(scene_pos, self._view.transform())
            if item and item.toolTip():
                QToolTip.showText(event.globalPos(), item.toolTip(), self._view)
                return True
        return super().eventFilter(obj, event)


# ---------------------------------------------------------------------------
# 3-D Bus Simulation widget  (QWebEngineView + Three.js r128)
# ---------------------------------------------------------------------------


class ThreeSimWidget(QWidget):
    """Interactive 3-D CAN bus animation (Three.js inside QWebEngineView).

    X = time (ms, scrolling window)
    Y = message row (sorted by frame_id)
    DLC encoded as bar width
    """

    _FALLBACK_HTML = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        "<style>body{background:#0d1117;display:flex;align-items:center;"
        "justify-content:center;height:100vh;color:#58a6ff;"
        "font-family:Consolas}</style></head>"
        "<body><h2>resources/3d_sim.html not found \u2014 "
        "re-install dbcdiff</h2></body></html>"
    )

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db               = None
        self._entries: list    = []
        self._sim_mode: str    = "viewer"

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        if _WEB_ENGINE_OK and _QWebEngineView is not None:
            self._view = _QWebEngineView()
            root.addWidget(self._view)
            self._view.setHtml(self._idle_html())
        else:
            self._view = None
            msg = QLabel(
                "<div style='text-align:center'>"
                "<h2 style='color:#58a6ff'>\U0001f5b2\ufe0f\u00a0 3D Bus Sim</h2>"
                "<p style='color:#8b949e;margin-top:8px'>"
                "PySide6-WebEngine is not installed.</p>"
                "<code style='background:#161b22;border:1px solid #30363d;"
                "padding:6px 14px;border-radius:4px;display:inline-block;"
                "margin-top:10px'>pip install PySide6-WebEngine</code>"
                "<p style='color:#8b949e;margin-top:8px;font-size:11px'>"
                "Then restart dbcdiff.</p></div>"
            )
            msg.setTextFormat(Qt.TextFormat.RichText)
            msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg.setStyleSheet("background:#0d1117;padding:40px;")
            root.addWidget(msg)

    def load(self, db, entries: list | None = None, mode: str = "viewer") -> None:
        """Populate the 3-D scene from *db* (cantools Database) and diff *entries*."""
        if self._view is None:
            return
        self._db       = db
        self._entries  = list(entries or [])
        self._sim_mode = mode
        self._refresh()

    def _refresh(self) -> None:
        if self._view is None or self._db is None:
            return
        import json as _j
        html = self._get_template().replace(
            "/*INJECT_DATA*/null/*END_INJECT*/",
            _j.dumps(self._build_data(), separators=(",", ":")),
        )
        self._view.setHtml(html)

    def _build_data(self) -> dict:
        _rank = {"breaking": 4, "functional": 3, "added": 2, "metadata": 1}
        sev: dict[str, str] = {}
        if self._sim_mode == "diff":
            for e in self._entries:
                parts = (getattr(e, "path", "") or "").split(".")
                if len(parts) >= 2 and parts[0] == "messages":
                    nm = parts[1]
                    sr = getattr(e.severity, "name", "METADATA").lower()
                    if getattr(e, "kind", "") in ("extra", "missing"):
                        sr = "added"
                    if _rank.get(sr, 0) > _rank.get(sev.get(nm, ""), 0):
                        sev[nm] = sr
        msgs = []
        for m in sorted(self._db.messages, key=lambda x: x.frame_id):
            msgs.append({
                "name":         m.name,
                "frame_id":     m.frame_id,
                "dlc":          m.length,
                "cycle_time":   m.cycle_time or 0,
                "senders":      list(m.senders or []),
                "comment":      m.comment or "",
                "signal_count": len(m.signals),
                "signals": [
                    {
                        "name":      s.name,
                        "start_bit": s.start,
                        "length":    s.length,
                        "is_signed": bool(getattr(s, "is_signed", False)),
                    }
                    for s in sorted(m.signals, key=lambda s: s.start)
                ],
                "severity": (sev.get(m.name, "unchanged")
                             if self._sim_mode == "diff" else None),
            })
        return {"mode": self._sim_mode, "messages": msgs}

    @staticmethod
    def _get_template() -> str:
        import sys as _sys

        # 1. File-adjacent dir — works for dev installs and installed wheels.
        p = Path(__file__).parent / "resources" / "3d_sim.html"
        if p.exists():
            return p.read_text(encoding="utf-8")

        # 2. PyInstaller onefile: bundle is extracted to sys._MEIPASS.
        #    --add-data=dbcdiff:dbcdiff puts everything under _MEIPASS/dbcdiff/
        if getattr(_sys, "frozen", False) and hasattr(_sys, "_MEIPASS"):
            p2 = Path(_sys._MEIPASS) / "dbcdiff" / "resources" / "3d_sim.html"
            if p2.exists():
                return p2.read_text(encoding="utf-8")

        # 3. importlib.resources — works for any importable package,
        #    including zip-based imports and editable installs.
        try:
            import importlib.resources as _ir
            ref = _ir.files("dbcdiff") / "resources" / "3d_sim.html"
            return ref.read_text(encoding="utf-8")
        except Exception:
            pass

        return ThreeSimWidget._FALLBACK_HTML

    @staticmethod
    def _idle_html() -> str:
        return (
            "<!DOCTYPE html><html><head><meta charset='utf-8'>"
            "<style>*{margin:0;padding:0}body{background:#0d1117;"
            "display:flex;flex-direction:column;align-items:center;"
            "justify-content:center;height:100vh;color:#c9d1d9;"
            "font-family:Consolas,monospace;gap:14px}"
            "h2{color:#58a6ff;font-size:18px}"
            "p{color:#8b949e;font-size:13px;text-align:center}</style>"
            "</head><body>"
            "<div style='font-size:48px'>\U0001f5b2\ufe0f</div>"
            "<h2>3D Bus Simulation</h2>"
            "<p>Run <b>Compare</b> or open <b>Visualize</b> mode<br>"
            "to populate the 3D scene.</p>"
            "</body></html>"
        )


# ---------------------------------------------------------------------------
# Decoder tab — live CAN frame decoder
# ---------------------------------------------------------------------------


class DecoderTab(QWidget):
    """Live CAN frame decoder — hex bytes in, signal physical values out."""

    _COLS = ["Signal", "Raw (hex)", "Physical", "Unit", "Min", "Max", "In Range?"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._db = None
        self._msg = None
        self._guard = False
        self._build_ui()

    def set_database(self, db) -> None:
        """Populate the message dropdown from *db* (a cantools Database)."""
        self._db = db
        self._msg_combo.blockSignals(True)
        self._msg_combo.clear()
        self._msg_combo.blockSignals(False)
        if db is None:
            self._clear_table()
            return
        for msg in sorted(db.messages, key=lambda m: m.name):
            self._msg_combo.addItem(f"0x{msg.frame_id:03X}  {msg.name}", userData=msg)
        if self._msg_combo.count():
            self._on_msg_changed(0)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        # ── message selector ──────────────────────────────────────────────
        top = QHBoxLayout()
        top.addWidget(QLabel("Message:"))
        self._msg_combo = QComboBox()
        self._msg_combo.setMinimumWidth(300)
        self._msg_combo.currentIndexChanged.connect(self._on_msg_changed)
        top.addWidget(self._msg_combo, stretch=1)
        top.addStretch()
        root.addLayout(top)

        # ── 8 byte inputs with per-column sliders ──────────────────────────
        byte_row = QHBoxLayout()
        byte_row.setSpacing(6)
        self._byte_edits: list[QLineEdit] = []
        self._byte_sliders: list[QSlider] = []
        for i in range(8):
            col_wrap = QVBoxLayout()
            col_wrap.setSpacing(2)
            lbl = QLabel(f"B{i}")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size:10px; color:#8b949e;")
            col_wrap.addWidget(lbl)
            edit = QLineEdit("00")
            edit.setMaxLength(2)
            edit.setFixedWidth(46)
            edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            edit.textChanged.connect(self._on_byte_changed)
            col_wrap.addWidget(edit)
            self._byte_edits.append(edit)
            slider = QSlider(Qt.Orientation.Vertical)
            slider.setRange(0, 255)
            slider.setVisible(False)
            slider.setFixedHeight(70)
            slider.valueChanged.connect(self._make_slider_handler(i))
            col_wrap.addWidget(slider, alignment=Qt.AlignmentFlag.AlignHCenter)
            self._byte_sliders.append(slider)
            byte_row.addLayout(col_wrap)
        byte_row.addStretch()
        root.addLayout(byte_row)

        # ── bit grid ──────────────────────────────────────────────────────
        grid_lbl = QLabel("Bit Layout")
        grid_lbl.setStyleSheet("font-weight:600; color:#c9d1d9; font-size:12px;")
        root.addWidget(grid_lbl)
        self._bit_grid = BitGridWidget()
        root.addWidget(self._bit_grid)

        # ── decoded signal table ───────────────────────────────────────────
        self._table = QTableWidget(0, len(self._COLS))
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.verticalHeader().setVisible(False)
        root.addWidget(self._table, stretch=1)

        # wire focus → show matching slider
        for i, edit in enumerate(self._byte_edits):
            edit.focusInEvent = self._make_focus_in(i, edit.focusInEvent)

    # ── helpers ───────────────────────────────────────────────────────────

    def _make_focus_in(self, idx: int, original):
        def handler(event):
            for j, sl in enumerate(self._byte_sliders):
                sl.setVisible(j == idx)
            original(event)
        return handler

    def _make_slider_handler(self, idx: int):
        def handler(val: int) -> None:
            if not self._guard:
                self._guard = True
                self._byte_edits[idx].setText(f"{val:02X}")
                self._guard = False
        return handler

    def _on_msg_changed(self, idx: int) -> None:
        self._msg = self._msg_combo.itemData(idx)
        self._bit_grid.load_message(self._msg)
        self._clear_table()
        self._decode()

    def _on_byte_changed(self) -> None:
        if not self._guard:
            self._decode()

    def _get_bytes(self) -> bytes:
        raw: list[int] = []
        for edit in self._byte_edits:
            text = edit.text().strip() or "00"
            try:
                raw.append(int(text, 16) & 0xFF)
            except ValueError:
                raw.append(0)
        return bytes(raw)

    def _decode(self) -> None:
        if self._msg is None:
            return
        length = self._msg.length
        data = self._get_bytes()[:length]
        data = data + bytes(length - len(data))
        try:
            decoded = self._msg.decode(data, decode_choices=False)
        except Exception:
            return
        self._refresh_table(decoded)
        self._bit_grid.set_bytes(data)

    def _refresh_table(self, decoded: dict) -> None:
        self._table.setSortingEnabled(False)
        sigs = sorted(self._msg.signals, key=lambda s: s.name)
        self._table.setRowCount(len(sigs))
        for row, sig in enumerate(sigs):
            phys = decoded.get(sig.name)
            raw_int = None
            if isinstance(phys, (int, float)):
                scale = float(getattr(sig, "scale", 1) or 1)
                offset = float(getattr(sig, "offset", 0) or 0)
                if scale:
                    raw_int = int(round((float(phys) - offset) / scale))
            raw_str = f"0x{raw_int:X}" if raw_int is not None else "\u2014"
            phys_str = (
                f"{phys:.4g}" if isinstance(phys, (int, float))
                else (str(phys) if phys is not None else "\u2014")
            )
            unit_str = getattr(sig, "unit", "") or ""
            min_val = sig.minimum
            max_val = sig.maximum
            min_str = str(min_val) if min_val is not None else "\u2014"
            max_str = str(max_val) if max_val is not None else "\u2014"
            in_range = True
            if isinstance(phys, (int, float)):
                if min_val is not None and phys < min_val:
                    in_range = False
                if max_val is not None and phys > max_val:
                    in_range = False
            range_text = "\u2713" if in_range else "\u2717"
            range_bg = "#1a3a1a" if in_range else "#3a1a1a"
            range_fg = "#2ea043" if in_range else "#ff453a"
            for col, val in enumerate(
                [sig.name, raw_str, phys_str, unit_str, min_str, max_str, range_text]
            ):
                it = QTableWidgetItem(val)
                it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if col == 6:
                    it.setBackground(QColor(range_bg))
                    it.setForeground(QColor(range_fg))
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self._table.setItem(row, col, it)
        self._table.setSortingEnabled(True)
        self._table.resizeColumnsToContents()

    def _clear_table(self) -> None:
        self._table.setRowCount(0)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("dbcdiff")
        self.setMinimumSize(1380, 860)
        self._entries: list[DiffEntry] = []
        self._consistency_records: list[dict] = []
        self._active_severities = {
            Severity.BREAKING.name,
            Severity.FUNCTIONAL.name,
            Severity.METADATA.name,
        }
        self._current_view_idx = 0
        self._db_a = None
        self._db_b = None

        central = QWidget()
        self.setCentralWidget(central)
        shell = QHBoxLayout(central)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self._drop_a = DBCDropZone("Base DBC")
        self._drop_b = DBCDropZone("Compare DBC")
        self._drop_a.file_chosen.connect(self._on_file_chosen)
        self._drop_b.file_chosen.connect(self._on_file_chosen)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 18, 18, 18)
        side.setSpacing(14)

        logo = QFrame()
        logo.setObjectName("logoBlock")
        logo_layout = QVBoxLayout(logo)
        logo_layout.setContentsMargins(16, 16, 16, 16)
        logo_layout.setSpacing(8)
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        mark = QLabel("db")
        mark.setObjectName("logoMark")
        brand_col = QVBoxLayout()
        brand_col.setSpacing(2)
        title = QLabel("dbcdiff")
        title.setObjectName("logoTitle")
        subtitle = QLabel("CAN database diff")
        subtitle.setObjectName("logoSubtitle")
        version = QLabel(f"v{__version__}")
        version.setObjectName("logoVersion")
        brand_col.addWidget(title)
        brand_col.addWidget(subtitle)
        brand_row.addWidget(mark)
        brand_row.addLayout(brand_col, 1)
        brand_row.addWidget(version, alignment=Qt.AlignmentFlag.AlignTop)
        logo_layout.addLayout(brand_row)
        side.addWidget(logo)

        mode_label = QLabel("Mode")
        mode_label.setObjectName("sectionLabel")
        side.addWidget(mode_label)
        self._mode_buttons: dict[str, QPushButton] = {}
        self._mode_stack = QStackedWidget()
        for idx, (key, text) in enumerate([
            ("compare", "Compare"),
            ("visualize", "Visualize"),
            ("sim", "3D Sim"),
            ("decode", "Decode"),
        ]):
            btn = QPushButton(text)
            btn.setObjectName("modeButton")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, mode=key: self._set_mode(mode))
            self._mode_buttons[key] = btn
            side.addWidget(btn)
        self._mode_buttons["compare"].setChecked(True)

        views_label = QLabel("Views")
        views_label.setObjectName("sectionLabel")
        side.addWidget(views_label)
        self._view_buttons: list[QPushButton] = []
        for idx, (name, dot_color, _) in enumerate(_VIEWS):
            pix = QPixmap(8, 8)
            pix.fill(Qt.GlobalColor.transparent)
            p = QPainter(pix)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QColor(dot_color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(0, 0, 8, 8)
            p.end()
            btn = QPushButton(name)
            btn.setObjectName("viewButton")
            btn.setIcon(QIcon(pix))
            btn.setIconSize(QSize(8, 8))
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, view_idx=idx: self._set_view(view_idx))
            self._view_buttons.append(btn)
            side.addWidget(btn)
        if self._view_buttons:
            self._view_buttons[0].setChecked(True)

        side.addStretch()

        load_base_btn = QPushButton("Load Base DBC")
        load_base_btn.setObjectName("ghostButton")
        load_base_btn.clicked.connect(self._drop_a._browse)
        side.addWidget(load_base_btn)

        load_compare_btn = QPushButton("Load Compare DBC")
        load_compare_btn.setObjectName("ghostButton")
        load_compare_btn.clicked.connect(self._drop_b._browse)
        side.addWidget(load_compare_btn)

        self._compare_btn = QPushButton("Compare Files")
        self._compare_btn.setObjectName("compareCta")
        self._compare_btn.setEnabled(False)
        self._compare_btn.clicked.connect(self._on_compare)
        side.addWidget(self._compare_btn)

        pills_label = QLabel("Files")
        pills_label.setObjectName("sectionLabel")
        side.addWidget(pills_label)
        self._base_file_pill, self._base_file_text = self._create_file_pill("File A", "Choose a source DBC", "NEW")
        self._compare_file_pill, self._compare_file_text = self._create_file_pill("File B", "Choose a target DBC", "OLD")
        side.addWidget(self._base_file_pill)
        side.addWidget(self._compare_file_pill)

        shell.addWidget(sidebar)

        main_wrap = QWidget()
        main = QVBoxLayout(main_wrap)
        main.setContentsMargins(18, 18, 18, 10)
        main.setSpacing(14)

        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(18, 12, 18, 12)
        topbar_layout.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        self._page_title = QLabel("Diff Report")
        self._page_title.setObjectName("pageTitle")
        self._page_subtitle = QLabel("Choose two DBC files to compare messages, signals, nodes, and consistency rules.")
        self._page_subtitle.setObjectName("pageSubtitle")
        title_block.addWidget(self._page_title)
        title_block.addWidget(self._page_subtitle)
        topbar_layout.addLayout(title_block)
        topbar_layout.addStretch()

        self._sev_chips: dict[str, QLabel] = {}
        for sev_name, label, icon_emoji, obj_name in [
            (Severity.BREAKING.name,   "Breaking",   "🔴", "chipBreaking"),
            (Severity.FUNCTIONAL.name, "Functional", "🟠", "chipFunctional"),
            ("added",                  "Added",       "🟢", "chipAdded"),
            (Severity.METADATA.name,   "Metadata",    "🔵", "chipMetadata"),
        ]:
            chip = QLabel(f"{icon_emoji} 0 {label}")
            chip.setObjectName(obj_name)
            self._sev_chips[sev_name] = chip
            topbar_layout.addWidget(chip)

        for label, handler, obj_name in [
            ("Export HTML", self._export_html, "exportButton"),
            ("Export CSV",  self._export_csv,  "exportButtonPrimary"),
        ]:
            btn = QPushButton(label)
            btn.setObjectName(obj_name)
            btn.clicked.connect(handler)
            topbar_layout.addWidget(btn)
        main.addWidget(topbar)

        summary_card = QFrame()
        summary_card.setObjectName("summaryWrap")
        summary_layout = QHBoxLayout(summary_card)
        summary_layout.setContentsMargins(12, 12, 12, 12)
        self._summary = SummaryBadge()
        summary_layout.addWidget(self._summary)
        main.addWidget(summary_card)

        filter_bar = QFrame()
        filter_bar.setObjectName("filterBar")
        filter_row = QHBoxLayout(filter_bar)
        filter_row.setContentsMargins(14, 12, 14, 12)
        filter_row.setSpacing(10)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search path, detail, values…")
        self._search_input.textChanged.connect(self._refresh_all_tabs)
        filter_row.addWidget(self._search_input, 2)

        self._protocol_combo = QComboBox()
        self._protocol_combo.setFixedWidth(120)
        self._protocol_combo.addItem("(all)")
        self._protocol_combo.currentTextChanged.connect(self._refresh_all_tabs)
        filter_row.addWidget(self._protocol_combo)

        self._ecu_combo = QComboBox()
        self._ecu_combo.setFixedWidth(140)
        self._ecu_combo.addItem("(all)")
        self._ecu_combo.currentTextChanged.connect(self._refresh_all_tabs)
        filter_row.addWidget(self._ecu_combo)

        self._msg_type_combo = QComboBox()
        self._msg_type_combo.setFixedWidth(150)
        self._msg_type_combo.addItem("(all)")
        self._msg_type_combo.currentTextChanged.connect(self._on_msg_type_changed)
        filter_row.addWidget(self._msg_type_combo)

        self._sort_combo = QComboBox()
        self._sort_combo.setFixedWidth(160)
        for label in [
            "Severity → Path",
            "Kind → Path",
            "Entity → Path",
            "Path A→Z",
            "Path Z→A",
        ]:
            self._sort_combo.addItem(label)
        self._sort_combo.currentTextChanged.connect(self._refresh_all_tabs)
        filter_row.addWidget(self._sort_combo)
        main.addWidget(filter_bar)

        compare_page = QWidget()
        compare_vbox = QVBoxLayout(compare_page)
        compare_vbox.setContentsMargins(0, 0, 0, 0)
        compare_vbox.setSpacing(14)

        self._drop_row_widget = QWidget()
        drop_row = self._drop_row_widget
        drop_hl = QHBoxLayout(drop_row)
        drop_hl.setContentsMargins(0, 0, 0, 0)
        drop_hl.setSpacing(14)
        drop_hl.addWidget(self._drop_a)
        drop_hl.addWidget(self._drop_b)
        compare_vbox.addWidget(drop_row, 0)

        results_area = QWidget()
        compare_layout = QHBoxLayout(results_area)
        compare_layout.setContentsMargins(0, 0, 0, 0)
        compare_layout.setSpacing(14)

        table_panel = QFrame()
        table_panel.setObjectName("tablePanel")
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(10, 10, 10, 10)
        table_layout.setSpacing(10)

        self._view_stack = QStackedWidget()
        self._view_tables: list[ResultsTable] = []
        for name, dot_color, _ in _VIEWS:
            tbl = ResultsTable()
            self._view_tables.append(tbl)
            self._view_stack.addWidget(tbl)

        _NODES_IDX = next(i for i, (n, _, _) in enumerate(_VIEWS) if "Nodes" in n)
        _node_diff_tbl = self._view_tables[_NODES_IDX]
        self._node_inv_tbl = QTableWidget(0, 5)
        self._node_inv_tbl.setHorizontalHeaderLabels(
            ["Name", "Comment", "TX Messages", "RX Signals", "Status"]
        )
        self._node_inv_tbl.horizontalHeader().setStretchLastSection(True)
        self._node_inv_tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._node_inv_tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._node_inv_tbl.setAlternatingRowColors(True)
        self._node_stack = QStackedWidget()
        self._node_stack.addWidget(_node_diff_tbl)
        self._node_stack.addWidget(self._node_inv_tbl)
        self._view_stack.removeWidget(_node_diff_tbl)
        self._view_stack.insertWidget(_NODES_IDX, self._node_stack)

        for _ti, _t in enumerate(self._view_tables):
            _t.currentItemChanged.connect(
                lambda cur, prev, ti=_ti: self._on_row_selected(ti)
            )

        table_layout.addWidget(self._view_stack)
        compare_layout.addWidget(table_panel, 1)

        self._detail = _DetailPanel()
        compare_layout.addWidget(self._detail)
        compare_vbox.addWidget(results_area, 1)

        self._mode_stack.addWidget(compare_page)
        self._mode_stack.addWidget(self._build_mode_page(
            "Visualize One DBC",
            "Open the structure viewer for the currently loaded base or compare file.",
            "Open Viewer",
            self._on_visualize,
        ))
        self._three_sim = ThreeSimWidget()
        self._mode_stack.addWidget(self._three_sim)
        self._decoder_tab = DecoderTab()
        self._mode_stack.addWidget(self._decoder_tab)  # index 3
        main.addWidget(self._mode_stack, 1)

        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — drop two DBC files to compare")

        self._thread: Optional[QThread] = None
        self._worker: Optional[_Worker] = None
        self._update_sev_chips()
        self._refresh_header_state()
        shell.addWidget(main_wrap, 1)

    def _create_file_pill(self, title: str, text: str, badge_text: str) -> tuple[QFrame, QLabel]:
        frame = QFrame()
        frame.setObjectName("filePill")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        cap = QLabel(title)
        cap.setObjectName("pillCaption")
        badge = QLabel(badge_text)
        badge.setObjectName(f"filePillBadge{badge_text.capitalize()}")
        value = QLabel(text)
        value.setWordWrap(True)
        value.setObjectName("filePillValue")
        row.addWidget(cap)
        row.addStretch()
        row.addWidget(badge)
        layout.addLayout(row)
        layout.addWidget(value)
        return frame, value

    def _build_mode_page(self, title: str, copy: str, cta: str, slot) -> QWidget:
        page = QFrame()
        page.setObjectName("modePageCard")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        lead = QLabel(title)
        lead.setObjectName("pageTitle")
        text = QLabel(copy)
        text.setWordWrap(True)
        text.setObjectName("modeCopy")
        btn = QPushButton(cta)
        btn.setObjectName("compareCta")
        btn.clicked.connect(slot)
        layout.addStretch()
        layout.addWidget(lead)
        layout.addWidget(text)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        return page

    def _set_mode(self, mode: str) -> None:
        mode_map = {"compare": 0, "visualize": 1, "sim": 2, "decode": 3}
        for key, btn in self._mode_buttons.items():
            btn.setChecked(key == mode)
        self._mode_stack.setCurrentIndex(mode_map[mode])
        self._refresh_header_state()

    def _set_view(self, view_idx: int) -> None:
        self._current_view_idx = view_idx
        for idx, btn in enumerate(self._view_buttons):
            btn.setChecked(idx == view_idx)
        self._view_stack.setCurrentIndex(view_idx)
        self._refresh_table()

    def _on_file_chosen(self, _path: str):
        # New file selected — clear old results and re-show drop zones
        self._entries = []
        self._db_a = None
        self._db_b = None
        self._drop_row_widget.setVisible(True)
        ready = self._drop_a.path and self._drop_b.path
        self._compare_btn.setEnabled(bool(ready))
        self._base_file_text.setText(Path(self._drop_a.path).name if self._drop_a.path else "Choose a source DBC")
        self._compare_file_text.setText(Path(self._drop_b.path).name if self._drop_b.path else "Choose a target DBC")
        self._refresh_header_state()
        if ready:
            self._status.showMessage(f"Ready: {Path(self._drop_a.path).name}  ↔  {Path(self._drop_b.path).name}")

    # -----------------------------------------------------------------------
    # Compare
    # -----------------------------------------------------------------------

    def _on_compare(self):
        if not self._drop_a.path or not self._drop_b.path:
            return
        self._set_mode("compare")  # ensure compare page is active
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
        self._drop_row_widget.setVisible(False)  # collapse drop zones; results get full height
        self._consistency_records = self._build_consistency_records(db_a, db_b)
        self._detail.set_databases(db_a, db_b)
        self._decoder_tab.set_database(db_b or db_a)
        try:
            self._three_sim.load(db_b or db_a, entries, "diff")
        except Exception:  # pylint: disable=broad-except
            import traceback as _tb; _tb.print_exc()
        self._compare_btn.setEnabled(True)
        self._summary.update(entries)
        self._update_sev_chips()
        self._refresh_all_tabs()
        self._refresh_header_state(compared=True)
        worst = max((e.severity for e in entries), default=None)
        if entries:
            worst_label = _sev_display(worst) if worst else "None"
            self._status.showMessage(
                f"✅  {len(entries)} difference(s) found  •  Worst severity: {worst_label}"
            )
        else:
            self._status.showMessage("✅  No differences — files are identical")
        self._update_msg_type_list()
        self._update_protocol_list()
        self._update_ecu_node_list()

    def _on_compare_error(self, msg: str):
        self._compare_btn.setEnabled(True)
        self._drop_row_widget.setVisible(True)  # restore drop zones on error
        self._refresh_header_state()
        self._status.showMessage(f"❌  Error: {msg}")
        QMessageBox.critical(self, "Compare Error", msg)

    def _populate_node_inventory(self, db_a) -> None:
        """Fill the static node inventory table (shown when no node diffs exist)."""
        tbl = self._node_inv_tbl
        tbl.clearContents()
        tbl.setRowCount(0)

        if db_a is None:
            return

        nodes = sorted(db_a.nodes or [], key=lambda n: n.name)
        node_tx: dict[str, list[str]] = {}
        for msg in db_a.messages:
            for sender in (msg.senders or []):
                node_tx.setdefault(sender, []).append(msg.name)
        node_rx: dict[str, int] = {}
        for msg in db_a.messages:
            for sig in msg.signals:
                for recv in (sig.receivers or []):
                    node_rx[recv] = node_rx.get(recv, 0) + 1
        tbl.setRowCount(len(nodes))
        for row, node in enumerate(nodes):
            for col, val in enumerate([
                node.name,
                node.comment or "—",
                str(len(node_tx.get(node.name, []))),
                str(node_rx.get(node.name, 0)),
                "Same in both files",
            ]):
                it = QTableWidgetItem(val)
                it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                if col >= 2:
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                tbl.setItem(row, col, it)
        tbl.resizeColumnsToContents()

    def _on_visualize(self) -> None:
        path = self._drop_b.path or self._drop_a.path
        if not path:
            return
        try:
            db = cantools.database.load_file(path)
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "Load Error", str(exc))
            return
        try:
            self._three_sim.load(db, [], "viewer")
        except Exception:  # pylint: disable=broad-except
            import traceback as _tb; _tb.print_exc()
        dlg = ViewerDialog(db, Path(path).name, self)
        dlg.exec()

    def _update_sev_chips(self) -> None:
        counts: dict[str, int] = {
            Severity.BREAKING.name:   0,
            Severity.FUNCTIONAL.name: 0,
            "added":                  0,
            Severity.METADATA.name:   0,
        }
        for entry in self._entries:
            if entry.severity.name in counts:
                counts[entry.severity.name] += 1
            if entry.value_a is None and entry.value_b is not None:
                counts["added"] += 1
        labels = {
            Severity.BREAKING.name:   ("\U0001f534", "Breaking"),
            Severity.FUNCTIONAL.name: ("\U0001f7e0", "Functional"),
            "added":                  ("\U0001f7e2", "Added"),
            Severity.METADATA.name:   ("\U0001f535", "Metadata"),
        }
        for sev_name, chip in self._sev_chips.items():
            icon_emoji, label = labels[sev_name]
            chip.setText(f"{icon_emoji} {counts.get(sev_name, 0)} {label}")

    def _refresh_header_state(self, compared: bool = False) -> None:
        current_mode = self._mode_stack.currentIndex()
        if current_mode == 1:
            self._page_title.setText("DBC Viewer")
            current_path = self._drop_b.path or self._drop_a.path
            self._page_subtitle.setText(
                Path(current_path).name if current_path else "Open one DBC file to inspect its structure."
            )
            return
        if current_mode == 2:
            self._page_title.setText("Simulation Preview")
            self._page_subtitle.setText("Reserved for future playback and geometry inspection workflows.")
            return

        if current_mode == 3:
            self._page_title.setText("Decoder")
            self._page_subtitle.setText(
                "Select a message and enter hex bytes to decode signal values live."
            )
            return

        self._page_title.setText("Diff Report")
        if self._drop_a.path and self._drop_b.path:
            file_a = Path(self._drop_a.path).name
            file_b = Path(self._drop_b.path).name
            self._page_subtitle.setText(
                f"{file_a} → {file_b}" if compared else f"Ready to compare {file_a} and {file_b}"
            )
        else:
            self._page_subtitle.setText("Choose two DBC files to compare messages, signals, nodes, and consistency rules.")

    def _get_msg_type_value(self) -> str:
        return self._msg_type_combo.currentText().strip()

    def _get_protocol_value(self) -> str:
        return self._protocol_combo.currentText().strip()

    def _get_ecu_value(self) -> str:
        return self._ecu_combo.currentText().strip()

    def _matches_search(self, entry: DiffEntry) -> bool:
        needle = self._search_input.text().strip().lower()
        if not needle:
            return True
        haystack = " | ".join([
            entry.entity or "",
            entry.kind or "",
            entry.path or "",
            entry.msg_type or "",
            entry.protocol or "",
            entry.detail or "",
            str(entry.value_a) if entry.value_a is not None else "",
            str(entry.value_b) if entry.value_b is not None else "",
        ]).lower()
        return needle in haystack

    def _entry_message_name(self, entry: DiffEntry) -> str:
        path = entry.path or ""
        if path.startswith("message."):
            return path.split(".", 1)[1].split("(", 1)[0]
        return path.split(".", 1)[0]

    def _entry_matches_ecu(self, entry: DiffEntry, ecu_name: str) -> bool:
        if ecu_name in ("", "(all)"):
            return True
        if entry.entity == "node":
            return ecu_name.lower() in (entry.path or "").lower()

        msg_name = self._entry_message_name(entry)
        for db in (self._db_a, self._db_b):
            if db is None:
                continue
            try:
                message = db.get_message_by_name(msg_name)
            except Exception:
                continue
            senders = set(message.senders or [])
            receivers = set()
            for signal in getattr(message, "signals", []):
                receivers.update(getattr(signal, "receivers", None) or [])
            if ecu_name in senders or ecu_name in receivers:
                return True
        return False

    def _sorted_entries(self, entries: list[DiffEntry]) -> list[DiffEntry]:
        mode = self._sort_combo.currentText()
        sev_rank = {
            Severity.BREAKING: 0,
            Severity.FUNCTIONAL: 1,
            Severity.METADATA: 2,
        }
        if mode == "Kind → Path":
            return sorted(entries, key=lambda e: (e.kind, e.path))
        if mode == "Entity → Path":
            return sorted(entries, key=lambda e: (e.entity, e.path))
        if mode == "Path Z→A":
            return sorted(entries, key=lambda e: e.path, reverse=True)
        if mode == "Path A→Z":
            return sorted(entries, key=lambda e: e.path)
        return sorted(entries, key=lambda e: (sev_rank.get(e.severity, 99), e.path))

    def _build_consistency_records(self, db_a, db_b) -> list[dict]:
        records: list[dict] = []
        for source, db in (("A", db_a), ("B", db_b)):
            if db is None:
                continue
            for issue in check_consistency(db):
                records.append({"source": source, "issue": issue})
        records.sort(
            key=lambda record: (
                {"ERROR": 0, "WARNING": 1, "INFO": 2}.get(record["issue"].level, 3),
                record["issue"].rule_id,
                record["source"],
                record["issue"].message_name,
                record["issue"].signal_name,
            )
        )
        return records

    def _filtered_entries(self, entity_set: Optional[set[str]]) -> list[DiffEntry]:
        filtered: list[DiffEntry] = []
        protocol_filter = self._get_protocol_value()
        msg_type_filter = self._get_msg_type_value()
        ecu_filter = self._get_ecu_value()

        for entry in self._entries:
            if entity_set is not None:
                if "__BREAKING__" in entity_set:
                    if entry.severity.name != Severity.BREAKING.name:
                        continue
                elif entry.entity not in entity_set:
                    continue
            if protocol_filter not in ("", "(all)") and (entry.protocol or "RAW") != protocol_filter:
                continue
            if msg_type_filter not in ("", "(all)") and entry.msg_type != msg_type_filter:
                continue
            if not self._entry_matches_ecu(entry, ecu_filter):
                continue
            if not self._matches_search(entry):
                continue
            filtered.append(entry)
        return self._sorted_entries(filtered)

    def _refresh_table(self):
        if 0 <= self._current_view_idx < len(_VIEWS) and 0 <= self._current_view_idx < len(self._view_tables):
            _, _, entity_set = _VIEWS[self._current_view_idx]
            self._view_tables[self._current_view_idx].populate(self._filtered_entries(entity_set))

    def _refresh_all_tabs(self):
        for tab_idx, (_, _, entity_set) in enumerate(_VIEWS):
            if tab_idx < len(self._view_tables):
                self._view_tables[tab_idx].populate(self._filtered_entries(entity_set))

        nodes_idx = next(i for i, (name, _, _) in enumerate(_VIEWS) if "Nodes" in name)
        if nodes_idx < len(self._view_tables) and self._view_tables[nodes_idx].rowCount() == 0:
            self._populate_node_inventory(self._db_a)
            self._node_stack.setCurrentIndex(1)
        else:
            self._node_stack.setCurrentIndex(0)

    def _update_protocol_list(self):
        current = self._protocol_combo.currentText().strip()
        values = sorted({(e.protocol or "RAW") for e in self._entries})
        self._protocol_combo.blockSignals(True)
        self._protocol_combo.clear()
        self._protocol_combo.addItem("(all)")
        for value in values:
            self._protocol_combo.addItem(value)
        idx = self._protocol_combo.findText(current)
        self._protocol_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._protocol_combo.blockSignals(False)

    def _update_ecu_node_list(self):
        current = self._ecu_combo.currentText().strip()
        values: set[str] = set()
        for db in (self._db_a, self._db_b):
            if db is None:
                continue
            for node in getattr(db, "nodes", []) or []:
                values.add(node.name)
            for message in getattr(db, "messages", []) or []:
                values.update(message.senders or [])
                for signal in getattr(message, "signals", []) or []:
                    values.update(getattr(signal, "receivers", None) or [])
        self._ecu_combo.blockSignals(True)
        self._ecu_combo.clear()
        self._ecu_combo.addItem("(all)")
        for value in sorted(values):
            self._ecu_combo.addItem(value)
        idx = self._ecu_combo.findText(current)
        self._ecu_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._ecu_combo.blockSignals(False)

    def _update_msg_type_list(self):
        current = self._msg_type_combo.currentText().strip()
        self._msg_type_combo.blockSignals(True)
        self._msg_type_combo.clear()
        self._msg_type_combo.addItem("(all)")
        if self._entries:
            for msg_type in sorted({e.msg_type for e in self._entries if e.msg_type}):
                self._msg_type_combo.addItem(msg_type)
        idx = self._msg_type_combo.findText(current)
        self._msg_type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._msg_type_combo.blockSignals(False)

    def _toggle_severity(self, severity_name: str) -> None:
        pass  # severity chips are read-only; no toggle filtering

    def _on_row_selected(self, table_idx: int) -> None:
        if 0 <= table_idx < len(self._view_tables):
            entry = self._view_tables[table_idx].current_entry()
            self._detail.update_entry(entry)

    def _on_msg_type_changed(self, _text: str):
        self._refresh_all_tabs()

    def _export_entries(self, suffix: str, filter_str: str, writer) -> None:
        if not self._entries:
            QMessageBox.information(self, "Nothing to export", "Run a comparison before exporting results.")
            return
        if _VIEWS[self._current_view_idx][0] == "Consistency":
            QMessageBox.information(
                self,
                "Consistency Export",
                "Consistency export is not wired to the existing diff exporters yet. Switch to a diff view to export results.",
            )
            return
        _, _, entity_set = _VIEWS[self._current_view_idx]
        visible = self._filtered_entries(entity_set)
        path, _ = QFileDialog.getSaveFileName(self, "Export report", f"dbcdiff_report{suffix}", filter_str)
        if not path:
            return
        if not Path(path).suffix:
            path += suffix
        try:
            with open(path, "w", encoding="utf-8", newline="") as fp:
                writer(visible, fp)
            self._status.showMessage(f"✅  Exported {len(visible)} entries to {Path(path).name}")
        except Exception as exc:  # pylint: disable=broad-except
            QMessageBox.critical(self, "Export Error", str(exc))

    def _export_html(self) -> None:
        self._export_entries(".html", "HTML files (*.html)", write_html)

    def _export_csv(self) -> None:
        self._export_entries(".csv", "CSV files (*.csv)", write_csv)

    def _export_json(self) -> None:
        self._export_entries(".json", "JSON files (*.json)", write_json)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def launch_gui():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("dbcdiff")
    _apply_app_theme(app)

    # ── License agreement ────────────────────────────────────────────────────
    lic = LicenseDialog()
    lic.setStyleSheet(_load_app_stylesheet())
    if lic.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())
