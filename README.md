# dbcdiff

> A professional **DBC file diff tool** for automotive CAN bus development.  
> Compare two `.dbc` databases, detect what changed, and understand the impact — from the CLI or a modern dark-theme GUI.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![cantools 41+](https://img.shields.io/badge/cantools-41%2B-orange)](https://pypi.org/project/cantools/)

---

## Features

| Feature | Details |
|---------|---------|
| **Breaking / Functional / Metadata** severity classification | Instantly see what actually matters |
| **Protocol detection** | Auto-identifies J1939, CAN FD, CAN XL, or Basic CAN |
| **File A / File B** consistent terminology | No ambiguous "old / new" language |
| **Three export formats** | HTML (self-contained), CSV, JSON |
| **PySide6 dark-theme GUI** | Drag-and-drop files, filter by severity |
| **CLI one-liner** | Pipe-friendly, non-zero exit on changes |
| **Standalone `.exe`** | PyInstaller or Nuitka build — no Python required on target |

---

## Installation

```bash
# From PyPI (when published)
pip install dbcdiff

# From source
git clone https://github.com/pawanct08/dbcdiff
cd dbcdiff
pip install -e ".[gui]"   # includes PySide6
```

### Dependencies

| Package | Purpose |
|---------|---------|
| `cantools>=41.0` | DBC parsing |
| `PySide6>=6.5` | GUI (optional — CLI works without it) |

---

## Quick Start

### CLI

```bash
# Basic diff (prints table, exits with severity code)
dbcdiff FileA.dbc FileB.dbc

# Export HTML report
dbcdiff FileA.dbc FileB.dbc --html report.html

# Export all formats
dbcdiff FileA.dbc FileB.dbc --html out.html --csv out.csv --json out.json

# Only show breaking changes; suppress table
dbcdiff FileA.dbc FileB.dbc --min-severity breaking -q --html breaking.html
```

#### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Files are identical |
| `1` | Metadata-only differences |
| `2` | Functional differences |
| `3` | Breaking differences |

Use in CI:

```bash
dbcdiff baseline.dbc candidate.dbc
if [ $? -ge 3 ]; then echo "BREAKING CHANGES – review required"; exit 1; fi
```

### GUI

```bash
# Launch GUI (double-click exe, or run without arguments)
dbcdiff
# or
dbcdiff-gui
```

1. Drag a `.dbc` file onto the **File A** drop zone (or click **Browse**).
2. Drag a `.dbc` file onto the **File B** drop zone.
3. Click **Compare**.
4. Filter by severity using the toolbar buttons.
5. Click **Export HTML** to save a shareable report.

---

## Sample Output

### CLI table

```
┌──────────────┬──────────┬────────────────────────────────────────┬
│ Severity     │ Kind     │ Path                                   │
├──────────────┼──────────┼────────────────────────────────────────┼
│ BREAKING     │ removed  │ EngineControl.TorqueRequest            │
│ BREAKING     │ added    │ EngineControl.TorqueRequestExt         │
│ FUNCTIONAL   │ changed  │ EngineControl.EngineSpeed.factor       │
│ FUNCTIONAL   │ changed  │ EngineControl.EngineSpeed.offset       │
│ METADATA     │ changed  │ EngineControl.EngineSpeed.unit         │
└──────────────┴──────────┴────────────────────────────────────────┘
Max severity: BREAKING  |  5 change(s)  |  Protocol: J1939
```

---

## HTML Report

The `--html` flag produces a **self-contained HTML file** (no external CSS or JS):

- Colour-coded severity rows
- Protocol badge and file header
- JavaScript filter buttons (All / Breaking / Functional / Metadata)
- Share or attach to pull request reviews

---

## Building a Standalone `.exe`

### Option A — PyInstaller (quick, ~60 MB)

```powershell
pip install pyinstaller pillow
.\build\build_exe.ps1
# → dist\dbcdiff-gui.exe
```

### Option B — Nuitka (native code, harder to decompile)

```powershell
pip install nuitka ordered-set zstandard pillow
# + install Visual Studio Build Tools (or MinGW-w64)
.\build\build_protected.ps1
# → dist\dbcdiff-gui.exe
```

See [`build/`](build/) for full scripts and [`DESIGN.md`](DESIGN.md) for
architecture details.

---

## Protocol Detection

dbcdiff automatically classifies the network from database heuristics:

| Protocol | Detection |
|----------|-----------|
| **CAN XL** | `is_fd` + DLC > 64 bytes |
| **CAN FD** | `is_fd` flag on any message |
| **J1939** | Extended 29-bit frame with non-zero PGN |
| **Basic CAN** | Default |

J1939 frames are decoded into **Priority / PGN / SA** fields for richer context.

---

## Severity Reference

| Severity | Colour | Meaning |
|----------|--------|---------|
| `BREAKING` | 🔴 Red | Message/signal added or removed; ID or DLC changed |
| `FUNCTIONAL` | 🟠 Orange | Factor, offset, range, byte order, value type changed |
| `METADATA` | 🟢 Green | Comment, unit, or attribute changed |
| `IDENTICAL` | — | No differences found |

---

## Project Layout

```
dbcdiff/
├── engine.py          # Core diff algorithm
├── protocol.py        # CAN protocol detection
├── cli.py             # CLI interface
├── gui.py             # PySide6 GUI
└── reporters/
    ├── html_reporter.py
    ├── csv_reporter.py
    └── json_reporter.py
build/
├── create_icon.py     # Generate icon.ico
├── build_exe.ps1      # PyInstaller build
└── build_protected.ps1  # Nuitka build
```

See [DESIGN.md](DESIGN.md) for full architecture documentation.

---

## License

MIT © 2024 dbcdiff contributors
