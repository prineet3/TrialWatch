# TrialWatch

**Clinical Trial Compliance & Risk Intelligence Dashboard**

Turning clinical trial noncompliance into visible, actionable risk.

## What it does

TrialWatch monitors 132,000+ clinical trials from ClinicalTrials.gov and surfaces:
- Which sponsors have the most noncompliant trials
- How much NIH public funding is linked to missing results
- Adverse event reports tied to overdue trials
- Individual sponsor risk profiles with phase and danger tier breakdowns

## Tech stack

- Python / Flask
- MongoDB Atlas
- Chart.js
- Vanilla JS + CSS

## Setup

1. Clone the repo
2. Create a virtual environment: `python -m venv venv && source venv/bin/activate`
3. Install dependencies: `pip install -r requirements.txt`
4. Set your MongoDB URI: `export MONGODB_URI="your-uri-here"`
5. Run: `python app.py`
6. Visit `http://127.0.0.1:5000`

## Data source

Compliance data sourced from ClinicalTrials.gov FDAAA ACT dataset. Updated monthly.
