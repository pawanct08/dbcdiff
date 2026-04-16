# dbcdiff Design Document

> Version 0.2.0 | Architecture & internals reference

---

## 1. Module Structure

```
dbcdiff/
├── __init__.py          # Public surface: compare_databases, Severity, DiffEntry
├── __main__.py          # Entry-point dispatcher: CLI (args) → GUI (no args)
├── cli.py               # Argument parsing, output formatting, exit codes
├── engine.py            # Core diff logic
├── protocol.py          # CAN protocol detection (J1939, FD, XL, Basic)
└── reporters/
    ├── __init__.py
    ├── html_reporter.py # Self-contained HTML report (inline CSS + JS)
    ├── csv_reporter.py  # CSV with fieldnames aligned to DiffEntry
    └── json_reporter.py # JSON with summary block + changes list

build/
├── create_icon.py       # Generates icon.ico (Pillow or fallback minimal ICO)
├── build_exe.ps1        # PyInstaller one-file build
└── build_protected.ps1  # Nuitka native-code protected build

tests/
├── a.dbc                # Reference DBC (File A)
└── b.dbc                # Modified DBC (File B)
```

---

## 2. Data Model

### `Severity` (engine.py)

```python
class Severity(IntEnum):
    IDENTICAL  = 0   # No change detected
    METADATA   = 1   # Comment, attribute, or non-functional property changed
    FUNCTIONAL = 2   # Signal range, factor, offset, byte order, value type
    BREAKING   = 3   # Message/signal added, removed, or ID/DLC changed
```

`IntEnum` is used so severities compare naturally (`BREAKING > FUNCTIONAL`).

### `DiffEntry` (engine.py)

```python
@dataclass
class DiffEntry:
    entity:   str        # e.g. "EngineSpeed" (signal) or "0x18FEF100" (message)
    kind:     str        # "added" | "removed" | "changed"
    severity: Severity
    path:     str        # dotted path, e.g. "EngineControl.EngineSpeed.factor"
    value_a:  Any        # Value in File A (None for added entities)
    value_b:  Any        # Value in File B (None for removed entities)
    detail:   str        # Human-readable explanation
    protocol: str        # Protocol tag from detect_protocol(), or ""
```

`value_a` / `value_b` replace the old `old_value` / `new_value` names introduced
in v0.1.0, aligning the code to the "File A / File B" terminology used throughout
the UI, CLI, and reports.

`as_dict()` returns a plain `dict` for JSON/CSV serialisation.

---

## 3. Diff Engine (engine.py)

### 3.1 Compare flow

```
compare_databases(db_a, db_b, path_a, path_b)
  │
  ├─ _compare_messages(db_a, db_b)
  │    ├─ Removed messages  → BREAKING / "removed"
  │    ├─ Added messages    → BREAKING / "added"
  │    └─ Common messages
  │         ├─ ID changed      → BREAKING
  │         ├─ DLC changed     → BREAKING
  │         ├─ Name changed    → METADATA
  │         └─ _compare_signals(msg_a, msg_b)
  │               ├─ Removed signals  → BREAKING
  │               ├─ Added signals    → BREAKING
  │               └─ Common signals
  │                    ├─ start_bit   → BREAKING
  │                    ├─ length      → BREAKING
  │                    ├─ byte_order  → FUNCTIONAL
  │                    ├─ value_type  → FUNCTIONAL
  │                    ├─ factor      → FUNCTIONAL
  │                    ├─ offset      → FUNCTIONAL
  │                    ├─ min/max     → FUNCTIONAL
  │                    ├─ unit        → METADATA
  │                    └─ comment     → METADATA
  │
  └─ (protocol tag appended to every DiffEntry.protocol)
```

### 3.2 Protocol tagging

Each `DiffEntry` is tagged with the protocol string returned by
`detect_protocol(db_a)` (file A takes precedence). This lets reporters and the
GUI display protocol context alongside each change.

---

## 4. Protocol Detection (protocol.py)

```
detect_protocol(db) → CANProtocol
```

Heuristic priority (highest to lowest):

| Priority | Protocol | Detection criterion |
|----------|----------|---------------------|
| 1st | CAN XL | `msg.is_fd` + DLC > 64 bytes → probable XL payload |
| 2nd | CAN FD | `msg.is_fd` is True on any message |
| 3rd | J1939  | Extended frame + 29-bit ID where PGN field is non-zero |
| 4th | Basic CAN | Default fallback |

J1939 frame decomposition:
- Priority: bits 28–26  
- PGN: bits 25–8 (PDU1: DA in byte 3; PDU2: GE group)  
- SA: bits 7–0

`protocol_summary(db)` returns a `dict` with protocol, message count, J1939
PGN list, and FD flag for informational display.

---

## 5. Reporters

### HTML reporter (html_reporter.py)

- Self-contained single HTML file — inline CSS, inline JS, no external deps.
- Header shows: `File A: <path>` vs `File B: <path>`, protocol badge, max severity badge.
- Table columns: Severity | Kind | Entity | Path | File A Value | File B Value | Protocol | Detail.
- JS filter buttons for All / Breaking / Functional / Metadata.
- Colour-coded severity rows matching the GUI palette.

### CSV reporter (csv_reporter.py)

Fieldnames: `entity, kind, severity, path, value_a, value_b, protocol, detail`

### JSON reporter (json_reporter.py)

```json
{
  "summary": {
    "file_a": "...",
    "file_b": "...",
    "max_severity": "BREAKING",
    "total": 12,
    "breaking": 3,
    "functional": 5,
    "metadata": 4
  },
  "changes": [
    {
      "entity": "EngineSpeed",
      "kind": "changed",
      "severity": "FUNCTIONAL",
      "path": "EngineControl.EngineSpeed.factor",
      "value_a": 0.125,
      "value_b": 0.25,
      "protocol": "J1939",
      "detail": "factor changed"
    }
  ]
}
```

---

## 6. GUI Architecture (gui.py)

### 6.1 Component hierarchy

```
MainWindow (QMainWindow)
├── QSplitter (horizontal)
│   ├── DBCDropZone  [File A]
│   └── DBCDropZone  [File B]
├── QToolBar  (Compare | Clear | Export HTML)
├── Filter bar  (All | Breaking | Functional | Metadata — QToolButton checkable)
├── SummaryBadge (Total / Breaking / Functional / Metadata chips)
└── ResultsTable (QTableWidget — 8 columns)
```

### 6.2 Threading model

Comparison is off the GUI thread to keep the UI responsive:

```
MainWindow._run_compare()
  │
  ├─ CompareWorker(QObject)  ← moved to QThread
  │     run():
  │       db_a = cantools.database.load_file(path_a)
  │       db_b = cantools.database.load_file(path_b)
  │       entries = compare_databases(db_a, db_b)
  │       emit finished(entries)   OR   emit error(msg)
  │
  └─ slot _on_compare_done(entries)   ← back on GUI thread
        ResultsTable.populate(entries)
        SummaryBadge.update(entries)
```

### 6.3 Colour palette (dark theme)

| Token | Hex | Used for |
|-------|-----|----------|
| `bg0` | `#0d1117` | Window background |
| `bg1` | `#161b22` | Widget surface |
| `bg2` | `#1f2937` | Alternate row, tooltip bg |
| `border` | `#30363d` | Borders, separators |
| `text` | `#e6edf3` | Primary text |
| `muted` | `#8b949e` | Secondary text |
| `accent` | `#1f6feb` | Primary accent (buttons, links) |
| `breaking` | `#f85149` | BREAKING severity |
| `functional` | `#f0883e` | FUNCTIONAL severity |
| `metadata` | `#3fb950` | METADATA severity |

---

## 7. CLI Design (cli.py)

```
dbcdiff [options] <file_a> <file_b>

Options:
  --html PATH     Export HTML report
  --csv  PATH     Export CSV
  --json PATH     Export JSON
  --min-severity  {breaking,functional,metadata}  Filter output
  -q / --quiet    Suppress table output
```

Exit codes:

| Code | Meaning |
|------|---------|
| 0 | No differences (IDENTICAL) |
| 1 | Metadata-only differences |
| 2 | Functional differences |
| 3 | Breaking differences |

---

## 8. Build System

### PyInstaller (fast, Python-bundled)

`build/build_exe.ps1` produces a single `.exe` that bundles the CPython
interpreter and all dependencies. Approx size: 50–90 MB.

```
pyinstaller --onefile --windowed --icon=build/icon.ico \
            --name=dbcdiff-gui                         \
            --add-data "dbcdiff;dbcdiff"               \
            dbcdiff/__main__.py
```

### Nuitka (native code, harder to reverse-engineer)

`build/build_protected.ps1` compiles Python source to C then to native machine
code. No `.pyc` files are bundled. The interpreter is also compiled in.
Requires MSVC or MinGW-w64. First build takes 3–10 minutes.

```
python -m nuitka --onefile --enable-plugin=pyside6 \
                 --windows-disable-console          \
                 --windows-icon-from-ico=build/icon.ico \
                 --output-filename=dbcdiff-gui.exe  \
                 dbcdiff/__main__.py
```

---

## 9. Dependency Versions

| Package | Version constraint | Purpose |
|---------|-------------------|---------|
| `cantools` | `>=41.0` | DBC parsing |
| `PySide6` | `>=6.5` | Qt6 GUI |
| `Pillow` | optional | Icon generation in build scripts |
| `pyinstaller` | optional | Std exe build |
| `nuitka` | optional | Native code build |
