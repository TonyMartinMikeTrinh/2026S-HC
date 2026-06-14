"""Render a :class:`~smarthome.benchmark.runner.BenchmarkReport` to HTML.

The same renderer powers both the dashboard ``/benchmark`` tab (as an injected
fragment) and the standalone ``python run.py benchmark`` report (a self-contained
page). Charts are plain CSS bars + tables — no external assets — matching the
demonstrator's dependency-free, local-first dashboard.
"""
from __future__ import annotations

import html

from .runner import ArchResult, BenchmarkReport

_COLOR = {"edge": "#3fb950", "cloud": "#4aa3ff", "hybrid": "#d29922"}


def _color(key: str) -> str:
    return _COLOR.get(key, "#8b98a5")


def _esc(s: object) -> str:
    return html.escape(str(s))


def _yn(value: bool, *, true_bad: bool = False) -> str:
    """Render a boolean as a coloured Yes/No chip."""
    good = (not value) if true_bad else value
    cls = "ok" if good else "bad"
    return f'<span class="bench-chip {cls}">{"yes" if value else "no"}</span>'


# --- chart primitives ------------------------------------------------------
def _bars(rows: list[tuple[str, float, str, str]]) -> str:
    """rows = [(label, width_pct, value_text, color)] -> a CSS bar group."""
    out = ['<div class="bench-bars">']
    for label, pct, value, color in rows:
        pct = max(0.0, min(100.0, pct))
        out.append(
            f'<div class="bench-bar"><span class="bench-lbl">{_esc(label)}</span>'
            f'<span class="bench-track"><span class="bench-fill" '
            f'style="width:{pct:.1f}%;background:{color}"></span></span>'
            f'<span class="bench-val">{_esc(value)}</span></div>')
    out.append("</div>")
    return "".join(out)


def _card(title: str, subtitle: str, body: str) -> str:
    return (f'<div class="bench-card"><h3>{_esc(title)}</h3>'
            f'<div class="bench-sub">{_esc(subtitle)}</div>{body}</div>')


# --- sections --------------------------------------------------------------
def _success_chart(archs: list[ArchResult]) -> str:
    rows = [(a.profile["label"], a.normal.success_pct, f'{a.normal.success_pct:g}%',
             _color(a.profile["key"])) for a in archs]
    return _card("Success rate over the test suite",
                 "correct device actions ÷ all prompts · normal operation · higher is better",
                 _bars(rows))


def _latency_chart(archs: list[ArchResult]) -> str:
    peak = max((a.normal.avg_latency_ms for a in archs), default=1.0) or 1.0
    rows = [(a.profile["label"], 100.0 * a.normal.avg_latency_ms / peak,
             f'{a.normal.avg_latency_ms:g} ms', _color(a.profile["key"]))
            for a in archs]
    return _card("Average response latency",
                 "modelled compute + network per request · normal operation · lower is better",
                 _bars(rows))


def _robustness_chart(archs: list[ArchResult]) -> str:
    rows: list[tuple[str, float, str, str]] = []
    for a in archs:
        c = _color(a.profile["key"])
        rows.append((f'{a.profile["label"]} — normal', a.normal.success_pct,
                     f'{a.normal.success_pct:g}%', c))
        rows.append((f'{a.profile["label"]} — outage', a.outage.success_pct,
                     f'{a.outage.success_pct:g}%', "#5a6b7b"))
    return _card("Robustness — success during a cloud/uplink outage",
                 "same suite with the cloud unreachable · local-first variants stay up",
                 _bars(rows))


def _profile_table(archs: list[ArchResult]) -> str:
    head = ("<tr><th>Architecture</th><th>Inference site</th><th>Net latency</th>"
            "<th>Cloud-dependent</th><th>Data leaves home</th><th>Local fallback</th>"
            "<th>Success<br>(normal)</th><th>Success<br>(outage)</th>"
            "<th>Avg latency</th></tr>")
    rows = []
    for a in archs:
        p = a.profile
        dot = f'<span class="bench-dot" style="background:{_color(p["key"])}"></span>'
        rows.append(
            f"<tr><td>{dot}{_esc(p['label'])}</td><td>{_esc(p['site'])}</td>"
            f"<td>{p['net_latency_ms']:g} ms</td>"
            f"<td>{_yn(p['cloud_dependent'], true_bad=True)}</td>"
            f"<td>{_yn(p['data_egress'], true_bad=True)}</td>"
            f"<td>{_yn(p['has_fallback'])}</td>"
            f"<td>{a.normal.success_pct:g}%</td>"
            f"<td>{a.outage.success_pct:g}%</td>"
            f"<td>{a.normal.avg_latency_ms:g} ms</td></tr>")
    return (_card("Architecture trade-offs", "the inference path for each variant",
                  f'<table class="bench-table"><thead>{head}</thead>'
                  f'<tbody>{"".join(rows)}</tbody></table>'))


def _case_matrix(archs: list[ArchResult]) -> str:
    head = "<tr><th>Prompt</th>" + "".join(
        f'<th>{_esc(a.profile["label"])}</th>' for a in archs) + "</tr>"
    # All architectures share the same case order/ids.
    base = archs[0].normal.cases
    rows = []
    for i, case in enumerate(base):
        cells = []
        for a in archs:
            r = a.normal.cases[i]
            if not r.served:
                mark = '<span class="bench-mark off">—</span>'
            elif r.correct:
                mark = '<span class="bench-mark ok">✓</span>'
            else:
                mark = '<span class="bench-mark bad">✗</span>'
            cells.append(f"<td>{mark}</td>")
        rows.append(f'<tr><td class="bench-prompt">{_esc(case.text)}</td>'
                    f'{"".join(cells)}</tr>')
    legend = ('<div class="bench-sub">'
              '<span class="bench-mark ok">✓</span> correct action · '
              '<span class="bench-mark bad">✗</span> wrong / missed · '
              '<span class="bench-mark off">—</span> unavailable</div>')
    return _card("Per-prompt results (normal operation)",
                 "where each architecture's model succeeds or fails",
                 legend + f'<table class="bench-table bench-matrix"><thead>{head}'
                 f'</thead><tbody>{"".join(rows)}</tbody></table>')


def _bench_style() -> str:
    return """
<style>
.bench{--b-ok:#3fb950;--b-bad:#f85149;--b-dim:#8b98a5;--b-line:#2c3a4a;
       --b-panel:#1a222c;--b-panel2:#222d3a;--b-txt:#e6edf3;color:var(--b-txt)}
.bench *{box-sizing:border-box}
.bench-meta{color:var(--b-dim);font-size:12px;margin:0 0 14px}
.bench-meta b{color:var(--b-txt)}
.bench-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px;margin-bottom:14px}
.bench-card{background:var(--b-panel);border:1px solid var(--b-line);border-radius:10px;padding:14px}
.bench-card h3{margin:0 0 2px;font-size:14px}
.bench-sub{color:var(--b-dim);font-size:11px;margin-bottom:10px}
.bench-bars{display:flex;flex-direction:column;gap:8px}
.bench-bar{display:flex;align-items:center;gap:10px;font-size:12px}
.bench-lbl{flex:0 0 150px;color:var(--b-dim);text-align:right;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bench-track{flex:1;height:14px;background:var(--b-panel2);border-radius:7px;overflow:hidden}
.bench-fill{display:block;height:100%;border-radius:7px;min-width:2px;transition:width .4s ease}
.bench-val{flex:0 0 64px;font-variant-numeric:tabular-nums}
.bench-table{width:100%;border-collapse:collapse;font-size:12px;margin-top:4px}
.bench-table th,.bench-table td{padding:6px 8px;border-bottom:1px solid var(--b-line);text-align:left}
.bench-table th{color:var(--b-dim);font-weight:600;font-size:11px}
.bench-matrix td,.bench-matrix th{text-align:center}
.bench-matrix .bench-prompt{text-align:left;color:var(--b-txt)}
.bench-prompt{max-width:320px}
.bench-chip{font-size:10px;padding:1px 7px;border-radius:6px;border:1px solid var(--b-line)}
.bench-chip.ok{color:var(--b-ok)} .bench-chip.bad{color:var(--b-bad)}
.bench-mark{font-weight:700}
.bench-mark.ok{color:var(--b-ok)} .bench-mark.bad{color:var(--b-bad)} .bench-mark.off{color:var(--b-dim)}
.bench-dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px;vertical-align:middle}
</style>"""


def render_report_html(report: BenchmarkReport, *, full_page: bool = False) -> str:
    """Render the report. ``full_page`` wraps it in a standalone HTML document."""
    archs = report.architectures
    meta = (f'<div class="bench-meta"><b>{report.suite_size}</b> prompts · '
            f'<b>{report.world_devices}</b> devices in <b>{report.world_rooms}</b> rooms · '
            f'seed <b>{report.seed}</b> · generated {_esc(report.generated_at)} · '
            "correctness is measured against gold intents; latency is a "
            "reproducible model that scales with home size</div>")
    body = (f'<div class="bench">{_bench_style()}{meta}'
            f'<div class="bench-grid">{_success_chart(archs)}{_latency_chart(archs)}'
            f'{_robustness_chart(archs)}</div>'
            f'{_profile_table(archs)}{_case_matrix(archs)}</div>')

    if not full_page:
        return body

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Smart-Home — Architecture Benchmark</title>
<style>body{{margin:0;background:#0f1419;color:#e6edf3;
font:14px/1.4 system-ui,Segoe UI,Roboto,sans-serif}}
header{{padding:14px 20px;background:#1a222c;border-bottom:1px solid #2c3a4a}}
header h1{{font-size:17px;margin:0}} header .s{{color:#8b98a5;font-size:12px}}
main{{padding:18px;max-width:1100px;margin:0 auto}}</style></head>
<body><header><h1>🏠 Smart-Home — Architecture Benchmark</h1>
<span class="s">Inference location trade-offs: edge · cloud · hybrid</span></header>
<main>{body}</main></body></html>"""


def print_console_summary(report: BenchmarkReport) -> None:
    """Print a compact comparison table to the terminal (rich)."""
    from rich.console import Console
    from rich.table import Table

    table = Table(title=f"Architecture benchmark · {report.suite_size} prompts · seed {report.seed}")
    table.add_column("Architecture")
    table.add_column("Success\n(normal)", justify="right")
    table.add_column("Success\n(outage)", justify="right")
    table.add_column("Avail.\n(outage)", justify="right")
    table.add_column("Avg latency", justify="right")
    table.add_column("Data egress", justify="center")
    for a in report.architectures:
        p = a.profile
        table.add_row(
            p["label"],
            f"{a.normal.success_pct:g}%",
            f"{a.outage.success_pct:g}%",
            f"{a.outage.availability_pct:g}%",
            f"{a.normal.avg_latency_ms:g} ms",
            "yes" if p["data_egress"] else "no",
        )
    Console().print(table)
