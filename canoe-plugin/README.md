# CANoe / CANalyzer Plugin for dbcdiff

Automatically compare DBC files before a CANoe measurement or test run,
blocking execution if incompatible changes are detected.

## Files

| File | Purpose |
|------|---------|
| `dbcdiff_canoe.py` | Python bridge script – wraps `dbcdiff` CLI, emits CANoe-friendly log output |
| `dbcdiff.capl` | CAPL integration – calls the Python bridge via `system()`, aborts on gate breach |

---

## Prerequisites

```bash
pip install dbcdiff          # in the Python environment CANoe will call
```

CANoe/CANalyzer **8.0 or later** is required for `system()` support.
In some organisations the `system()` call must be explicitly enabled under
**Options › Allow script execution with system()**.

---

## Quick Start

### 1 – Python bridge (standalone / CI)

```bash
python dbcdiff_canoe.py \
    --base "C:/Project/baseline.dbc" \
    --head "C:/Project/current.dbc"  \
    --html "C:/Temp/report.html"     \
    --json "C:/Temp/report.json"     \
    --severity FUNCTIONAL            \
    --open-browser
```

Exit codes:

| Code | Meaning |
|------|---------|
| 0 | Identical or below gate |
| 1 | Gate breached |

The underlying `dbcdiff` severity exit codes (0–3) are printed to stdout
and can be parsed from CAPL.

### 2 – CAPL integration

1. Copy both files into your CANoe project folder (e.g. `canoe-plugin/`).
2. Open `dbcdiff.capl` in the CAPL Browser.
3. Edit the **DBC Diff Configuration** variables at the top of the file:

```capl
char BASE_DBC[512]   = "C:\\Project\\can\\vehicle_baseline.dbc";
char HEAD_DBC[512]   = "C:\\Project\\can\\vehicle_current.dbc";
char PYTHON_EXE[512] = "python";
char SCRIPT_PATH[512]= "C:\\Project\\canoe-plugin\\dbcdiff_canoe.py";
char REPORT_DIR[512] = "C:\\Temp\\dbc_diff_reports";
char SEVERITY_GATE[32]= "BREAKING";
```

4. The `OnPreStart` handler runs automatically before each measurement.
   To use it in a test module instead, call `RunDbcDiff()` from a `testcase`.

### 3 – Severity gate

| Value | Blocks on |
|-------|-----------|
| `METADATA` | Any attribute or comment change |
| `FUNCTIONAL` | Signal factor, offset, unit, value table, DLC, etc. |
| `BREAKING` | Removed signals or messages _(default)_ |

Set `g_abortOnBreaking = 0` to log differences without ever stopping CANoe.

---

## Output

The Python bridge always writes two files to `--report-dir`:

* **diff_report.html** – visual side-by-side HTML diff (open in any browser)
* **diff_report.json** – machine-readable summary

Example JSON summary:

```json
{
  "summary": {
    "max_severity": 2,
    "breaking": 0,
    "functional": 3,
    "metadata": 1,
    "total_changes": 4
  },
  "changes": [ ... ]
}
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `system()` has no effect | Enable script execution in CANoe Options |
| `dbcdiff: command not found` | Set `PYTHON_EXE` to the full path, e.g. `C:\Python312\python.exe` |
| Reports not generated | Check that `REPORT_DIR` exists and is writable |
| Gate triggers on first run | Add `--severity BREAKING` flag or set `g_abortOnBreaking = 0` |
