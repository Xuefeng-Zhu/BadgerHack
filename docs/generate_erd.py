#!/usr/bin/env python3
"""Generate an ER diagram for the Badger Sett database."""

import graphviz

dot = graphviz.Digraph("BadgerSett", format="svg", engine="dot")
dot.attr(rankdir="LR", bgcolor="#0f1117", pad="0.5",
         fontname="Helvetica", nodesep="0.8", ranksep="1.2")
dot.attr("node", shape="none", fontname="Helvetica", fontsize="11")
dot.attr("edge", color="#6c8cff", fontcolor="#8b8fa3", fontsize="9",
         arrowsize="0.7", penwidth="1.2")


def table(name, columns, color="#6c8cff"):
    """Build an HTML-like label for a table node."""
    header_bg = color
    rows = ""
    for col_name, col_type, is_pk, is_fk in columns:
        prefix = ""
        if is_pk:
            prefix = '<font color="#4ade80">PK </font>'
        elif is_fk:
            prefix = '<font color="#fb923c">FK </font>'
        rows += (
            f'<tr><td align="left" bgcolor="#1a1d27">'
            f'  {prefix}<font color="#e1e4ed">{col_name}</font>'
            f'  <font color="#555"> {col_type}</font>'
            f'</td></tr>\n'
        )
    label = f'''<
    <table border="0" cellborder="0" cellspacing="0" cellpadding="6">
        <tr><td bgcolor="{header_bg}" align="center">
            <font color="#ffffff" point-size="13"><b>  {name}  </b></font>
        </td></tr>
        {rows}
    </table>>'''
    dot.node(name, label=label)


# ── Tables ───────────────────────────────────────────────────────────────

table("browser", [
    ("id", "INTEGER", True, False),
    ("name", "VARCHAR(20)", False, False),
], color="#4ade80")

table("scan", [
    ("id", "INTEGER", True, False),
    ("start_time", "TIMESTAMP", False, False),
    ("end_time", "TIMESTAMP", False, False),
    ("region", "VARCHAR(4)", False, False),
    ("num_sites", "INTEGER", False, False),
    ("browser_id", "INTEGER", False, True),
    ("no_blocking", "BOOLEAN", False, False),
    ("daily_scan", "BOOLEAN", False, False),
], color="#6c8cff")

table("site", [
    ("id", "INTEGER", True, False),
    ("fqdn", "VARCHAR(200)", False, False),
], color="#4ade80")

table("site_status", [
    ("id", "INTEGER", True, False),
    ("name", "VARCHAR(20)", False, False),
], color="#4ade80")

table("error", [
    ("id", "INTEGER", True, False),
    ("name", "VARCHAR(200)", False, False),
], color="#4ade80")

table("tracker", [
    ("id", "INTEGER", True, False),
    ("base", "VARCHAR(200)", False, False),
], color="#4ade80")

table("tracking_type", [
    ("id", "INTEGER", True, False),
    ("name", "VARCHAR(50)", False, False),
], color="#4ade80")

table("scan_sites", [
    ("scan_id", "INTEGER", False, True),
    ("initial_site_id", "INTEGER", False, True),
    ("final_site_id", "INTEGER", False, True),
    ("status_id", "INTEGER", False, True),
    ("error_id", "INTEGER", False, True),
    ("start_time", "TIMESTAMP", False, False),
    ("end_time", "TIMESTAMP", False, False),
], color="#fb923c")

table("scan_crashes", [
    ("scan_id", "INTEGER", False, True),
    ("error_id", "INTEGER", False, True),
    ("time", "TIMESTAMP", False, False),
], color="#fb923c")

table("tracking", [
    ("scan_id", "INTEGER", False, True),
    ("site_id", "INTEGER", False, True),
    ("tracker_id", "INTEGER", False, True),
    ("tracking_type_id", "INTEGER", False, True),
], color="#fb923c")

# ── Relationships ────────────────────────────────────────────────────────

dot.edge("scan", "browser", label="browser_id", style="dashed")

dot.edge("scan_sites", "scan", label="scan_id")
dot.edge("scan_sites", "site", label="initial_site_id")
dot.edge("scan_sites", "site", label="final_site_id")
dot.edge("scan_sites", "site_status", label="status_id")
dot.edge("scan_sites", "error", label="error_id", style="dashed")

dot.edge("scan_crashes", "scan", label="scan_id")
dot.edge("scan_crashes", "error", label="error_id")

dot.edge("tracking", "scan", label="scan_id")
dot.edge("tracking", "site", label="site_id")
dot.edge("tracking", "tracker", label="tracker_id")
dot.edge("tracking", "tracking_type", label="tracking_type_id", style="dashed")

dot.render("docs/erd", cleanup=True)
print("Generated docs/erd.svg")

dot.format = "png"
dot.attr(dpi="150")
dot.render("docs/erd", cleanup=True)
print("Generated docs/erd.png")
