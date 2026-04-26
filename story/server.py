#!/usr/bin/env python3
"""Lightweight API server for the story site's live tracker lookup."""

import json
import sqlite3
from pathlib import Path

from flask import Flask, send_from_directory, g, jsonify, request

app = Flask(__name__, static_folder=".", static_url_path="")
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


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/api/site/<path:domain>")
def site_lookup(domain):
    db = get_db()
    domain = domain.strip().lower()

    site = db.execute("SELECT id, fqdn FROM site WHERE fqdn = ?", (domain,)).fetchone()
    if not site:
        return jsonify({"error": "Site not found"}), 404

    site_id = site["id"]

    # Latest no-blocking scan trackers
    latest_nb = db.execute(
        "SELECT id FROM scan WHERE no_blocking = 1 ORDER BY start_time DESC LIMIT 1"
    ).fetchone()
    if not latest_nb:
        return jsonify({"error": "No scan data available"}), 404

    trackers = [dict(r) for r in db.execute("""
        SELECT t.base AS tracker,
               COALESCE(tt.name, 'unknown') AS type
        FROM tracking tr
        JOIN tracker t ON t.id = tr.tracker_id
        LEFT JOIN tracking_type tt ON tt.id = tr.tracking_type_id
        WHERE tr.scan_id = ? AND tr.site_id = ?
        ORDER BY t.base
    """, (latest_nb["id"], site_id)).fetchall()]

    # Tracker count trend (monthly)
    trend = [dict(r) for r in db.execute("""
        SELECT strftime('%Y-%m', s.start_time) AS month,
               COUNT(DISTINCT tr.tracker_id) AS trackers
        FROM tracking tr
        JOIN scan s ON s.id = tr.scan_id
        WHERE tr.site_id = ? AND s.no_blocking = 1
        GROUP BY month ORDER BY month
    """, (site_id,)).fetchall()]

    # Percentile among all sites in latest scan
    all_counts = db.execute("""
        SELECT COUNT(DISTINCT tracker_id) AS cnt
        FROM tracking WHERE scan_id = ?
        GROUP BY site_id ORDER BY cnt
    """, (latest_nb["id"],)).fetchall()
    all_counts = [r["cnt"] for r in all_counts]
    this_count = len(set(t["tracker"] for t in trackers))
    below = sum(1 for c in all_counts if c < this_count)
    percentile = round(100 * below / len(all_counts)) if all_counts else 0

    # Top co-trackers (other trackers commonly seen with this site's trackers)
    tracker_names = [t["tracker"] for t in trackers]

    return jsonify({
        "domain": domain,
        "tracker_count": this_count,
        "trackers": trackers,
        "trend": trend,
        "percentile": percentile,
        "total_sites_in_scan": len(all_counts),
    })


@app.route("/api/search")
def site_search():
    q = request.args.get("q", "").strip().lower()
    if len(q) < 2:
        return jsonify([])

    db = get_db()

    # Sites that have tracking data in the latest no-blocking scan
    latest_nb = db.execute(
        "SELECT id FROM scan WHERE no_blocking = 1 ORDER BY start_time DESC LIMIT 1"
    ).fetchone()

    results = db.execute("""
        SELECT DISTINCT si.fqdn
        FROM site si
        JOIN tracking tr ON tr.site_id = si.id
        WHERE tr.scan_id = ? AND si.fqdn LIKE ?
        ORDER BY
            CASE WHEN si.fqdn LIKE ? THEN 0 ELSE 1 END,
            si.fqdn
        LIMIT 8
    """, (latest_nb["id"], f"%{q}%", f"{q}%")).fetchall()

    return jsonify([r["fqdn"] for r in results])


if __name__ == "__main__":
    app.run(debug=True, port=5001)
