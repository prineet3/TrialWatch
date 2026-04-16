from flask import Flask, render_template_string, request
import plotly.express as px
import plotly.utils
import json

from trialwatch_queries import (
    connect,
    get_compliance_overview,
    get_top_overdue_sponsors,
    get_top_dollar_sponsors,
    get_top_danger_sponsors,
    get_sponsor_detail,
    search_sponsors,
)

MONGODB_URI = "mongodb+srv://gb3013:EswRpPsIS7bPgTB4@trialwatch.zrkdkfu.mongodb.net/?appName=TrialWatch"

app = Flask(__name__)
db = connect(MONGODB_URI)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>TrialWatch Dashboard</title>
  <script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <style>
    body { font-family: Arial, sans-serif; background:#f7f8fa; margin:0; }
    .container { width:92%; margin:24px auto; }
    h1 { margin-bottom:4px; }
    .subtitle { color:#666; margin-bottom:20px; }
    .metrics { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }
    .card { background:white; padding:16px; border-radius:12px; box-shadow:0 2px 10px rgba(0,0,0,0.06); }
    .metric-label { font-size:13px; color:#666; }
    .metric-value { font-size:28px; font-weight:bold; margin-top:6px; }
    .metric-sub { font-size:12px; color:#999; margin-top:4px; }
    .grid { display:grid; grid-template-columns:repeat(2,1fr); gap:16px; margin-bottom:24px; }
    .chart-card { background:white; padding:16px; border-radius:12px; box-shadow:0 2px 10px rgba(0,0,0,0.06); }
    .section-title { margin:24px 0 10px; }
    table { width:100%; border-collapse:collapse; background:white; border-radius:10px; overflow:hidden; margin-bottom:24px; }
    th, td { padding:8px 10px; border-bottom:1px solid #eee; font-size:13px; text-align:left; }
    th { background:#f0f3f8; }
    .filters { background:white; padding:12px 16px; border-radius:12px; margin-bottom:18px; box-shadow:0 2px 10px rgba(0,0,0,0.06); }
    input[type=text] { padding:6px 8px; border-radius:8px; border:1px solid #ccc; width:220px; }
    button { padding:6px 12px; border-radius:8px; border:none; background:#0b5ed7; color:white; cursor:pointer; margin-left:8px; }
    @media(max-width:900px){ .metrics,.grid{grid-template-columns:1fr;} }
  </style>
</head>
<body>
<div class="container">
  <h1>TrialWatch</h1>
  <div class="subtitle">Clinical Trial Compliance & Risk Dashboard</div>

  <form method="get" class="filters">
    <label><strong>Sponsor Search:</strong></label>
    <input type="text" name="sponsor" value="{{ sponsor_query or '' }}" placeholder="e.g. Novartis">
    <button type="submit">Search</button>
  </form>

  <div class="metrics">
    <div class="card">
      <div class="metric-label">Total ACT Trials</div>
      <div class="metric-value">{{ "{:,}".format(overview.get("total_trials", 0)) }}</div>
    </div>
    <div class="card">
      <div class="metric-label">Non-compliant (Late + Missing)</div>
      <div class="metric-value">{{ "{:,}".format(overview.get("total_noncompliant", 0)) }}</div>
      <div class="metric-sub">{{ "{:.1f}%".format(overview.get("pct_noncompliant", 0)) }} of all trials</div>
    </div>
    <div class="card">
      <div class="metric-label">NIH $ at risk</div>
      <div class="metric-value">$11.5B</div>
      <div class="metric-sub">From risk_enrichment</div>
    </div>
    <div class="card">
      <div class="metric-label">AE reports linked</div>
      <div class="metric-value">14M</div>
      <div class="metric-sub">From risk_enrichment</div>
    </div>
  </div>

  <div class="grid">
    <div class="chart-card">
      <div id="status_chart"></div>
    </div>
    <div class="chart-card">
      <div id="overdue_chart"></div>
    </div>
    <div class="chart-card">
      <div id="dollar_chart"></div>
    </div>
    <div class="chart-card">
      <div id="danger_chart"></div>
    </div>
  </div>

  <h3 class="section-title">Top Overdue Sponsors</h3>
  <table>
    <thead>
      <tr>
        <th>Sponsor</th>
        <th>Noncompliant Trials</th>
        <th>Late</th>
        <th>Missing</th>
        <th>Max Days Overdue</th>
      </tr>
    </thead>
    <tbody>
      {% for row in top_overdue %}
      <tr>
        <td>{{ row.get("sponsor", "N/A") }}</td>
        <td>{{ row.get("noncompliant_count", 0) }}</td>
        <td>{{ row.get("late_count", 0) }}</td>
        <td>{{ row.get("missing_count", 0) }}</td>
        <td>{{ row.get("max_days_overdue", 0) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <h3 class="section-title">Top NIH $ at Risk</h3>
  <table>
    <thead>
      <tr>
        <th>Sponsor</th>
        <th>NIH $ at Risk</th>
        <th>Noncompliant Trials</th>
        <th>Total AE Reports</th>
      </tr>
    </thead>
    <tbody>
      {% for row in top_dollar %}
      <tr>
        <td>{{ row.get("sponsor", "N/A") }}</td>
        <td>{{ "{:,.0f}".format(row.get("dollars_at_risk", 0)) }}</td>
        <td>{{ row.get("noncompliant_trials", 0) }}</td>
        <td>{{ "{:,.0f}".format(row.get("total_aes", 0)) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  <h3 class="section-title">Top Danger Sponsors</h3>
  <table>
    <thead>
      <tr>
        <th>Sponsor</th>
        <th>Noncompliant Trials</th>
        <th>Total AE Reports</th>
        <th>NIH $ at Risk</th>
      </tr>
    </thead>
    <tbody>
      {% for row in top_danger %}
      <tr>
        <td>{{ row.get("sponsor", "N/A") }}</td>
        <td>{{ row.get("noncompliant_trials", 0) }}</td>
        <td>{{ "{:,.0f}".format(row.get("total_aes", 0)) }}</td>
        <td>{{ "{:,.0f}".format(row.get("dollars_at_risk", 0)) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>

  {% if sponsor_name %}
  <h3 class="section-title">Non-compliant Trials for {{ sponsor_name }}</h3>
  <table>
    <thead>
      <tr>
        <th>NCT ID</th>
        <th>Status</th>
        <th>Days Overdue</th>
      </tr>
    </thead>
    <tbody>
      {% for t in sponsor_trials %}
      <tr>
        <td>{{ t.get("nct_id", "N/A") }}</td>
        <td>{{ t.get("compliance_status_v2", "N/A") }}</td>
        <td>{{ t.get("days_overdue", 0) }}</td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  {% endif %}
</div>

<script>
  var statusFig = {{ status_graph | safe }};
  Plotly.newPlot('status_chart', statusFig.data, statusFig.layout, {responsive:true});

  var overdueFig = {{ overdue_graph | safe }};
  Plotly.newPlot('overdue_chart', overdueFig.data, overdueFig.layout, {responsive:true});

  var dollarFig = {{ dollar_graph | safe }};
  Plotly.newPlot('dollar_chart', dollarFig.data, dollarFig.layout, {responsive:true});

  var dangerFig = {{ danger_graph | safe }};
  Plotly.newPlot('danger_chart', dangerFig.data, dangerFig.layout, {responsive:true});
</script>
</body>
</html>
"""

@app.route("/", methods=["GET"])
def dashboard():
    sponsor_query = request.args.get("sponsor", "").strip()

    overview = get_compliance_overview(db) or {}
    top_overdue = get_top_overdue_sponsors(db, n=10) or []
    top_dollar = get_top_dollar_sponsors(db, n=10) or []
    top_danger = get_top_danger_sponsors(db, n=10) or []

    sponsor_name = None
    sponsor_trials = []
    if sponsor_query:
        matches = search_sponsors(db, sponsor_query) or []
        if matches:
            sponsor_name = matches[0].get("org_name") or matches[0].get("sponsor")
            sponsor_trials = get_sponsor_detail(db, sponsor_name) or []

    by_status = overview.get("by_status", {})
    fig_status = px.bar(
        x=list(by_status.keys()),
        y=list(by_status.values()),
        title="Compliance Status Distribution",
        labels={"x": "Status", "y": "Number of Trials"},
    )

    fig_status.update_layout(margin=dict(l=20, r=20, t=50, b=20))

    fig_overdue = px.bar(
        top_overdue,
        x="max_days_overdue",
        y="sponsor",
        orientation="h",
        title="Top Overdue Sponsors (by max days overdue)",
        labels={"max_days_overdue": "Max Days Overdue", "sponsor": "Sponsor"},
    )
    fig_overdue.update_layout(margin=dict(l=20, r=20, t=50, b=20), yaxis={"categoryorder": "total ascending"})

    fig_dollar = px.bar(
        top_dollar,
        x="dollars_at_risk",
        y="sponsor",
        orientation="h",
        title="Top NIH $ at Risk",
        labels={"dollars_at_risk": "NIH $ at Risk", "sponsor": "Sponsor"},
    )
    fig_dollar.update_layout(margin=dict(l=20, r=20, t=50, b=20), yaxis={"categoryorder": "total ascending"})

    fig_danger = px.bar(
        top_danger,
        x="noncompliant_trials",
        y="sponsor",
        orientation="h",
        title="Top Danger Sponsors",
        labels={"noncompliant_trials": "Noncompliant Trials", "sponsor": "Sponsor"},
    )
    fig_danger.update_layout(margin=dict(l=20, r=20, t=50, b=20), yaxis={"categoryorder": "total ascending"})

    return render_template_string(
        HTML_TEMPLATE,
        overview=overview,
        top_overdue=top_overdue,
        top_dollar=top_dollar,
        top_danger=top_danger,
        sponsor_query=sponsor_query,
        sponsor_name=sponsor_name,
        sponsor_trials=sponsor_trials,
        status_graph=json.dumps(fig_status, cls=plotly.utils.PlotlyJSONEncoder),
        overdue_graph=json.dumps(fig_overdue, cls=plotly.utils.PlotlyJSONEncoder),
        dollar_graph=json.dumps(fig_dollar, cls=plotly.utils.PlotlyJSONEncoder),
        danger_graph=json.dumps(fig_danger, cls=plotly.utils.PlotlyJSONEncoder),
    )

if __name__ == "__main__":
    app.run(debug=True)