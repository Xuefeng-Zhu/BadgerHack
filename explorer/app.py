#!/usr/bin/env python3

"""Badger Sett Data Explorer — a web dashboard for browsing tracker data."""

import json
import sqlite3
from pathlib import Path

import plotly
import plotly.graph_objects as go
from flask import Flask, g, render_template, request, jsonify

app = Flask(__name__)
DB_PATH = Path(__file__).parent.parent / "badger.sqlite3"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(str(DB_PATH))
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ── helpers ──────────────────────────────────────────────────────────────

def to_plotly_json(fig):
    """Serialize a Plotly figure to JSON for the template."""
    return json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)


# ── routes ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    db = get_db()

    # summary stats
    stats = {}
    for label, query in [
        ("scans", "SELECT COUNT(*) FROM scan"),
        ("sites", "SELECT COUNT(DISTINCT fqdn) FROM site"),
        ("trackers", "SELECT COUNT(DISTINCT base) FROM tracker"),
        ("tracking_records", "SELECT COUNT(*) FROM tracking"),
    ]:
        stats[label] = f"{db.execute(query).fetchone()[0]:,}"

    date_range = db.execute(
        "SELECT MIN(start_time), MAX(start_time) FROM scan"
    ).fetchone()
    stats["date_from"] = date_range[0][:10]
    stats["date_to"] = date_range[1][:10]

    # scans over time by browser
    rows = db.execute("""
        SELECT strftime('%Y-%m', s.start_time) AS month,
               b.name AS browser, COUNT(*) AS cnt
        FROM scan s JOIN browser b ON b.id = s.browser_id
        GROUP BY month, browser ORDER BY month
    """).fetchall()
    months = sorted(set(r["month"] for r in rows))
    browsers = sorted(set(r["browser"] for r in rows))
    scan_fig = go.Figure()
    for br in browsers:
        counts = {r["month"]: r["cnt"] for r in rows if r["browser"] == br}
        scan_fig.add_trace(go.Bar(
            x=months, y=[counts.get(m, 0) for m in months], name=br))
    scan_fig.update_layout(
        barmode="stack", title="Scans per Month by Browser",
        xaxis_title="Month", yaxis_title="Scans",
        margin=dict(t=40, b=40, l=50, r=20), height=350,
        legend=dict(orientation="h", y=1.12))

    # top 20 trackers (last 365 days)
    top_trackers = db.execute("""
        SELECT t.base, COUNT(DISTINCT tr.site_id) AS site_count
        FROM tracking tr
        JOIN tracker t ON t.id = tr.tracker_id
        JOIN scan s ON s.id = tr.scan_id
        WHERE s.start_time >= date('now', '-365 days')
        GROUP BY t.base ORDER BY site_count DESC LIMIT 20
    """).fetchall()
    tracker_fig = go.Figure(go.Bar(
        x=[r["site_count"] for r in reversed(top_trackers)],
        y=[r["base"] for r in reversed(top_trackers)],
        orientation="h"))
    tracker_fig.update_layout(
        title="Top 20 Trackers (sites tracked, last 365 days)",
        xaxis_title="Unique Sites", margin=dict(t=40, b=40, l=160, r=20),
        height=500)

    # tracking types breakdown
    type_rows = db.execute("""
        SELECT COALESCE(tt.name, 'unknown') AS ttype, COUNT(*) AS cnt
        FROM tracking tr LEFT JOIN tracking_type tt ON tt.id = tr.tracking_type_id
        GROUP BY ttype ORDER BY cnt DESC
    """).fetchall()
    type_fig = go.Figure(go.Pie(
        labels=[r["ttype"] for r in type_rows],
        values=[r["cnt"] for r in type_rows],
        hole=0.4))
    type_fig.update_layout(
        title="Tracking Types", margin=dict(t=40, b=20, l=20, r=20),
        height=350)

    # site visit status breakdown
    status_rows = db.execute("""
        SELECT ss.name, COUNT(*) AS cnt
        FROM scan_sites sc JOIN site_status ss ON ss.id = sc.status_id
        GROUP BY ss.name ORDER BY cnt DESC
    """).fetchall()
    status_fig = go.Figure(go.Pie(
        labels=[r["name"] for r in status_rows],
        values=[r["cnt"] for r in status_rows],
        hole=0.4))
    status_fig.update_layout(
        title="Site Visit Outcomes", margin=dict(t=40, b=20, l=20, r=20),
        height=350)

    return render_template("index.html",
        stats=stats,
        scan_chart=to_plotly_json(scan_fig),
        tracker_chart=to_plotly_json(tracker_fig),
        type_chart=to_plotly_json(type_fig),
        status_chart=to_plotly_json(status_fig))


@app.route("/trackers")
def trackers():
    db = get_db()
    search = request.args.get("q", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    per_page = 50

    where = ""
    params = []
    if search:
        where = "WHERE t.base LIKE ?"
        params = [f"%{search}%"]

    total = db.execute(
        f"SELECT COUNT(DISTINCT t.id) FROM tracker t {where}", params
    ).fetchone()[0]

    rows = db.execute(f"""
        SELECT t.base,
               COUNT(DISTINCT tr.site_id) AS site_count,
               COUNT(DISTINCT tr.scan_id) AS scan_count
        FROM tracker t
        JOIN tracking tr ON tr.tracker_id = t.id
        {where}
        GROUP BY t.id
        ORDER BY site_count DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, (page - 1) * per_page]).fetchall()

    return render_template("trackers.html",
        trackers=rows, search=search,
        page=page, per_page=per_page, total=total)


@app.route("/tracker/<path:domain>")
def tracker_detail(domain):
    db = get_db()

    tracker = db.execute(
        "SELECT id, base FROM tracker WHERE base = ?", (domain,)
    ).fetchone()
    if not tracker:
        return "Tracker not found", 404

    # prevalence over time (monthly unique sites)
    trend = db.execute("""
        SELECT strftime('%Y-%m', s.start_time) AS month,
               COUNT(DISTINCT tr.site_id) AS site_count
        FROM tracking tr
        JOIN scan s ON s.id = tr.scan_id
        WHERE tr.tracker_id = ?
        GROUP BY month ORDER BY month
    """, (tracker["id"],)).fetchall()

    trend_fig = go.Figure(go.Scatter(
        x=[r["month"] for r in trend],
        y=[r["site_count"] for r in trend],
        mode="lines+markers", fill="tozeroy"))
    trend_fig.update_layout(
        title=f"Sites tracking by {domain} over time",
        xaxis_title="Month", yaxis_title="Unique Sites",
        margin=dict(t=40, b=40, l=50, r=20), height=350)

    # top sites this tracker appears on
    top_sites = db.execute("""
        SELECT si.fqdn, COUNT(DISTINCT tr.scan_id) AS scan_count
        FROM tracking tr
        JOIN site si ON si.id = tr.site_id
        WHERE tr.tracker_id = ?
        GROUP BY si.fqdn ORDER BY scan_count DESC LIMIT 50
    """, (tracker["id"],)).fetchall()

    # tracking types used
    types = db.execute("""
        SELECT COALESCE(tt.name, 'unknown') AS ttype, COUNT(*) AS cnt
        FROM tracking tr
        LEFT JOIN tracking_type tt ON tt.id = tr.tracking_type_id
        WHERE tr.tracker_id = ?
        GROUP BY ttype ORDER BY cnt DESC
    """, (tracker["id"],)).fetchall()

    return render_template("tracker_detail.html",
        tracker=tracker, top_sites=top_sites, types=types,
        trend_chart=to_plotly_json(trend_fig))


@app.route("/sites")
def sites():
    db = get_db()
    search = request.args.get("q", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    per_page = 50

    where = ""
    params = []
    if search:
        where = "WHERE si.fqdn LIKE ?"
        params = [f"%{search}%"]

    total = db.execute(
        f"SELECT COUNT(*) FROM site si {where}", params
    ).fetchone()[0]

    rows = db.execute(f"""
        SELECT si.fqdn,
               COUNT(DISTINCT tr.tracker_id) AS tracker_count,
               COUNT(DISTINCT tr.scan_id) AS scan_count
        FROM site si
        LEFT JOIN tracking tr ON tr.site_id = si.id
        {where}
        GROUP BY si.id
        ORDER BY tracker_count DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, (page - 1) * per_page]).fetchall()

    return render_template("sites.html",
        sites=rows, search=search,
        page=page, per_page=per_page, total=total)


@app.route("/site/<path:domain>")
def site_detail(domain):
    db = get_db()

    site = db.execute(
        "SELECT id, fqdn FROM site WHERE fqdn = ?", (domain,)
    ).fetchone()
    if not site:
        return "Site not found", 404

    # trackers on this site
    site_trackers = db.execute("""
        SELECT t.base, COUNT(DISTINCT tr.scan_id) AS scan_count,
               GROUP_CONCAT(DISTINCT COALESCE(tt.name, 'unknown')) AS types
        FROM tracking tr
        JOIN tracker t ON t.id = tr.tracker_id
        LEFT JOIN tracking_type tt ON tt.id = tr.tracking_type_id
        WHERE tr.site_id = ?
        GROUP BY t.base ORDER BY scan_count DESC LIMIT 100
    """, (site["id"],)).fetchall()

    # tracker count over time
    trend = db.execute("""
        SELECT strftime('%Y-%m', s.start_time) AS month,
               COUNT(DISTINCT tr.tracker_id) AS tracker_count
        FROM tracking tr
        JOIN scan s ON s.id = tr.scan_id
        WHERE tr.site_id = ?
        GROUP BY month ORDER BY month
    """, (site["id"],)).fetchall()

    trend_fig = go.Figure(go.Scatter(
        x=[r["month"] for r in trend],
        y=[r["tracker_count"] for r in trend],
        mode="lines+markers", fill="tozeroy"))
    trend_fig.update_layout(
        title=f"Trackers on {domain} over time",
        xaxis_title="Month", yaxis_title="Unique Trackers",
        margin=dict(t=40, b=40, l=50, r=20), height=350)

    # visit history
    visits = db.execute("""
        SELECT s.start_time, ss.name AS status,
               si2.fqdn AS final_domain
        FROM scan_sites sc
        JOIN scan s ON s.id = sc.scan_id
        JOIN site_status ss ON ss.id = sc.status_id
        JOIN site si2 ON si2.id = sc.final_site_id
        WHERE sc.initial_site_id = ?
        ORDER BY s.start_time DESC LIMIT 50
    """, (site["id"],)).fetchall()

    return render_template("site_detail.html",
        site=site, trackers=site_trackers, visits=visits,
        trend_chart=to_plotly_json(trend_fig))


@app.route("/query", methods=["GET", "POST"])
def query():
    results = None
    columns = None
    sql = ""
    error = None
    row_count = 0

    if request.method == "POST":
        sql = request.form.get("sql", "").strip()
        if sql:
            # basic safety: only allow SELECT
            if not sql.upper().startswith("SELECT"):
                error = "Only SELECT queries are allowed."
            else:
                try:
                    db = get_db()
                    cur = db.execute(sql + (" LIMIT 500" if "limit" not in sql.lower() else ""))
                    columns = [desc[0] for desc in cur.description] if cur.description else []
                    results = cur.fetchall()
                    row_count = len(results)
                except Exception as e:
                    error = str(e)

    # provide schema info
    db = get_db()
    schema = db.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence' ORDER BY name"
    ).fetchall()

    return render_template("query.html",
        sql=sql, results=results, columns=columns,
        error=error, row_count=row_count, schema=schema)


if __name__ == "__main__":
    app.run(debug=True, port=5001)
