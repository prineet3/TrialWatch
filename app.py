"""
app.py — TrialWatch Flask Application
======================================
Main entry point for the TrialWatch web application.

Defines all routes for the dashboard UI and JSON API endpoints.
Connects to MongoDB Atlas on startup using the MONGODB_URI environment variable.

Routes:
    GET  /                              → Dashboard HTML page
    GET  /api/overview                  → Headline KPI stats (total trials, noncompliance rate)
    GET  /api/top-overdue-sponsors      → Top N sponsors by noncompliant trial count
    GET  /api/top-dollar-sponsors       → Top N sponsors by NIH funding at risk
    GET  /api/top-danger-sponsors       → Top N sponsors by adverse event volume
    GET  /api/trial/<nct_id>            → Full detail record for a single trial
    GET  /api/sponsor/<sponsor_name>    → Summary data for a single sponsor
    GET  /api/search/sponsors           → Fuzzy sponsor name search
    GET  /sponsor/<sponsor_name>        → Full sponsor intelligence profile page (HTML)

Course: APAN5400 Data Engineering · Group 8 · Spring 2026
"""

import os
import re
from flask import Flask, jsonify, request, render_template
from urllib.parse import unquote

# Import all 8 query functions from our MongoDB query module
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

# ── APP INITIALIZATION ────────────────────────────────────────────────────────

app = Flask(__name__)

# Load MongoDB URI from environment variable (never hardcoded for security)
# Set this in .env locally or in Render dashboard for production
MONGO_URI = os.getenv("MONGODB_URI")

# Establish a single shared database connection at startup
# db is a PyMongo Database object passed into all query functions
db = connect(MONGO_URI)


# ── DASHBOARD UI ROUTE ────────────────────────────────────────────────────────

@app.route("/")
def home():
    """
    Serve the main dashboard HTML page.
    The dashboard fetches its data client-side via the /api/* endpoints below.
    """
    return render_template("dashboard.html")


# ── JSON API ROUTES ───────────────────────────────────────────────────────────

@app.route("/api/overview")
def api_overview():
    """
    Return headline KPI stats for the dashboard hero section.
    Includes total trials, breakdown by compliance status, and noncompliance %.
    """
    return jsonify(get_compliance_overview(db))


@app.route("/api/top-overdue-sponsors")
def api_top_overdue_sponsors():
    """
    Return the top N sponsors ranked by number of noncompliant trials (LATE + MISSING).
    Query param: n (int, default=10) — number of sponsors to return.
    Used to populate the 'Top Overdue Sponsors' leaderboard on the dashboard.
    """
    n = int(request.args.get("n", 10))
    return jsonify(get_top_overdue_sponsors(db, n))


@app.route("/api/top-dollar-sponsors")
def api_top_dollar_sponsors():
    """
    Return the top N sponsors ranked by NIH public funding at risk (deduped).
    Query param: n (int, default=10) — number of sponsors to return.
    Funding data sourced from NIH Reporter API during Step 2 enrichment.
    """
    n = int(request.args.get("n", 10))
    return jsonify(get_top_dollar_sponsors(db, n))


@app.route("/api/top-danger-sponsors")
def api_top_danger_sponsors():
    """
    Return the top N sponsors ranked by total adverse event (AE) report volume.
    Query param: n (int, default=10) — number of sponsors to return.
    AE data sourced from FDA FAERS (65.7M rows processed in Step 2).
    """
    n = int(request.args.get("n", 10))
    return jsonify(get_top_danger_sponsors(db, n))


@app.route("/api/trial/<nct_id>")
def api_trial_detail(nct_id):
    """
    Return the full unified record for a single clinical trial by NCT ID.
    Joins data from all 3 MongoDB collections: trials, compliance_status, risk_enrichment.
    Returns 404 if the NCT ID is not found in the database.
    """
    result = get_trial_detail(db, nct_id)
    if result:
        return jsonify(result)
    return jsonify({"error": "Trial not found"}), 404


@app.route("/api/sponsor/<path:sponsor_name>")
def api_sponsor_detail(sponsor_name):
    """
    Return all noncompliant trials for a given sponsor, sorted by days overdue.
    Uses <path:> converter to allow slashes in sponsor names (e.g. 'Pfizer/BioNTech').
    Query param: limit (int, default=100) — max number of trials to return.
    """
    limit = int(request.args.get("limit", 100))
    return jsonify(get_sponsor_detail(db, sponsor_name, limit))


@app.route("/api/search/sponsors")
def api_search_sponsors():
    """
    Fuzzy case-insensitive sponsor name search for the dashboard search bar.
    Query param: q (str) — search term (returns empty list if blank).
    Query param: limit (int, default=10) — max number of results.
    """
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])  # Return empty list for blank queries
    limit = int(request.args.get("limit", 10))
    return jsonify(search_sponsors(db, q, limit))


# ── SPONSOR INTELLIGENCE PROFILE PAGE ────────────────────────────────────────

@app.route("/sponsor/<path:sponsor_name>")
def sponsor_profile(sponsor_name):
    """
    Render a full intelligence profile page for a single sponsor.

    This route performs a manual 3-way join across MongoDB collections
    (trials, compliance_status, risk_enrichment) and computes all
    summary statistics server-side before passing them to the Jinja2 template.

    Steps:
        1. Fetch all trials for the sponsor from the 'trials' collection
        2. Fetch compliance records for those trial NCT IDs
        3. Fetch risk enrichment records for those trial NCT IDs
        4. Merge all three into a unified list of trial dicts
        5. Compute summary stats (counts, rates, phase breakdown, danger tiers)
        6. Sort and extract the 10 most overdue trials
        7. Render sponsor_profile.html with all computed data

    Returns 404 if no trials are found for the given sponsor name.
    """

    # URL-decode the sponsor name (handles encoded characters like %26 → &)
    sponsor_name = unquote(sponsor_name)

    # ── STEP 1: Fetch all trials for this sponsor ─────────────────────────────
    # Use re.escape to safely handle special regex characters in sponsor names
    # (e.g. parentheses in 'Pfizer (Germany) GmbH' would break the regex otherwise)
    escaped = re.escape(sponsor_name)
    trials = list(db["trials"].find(
        {"org_name": {"$regex": f"^{escaped}$", "$options": "i"}}  # Case-insensitive exact match
    ))

    # Return 404 if sponsor doesn't exist in our database
    if not trials:
        return render_template("sponsor_not_found.html", sponsor=sponsor_name), 404

    # Extract all NCT IDs for this sponsor to use in subsequent lookups
    nct_ids = [t["nct_id"] for t in trials]

    # ── STEP 2: Fetch compliance records ─────────────────────────────────────
    # Build a dict keyed by nct_id for O(1) lookup during merge step
    compliance_map = {
        c["nct_id"]: c
        for c in db["compliance_status"].find({"nct_id": {"$in": nct_ids}})
    }

    # ── STEP 3: Fetch risk enrichment records ─────────────────────────────────
    # risk_enrichment contains danger scores and NIH funding from Step 2 pipeline
    risk_map = {
        r["nct_id"]: r
        for r in db["risk_enrichment"].find({"nct_id": {"$in": nct_ids}})
    }

    # ── STEP 4: Merge all three collections into one unified list ─────────────
    merged = []
    for t in trials:
        nid = t["nct_id"]
        c = compliance_map.get(nid, {})   # Default to empty dict if no compliance record
        r = risk_map.get(nid, {})         # Default to empty dict if no risk record
        merged.append({
            "nct_id":             nid,
            "status":             t.get("overall_status", "UNKNOWN"),
            "phases":             t.get("phases", []),
            "study_type":         t.get("study_type", ""),
            "org_class":          t.get("org_class", "UNKNOWN"),       # INDUSTRY / NIH / OTHER
            "primary_completion": t.get("primary_completion_date", ""),
            "compliance_status":  c.get("compliance_status", "UNKNOWN"),  # COMPLIANT/LATE/MISSING/NOT_DUE_YET
            "days_overdue":       c.get("days_overdue", 0),
            "is_overdue":         c.get("is_overdue", False),
            "ae_count":           r.get("ae_count_deduped", r.get("ae_count", 0)),  # Prefer deduped count
            "danger_score":       r.get("danger_score"),       # 0–100 log-normalized score
            "danger_tier":        r.get("danger_tier"),        # CRITICAL/HIGH/MODERATE/LOW/NO DATA
            "public_dollars":     r.get("funding_deduped", r.get("public_dollars_at_risk", 0)),
            "matched_ingredient": r.get("matched_ingredient", ""),  # Drug name matched to FAERS
        })

    # ── STEP 5: Compute summary statistics ───────────────────────────────────

    total = len(merged)

    # Count trials by compliance status (COMPLIANT, LATE, MISSING, NOT_DUE_YET)
    compliance_counts = {}
    for m in merged:
        s = m["compliance_status"]
        compliance_counts[s] = compliance_counts.get(s, 0) + 1

    late         = compliance_counts.get("LATE", 0)
    missing      = compliance_counts.get("MISSING", 0)
    compliant    = compliance_counts.get("COMPLIANT", 0)
    not_due      = compliance_counts.get("NOT_DUE_YET", 0)
    noncompliant = late + missing   # Total noncompliant = LATE + MISSING

    # Aggregate totals for KPI cards on the profile page
    total_ae      = sum(m["ae_count"] or 0 for m in merged)
    total_dollars = sum(m["public_dollars"] or 0 for m in merged)
    max_days_over = max((m["days_overdue"] or 0 for m in merged), default=0)

    # Compliance rate = compliant / trials that have a deadline (excludes NOT_DUE_YET)
    has_deadline    = total - not_due
    compliance_rate = round(compliant / has_deadline * 100, 1) if has_deadline > 0 else 0

    # Count trials by clinical phase (Phase 1, 2, 3, 4) for the phase breakdown chart
    phase_counts = {}
    for m in merged:
        for ph in (m["phases"] or ["UNKNOWN"]):
            phase_counts[ph] = phase_counts.get(ph, 0) + 1

    # Count trials by danger tier for the risk distribution panel
    danger_tiers = {}
    for m in merged:
        dt = m["danger_tier"]
        if dt:
            danger_tiers[dt] = danger_tiers.get(dt, 0) + 1

    # ── STEP 6: Extract top 10 most overdue trials ────────────────────────────
    # Only include trials flagged as overdue, sorted by days_overdue descending
    overdue_trials = sorted(
        [m for m in merged if m["is_overdue"]],
        key=lambda x: x["days_overdue"],
        reverse=True
    )[:10]

    # ── STEP 7: Package stats dict for template ───────────────────────────────
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
        "max_years_over":  round(max_days_over / 365, 1),  # Convert days → years for display
        "phase_counts":    phase_counts,
        "danger_tiers":    danger_tiers,
        "org_class":       trials[0].get("org_class", "UNKNOWN"),  # INDUSTRY / NIH / OTHER
    }

    # Render the Jinja2 HTML template with all computed data
    return render_template(
        "sponsor_profile.html",
        sponsor=sponsor_name,
        stats=stats,
        overdue_trials=overdue_trials,
        compliance_counts=compliance_counts,
    )


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Run in debug mode locally; Gunicorn is used in production on Render
    app.run(debug=True)