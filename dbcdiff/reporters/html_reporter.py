"""
reporters/html_reporter.py
Generates a self-contained dark-theme HTML diff report.
"""

from __future__ import annotations
import html
import json
from typing import TextIO
from ..engine import DiffEntry, Severity, max_severity, ADDED, REMOVED, CHANGED


# ---------------------------------------------------------------------------
# Severity colours & labels
# ---------------------------------------------------------------------------

_SEV_BADGE = {
    Severity.BREAKING:   ('<span class="badge breaking">🔴 BREAKING</span>',   "breaking"),
    Severity.FUNCTIONAL: ('<span class="badge functional">🟠 FUNCTIONAL</span>', "functional"),
    Severity.METADATA:   ('<span class="badge metadata">🟡 METADATA</span>',   "metadata"),
}
_KIND_BADGE = {
    ADDED:   '<span class="badge added">➕ ADDED</span>',
    REMOVED: '<span class="badge removed">➖ REMOVED</span>',
    CHANGED: '<span class="badge changed">✏️ CHANGED</span>',
}

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0d1117; color: #c9d1d9; }
header { background: #161b22; padding: 20px 32px; border-bottom: 1px solid #30363d;
         display: flex; align-items: center; gap: 16px; }
header h1 { font-size: 1.4rem; font-weight: 600; }
header .subtitle { color: #8b949e; font-size: .85rem; }
.summary-bar { background: #161b22; padding: 16px 32px; border-bottom: 1px solid #30363d;
               display: flex; gap: 24px; align-items: center; flex-wrap: wrap; }
.stat { text-align: center; }
.stat .num { font-size: 1.8rem; font-weight: 700; }
.stat .lbl { font-size: .75rem; color: #8b949e; text-transform: uppercase; letter-spacing: .05em; }
.num.breaking   { color: #f85149; }
.num.functional { color: #d29922; }
.num.metadata   { color: #e3b341; }
.num.added      { color: #3fb950; }
.num.removed    { color: #f85149; }
.donut-wrap { margin-left: auto; }
canvas { display: block; }

.filters { padding: 12px 32px; background: #0d1117; display: flex; gap: 8px; flex-wrap: wrap; }
button.filter-btn {
  background: #21262d; color: #c9d1d9; border: 1px solid #30363d;
  border-radius: 6px; padding: 4px 14px; cursor: pointer; font-size: .8rem;
  transition: background .15s;
}
button.filter-btn:hover { background: #30363d; }
button.filter-btn.active { border-color: #58a6ff; color: #58a6ff; }

table { width: 100%; border-collapse: collapse; font-size: .82rem; }
thead th { background: #161b22; padding: 8px 12px; text-align: left;
           border-bottom: 1px solid #30363d; color: #8b949e;
           position: sticky; top: 0; z-index: 1; }
tbody tr { border-bottom: 1px solid #161b22; transition: background .1s; }
tbody tr:hover { background: #161b22; }
td { padding: 7px 12px; vertical-align: top; word-break: break-all; }
td.path { font-family: 'Cascadia Code', 'Fira Code', monospace; font-size: .78rem; color: #8b949e; }
td.old  { color: #f85149; }
td.new  { color: #3fb950; }
.badge { border-radius: 4px; padding: 2px 6px; font-size: .72rem; font-weight: 600;
         white-space: nowrap; }
.badge.breaking   { background: #3d1f1f; color: #f85149; }
.badge.functional { background: #3d2e10; color: #d29922; }
.badge.metadata   { background: #3d3010; color: #e3b341; }
.badge.added      { background: #1a3828; color: #3fb950; }
.badge.removed    { background: #3d1f1f; color: #f85149; }
.badge.changed    { background: #1f2d3d; color: #58a6ff; }

.empty { padding: 48px; text-align: center; color: #8b949e; font-size: 1rem; }
.table-wrap { padding: 0 32px 32px; }
/* Bit-layout visualiser */
.bit-section { padding: 0 32px 24px; }
.bit-section h3 { color: #8b949e; font-size: .8rem; text-transform: uppercase;
                  letter-spacing: .06em; margin-bottom: 8px; margin-top: 16px; }
.bit-panels { display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 8px; }
.bit-panel { background: #161b22; border: 1px solid #30363d; border-radius: 6px;
             padding: 12px; }
.bit-panel h4 { font-size: .75rem; color: #8b949e; margin-bottom: 6px; }
.bit-grid { display: grid; grid-template-columns: repeat(8, 28px);
            gap: 2px; font-size: .65rem; }
.bit-cell { width: 28px; height: 28px; border-radius: 3px; display: flex;
            align-items: center; justify-content: center;
            border: 1px solid #30363d; color: #0d1117; font-weight: 600; }
.bit-cell.unused { background: #21262d; color: #8b949e; border-color: #21262d; }
.bit-legend { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }
.bit-legend-item { display: flex; align-items: center; gap: 4px; font-size: .7rem; }
.bit-legend-swatch { width: 12px; height: 12px; border-radius: 2px; }
"""

_JS = """
// Donut chart
(function () {
  const data = JSON.parse(document.getElementById('chart-data').textContent);
  const canvas = document.getElementById('donut');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0) return;
  const cx = canvas.width / 2, cy = canvas.height / 2, R = 56, r = 34;
  let angle = -Math.PI / 2;
  data.forEach(d => {
    const slice = (d.value / total) * 2 * Math.PI;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, R, angle, angle + slice);
    ctx.closePath();
    ctx.fillStyle = d.color;
    ctx.fill();
    angle += slice;
  });
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, 2 * Math.PI);
  ctx.fillStyle = '#161b22';
  ctx.fill();
  ctx.fillStyle = '#c9d1d9';
  ctx.font = 'bold 16px system-ui';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(total, cx, cy);
})();

// Filter buttons
document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', function () {
    const sev = this.dataset.sev;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    this.classList.add('active');
    document.querySelectorAll('tbody tr').forEach(row => {
      row.style.display = (sev === 'all' || row.dataset.sev === sev) ? '' : 'none';
    });
  });
});
document.querySelector('[data-sev="all"]').classList.add('active');
"""


def write_html(entries: list[DiffEntry], fp: TextIO,
               file_a: str = "", file_b: str = "",
               db_a=None, db_b=None) -> None:
    sev_counts = {
        "breaking":   sum(1 for e in entries if e.severity == Severity.BREAKING),
        "functional": sum(1 for e in entries if e.severity == Severity.FUNCTIONAL),
        "metadata":   sum(1 for e in entries if e.severity == Severity.METADATA),
        "added":      sum(1 for e in entries if e.kind == ADDED),
        "removed":    sum(1 for e in entries if e.kind == REMOVED),
    }
    chart_data = json.dumps([
        {"label": "Breaking",   "value": sev_counts["breaking"],   "color": "#f85149"},
        {"label": "Functional", "value": sev_counts["functional"], "color": "#d29922"},
        {"label": "Metadata",   "value": sev_counts["metadata"],   "color": "#e3b341"},
        {"label": "Added",      "value": sev_counts["added"],      "color": "#3fb950"},
        {"label": "Removed",    "value": sev_counts["removed"],    "color": "#8957e5"},
    ])

    rows_html = _build_rows(entries)
    bit_section = _build_bit_sections(entries, db_a, db_b) if (db_a and db_b) else ""

    fp.write(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>dbcdiff report</title>
<style>{_CSS}</style>
</head>
<body>
<header>
  <div>
    <h1>&#127891; dbcdiff Report</h1>
    <div class="subtitle">
      <strong>File A:</strong> {html.escape(file_a or '(unknown)')}
      &nbsp;vs&nbsp;
      <strong>File B:</strong> {html.escape(file_b or '(unknown)')}
    </div>
  </div>
</header>

<div class="summary-bar">
  <div class="stat"><div class="num breaking">{sev_counts['breaking']}</div><div class="lbl">Breaking</div></div>
  <div class="stat"><div class="num functional">{sev_counts['functional']}</div><div class="lbl">Functional</div></div>
  <div class="stat"><div class="num metadata">{sev_counts['metadata']}</div><div class="lbl">Metadata</div></div>
  <div class="stat"><div class="num added">{sev_counts['added']}</div><div class="lbl">Added</div></div>
  <div class="stat"><div class="num removed">{sev_counts['removed']}</div><div class="lbl">Removed</div></div>
  <div class="donut-wrap">
    <canvas id="donut" width="120" height="120"></canvas>
    <script id="chart-data" type="application/json">{chart_data}</script>
  </div>
</div>

<div class="filters">
  <button class="filter-btn" data-sev="all">All ({len(entries)})</button>
  <button class="filter-btn" data-sev="breaking">🔴 Breaking ({sev_counts['breaking']})</button>
  <button class="filter-btn" data-sev="functional">🟠 Functional ({sev_counts['functional']})</button>
  <button class="filter-btn" data-sev="metadata">🟡 Metadata ({sev_counts['metadata']})</button>
</div>
{bit_section}

<div class="table-wrap">
{"" if entries else '<div class="empty">✅ No differences found — files are identical.</div>'}
{"" if not entries else f"""
<table>
  <thead>
    <tr>
      <th>Severity</th>
      <th>Kind</th>
      <th>Entity</th>
      <th>Path</th>
      <th>File A Value</th>
      <th>File B Value</th>
      <th>Protocol</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>"""}
</div>

<script>{_JS}</script>
</body>
</html>
""")


def _build_rows(entries: list[DiffEntry]) -> str:
    parts = []
    for e in entries:
        sev_key = {
            Severity.BREAKING:   "breaking",
            Severity.FUNCTIONAL: "functional",
            Severity.METADATA:   "metadata",
        }.get(e.severity, "metadata")
        sev_badge, _ = _SEV_BADGE.get(e.severity, ("", ""))
        kind_badge = _KIND_BADGE.get(e.kind, e.kind)
        old_v = _fmt_val(e.value_a)
        new_v = _fmt_val(e.value_b)
        proto = html.escape(e.protocol) if e.protocol else '<span style="color:#8b949e">—</span>'
        parts.append(
            f'<tr data-sev="{sev_key}">'
            f'<td>{sev_badge}</td>'
            f'<td>{kind_badge}</td>'
            f'<td>{html.escape(e.entity)}</td>'
            f'<td class="path">{html.escape(e.path)}</td>'
            f'<td class="old">{old_v}</td>'
            f'<td class="new">{new_v}</td>'
            f'<td class="path">{proto}</td>'
            f'</tr>'
        )
    return "\n    ".join(parts)


def _fmt_val(v) -> str:
    if v is None:
        return '<span style="color:#8b949e">—</span>'
    return html.escape(str(v))


# ---------------------------------------------------------------------------
# Bit-layout visualiser helpers  (Feature #3)
# ---------------------------------------------------------------------------

_BIT_COLORS = [
    "#58a6ff", "#3fb950", "#d29922", "#f85149", "#8957e5",
    "#39d353", "#ff7b72", "#ffa657", "#79c0ff", "#56d364",
]


def _build_signal_bit_map(msg) -> dict[int, str]:
    """Return {bit_position: signal_name} for every bit in msg."""
    bit_map: dict[int, str] = {}
    for sig in msg.signals:
        for i in range(sig.length):
            bit_map[sig.start + i] = sig.name
    return bit_map


def _render_bit_panel(title: str, msg, color_map: dict[str, str]) -> str:
    """Render one side (old or new) of the bit-layout grid as HTML."""
    total_bits = msg.length * 8
    bit_map = _build_signal_bit_map(msg)
    cells = []
    for bit in range(total_bits):
        sig_name = bit_map.get(bit)
        if sig_name:
            bg = color_map.get(sig_name, "#58a6ff")
            cells.append(
                f'<div class="bit-cell" style="background:{bg}" '
                f'title="{html.escape(sig_name)} bit {bit}">{bit % 8}</div>'
            )
        else:
            cells.append(f'<div class="bit-cell unused">{bit % 8}</div>')
    grid = "\n    ".join(cells)
    legend_items = ""
    for sig_name, color in color_map.items():
        legend_items += (
            f'<div class="bit-legend-item">'
            f'<div class="bit-legend-swatch" style="background:{color}"></div>'
            f'{html.escape(sig_name)}</div>'
        )
    return (
        f'<div class="bit-panel"><h4>{html.escape(title)}</h4>'
        f'<div class="bit-grid">\n    {grid}\n</div>'
        f'<div class="bit-legend">{legend_items}</div></div>'
    )


def _build_bit_sections(entries: list[DiffEntry], db_a, db_b) -> str:
    """Build HTML for changed messages' bit-layout side-by-side panels."""
    changed_msg_names = {
        e.entity
        for e in entries
        if e.kind == CHANGED and e.path.split(".")[0] == e.entity
    }
    if not changed_msg_names:
        return ""
    sections = []
    msg_map_a = {m.name: m for m in db_a.messages}
    msg_map_b = {m.name: m for m in db_b.messages}
    for name in sorted(changed_msg_names):
        ma = msg_map_a.get(name)
        mb = msg_map_b.get(name)
        if not ma or not mb:
            continue
        all_sigs = sorted({s.name for s in ma.signals} | {s.name for s in mb.signals})
        color_map = {
            sig: _BIT_COLORS[i % len(_BIT_COLORS)]
            for i, sig in enumerate(all_sigs)
        }
        panel_a = _render_bit_panel("File A", ma, color_map)
        panel_b = _render_bit_panel("File B", mb, color_map)
        sections.append(
            f'<div class="bit-section">'
            f'<h3>Bit Layout: {html.escape(name)}</h3>'
            f'<div class="bit-panels">{panel_a}{panel_b}</div>'
            f'</div>'
        )
    return "\n".join(sections)
