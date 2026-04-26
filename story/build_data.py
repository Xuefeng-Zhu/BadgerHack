#!/usr/bin/env python3
"""Pre-compute all data needed for the scrollytelling site from badger.sqlite3."""

import json
import sqlite3
from pathlib import Path

DB = Path(__file__).parent.parent / "badger.sqlite3"
OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)

db = sqlite3.connect(str(DB))
db.row_factory = sqlite3.Row


def query(sql, params=()):
    return [dict(r) for r in db.execute(sql, params).fetchall()]


# ── 1. Summary stats ────────────────────────────────────────────────────

stats = {}
stats["total_scans"] = db.execute("SELECT COUNT(*) FROM scan").fetchone()[0]
stats["total_sites"] = db.execute("SELECT COUNT(DISTINCT fqdn) FROM site").fetchone()[0]
stats["total_trackers"] = db.execute("SELECT COUNT(DISTINCT base) FROM tracker").fetchone()[0]
stats["total_tracking"] = db.execute("SELECT COUNT(*) FROM tracking").fetchone()[0]

date_range = db.execute("SELECT MIN(start_time), MAX(start_time) FROM scan").fetchone()
stats["date_from"] = date_range[0][:10]
stats["date_to"] = date_range[1][:10]

# Use no-blocking scans for true tracking picture (no Privacy Badger interference)
latest_nb = db.execute(
    "SELECT id FROM scan WHERE no_blocking = 1 ORDER BY start_time DESC LIMIT 1"
).fetchone()[0]
earliest_nb = db.execute(
    "SELECT id FROM scan WHERE no_blocking = 1 ORDER BY start_time ASC LIMIT 1"
).fetchone()[0]

# Also keep a blocking scan for the site checker
latest_scan = db.execute(
    "SELECT id FROM scan WHERE no_blocking = 0 ORDER BY start_time DESC LIMIT 1"
).fetchone()[0]

for label, scan_id in [("latest", latest_nb), ("earliest", earliest_nb)]:
    avg = db.execute("""
        SELECT AVG(cnt) FROM (
            SELECT COUNT(DISTINCT tracker_id) AS cnt
            FROM tracking WHERE scan_id = ?
            GROUP BY site_id
        )
    """, (scan_id,)).fetchone()[0]
    stats[f"avg_trackers_{label}"] = round(avg, 1)

    total_sites = db.execute(
        "SELECT COUNT(DISTINCT site_id) FROM tracking WHERE scan_id = ?", (scan_id,)
    ).fetchone()[0]
    scanned = db.execute("SELECT num_sites FROM scan WHERE id = ?", (scan_id,)).fetchone()[0]
    stats[f"pct_with_trackers_{label}"] = round(100 * total_sites / scanned)

earliest_date = db.execute("SELECT start_time FROM scan WHERE id = ?", (earliest_nb,)).fetchone()[0][:4]
stats["earliest_year"] = earliest_date

# Google's reach
google_reach = db.execute("""
    SELECT COUNT(DISTINCT tr.site_id) FROM tracking tr
    JOIN tracker t ON t.id = tr.tracker_id
    WHERE tr.scan_id = ? AND t.base = 'google.com'
""", (latest_nb,)).fetchone()[0]
total_tracked = db.execute(
    "SELECT COUNT(DISTINCT site_id) FROM tracking WHERE scan_id = ?", (latest_nb,)
).fetchone()[0]
stats["google_pct"] = round(100 * google_reach / total_tracked)

with open(OUT / "stats.json", "w") as f:
    json.dump(stats, f, indent=2)
print("✓ stats.json")


# ── 2. Top 25 trackers (last 365 days) ─────────────────────────────────

top_trackers = query("""
    SELECT t.base AS name, COUNT(DISTINCT tr.site_id) AS sites
    FROM tracking tr
    JOIN tracker t ON t.id = tr.tracker_id
    JOIN scan s ON s.id = tr.scan_id
    WHERE s.start_time >= date('now', '-365 days') AND s.no_blocking = 0
    GROUP BY t.base ORDER BY sites DESC LIMIT 25
""")

with open(OUT / "top_trackers.json", "w") as f:
    json.dump(top_trackers, f, indent=2)
print("✓ top_trackers.json")


# ── 3. Tracker prevalence over time (monthly, top 10) ──────────────────

top10_names = [r["name"] for r in top_trackers[:10]]
placeholders = ",".join("?" * len(top10_names))

# First get total tracked sites per scan (no-blocking scans show true tracking)
scan_totals = {r["id"]: r["total"] for r in query("""
    SELECT s.id, COUNT(DISTINCT tr.site_id) AS total
    FROM scan s JOIN tracking tr ON tr.scan_id = s.id
    WHERE s.no_blocking = 1
    GROUP BY s.id
""")}

# Then get per-tracker per-scan counts
raw = query(f"""
    SELECT s.id AS scan_id,
           strftime('%Y-%m', s.start_time) AS month,
           t.base AS name,
           COUNT(DISTINCT tr.site_id) AS sites
    FROM tracking tr
    JOIN tracker t ON t.id = tr.tracker_id
    JOIN scan s ON s.id = tr.scan_id
    WHERE t.base IN ({placeholders}) AND s.no_blocking = 1
    GROUP BY s.id, t.base
    ORDER BY month
""", top10_names)

# Compute percentage and average by month
from collections import defaultdict
month_data = defaultdict(lambda: defaultdict(list))
for row in raw:
    total = scan_totals.get(row["scan_id"], 1)
    pct = round(100.0 * row["sites"] / total, 1)
    month_data[row["name"]][row["month"]].append(pct)

trends = []
for name in top10_names:
    for m in sorted(month_data[name].keys()):
        vals = month_data[name][m]
        trends.append({
            "month": m,
            "name": name,
            "pct": round(sum(vals) / len(vals), 1)
        })

with open(OUT / "tracker_trends.json", "w") as f:
    json.dump(trends, f, indent=2)
print("✓ tracker_trends.json")


# ── 4. Tracking scale over time ──────────────────────────────────────

# No-blocking: distribution of tracker counts + comparison with blocking
scale_data = query("""
    SELECT strftime('%Y-%m', s.start_time) AS month,
           s.no_blocking,
           COUNT(*) AS total_sites,
           SUM(CASE WHEN cnt = 0 THEN 1 ELSE 0 END) AS zero,
           SUM(CASE WHEN cnt BETWEEN 1 AND 4 THEN 1 ELSE 0 END) AS low,
           SUM(CASE WHEN cnt BETWEEN 5 AND 9 THEN 1 ELSE 0 END) AS medium,
           SUM(CASE WHEN cnt BETWEEN 10 AND 19 THEN 1 ELSE 0 END) AS high,
           SUM(CASE WHEN cnt >= 20 THEN 1 ELSE 0 END) AS extreme,
           ROUND(AVG(cnt), 1) AS avg_trackers
    FROM (
        SELECT tr.scan_id, tr.site_id, COUNT(DISTINCT tr.tracker_id) AS cnt
        FROM tracking tr GROUP BY tr.scan_id, tr.site_id
    ) sub
    JOIN scan s ON s.id = sub.scan_id
    GROUP BY month, s.no_blocking
    ORDER BY month
""")

# Separate into no-blocking (true picture) and blocking (with PB)
tracking_scale = {
    "no_blocking": [],
    "blocking": []
}
for row in scale_data:
    t = row["total_sites"]
    entry = {
        "month": row["month"],
        "avg": row["avg_trackers"],
        "pct_low": round(100 * row["low"] / t, 1),
        "pct_medium": round(100 * row["medium"] / t, 1),
        "pct_high": round(100 * row["high"] / t, 1),
        "pct_extreme": round(100 * row["extreme"] / t, 1),
    }
    key = "no_blocking" if row["no_blocking"] else "blocking"
    tracking_scale[key].append(entry)

with open(OUT / "tracking_scale.json", "w") as f:
    json.dump(tracking_scale, f, indent=2)
print("✓ tracking_scale.json")


# ── 5. Tracking types breakdown ─────────────────────────────────────────

types = query("""
    SELECT COALESCE(tt.name, 'unknown') AS name, COUNT(*) AS count
    FROM tracking tr
    LEFT JOIN tracking_type tt ON tt.id = tr.tracking_type_id
    GROUP BY name ORDER BY count DESC
""")

with open(OUT / "tracking_types.json", "w") as f:
    json.dump(types, f, indent=2)
print("✓ tracking_types.json")


# ── 6. Tracker concentration — top N trackers cover X% of observations ──

total_obs = db.execute("""
    SELECT COUNT(*) FROM tracking tr
    JOIN scan s ON s.id = tr.scan_id WHERE s.no_blocking = 0
""").fetchone()[0]

concentration = query("""
    SELECT t.base AS name, COUNT(*) AS observations
    FROM tracking tr
    JOIN tracker t ON t.id = tr.tracker_id
    JOIN scan s ON s.id = tr.scan_id
    WHERE s.no_blocking = 0
    GROUP BY t.base ORDER BY observations DESC LIMIT 50
""")

running = 0
for row in concentration:
    running += row["observations"]
    row["cumulative_pct"] = round(100 * running / total_obs, 1)

with open(OUT / "concentration.json", "w") as f:
    json.dump(concentration, f, indent=2)
print("✓ concentration.json")


# ── 7. Per-site tracker data (for site lookup) ─────────────────────────

# Use no-blocking scan for the site checker (shows true tracking)
site_data = query("""
    SELECT si.fqdn AS site,
           t.base AS tracker,
           COALESCE(tt.name, 'unknown') AS type
    FROM tracking tr
    JOIN site si ON si.id = tr.site_id
    JOIN tracker t ON t.id = tr.tracker_id
    LEFT JOIN tracking_type tt ON tt.id = tr.tracking_type_id
    WHERE tr.scan_id = ?
    ORDER BY si.fqdn, t.base
""", (latest_nb,))

# Group by site
site_lookup = {}
for row in site_data:
    site = row["site"]
    if site not in site_lookup:
        site_lookup[site] = {"trackers": [], "types": set()}
    site_lookup[site]["trackers"].append(row["tracker"])
    site_lookup[site]["types"].add(row["type"])

# Convert sets to lists and compute counts
site_index = {}
for site, data in site_lookup.items():
    unique_trackers = sorted(set(data["trackers"]))
    site_index[site] = {
        "count": len(unique_trackers),
        "trackers": unique_trackers[:20],  # top 20 for display
        "total": len(unique_trackers),
        "types": sorted(data["types"])
    }

# Add per-site tracker count trends (monthly, no-blocking scans only)
print("  Computing per-site trends...")
site_ids = {row["fqdn"]: row["id"] for row in query(
    "SELECT id, fqdn FROM site WHERE fqdn IN ({})".format(
        ",".join("?" * len(site_index))), list(site_index.keys()))}

trend_rows = query("""
    SELECT tr.site_id, strftime('%Y-%m', s.start_time) AS month,
           COUNT(DISTINCT tr.tracker_id) AS trackers
    FROM tracking tr
    JOIN scan s ON s.id = tr.scan_id
    WHERE s.no_blocking = 1
    GROUP BY tr.site_id, month
    ORDER BY tr.site_id, month
""")

# Index trends by site_id
site_id_to_fqdn = {v: k for k, v in site_ids.items()}
for row in trend_rows:
    fqdn = site_id_to_fqdn.get(row["site_id"])
    if fqdn and fqdn in site_index:
        if "trend" not in site_index[fqdn]:
            site_index[fqdn]["trend"] = []
        site_index[fqdn]["trend"].append({
            "month": row["month"], "trackers": row["trackers"]
        })

with open(OUT / "site_index.json", "w") as f:
    json.dump(site_index, f)
print(f"✓ site_index.json ({len(site_index)} sites)")


# ── 8. Browser comparison ───────────────────────────────────────────────

browser_stats = query("""
    SELECT b.name AS browser,
           COUNT(DISTINCT s.id) AS scans,
           ROUND(100.0 * SUM(CASE WHEN ss.name = 'success' THEN 1 ELSE 0 END) / COUNT(*), 1) AS success_rate
    FROM scan_sites sc
    JOIN scan s ON s.id = sc.scan_id
    JOIN browser b ON b.id = s.browser_id
    JOIN site_status ss ON ss.id = sc.status_id
    GROUP BY b.name
""")

with open(OUT / "browser_stats.json", "w") as f:
    json.dump(browser_stats, f, indent=2)
print("✓ browser_stats.json")


# ── 9. Sites with most trackers (latest scan) ──────────────────────────

most_tracked_sites = query("""
    SELECT si.fqdn AS site, COUNT(DISTINCT tr.tracker_id) AS trackers
    FROM tracking tr
    JOIN site si ON si.id = tr.site_id
    WHERE tr.scan_id = ?
    GROUP BY si.fqdn ORDER BY trackers DESC LIMIT 30
""", (latest_nb,))

with open(OUT / "most_tracked_sites.json", "w") as f:
    json.dump(most_tracked_sites, f, indent=2)
print("✓ most_tracked_sites.json")


db.close()
print("\nAll data files generated in story/data/")
