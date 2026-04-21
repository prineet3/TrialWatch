from flask import Flask, jsonify, request, render_template
from urllib.parse import unquote
from trialwatch_queries import (
    connect,
    get_compliance_overview,
    get_top_overdue_sponsors,
    get_top_dollar_sponsors,
    get_top_danger_sponsors,
    get_trial_detail,
    get_sponsor_detail,
    search_sponsors
)

app = Flask(__name__)

import os
MONGO_URI = os.getenv("MONGODB_URI")
db = connect(MONGO_URI)

# ── EXISTING ROUTES (unchanged) ─────────────────────────────────────────────

@app.route("/")
def home():
    return render_template("dashboard.html")

@app.route("/api/overview")
def api_overview():
    return jsonify(get_compliance_overview(db))

@app.route("/api/top-overdue-sponsors")
def api_top_overdue_sponsors():
    n = int(request.args.get("n", 10))
    return jsonify(get_top_overdue_sponsors(db, n))

@app.route("/api/top-dollar-sponsors")
def api_top_dollar_sponsors():
    n = int(request.args.get("n", 10))
    return jsonify(get_top_dollar_sponsors(db, n))

@app.route("/api/top-danger-sponsors")
def api_top_danger_sponsors():
    n = int(request.args.get("n", 10))
    return jsonify(get_top_danger_sponsors(db, n))

@app.route("/api/trial/<nct_id>")
def api_trial_detail(nct_id):
    result = get_trial_detail(db, nct_id)
    if result:
        return jsonify(result)
    return jsonify({"error": "Trial not found"}), 404

@app.route("/api/sponsor/<path:sponsor_name>")
def api_sponsor_detail(sponsor_name):
    limit = int(request.args.get("limit", 100))
    return jsonify(get_sponsor_detail(db, sponsor_name, limit))

@app.route("/api/search/sponsors")
def api_search_sponsors():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    limit = int(request.args.get("limit", 10))
    return jsonify(search_sponsors(db, q, limit))

# ── NEW: SPONSOR PROFILE PAGE ────────────────────────────────────────────────

@app.route("/sponsor/<path:sponsor_name>")
def sponsor_profile(sponsor_name):
    sponsor_name = unquote(sponsor_name)

    # 1. All trials for this sponsor
    trials = list(db["trials"].find(
        {"org_name": {"$regex": f"^{sponsor_name}$", "$options": "i"}}
    ))

    if not trials:
        return render_template("sponsor_not_found.html", sponsor=sponsor_name), 404

    nct_ids = [t["nct_id"] for t in trials]

    # 2. Compliance data
    compliance_map = {
        c["nct_id"]: c
        for c in db["compliance_status"].find({"nct_id": {"$in": nct_ids}})
    }

    # 3. Risk enrichment data
    risk_map = {
        r["nct_id"]: r
        for r in db["risk_enrichment"].find({"nct_id": {"$in": nct_ids}})
    }

    # 4. Merge into one list
    merged = []
    for t in trials:
        nid = t["nct_id"]
        c = compliance_map.get(nid, {})
        r = risk_map.get(nid, {})
        merged.append({
            "nct_id":             nid,
            "status":             t.get("overall_status", "UNKNOWN"),
            "phases":             t.get("phases", []),
            "study_type":         t.get("study_type", ""),
            "org_class":          t.get("org_class", "UNKNOWN"),
            "primary_completion": t.get("primary_completion_date", ""),
            "compliance_status":  c.get("compliance_status", "UNKNOWN"),
            "days_overdue":       c.get("days_overdue", 0),
            "is_overdue":         c.get("is_overdue", False),
            "ae_count":           r.get("ae_count_deduped", r.get("ae_count", 0)),
            "danger_score":       r.get("danger_score"),
            "danger_tier":        r.get("danger_tier"),
            "public_dollars":     r.get("funding_deduped", r.get("public_dollars_at_risk", 0)),
            "matched_ingredient": r.get("matched_ingredient", ""),
        })

    # 5. Summary stats
    total = len(merged)
    compliance_counts = {}
    for m in merged:
        s = m["compliance_status"]
        compliance_counts[s] = compliance_counts.get(s, 0) + 1

    late      = compliance_counts.get("LATE", 0)
    missing   = compliance_counts.get("MISSING", 0)
    compliant = compliance_counts.get("COMPLIANT", 0)
    not_due   = compliance_counts.get("NOT_DUE_YET", 0)
    noncompliant = late + missing

    total_ae      = sum(m["ae_count"] or 0 for m in merged)
    total_dollars = sum(m["public_dollars"] or 0 for m in merged)
    max_days_over = max((m["days_overdue"] or 0 for m in merged), default=0)

    has_deadline    = total - not_due
    compliance_rate = round(compliant / has_deadline * 100, 1) if has_deadline > 0 else 0

    phase_counts = {}
    for m in merged:
        for ph in (m["phases"] or ["UNKNOWN"]):
            phase_counts[ph] = phase_counts.get(ph, 0) + 1

    danger_tiers = {}
    for m in merged:
        dt = m["danger_tier"]
        if dt:
            danger_tiers[dt] = danger_tiers.get(dt, 0) + 1

    overdue_trials = sorted(
        [m for m in merged if m["is_overdue"]],
        key=lambda x: x["days_overdue"],
        reverse=True
    )[:10]

    stats = {
        "total":           total,
        "noncompliant":    noncompliant,
        "late":            late,
        "missing":         missing,
        "compliant":       compliant,
        "not_due":         not_due,
        "compliance_rate": compliance_rate,
        "total_ae":        total_ae,
        "total_dollars":   total_dollars,
        "max_days_over":   max_days_over,
        "max_years_over":  round(max_days_over / 365, 1),
        "phase_counts":    phase_counts,
        "danger_tiers":    danger_tiers,
        "org_class":       trials[0].get("org_class", "UNKNOWN"),
    }

    return render_template(
        "sponsor_profile.html",
        sponsor=sponsor_name,
        stats=stats,
        overdue_trials=overdue_trials,
        compliance_counts=compliance_counts,
    )

# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True)