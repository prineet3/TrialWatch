"""
TrialWatch Query API
====================
Importable query functions for the dashboard and chatbot teams.

Usage:
    from trialwatch_queries import connect, get_compliance_overview

    db = connect("mongodb+srv://USER:PASS@cluster.mongodb.net/")
    overview = get_compliance_overview(db)
    print(overview)

All functions take `db` (a pymongo Database object) as the first argument.

Notes:
- Dollar amounts use `funding_deduped` and adverse events use `ae_count_deduped`
  to avoid double-counting when a single grant or drug is attributed across
  multiple trials.
- Trials collection includes `conditions` and `intervention_names` arrays per trial.
"""
from pymongo import MongoClient


def connect(connection_string, db_name="trialwatch_db"):
    """Connect to MongoDB Atlas and return a database handle."""
    client = MongoClient(connection_string)
    return client[db_name]


def get_compliance_overview(db):
    """Headline KPIs for dashboard hero.

    Returns:
        dict with total_trials, by_status (dict), total_noncompliant, pct_noncompliant
    """
    coll = db["compliance_status"]
    total = coll.count_documents({})
    pipeline = [{"$group": {"_id": "$compliance_status", "count": {"$sum": 1}}}]
    by_status = {row["_id"]: row["count"] for row in coll.aggregate(pipeline)}
    noncompliant = by_status.get("LATE", 0) + by_status.get("MISSING", 0)
    return {
        "total_trials": total,
        "by_status": by_status,
        "total_noncompliant": noncompliant,
        "pct_noncompliant": round((noncompliant / total) * 100, 1)
    }


def get_top_overdue_sponsors(db, n=10):
    """Top N sponsors by non-compliant trial count."""
    pipeline = [
        {"$match": {"compliance_status": {"$in": ["LATE", "MISSING"]}}},
        {"$lookup": {"from": "trials", "localField": "_id", "foreignField": "_id", "as": "trial"}},
        {"$unwind": "$trial"},
        {"$group": {
            "_id": "$trial.org_name",
            "sponsor_class": {"$first": "$trial.org_class"},
            "noncompliant_count": {"$sum": 1},
            "late_count": {"$sum": {"$cond": [{"$eq": ["$compliance_status", "LATE"]}, 1, 0]}},
            "missing_count": {"$sum": {"$cond": [{"$eq": ["$compliance_status", "MISSING"]}, 1, 0]}},
            "max_days_overdue": {"$max": "$days_overdue"}
        }},
        {"$sort": {"noncompliant_count": -1}},
        {"$limit": n},
        {"$project": {"sponsor": "$_id", "sponsor_class": 1, "noncompliant_count": 1,
                      "late_count": 1, "missing_count": 1, "max_days_overdue": 1, "_id": 0}}
    ]
    return list(db["compliance_status"].aggregate(pipeline))


def get_top_dollar_sponsors(db, n=10):
    """Top N sponsors by NIH dollars at risk (deduped)."""
    pipeline = [
        {"$group": {
            "_id": "$org_name",
            "noncompliant_trials": {"$sum": 1},
            "dollars_at_risk": {"$sum": "$funding_deduped"},
            "total_aes": {"$sum": "$ae_count_deduped"}
        }},
        {"$match": {"dollars_at_risk": {"$gt": 0}}},
        {"$sort": {"dollars_at_risk": -1}},
        {"$limit": n},
        {"$project": {"sponsor": "$_id", "noncompliant_trials": 1,
                      "dollars_at_risk": 1, "total_aes": 1, "_id": 0}}
    ]
    return list(db["risk_enrichment"].aggregate(pipeline))


def get_top_danger_sponsors(db, n=10):
    """Top N sponsors by adverse event volume (deduped)."""
    pipeline = [
        {"$group": {
            "_id": "$org_name",
            "noncompliant_trials": {"$sum": 1},
            "total_aes": {"$sum": "$ae_count_deduped"},
            "dollars_at_risk": {"$sum": "$funding_deduped"}
        }},
        {"$match": {"total_aes": {"$gt": 0}}},
        {"$sort": {"total_aes": -1}},
        {"$limit": n},
        {"$project": {"sponsor": "$_id", "noncompliant_trials": 1,
                      "total_aes": 1, "dollars_at_risk": 1, "_id": 0}}
    ]
    return list(db["risk_enrichment"].aggregate(pipeline))


def get_trial_detail(db, nct_id):
    """Full unified record for a single trial (joins all 3 collections).

    Returns dict with sponsor, status, drug, conditions, interventions,
    danger metrics, dollars at risk. Or None if NCT ID not found.
    """
    pipeline = [
        {"$match": {"_id": nct_id}},
        {"$lookup": {"from": "trials", "localField": "_id", "foreignField": "_id", "as": "trial"}},
        {"$unwind": "$trial"},
        {"$lookup": {"from": "risk_enrichment", "localField": "_id", "foreignField": "_id", "as": "risk"}},
        {"$unwind": {"path": "$risk", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "nct_id": "$_id", "_id": 0,
            "sponsor": "$trial.org_name",
            "sponsor_class": "$trial.org_class",
            "phases": "$trial.phases",
            "study_type": "$trial.study_type",
            "overall_status": "$trial.overall_status",
            "conditions": "$trial.conditions",
            "intervention_names": "$trial.intervention_names",
            "primary_completion_date": "$trial.primary_dt",
            "deadline": 1,
            "results_submitted_date": "$trial.results_dt",
            "compliance_status": 1,
            "days_overdue": 1,
            "drug_ingredient": "$risk.matched_ingredient",
            "ae_count": {"$ifNull": ["$risk.ae_count_deduped", 0]},
            "danger_score": {"$ifNull": ["$risk.danger_score", 0]},
            "danger_tier": {"$ifNull": ["$risk.danger_tier", "NO DATA"]},
            "public_dollars_at_risk": {"$ifNull": ["$risk.funding_deduped", 0]}
        }}
    ]
    results = list(db["compliance_status"].aggregate(pipeline))
    return results[0] if results else None


def get_sponsor_detail(db, sponsor_name, limit=20):
    """All non-compliant trials for a single sponsor, sorted by days overdue."""
    pipeline = [
        {"$match": {"org_name": sponsor_name, "compliance_status": {"$in": ["LATE", "MISSING"]}}},
        {"$lookup": {"from": "compliance_status", "localField": "_id", "foreignField": "_id", "as": "comp"}},
        {"$unwind": "$comp"},
        {"$sort": {"comp.days_overdue": -1}},
        {"$limit": limit},
        {"$project": {
            "nct_id": "$_id", "_id": 0,
            "compliance_status": 1,
            "days_overdue": "$comp.days_overdue",
            "drug_ingredient": "$matched_ingredient",
            "ae_count": "$ae_count_deduped",
            "danger_tier": 1,
            "public_dollars_at_risk": "$funding_deduped"
        }}
    ]
    return list(db["risk_enrichment"].aggregate(pipeline))


def search_sponsors(db, query_string, limit=10):
    """Fuzzy sponsor name search (case-insensitive partial match)."""
    import re
    regex = re.compile(query_string, re.IGNORECASE)
    pipeline = [
        {"$match": {"org_name": {"$regex": regex}}},
        {"$group": {"_id": "$org_name", "trial_count": {"$sum": 1}}},
        {"$sort": {"trial_count": -1}},
        {"$limit": limit},
        {"$project": {"sponsor": "$_id", "trial_count": 1, "_id": 0}}
    ]
    return list(db["risk_enrichment"].aggregate(pipeline))
