"""
trialwatch_queries.py — TrialWatch MongoDB Query Module
========================================================
Reusable query functions for the TrialWatch compliance intelligence platform.
All functions operate on a shared PyMongo Database object (db) passed as
the first argument — no global state or repeated connections.

MongoDB Collections Used:
    - trials             : Trial metadata from ClinicalTrials.gov AACT flat files
                           Fields: nct_id, org_name, org_class, phases, study_type,
                                   overall_status, primary_completion_date
    - compliance_status  : FDAAA 801 compliance classification computed in Step 1 (PySpark)
                           Fields: nct_id, compliance_status, days_overdue, is_overdue, deadline
    - risk_enrichment    : Danger scores and NIH funding computed in Step 2 (PySpark + APIs)
                           Fields: nct_id, org_name, matched_ingredient, ae_count_deduped,
                                   danger_score, danger_tier, funding_deduped

Naming conventions:
    - ae_count_deduped   : Adverse event count after deduplication across FAERS reports
    - funding_deduped    : NIH funding deduplicated to avoid double-counting multi-trial grants
    - danger_score       : 0–100 log-normalized score based on AE counts
    - danger_tier        : CRITICAL / HIGH / MODERATE / LOW / NO DATA

Usage:
    from trialwatch_queries import connect, get_compliance_overview
    db = connect("mongodb+srv://USER:PASS@cluster.mongodb.net/")
    overview = get_compliance_overview(db)

Course: APAN5400 Data Engineering · Group 8 · Spring 2026
"""

from pymongo import MongoClient
import re


# ── CONNECTION ────────────────────────────────────────────────────────────────

def connect(connection_string, db_name="trialwatch_db"):
    """
    Connect to MongoDB Atlas and return a database handle.

    Args:
        connection_string (str): Full MongoDB Atlas URI.
                                 Loaded from MONGODB_URI environment variable in app.py.
        db_name (str): Name of the database to connect to. Default: 'trialwatch_db'.

    Returns:
        pymongo.database.Database: Database handle passed into all query functions.
    """
    client = MongoClient(connection_string)
    return client[db_name]


# ── DASHBOARD KPI QUERIES ─────────────────────────────────────────────────────

def get_compliance_overview(db):
    """
    Return headline KPI statistics for the dashboard hero section.

    Aggregates the compliance_status collection to compute:
        - Total number of ACT trials in the database
        - Trial count broken down by compliance status
        - Total noncompliant trials (LATE + MISSING combined)
        - Noncompliance percentage

    Args:
        db: PyMongo Database object.

    Returns:
        dict: {
            "total_trials": int,
            "by_status": {"COMPLIANT": int, "LATE": int, "MISSING": int, "NOT_DUE_YET": int},
            "total_noncompliant": int,
            "pct_noncompliant": float
        }
    """
    coll = db["compliance_status"]
    total = coll.count_documents({})  # Total ACT trials in our filtered dataset (132,185)

    # Group trials by compliance_status and count each category
    pipeline = [
        {"$group": {"_id": "$compliance_status", "count": {"$sum": 1}}}
    ]

    # Convert aggregation result to a flat dict: {"LATE": 57821, "MISSING": 34936, ...}
    by_status = {row["_id"]: row["count"] for row in coll.aggregate(pipeline)}

    # Noncompliant = LATE (submitted but past deadline) + MISSING (never submitted)
    noncompliant = by_status.get("LATE", 0) + by_status.get("MISSING", 0)

    return {
        "total_trials":      total,
        "by_status":         by_status,
        "total_noncompliant": noncompliant,
        "pct_noncompliant":  round((noncompliant / total) * 100, 1) if total else 0
    }


def get_top_overdue_sponsors(db, n=10):
    """
    Return the top N sponsors ranked by number of noncompliant trials.

    Joins compliance_status → trials via $lookup to attach org_name and org_class,
    then groups by sponsor and counts LATE + MISSING trials per sponsor.

    Used for: Dashboard leaderboard table, Chart.js horizontal bar chart.

    Args:
        db: PyMongo Database object.
        n (int): Number of sponsors to return. Default: 10.

    Returns:
        list[dict]: Each dict contains:
            - sponsor (str): Organization name
            - sponsor_class (str): INDUSTRY / NIH / OTHER
            - noncompliant_count (int): Total LATE + MISSING trials
            - late_count (int): Trials with results submitted after deadline
            - missing_count (int): Trials with results never submitted
            - max_days_overdue (int): Worst single-trial overdue days for this sponsor
    """
    pipeline = [
        # Filter to only noncompliant trials (LATE or MISSING)
        {"$match": {"compliance_status": {"$in": ["LATE", "MISSING"]}}},

        # Join with trials collection to get org_name and org_class
        {
            "$lookup": {
                "from": "trials",
                "localField": "_id",       # compliance_status._id = nct_id
                "foreignField": "_id",     # trials._id = nct_id
                "as": "trial"
            }
        },
        {"$unwind": "$trial"},  # Flatten the joined array (1-to-1 join)

        # Group by sponsor: count noncompliant trials and compute max overdue days
        {
            "$group": {
                "_id":               "$trial.org_name",
                "sponsor_class":     {"$first": "$trial.org_class"},
                "noncompliant_count": {"$sum": 1},
                # Conditional count: only add 1 if compliance_status == "LATE"
                "late_count": {
                    "$sum": {"$cond": [{"$eq": ["$compliance_status", "LATE"]}, 1, 0]}
                },
                # Conditional count: only add 1 if compliance_status == "MISSING"
                "missing_count": {
                    "$sum": {"$cond": [{"$eq": ["$compliance_status", "MISSING"]}, 1, 0]}
                },
                "max_days_overdue": {"$max": "$days_overdue"}
            }
        },
        {"$sort": {"noncompliant_count": -1}},  # Sort descending by noncompliant count
        {"$limit": n},

        # Rename _id → sponsor for cleaner API response
        {
            "$project": {
                "_id": 0,
                "sponsor":           "$_id",
                "sponsor_class":     1,
                "noncompliant_count": 1,
                "late_count":        1,
                "missing_count":     1,
                "max_days_overdue":  1
            }
        }
    ]

    return list(db["compliance_status"].aggregate(pipeline))


def get_top_dollar_sponsors(db, n=10):
    """
    Return the top N sponsors ranked by NIH public funding at risk.

    Uses the risk_enrichment collection which was populated in Step 2 by
    querying the NIH Reporter API for grants linked to noncompliant trials.
    funding_deduped avoids double-counting grants shared across multiple trials.

    Used for: Dashboard 'Top Dollar Sponsors' chart and sponsor profile KPI cards.

    Args:
        db: PyMongo Database object.
        n (int): Number of sponsors to return. Default: 10.

    Returns:
        list[dict]: Each dict contains:
            - sponsor (str): Organization name
            - noncompliant_trials (int): Number of noncompliant trials with risk data
            - dollars_at_risk (float): Total deduplicated NIH funding at risk (USD)
            - total_aes (int): Total adverse event reports linked to this sponsor
    """
    pipeline = [
        # Group all risk_enrichment records by sponsor (org_name)
        {
            "$group": {
                "_id":                "$org_name",
                "noncompliant_trials": {"$sum": 1},
                "dollars_at_risk":     {"$sum": "$funding_deduped"},      # NIH Reporter funding
                "total_aes":           {"$sum": "$ae_count_deduped"}       # FAERS adverse events
            }
        },
        # Only include sponsors with at least some funding at risk
        {"$match": {"dollars_at_risk": {"$gt": 0}}},
        {"$sort": {"dollars_at_risk": -1}},  # Sort descending by funding at risk
        {"$limit": n},
        {
            "$project": {
                "_id": 0,
                "sponsor":             "$_id",
                "noncompliant_trials": 1,
                "dollars_at_risk":     1,
                "total_aes":           1
            }
        }
    ]

    return list(db["risk_enrichment"].aggregate(pipeline))


def get_top_danger_sponsors(db, n=10):
    """
    Return the top N sponsors ranked by total adverse event (AE) report volume.

    AE data comes from FDA FAERS (65.7M rows processed in Step 2 via PySpark).
    Trials were matched to FAERS records by drug ingredient name using
    OpenFDA Drug Labels API for brand ↔ generic normalization.
    ae_count_deduped removes duplicate reports for the same drug-trial pair.

    Used for: Dashboard danger chart and sponsor risk tier analysis.

    Args:
        db: PyMongo Database object.
        n (int): Number of sponsors to return. Default: 10.

    Returns:
        list[dict]: Each dict contains:
            - sponsor (str): Organization name
            - noncompliant_trials (int): Number of trials with AE data
            - total_aes (int): Total deduplicated adverse event reports
            - dollars_at_risk (float): NIH funding at risk for this sponsor
    """
    pipeline = [
        # Group by sponsor and sum AE counts and funding
        {
            "$group": {
                "_id":                "$org_name",
                "noncompliant_trials": {"$sum": 1},
                "total_aes":           {"$sum": "$ae_count_deduped"},   # FDA FAERS AE count
                "dollars_at_risk":     {"$sum": "$funding_deduped"}     # NIH Reporter funding
            }
        },
        # Only include sponsors with at least one adverse event linked
        {"$match": {"total_aes": {"$gt": 0}}},
        {"$sort": {"total_aes": -1}},   # Sort descending by AE volume
        {"$limit": n},
        {
            "$project": {
                "_id": 0,
                "sponsor":             "$_id",
                "noncompliant_trials": 1,
                "total_aes":           1,
                "dollars_at_risk":     1
            }
        }
    ]

    return list(db["risk_enrichment"].aggregate(pipeline))


# ── DETAIL QUERIES ────────────────────────────────────────────────────────────

def get_trial_detail(db, nct_id):
    """
    Return a fully unified record for a single clinical trial by NCT ID.

    Performs a 3-way $lookup join across all three MongoDB collections:
        compliance_status → trials → risk_enrichment
    Returns a single flat dict with all fields needed for a trial detail view.

    Args:
        db: PyMongo Database object.
        nct_id (str): ClinicalTrials.gov NCT identifier (e.g. 'NCT00001017').

    Returns:
        dict or None: Unified trial record, or None if NCT ID not found.
        Fields include: sponsor, compliance_status, days_overdue, danger_score,
                        danger_tier, ae_count, public_dollars_at_risk, phases, etc.
    """
    pipeline = [
        # Start from compliance_status collection — match the requested NCT ID
        {"$match": {"_id": nct_id}},

        # Join with trials collection to get trial metadata
        {
            "$lookup": {
                "from":         "trials",
                "localField":   "_id",    # compliance_status._id = nct_id
                "foreignField": "_id",    # trials._id = nct_id
                "as":           "trial"
            }
        },
        {"$unwind": "$trial"},  # Flatten 1-to-1 join result

        # Join with risk_enrichment for danger score and NIH funding
        {
            "$lookup": {
                "from":         "risk_enrichment",
                "localField":   "_id",
                "foreignField": "_id",
                "as":           "risk"
            }
        },
        # preserveNullAndEmptyArrays=True keeps trials with no risk data (43.6% have matches)
        {"$unwind": {"path": "$risk", "preserveNullAndEmptyArrays": True}},

        # Project final output fields — flatten nested trial/risk subdocuments
        {
            "$project": {
                "_id":                    0,
                "nct_id":                 "$_id",
                "sponsor":                "$trial.org_name",
                "sponsor_class":          "$trial.org_class",
                "phases":                 "$trial.phases",
                "study_type":             "$trial.study_type",
                "overall_status":         "$trial.overall_status",
                "conditions":             "$trial.conditions",
                "intervention_names":     "$trial.intervention_names",
                "primary_completion_date": "$trial.primary_dt",
                "deadline":               1,                        # From compliance_status
                "results_submitted_date": "$trial.results_dt",
                "compliance_status":      1,                        # From compliance_status
                "days_overdue":           1,                        # From compliance_status
                "drug_ingredient":        "$risk.matched_ingredient",
                # Use $ifNull to return 0 when no risk record exists for this trial
                "ae_count":              {"$ifNull": ["$risk.ae_count_deduped", 0]},
                "danger_score":          {"$ifNull": ["$risk.danger_score", 0]},
                "danger_tier":           {"$ifNull": ["$risk.danger_tier", "NO DATA"]},
                "public_dollars_at_risk": {"$ifNull": ["$risk.funding_deduped", 0]}
            }
        }
    ]

    results = list(db["compliance_status"].aggregate(pipeline))
    return results[0] if results else None  # Return first result or None if not found


def get_sponsor_detail(db, sponsor_name, limit=20):
    """
    Return all noncompliant trials for a single sponsor, sorted by days overdue.

    Starts from risk_enrichment (which contains org_name), then joins
    compliance_status to get overdue days. Only returns LATE or MISSING trials.

    Used for: Sponsor intelligence profile page trial table.

    Args:
        db: PyMongo Database object.
        sponsor_name (str): Exact organization name (case-sensitive).
        limit (int): Maximum number of trials to return. Default: 20.

    Returns:
        list[dict]: Noncompliant trials sorted by days_overdue descending.
        Each dict includes: nct_id, compliance_status, days_overdue,
                            drug_ingredient, ae_count, danger_tier, public_dollars_at_risk.
    """
    pipeline = [
        # Filter risk_enrichment to the target sponsor's noncompliant trials only
        {
            "$match": {
                "org_name":          sponsor_name,
                "compliance_status": {"$in": ["LATE", "MISSING"]}
            }
        },

        # Join with compliance_status to get days_overdue
        {
            "$lookup": {
                "from":         "compliance_status",
                "localField":   "_id",
                "foreignField": "_id",
                "as":           "comp"
            }
        },
        {"$unwind": "$comp"},   # Flatten the joined array

        {"$sort": {"comp.days_overdue": -1}},   # Most overdue first
        {"$limit": limit},

        {
            "$project": {
                "_id": 0,
                "nct_id":                 "$_id",
                "compliance_status":      1,
                "days_overdue":           "$comp.days_overdue",
                "drug_ingredient":        "$matched_ingredient",
                "ae_count":               "$ae_count_deduped",
                "danger_tier":            1,
                "public_dollars_at_risk": "$funding_deduped"
            }
        }
    ]

    return list(db["risk_enrichment"].aggregate(pipeline))


def search_sponsors(db, query_string, limit=10):
    """
    Fuzzy case-insensitive sponsor name search for the dashboard search bar.

    Uses a MongoDB $regex match on org_name in the risk_enrichment collection,
    then groups results by sponsor and returns them sorted by trial count.
    This allows partial matches (e.g. 'pfizer' matches 'Pfizer Inc.').

    Args:
        db: PyMongo Database object.
        query_string (str): Partial or full sponsor name to search for.
        limit (int): Maximum number of results to return. Default: 10.

    Returns:
        list[dict]: Matching sponsors sorted by trial count descending.
        Each dict includes:
            - sponsor (str): Full organization name
            - trial_count (int): Number of trials in the risk_enrichment collection
    """
    # Compile regex with IGNORECASE flag for case-insensitive partial matching
    regex = re.compile(query_string, re.IGNORECASE)

    pipeline = [
        # Match any org_name that contains the query string (partial match)
        {"$match": {"org_name": {"$regex": regex}}},

        # Group by org_name and count how many trials each sponsor has
        {
            "$group": {
                "_id":         "$org_name",
                "trial_count": {"$sum": 1}
            }
        },
        {"$sort": {"trial_count": -1}},  # Most trials first (most relevant sponsors first)
        {"$limit": limit},
        {
            "$project": {
                "_id": 0,
                "sponsor":     "$_id",
                "trial_count": 1
            }
        }
    ]

    return list(db["risk_enrichment"].aggregate(pipeline))