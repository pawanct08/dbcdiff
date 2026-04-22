# Changelog

All notable changes to **dbcdiff** are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/); versioning follows [Semantic Versioning](https://semver.org/).

---

## [0.4.0] – 2026-04-22

### Added
- **GUI export fix**: `_do_convert()` now calls `write_excel()` (5 sheets) instead of the old `dbc_to_excel()` helper (3 sheets) — Value Tables and Nodes sheets now appear in GUI-generated workbooks.
- **JSON reporter v0.3 schema**: `summary` block gains `added`, `removed`, `renamed` counts and renames `worst` → `worst_severity`; `bus_load_delta` is now emitted before `diffs` in the payload.
- **Excel reporter enhancements**: Frame ID shown in both hex and decimal in the Messages sheet; hex-only in the Signals sheet; Value Tables sheet carries Frame ID and alternating row colour per message group; TX/RX columns use `_NodeLists` hidden sheet for DataValidation drop-downs.
- **`export-matrix` CLI sub-command**: `dbcdiff export-matrix [--out FILE] <dbc>` generates the full Excel workbook from the command line.
- **PyPI packaging**: added `Topic :: Software Development :: Automotive` classifier; keywords expanded with `CAN`, `DBC`, `ECU`.

### Changed
- `pyproject.toml`: keywords and classifiers updated for better PyPI discoverability.
- `__init__.__version__` bumped to `0.4.0` (was `0.3.0`).

---

## [0.3.0] – 2026-03

### Added
- **Excel reporter** (`reporters/excel_reporter.py`): multi-sheet `.xlsx` output via `write_excel(db, path)` with Messages, Signals, Value Tables, Nodes, and hidden `_NodeLists` sheets.
- **JSON reporter** (`reporters/json_reporter.py`): structured diff report with `meta`, `summary`, `bus_load_delta`, and `diffs` array (`as_dict()` per entry).
- **Bus-load delta**: cycle-time changes in the diff output are aggregated into a `bus_load_delta` block.
- Cross-message signal rename detection (`_resolve_cross_message_signal_renames`).

### Changed
- Engine: `DiffEntry.as_dict()` extended with `kind`, `entity`, `severity` fields.

---

## [0.2.0] – 2026-02

### Added
- `Severity` enum (`BREAKING`, `FUNCTIONAL`, `METADATA`) and `max_severity()` helper.
- `DiffEntry` dataclass with `as_dict()` serialisation.
- GUI: side-by-side diff viewer with colour-coded severity rows.
- CLI: `dbcdiff <a.dbc> <b.dbc>` with `--json`, `--out`, `--no-colour` flags.
- Basic Excel export via `converter.dbc_to_excel()` (3 sheets — superseded in 0.4.0).

---

## [0.1.0] – 2026-01

### Added
- Initial release: parse two `.dbc` files with `cantools`, emit a flat list of added/removed/changed messages and signals.
- Entry point `dbcdiff` registered via `pyproject.toml`.

---

[0.4.0]: https://github.com/pawanct08/dbcdiff/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/pawanct08/dbcdiff/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/pawanct08/dbcdiff/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/pawanct08/dbcdiff/releases/tag/v0.1.0
