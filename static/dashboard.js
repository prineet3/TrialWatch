let statusChart = null;
let overdueChart = null;

function byId(id) { return document.getElementById(id); }

function formatNumber(value) {
  return new Intl.NumberFormat("en-US").format(Number(value || 0));
}

function formatCompact(value) {
  return new Intl.NumberFormat("en-US", {
    notation: "compact", maximumFractionDigits: 1
  }).format(Number(value || 0));
}

function formatCurrencyCompact(value) {
  return new Intl.NumberFormat("en-US", {
    style: "currency", currency: "USD",
    notation: "compact", maximumFractionDigits: 1
  }).format(Number(value || 0));
}

async function fetchJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.json();
}

function showChartError(canvasId, message) {
  const canvas = byId(canvasId);
  if (!canvas) return;
  const wrap = canvas.parentElement;
  if (wrap) wrap.innerHTML = `<div style="padding:20px;color:#b42318;font-weight:600;">${message}</div>`;
}

function getInitials(name) {
  return (name || "?").split(" ").slice(0, 2).map(w => w[0]).join("").toUpperCase();
}

function showResultsPanel() {
  byId("searchResultsWrap")?.classList.add("has-results");
}

function hideResultsPanel() {
  byId("searchResultsWrap")?.classList.remove("has-results");
}

function renderOverview(overview, dollars, danger) {
  const total     = Number(overview?.total_trials || 0);
  const missing   = Number(overview?.by_status?.MISSING || 0);
  const late      = Number(overview?.by_status?.LATE || 0);
  const compliant = Number(overview?.by_status?.COMPLIANT || 0);

  byId("totalTrials").textContent        = formatNumber(total);
  byId("noncompliantTrials").textContent = formatNumber(overview?.total_noncompliant || 0);
  byId("pctNoncompliant").textContent    = `${overview?.pct_noncompliant || 0}% of all monitored trials`;

  const totalDollars = (dollars || []).reduce((s, r) => s + Number(r.dollars_at_risk || 0), 0);
  const totalAEs     = (danger  || []).reduce((s, r) => s + Number(r.total_aes     || 0), 0);

  if (byId("dollarsAtRisk"))  byId("dollarsAtRisk").textContent  = formatCurrencyCompact(totalDollars);
  if (byId("aeLinked"))       byId("aeLinked").textContent       = formatCompact(totalAEs);
  if (byId("missingRate"))    byId("missingRate").textContent    = total ? `${((missing   / total) * 100).toFixed(1)}%` : "0%";
  if (byId("lateRate"))       byId("lateRate").textContent       = total ? `${((late      / total) * 100).toFixed(1)}%` : "0%";
  if (byId("complianceRate")) byId("complianceRate").textContent = total ? `${((compliant / total) * 100).toFixed(1)}%` : "0%";
}

function renderStatusChart(overview) {
  const canvas = byId("statusChart");
  if (!canvas) return;
  const labels = ["Missing", "Late", "Compliant", "Not due yet"];
  const values = [
    Number(overview?.by_status?.MISSING     || 0),
    Number(overview?.by_status?.LATE        || 0),
    Number(overview?.by_status?.COMPLIANT   || 0),
    Number(overview?.by_status?.NOT_DUE_YET || 0)
  ];
  try {
    if (statusChart) statusChart.destroy();
    statusChart = new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: { labels, datasets: [{ data: values, backgroundColor: ["#cf335f","#f59e0b","#1f8f5f","#4f46e5"], borderRadius: 10, borderSkipped: false, maxBarThickness: 70 }] },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 700 },
        plugins: { legend: { display: false }, tooltip: { backgroundColor: "#111827", padding: 12 } },
        scales: {
          x: { grid: { display: false }, ticks: { color: "#667085", font: { weight: 600 } } },
          y: { beginAtZero: true, ticks: { color: "#667085", callback: v => formatCompact(v) }, grid: { color: "#edf1f7" } }
        }
      }
    });
  } catch (err) { showChartError("statusChart", "Status chart failed to render."); }
}

function renderOverdueChart(rows) {
  const canvas = byId("overdueChart");
  if (!canvas) return;
  const top    = (rows || []).slice(0, 8).reverse();
  const labels = top.map(r => r.sponsor);
  const values = top.map(r => Number(r.max_days_overdue || 0));
  try {
    if (overdueChart) overdueChart.destroy();
    overdueChart = new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: { labels, datasets: [{ data: values, backgroundColor: "#4f46e5", borderRadius: 10, borderSkipped: false }] },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false, animation: { duration: 700 },
        plugins: { legend: { display: false }, tooltip: { backgroundColor: "#111827", padding: 12 } },
        scales: {
          y: { grid: { display: false }, ticks: { color: "#475467", font: { size: 12, weight: 600 } } },
          x: { beginAtZero: true, grid: { color: "#edf1f7" }, ticks: { color: "#667085", callback: v => formatCompact(v) } }
        }
      }
    });
  } catch (err) { showChartError("overdueChart", "Overdue sponsor chart failed to render."); }
}

function renderOverdueTable(rows) {
  const body = byId("overdueTableBody");
  if (!body) return;
  const maxDays = Math.max(...(rows || []).map(r => Number(r.max_days_overdue || 0)), 1);
  body.innerHTML = (rows || []).map(row => {
    const pct = Math.round((Number(row.max_days_overdue || 0) / maxDays) * 100);
    return `
    <tr>
      <td><a href="/sponsor/${encodeURIComponent(row.sponsor)}" class="sponsor-link">${row.sponsor || "—"}</a></td>
      <td><span class="class-pill">${row.sponsor_class || "—"}</span></td>
      <td><span class="nc-count">${formatNumber(row.noncompliant_count)}</span></td>
      <td>${formatNumber(row.late_count)}</td>
      <td>${formatNumber(row.missing_count)}</td>
      <td>
        <div class="bar-cell">
          <div class="mini-bar"><div class="mini-bar-fill" style="width:${pct}%"></div></div>
          <span class="days-val">${formatNumber(row.max_days_overdue)}d</span>
        </div>
      </td>
      <td><a href="/sponsor/${encodeURIComponent(row.sponsor)}" class="view-profile-btn">View profile →</a></td>
    </tr>`;
  }).join("");
}

async function focusOnSponsor(name) {
  hideResultsPanel();
  const mode     = byId("viewModeLabel");
  const selected = byId("selectedSponsorLabel");
  if (mode)     mode.textContent     = "Viewing: Focused sponsor";
  if (selected) selected.textContent = name;
  try {
    const trials = await fetchJSON(`/api/sponsor/${encodeURIComponent(name)}?limit=100`);
    if (!trials.length) return;
    const totalDollars = trials.reduce((s, t) => s + Number(t.public_dollars_at_risk || 0), 0);
    const totalAEs     = trials.reduce((s, t) => s + Number(t.ae_count || 0), 0);
    const ncLabel      = byId("noncompliantTrials");
    const dollarsLabel = byId("dollarsAtRisk");
    const aeLabel      = byId("aeLinked");
    if (ncLabel)      ncLabel.textContent     = `${formatNumber(trials.length)} (focused)`;
    if (dollarsLabel) dollarsLabel.textContent = formatCurrencyCompact(totalDollars);
    if (aeLabel)      aeLabel.textContent      = formatCompact(totalAEs);
    [ncLabel, dollarsLabel, aeLabel].forEach(el => {
      if (!el) return;
      el.classList.remove("kpi-pulse");
      void el.offsetWidth;
      el.classList.add("kpi-pulse");
    });
    const sponsorRows = trials.map(t => ({
      sponsor:            name,
      sponsor_class:      t.danger_tier || "",
      noncompliant_count: 1,
      late_count:         t.compliance_status === "LATE"    ? 1 : 0,
      missing_count:      t.compliance_status === "MISSING" ? 1 : 0,
      max_days_overdue:   t.days_overdue || 0
    }));
    renderOverdueChart(sponsorRows);
    renderOverdueTable(sponsorRows);
  } catch (err) { console.error("focusOnSponsor error", err); }
}

function resetGlobalView() {
  hideResultsPanel();
  const mode     = byId("viewModeLabel");
  const selected = byId("selectedSponsorLabel");
  if (mode)     mode.textContent     = "Viewing: All sponsors";
  if (selected) selected.textContent = "";
  loadDashboard();
}

async function searchSponsors() {
  const q   = byId("sponsorSearch")?.value.trim() || "";
  const box = byId("searchResults");
  if (!box) return;

  if (!q) {
    box.innerHTML = "";
    hideResultsPanel();
    resetGlobalView();
    return;
  }

  box.innerHTML = `<p class="empty-copy">Searching…</p>`;
  showResultsPanel();

  try {
    const results = await fetchJSON(`/api/search/sponsors?q=${encodeURIComponent(q)}`);

    if (!results.length) {
      box.innerHTML = `<p class="empty-copy">No matching sponsors found.</p>`;
      showResultsPanel();
      return;
    }

    box.innerHTML = results.map(item => `
      <div class="result-card">
        <div class="result-card-inner">
          <div class="result-card-left">
            <div class="result-avatar">${getInitials(item.sponsor)}</div>
            <button class="result-click" data-sponsor="${item.sponsor}">
              <div class="result-text">
                <h4>${item.sponsor}</h4>
                <p>${formatNumber(item.trial_count)} trials in the enriched sponsor index</p>
              </div>
            </button>
          </div>
          <div class="result-card-right">
            <span class="result-count-pill">${formatNumber(item.trial_count)} trials</span>
            <a href="/sponsor/${encodeURIComponent(item.sponsor)}" class="profile-btn">View profile →</a>
          </div>
        </div>
      </div>
    `).join("");

    showResultsPanel();

    box.querySelectorAll(".result-click").forEach(btn => {
      btn.addEventListener("click", () => focusOnSponsor(btn.getAttribute("data-sponsor")));
    });

  } catch (err) {
    console.error("search error", err);
    box.innerHTML = `<p class="empty-copy">Search failed. Please try again.</p>`;
    showResultsPanel();
  }
}

async function loadDashboard() {
  try {
    const [overview, overdue, dollars, danger] = await Promise.all([
      fetchJSON("/api/overview"),
      fetchJSON("/api/top-overdue-sponsors?n=10"),
      fetchJSON("/api/top-dollar-sponsors?n=10"),
      fetchJSON("/api/top-danger-sponsors?n=10")
    ]);
    renderOverview(overview, dollars, danger);
    renderStatusChart(overview);
    renderOverdueChart(overdue);
    renderOverdueTable(overdue);
  } catch (err) {
    console.error("dashboard load error", err);
    showChartError("statusChart", "Dashboard data failed to load.");
    showChartError("overdueChart", "Dashboard data failed to load.");
  }
}

const searchBtn     = byId("searchBtn");
const sponsorSearch = byId("sponsorSearch");

if (searchBtn)     searchBtn.addEventListener("click", searchSponsors);
if (sponsorSearch) sponsorSearch.addEventListener("keydown", e => {
  if (e.key === "Enter") searchSponsors();
  if (e.key === "Escape") {
    byId("sponsorSearch").value = "";
    hideResultsPanel();
    resetGlobalView();
  }
});

// close results when clicking outside
document.addEventListener("click", (e) => {
  const wrap = byId("searchResultsWrap");
  const nav  = document.querySelector(".tw-nav");
  if (wrap && nav && !wrap.contains(e.target) && !nav.contains(e.target)) {
    hideResultsPanel();
  }
});

window.addEventListener("load", loadDashboard);