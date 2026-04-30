# TrialWatch 🔭
### Clinical Trial Compliance Intelligence System

> Turning clinical trial noncompliance into visible, actionable risk.

**Live at:** [trialwatch-flask.onrender.com](https://trialwatch-flask.onrender.com)  
---

## What It Does

Under FDAAA 801 (2007), all Applicable Clinical Trials (ACTs) must report results within 12 months of completion. 18 years later, **over 70% of trials are noncompliant** — with no single system connecting who owes results, what drugs were tested, what adverse events occurred, and how much taxpayer money is at stake.

TrialWatch aggregates four federal public datasets to surface noncompliant sponsors, link adverse event reports, and quantify taxpayer funding at risk — all in one searchable, live, publicly accessible dashboard.

---

## Key Stats

| Metric | Value |
|---|---|
| Total ACT Trials Monitored | 132,185 |
| Noncompliant Trials | 92,757 (70.2%) |
| NIH Funding at Risk | $1.6B |
| FDA FAERS Rows Processed | 65.7M |
| Worst Offender | 33 years overdue |

---

## Data Sources (Zero Licensing Cost)

| Source | Type | Volume | Output |
|---|---|---|---|
| [ClinicalTrials.gov](https://clinicaltrials.gov) | AACT flat files + REST API | ~581K trials | Compliance status & ACT filtering |
| [FDA FAERS](https://www.fda.gov/drugs/questions-and-answers-fdas-adverse-event-reporting-system-faers) | Bulk CSV | 65.7M AE reports | Danger scoring & AE linkage |
| [NIH Reporter](https://reporter.nih.gov/) | REST API | Federal grant data | Public funding at risk per sponsor |
| [OpenFDA Drug Labels](https://open.fda.gov/) | REST API | Drug label database | Brand ↔ generic standardization |

---

## Architecture

```
ClinicalTrials.gov (581K)  +  FDA FAERS (65.7M)  +  NIH Reporter  +  OpenFDA
          │
          ▼
  Step 1 — PySpark (Google Colab)
  581K → 132K ACT filter · FDAAA compliance logic
  → trialsclean.csv + compliancemetrics.csv
          │
          ▼
  Step 2 — API + PySpark Enrichment
  FAERS matching · NIH funding lookup · Danger scoring (0–100)
  → risk_enrichment.csv
          │
          ▼
  Step 3 — MongoDB Atlas (M0 free tier)
  3 collections: trials · compliance_status · risk_enrichment
  $lookup aggregation joins · 7 query functions → trialwatch_queries.py
          │
          ▼
  Step 4 — Flask + Gunicorn + Render
  6 routes · Jinja2 templates · Chart.js · CI/CD via GitHub
  → trialwatch-flask.onrender.com
```

---

## Repo Structure

```
trialwatch_flask/
│
├── README.md
├── .gitignore
├── requirements.txt
├── render.yaml
│
├── app/                          # Flask application
│   ├── __init__.py
│   ├── routes.py                 # 6 routes: dashboard, 4 APIs, sponsor profiles
│   ├── trialwatch_queries.py     # 7 reusable MongoDB query functions
│   ├── templates/                # Jinja2 HTML templates
│   └── static/                   # CSS, JS, Chart.js assets
│
├── pipeline/                     # Data processing scripts
│   ├── 01_ingestion/             # PySpark: ClinicalTrials → trialsclean.csv
│   ├── 02_enrichment/            # FAERS matching + NIH funding lookup
│   └── 03_mongodb_load/          # PyMongo CSV loader
│
├── notebooks/                    # Google Colab notebooks (.ipynb)
│
├── data/                         # Gitignored — CSVs too large for GitHub
│   └── .gitkeep
│
└── docs/
    └── architecture.png
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Big Data Processing | PySpark on Google Colab |
| Database | MongoDB Atlas M0 (NoSQL) |
| Python Driver | PyMongo |
| Web Framework | Flask + Gunicorn |
| Frontend | Jinja2 + Vanilla JS + Chart.js |
| Deployment | Render (GitHub CI/CD) |

---

## Setup & Run Locally

### Prerequisites
- Python 3.9+
- MongoDB Atlas account (free M0 tier)
- `.env` file with your MongoDB URI (see below)

### Installation

```bash
git clone https://github.com/prineet3/trialwatch_flask.git
cd trialwatch_flask
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the root directory:

```
MONGO_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/trialwatch
```

> ⚠️ Never commit your `.env` file. It is excluded via `.gitignore`.

### Run the App

```bash
python app.py
# or with Gunicorn:
gunicorn app:app
```

Visit `http://localhost:5000`

---

## Data Pipeline

The full pipeline runs in Google Colab. See `/notebooks/` for step-by-step notebooks:

1. **Step 1 — Ingestion:** Download AACT flat files, filter to 132K ACTs, classify compliance status
2. **Step 2 — Enrichment:** Match trials to FDA FAERS adverse events, query NIH Reporter for funding, assign danger scores (0–100)
3. **Step 3 — Load:** Push CSVs into MongoDB Atlas via PyMongo, set indexes, verify $lookup joins

---

## Danger Score Methodology

Danger scores (0–100) are assigned via log normalization of adverse event counts from FDA FAERS:

| Tier | Score Range |
|---|---|
| CRITICAL | 80–100 |
| HIGH | 60–79 |
| MODERATE | 40–59 |
| LOW | 1–39 |
| NO DATA | 0 |

43.6% of noncompliant trials were matched to a drug with adverse event data.

---

## Data Governance

- MongoDB URI stored as environment variable — never committed to Git
- `.env` + `.gitignore` enforced across all environments
- HTTPS enforced on Render deployment
- All 4 data sources are federally mandated public datasets — no licensing required
- No PII collected — aggregate trial metadata only
- No HIPAA or GDPR concerns

---

## Scalability Path

| Current (Prototype) | Production |
|---|---|
| Google Colab (PySpark) | AWS EMR managed Spark |
| MongoDB Atlas M0 (512MB) | MongoDB Atlas M10+ with sharding |
| Render free tier (Flask) | FastAPI + Gunicorn + AWS ALB |
| Docker Compose Kafka | AWS MSK managed Kafka |

---
## License

All underlying data is federally mandated and publicly licensed. This codebase is for academic use.
