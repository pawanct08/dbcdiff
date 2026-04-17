# DBC Diff — VS Code Extension

Inline semantic diff for **CANbus DBC** files directly inside VS Code.  
Uses the [`dbcdiff`](https://github.com/pawanct08/dbcdiff) Python package
to compare signal names, bit-lengths, byte orders, factor/offset,
min/max, enumerations, and message attributes.

## Features

| Command | Description |
|---|---|
| **DBC: Show Semantic Diff (vs HEAD)** | Compare the open `.dbc` file against its last committed (git HEAD) version. Shows an HTML report beside the editor. |
| **DBC: Compare with…** | Pick any second `.dbc` file to compare against. |

Both commands are also available from:
- The **editor title bar** (when a `.dbc` file is active) — `$(diff)` button
- The **Explorer context menu** when right-clicking a `.dbc` file

A colour-coded notification badge shows the severity at a glance:

| Badge | Meaning |
|---|---|
| 🟢 Identical | No semantic differences |
| 🟡 Metadata | Comment / attribute changes only |
| 🟠 Functional | Signal or message parameter changes |
| 🔴 BREAKING | Removed signals / incompatible changes |

## Requirements

1. **Python ≥ 3.10** with `dbcdiff` installed:
   ```bash
   pip install dbcdiff
   # or, for a specific venv:
   /path/to/venv/bin/pip install dbcdiff
   ```
2. **git** in PATH (needed for *vs HEAD* comparison).

## Extension Settings

| Setting | Default | Description |
|---|---|---|
| `dbcdiff.pythonPath` | `"python"` | Python interpreter that has `dbcdiff` installed. Set to the full path of a virtualenv's Python if needed. |

Example (`settings.json`):
```json
{
  "dbcdiff.pythonPath": "/home/user/.venv/bin/python"
}
```

## Building from Source

```bash
cd vscode-extension
npm install
npm run compile          # one-shot build
# or:
npm run watch            # incremental rebuild

# Package as a .vsix:
npm run package          # requires @vscode/vsce
```

Then install the `.vsix` via  
**Extensions → ⋯ → Install from VSIX…** in VS Code.

## How it Works

1. The extension calls `git show HEAD:<file>` to retrieve the committed DBC content and writes it to a temp file.
2. It then runs `python -m dbcdiff <temp_base> <current_file> --html-out <tmp.html> --json-out <tmp.json>`.
3. The HTML report is displayed in a VS Code Webview panel.
4. The JSON summary drives the colour-coded notification.

## License

MIT
