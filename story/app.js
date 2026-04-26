/* ── Badger Sett Story — Main App ─────────────────────────────────── */

const PLOT_LAYOUT = {
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    font: { color: "#6b7394", size: 12, family: "-apple-system, system-ui, sans-serif" },
    margin: { t: 30, b: 50, l: 60, r: 20 },
    xaxis: { gridcolor: "#1e2230", zerolinecolor: "#1e2230" },
    yaxis: { gridcolor: "#1e2230", zerolinecolor: "#1e2230" },
};

const PLOT_CONFIG = { responsive: true, displayModeBar: false };

const COLORS = [
    "#6c8cff", "#a78bfa", "#4ade80", "#fb923c", "#f87171",
    "#fbbf24", "#38bdf8", "#e879f9", "#34d399", "#f472b6"
];

const METHOD_DESCRIPTIONS = {
    beacon: "Tracking pixels and beacons — tiny invisible requests sent to third-party servers to log your visit. The most common tracking method on the web.",
    canvas: "Canvas fingerprinting — using your browser's drawing capabilities to create a unique identifier, even without cookies.",
    pixelcookieshare: "Pixel cookie sharing — combining tracking pixels with cookies to share your identity across different advertising networks.",
    unknown: "Unclassified tracking — third-party domains observed tracking across multiple sites, but the specific technique wasn't categorized."
};

let siteIndex = {};

/* ── Data loading ────────────────────────────────────────────────── */

async function loadJSON(file) {
    const resp = await fetch(`data/${file}`);
    return resp.json();
}

async function init() {
    const [stats, topTrackers, trends, trackingScale, types, concentration, sites, mostTracked] =
        await Promise.all([
            loadJSON("stats.json"),
            loadJSON("top_trackers.json"),
            loadJSON("tracker_trends.json"),
            loadJSON("tracking_scale.json"),
            loadJSON("tracking_types.json"),
            loadJSON("concentration.json"),
            loadJSON("site_index.json"),
            loadJSON("most_tracked_sites.json"),
        ]);

    siteIndex = sites;

    fillStats(stats);
    renderTrackingScale(trackingScale);
    renderTopTrackers(topTrackers, stats);
    renderConcentration(concentration);
    renderTypes(types);
    renderTrends(trends);
    renderMostTracked(mostTracked);
    setupSiteChecker();
    setupScrollObserver();
}

/* ── Fill in stats ───────────────────────────────────────────────── */

function fillStats(s) {
    setText("stat-scans", Number(s.total_scans).toLocaleString());
    setText("stat-sites", Number(s.total_sites).toLocaleString());
    setText("stat-years", `${s.date_from.slice(0, 4)}–${s.date_to.slice(0, 4)}`);
    setText("avg-now", s.avg_trackers_latest);
    setText("google-pct", s.google_pct + "%");
}

function setText(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

/* ── Chart: Tracking scale — stacked area + PB comparison ────────── */

function renderTrackingScale(data) {
    const nb = data.no_blocking;
    const bl = data.blocking;

    if (!nb || nb.length === 0) return;

    const fig = {
        data: [
            {
                x: nb.map(d => d.month), y: nb.map(d => d.pct_extreme),
                name: "20+ trackers", type: "scatter", mode: "lines",
                fill: "tozeroy", fillcolor: "rgba(248,113,113,0.6)",
                line: { color: "#f87171", width: 0 },
                stackgroup: "one",
                hovertemplate: "%{x}: %{y}% of sites<extra>20+ trackers</extra>"
            },
            {
                x: nb.map(d => d.month), y: nb.map(d => d.pct_high),
                name: "10–19 trackers", type: "scatter", mode: "lines",
                fill: "tonexty", fillcolor: "rgba(251,146,60,0.5)",
                line: { color: "#fb923c", width: 0 },
                stackgroup: "one",
                hovertemplate: "%{x}: %{y}% of sites<extra>10–19 trackers</extra>"
            },
            {
                x: nb.map(d => d.month), y: nb.map(d => d.pct_medium),
                name: "5–9 trackers", type: "scatter", mode: "lines",
                fill: "tonexty", fillcolor: "rgba(251,191,36,0.4)",
                line: { color: "#fbbf24", width: 0 },
                stackgroup: "one",
                hovertemplate: "%{x}: %{y}% of sites<extra>5–9 trackers</extra>"
            },
            {
                x: nb.map(d => d.month), y: nb.map(d => d.pct_low),
                name: "1–4 trackers", type: "scatter", mode: "lines",
                fill: "tonexty", fillcolor: "rgba(74,222,128,0.3)",
                line: { color: "#4ade80", width: 0 },
                stackgroup: "one",
                hovertemplate: "%{x}: %{y}% of sites<extra>1–4 trackers</extra>"
            },
            // Average line for no-blocking
            {
                x: nb.map(d => d.month), y: nb.map(d => d.avg),
                name: "Avg (no blocker)", type: "scatter", mode: "lines+markers",
                line: { color: "#fff", width: 2.5, dash: "dot" },
                marker: { size: 4, color: "#fff" },
                yaxis: "y2",
                hovertemplate: "%{x}: <b>%{y} trackers/site</b><extra>Without Privacy Badger</extra>"
            },
            // Average line for blocking (Privacy Badger ON)
            ...(bl && bl.length > 0 ? [{
                x: bl.map(d => d.month), y: bl.map(d => d.avg),
                name: "Avg (Privacy Badger)", type: "scatter", mode: "lines+markers",
                line: { color: "#6c8cff", width: 2.5 },
                marker: { size: 4, color: "#6c8cff" },
                yaxis: "y2",
                hovertemplate: "%{x}: <b>%{y} trackers/site</b><extra>With Privacy Badger</extra>"
            }] : []),
        ],
        layout: {
            ...PLOT_LAYOUT,
            height: 420,
            yaxis: {
                ...PLOT_LAYOUT.yaxis,
                title: "% of sites (stacked)",
                ticksuffix: "%",
                side: "left",
            },
            yaxis2: {
                title: "Avg trackers per site",
                overlaying: "y",
                side: "right",
                showgrid: false,
                titlefont: { color: "#8b8fa3" },
                tickfont: { color: "#8b8fa3" },
                rangemode: "tozero",
            },
            legend: {
                orientation: "h", y: -0.2,
                font: { color: "#8b8fa3", size: 11 },
                xanchor: "center", x: 0.5,
            },
            hovermode: "x unified",
        }
    };
    Plotly.newPlot("chart-avg-over-time", fig.data, fig.layout, PLOT_CONFIG);
}

/* ── Chart: Top trackers bar ─────────────────────────────────────── */

function renderTopTrackers(data, stats) {
    const reversed = [...data].reverse();
    const fig = {
        data: [{
            x: reversed.map(d => d.sites),
            y: reversed.map(d => d.name),
            type: "bar",
            orientation: "h",
            marker: {
                color: reversed.map((_, i) =>
                    `rgba(108,140,255,${0.3 + 0.7 * (i / reversed.length)})`),
            },
            hovertemplate: "<b>%{y}</b><br>Found on %{x} sites<extra></extra>"
        }],
        layout: {
            ...PLOT_LAYOUT,
            margin: { ...PLOT_LAYOUT.margin, l: 160 },
            xaxis: { ...PLOT_LAYOUT.xaxis, title: "Websites tracked" },
            height: 650,
        }
    };
    Plotly.newPlot("chart-top-trackers", fig.data, fig.layout, PLOT_CONFIG);
}

/* ── Chart: Concentration curve ──────────────────────────────────── */

function renderConcentration(data) {
    setText("top10-pct", data[9]?.cumulative_pct || "—");
    setText("top50-pct", data[data.length - 1]?.cumulative_pct || "—");

    const fig = {
        data: [{
            x: data.map((_, i) => i + 1),
            y: data.map(d => d.cumulative_pct),
            type: "scatter",
            mode: "lines+markers",
            fill: "tozeroy",
            fillcolor: "rgba(167,139,250,0.1)",
            line: { color: "#a78bfa", width: 2.5 },
            marker: { size: 5, color: "#a78bfa" },
            text: data.map(d => d.name),
            hovertemplate: "#%{x}: <b>%{text}</b><br>Cumulative: %{y}%<extra></extra>"
        }],
        layout: {
            ...PLOT_LAYOUT,
            xaxis: { ...PLOT_LAYOUT.xaxis, title: "Number of tracker domains (ranked)" },
            yaxis: { ...PLOT_LAYOUT.yaxis, title: "Cumulative % of tracking", range: [0, 100] },
            height: 400,
            shapes: [{
                type: "line", x0: 10, x1: 10, y0: 0, y1: 100,
                line: { color: "rgba(167,139,250,0.4)", width: 1, dash: "dash" }
            }],
            annotations: [{
                x: 10, y: data[9]?.cumulative_pct || 0,
                text: `Top 10: ${data[9]?.cumulative_pct}%`,
                showarrow: true, arrowcolor: "#a78bfa",
                font: { color: "#a78bfa", size: 11 },
                ax: 60, ay: -30
            }]
        }
    };
    Plotly.newPlot("chart-concentration", fig.data, fig.layout, PLOT_CONFIG);
}

/* ── Chart: Tracking types ───────────────────────────────────────── */

function renderTypes(data) {
    // method cards
    const container = document.getElementById("method-cards");
    if (container) {
        const known = data.filter(d => d.name !== "unknown");
        known.forEach(d => {
            const card = document.createElement("div");
            card.className = "method-card";
            card.innerHTML = `
                <div class="method-name">${d.name}</div>
                <div class="method-desc">${METHOD_DESCRIPTIONS[d.name] || ""}</div>
            `;
            container.appendChild(card);
        });
    }

    const fig = {
        data: [{
            labels: data.map(d => d.name),
            values: data.map(d => d.count),
            type: "pie",
            hole: 0.45,
            marker: { colors: COLORS },
            textinfo: "label+percent",
            textfont: { color: "#d4d8e8", size: 12 },
            hovertemplate: "<b>%{label}</b><br>%{value:,} observations<br>%{percent}<extra></extra>"
        }],
        layout: {
            ...PLOT_LAYOUT,
            height: 380,
            showlegend: false,
        }
    };
    Plotly.newPlot("chart-types", fig.data, fig.layout, PLOT_CONFIG);
}

/* ── Chart: Tracker trends ───────────────────────────────────────── */

function renderTrends(data) {
    // group by tracker name
    const byName = {};
    data.forEach(d => {
        if (!byName[d.name]) byName[d.name] = [];
        byName[d.name].push(d);
    });

    const traces = Object.entries(byName).map(([name, points], i) => ({
        x: points.map(p => p.month),
        y: points.map(p => p.pct),
        name,
        type: "scatter",
        mode: "lines+markers",
        line: { color: COLORS[i % COLORS.length], width: 2.5, shape: "spline" },
        marker: { size: 4, color: COLORS[i % COLORS.length] },
        hovertemplate: `<b>${name}</b><br>%{x}: %{y}% of sites<extra></extra>`
    }));

    const fig = {
        data: traces,
        layout: {
            ...PLOT_LAYOUT,
            height: 500,
            yaxis: {
                ...PLOT_LAYOUT.yaxis,
                title: "% of tracked sites",
                ticksuffix: "%",
                rangemode: "tozero",
            },
            legend: {
                orientation: "h", y: -0.2,
                font: { color: "#8b8fa3", size: 11 },
                xanchor: "center", x: 0.5,
            },
            hovermode: "x unified",
        }
    };
    Plotly.newPlot("chart-trends", fig.data, fig.layout, PLOT_CONFIG);
}

/* ── Chart: Most tracked sites ───────────────────────────────────── */

function renderMostTracked(data) {
    const reversed = [...data].reverse();
    const maxTrackers = Math.max(...data.map(d => d.trackers));

    const fig = {
        data: [{
            x: reversed.map(d => d.trackers),
            y: reversed.map(d => d.site),
            type: "bar",
            orientation: "h",
            marker: {
                color: reversed.map(d => {
                    const pct = d.trackers / maxTrackers;
                    if (pct > 0.8) return "#f87171";
                    if (pct > 0.5) return "#fb923c";
                    if (pct > 0.3) return "#fbbf24";
                    return "#4ade80";
                }),
            },
            hovertemplate: "<b>%{y}</b><br>%{x} trackers<extra></extra>"
        }],
        layout: {
            ...PLOT_LAYOUT,
            margin: { ...PLOT_LAYOUT.margin, l: 180 },
            xaxis: { ...PLOT_LAYOUT.xaxis, title: "Number of trackers" },
            height: 700,
        }
    };
    Plotly.newPlot("chart-most-tracked", fig.data, fig.layout, PLOT_CONFIG);
}

/* ── Site checker ────────────────────────────────────────────────── */

function setupSiteChecker() {
    const input = document.getElementById("site-input");
    const sugBox = document.getElementById("site-suggestions");
    const resultBox = document.getElementById("site-result");
    const noResultBox = document.getElementById("site-no-result");
    let debounceTimer = null;

    input.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        const q = input.value.trim().toLowerCase();

        if (q.length < 2) {
            sugBox.classList.remove("open");
            return;
        }

        debounceTimer = setTimeout(async () => {
            try {
                const resp = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
                const matches = await resp.json();

                sugBox.innerHTML = "";
                if (matches.length === 0) {
                    sugBox.classList.remove("open");
                    return;
                }

                matches.forEach(site => {
                    const div = document.createElement("div");
                    div.className = "suggestion";
                    const idx = site.indexOf(q);
                    if (idx >= 0) {
                        div.innerHTML = site.slice(0, idx) +
                            `<strong>${site.slice(idx, idx + q.length)}</strong>` +
                            site.slice(idx + q.length);
                    } else {
                        div.textContent = site;
                    }
                    div.addEventListener("click", () => {
                        input.value = site;
                        sugBox.classList.remove("open");
                        loadSiteData(site);
                    });
                    sugBox.appendChild(div);
                });

                sugBox.classList.add("open");
            } catch (e) {
                // fall back to local index
                fallbackSearch(q, sugBox);
            }
        }, 200);
    });

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            sugBox.classList.remove("open");
            const q = input.value.trim().toLowerCase();
            if (q) loadSiteData(q);
        }
    });

    document.addEventListener("click", (e) => {
        if (!e.target.closest(".site-search")) {
            sugBox.classList.remove("open");
        }
    });

    function fallbackSearch(q, sugBox) {
        const allSites = Object.keys(siteIndex).sort();
        const startsWith = allSites.filter(s => s.startsWith(q)).slice(0, 5);
        const contains = allSites.filter(s => !s.startsWith(q) && s.includes(q)).slice(0, 5);
        const matches = [...startsWith, ...contains].slice(0, 8);

        sugBox.innerHTML = "";
        if (matches.length === 0) { sugBox.classList.remove("open"); return; }

        matches.forEach(site => {
            const div = document.createElement("div");
            div.className = "suggestion";
            div.textContent = site;
            div.addEventListener("click", () => {
                input.value = site;
                sugBox.classList.remove("open");
                loadSiteData(site);
            });
            sugBox.appendChild(div);
        });
        sugBox.classList.add("open");
    }
}

async function loadSiteData(domain) {
    const resultBox = document.getElementById("site-result");
    const noResultBox = document.getElementById("site-no-result");

    resultBox.classList.add("hidden");
    noResultBox.classList.add("hidden");

    try {
        const resp = await fetch(`/api/site/${encodeURIComponent(domain)}`);

        if (!resp.ok) {
            // fall back to local index
            if (siteIndex[domain]) {
                showLocalResult(domain);
            } else {
                noResultBox.textContent = `No data found for "${domain}". Try a popular site like nytimes.com or amazon.com.`;
                noResultBox.classList.remove("hidden");
            }
            return;
        }

        const data = await resp.json();
        showApiResult(data);
    } catch (e) {
        // API unavailable, fall back to local
        if (siteIndex[domain]) {
            showLocalResult(domain);
        } else {
            noResultBox.textContent = `No data found for "${domain}". Try a popular site like nytimes.com or amazon.com.`;
            noResultBox.classList.remove("hidden");
        }
    }
}

function showApiResult(data) {
    const resultBox = document.getElementById("site-result");
    const count = data.tracker_count;
    const grade = getGrade(count);

    // Grade badge
    const gradeEl = document.getElementById("result-grade");
    gradeEl.textContent = grade.letter;
    gradeEl.className = `result-grade grade-${grade.letter.toLowerCase()}`;

    // Domain & label
    document.getElementById("result-domain").textContent = data.domain;
    document.getElementById("result-grade-label").textContent = grade.label;

    // Stats
    document.getElementById("result-count").textContent = count;

    const types = [...new Set(data.trackers.map(t => t.type))].filter(t => t !== "unknown");
    document.getElementById("result-types").textContent = types.length > 0 ? types.join(", ") : "—";

    document.getElementById("result-percentile").textContent =
        `Top ${100 - data.percentile}%`;

    // Trend chart
    if (data.trend && data.trend.length > 1) {
        const trendEl = document.getElementById("result-trend-chart");
        trendEl.style.display = "block";
        Plotly.newPlot(trendEl, [{
            x: data.trend.map(d => d.month),
            y: data.trend.map(d => d.trackers),
            type: "scatter",
            mode: "lines+markers",
            fill: "tozeroy",
            fillcolor: "rgba(108,140,255,0.08)",
            line: { color: "#6c8cff", width: 2 },
            marker: { size: 4, color: "#6c8cff" },
            hovertemplate: "%{x}<br><b>%{y} trackers</b><extra></extra>"
        }], {
            ...PLOT_LAYOUT,
            height: 220,
            margin: { t: 20, b: 40, l: 45, r: 15 },
            yaxis: { ...PLOT_LAYOUT.yaxis, title: "Trackers" },
            xaxis: { ...PLOT_LAYOUT.xaxis },
        }, PLOT_CONFIG);
    } else {
        document.getElementById("result-trend-chart").style.display = "none";
    }

    // Tracker list
    const uniqueTrackers = [...new Set(data.trackers.map(t => t.tracker))].sort();
    document.getElementById("result-trackers-heading").textContent =
        `Trackers detected (${uniqueTrackers.length})`;

    const listEl = document.getElementById("result-tracker-list");
    const displayTrackers = uniqueTrackers.slice(0, 30);
    listEl.innerHTML = displayTrackers
        .map(t => `<span class="tracker-tag">${t}</span>`)
        .join("") +
        (uniqueTrackers.length > 30
            ? `<span class="tracker-tag" style="opacity:0.5">+${uniqueTrackers.length - 30} more</span>`
            : "");

    resultBox.classList.remove("hidden");
}

function showLocalResult(domain) {
    const data = siteIndex[domain];
    if (!data) return;

    const allCounts = Object.values(siteIndex).map(s => s.count).sort((a, b) => a - b);
    const percentile = Math.round(100 * allCounts.filter(c => c < data.count).length / allCounts.length);

    showApiResult({
        domain,
        tracker_count: data.count,
        trackers: data.trackers.map(t => ({
            tracker: t,
            type: data.types ? data.types.find(ty => ty !== "unknown") || "unknown" : "unknown"
        })),
        trend: data.trend || [],
        percentile,
        total_sites_in_scan: Object.keys(siteIndex).length,
    });
}

function getGrade(count) {
    if (count <= 3) return { letter: "A", label: "Very few trackers" };
    if (count <= 8) return { letter: "B", label: "Below average tracking" };
    if (count <= 15) return { letter: "C", label: "Average tracking" };
    if (count <= 25) return { letter: "D", label: "Above average tracking" };
    return { letter: "F", label: "Heavy tracking" };
}

/* ── Scroll animations (disabled) ─────────────────────────────────── */

function setupScrollObserver() {
    // animations removed for layout stability
}

/* ── Go ──────────────────────────────────────────────────────────── */
init();
