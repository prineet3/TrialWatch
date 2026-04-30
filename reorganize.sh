#!/bin/bash
# Run this from inside your trialwatch_flask folder
# cd path/to/trialwatch_flask && bash reorganize.sh

echo "Creating folder structure..."
mkdir -p app/templates
mkdir -p app/static
mkdir -p pipeline/01_ingestion
mkdir -p pipeline/02_enrichment
mkdir -p notebooks
mkdir -p data
mkdir -p docs

echo "Moving Flask app files..."
# Move core app files into app/
mv trialwatch_queries.py app/trialwatch_queries.py 2>/dev/null || echo "  trialwatch_queries.py already moved or missing"

echo "Moving templates and static..."
# templates/ and static/ go inside app/
mv templates app/templates 2>/dev/null || echo "  templates/ already in place or missing"
mv static app/static 2>/dev/null || echo "  static/ already in place or missing"

echo "Moving notebooks..."
mv "Step1 - Spark (1).ipynb" notebooks/step1_ingestion.ipynb 2>/dev/null || echo "  Step1 notebook already moved or missing"
mv "Copy of Copy of risk_enrichment_spark.ipynb" notebooks/step2_enrichment.ipynb 2>/dev/null || echo "  Step2 notebook already moved or missing"

echo "Moving CSV data files..."
mv "trialsclean (1).csv" data/trialsclean.csv 2>/dev/null || echo "  trialsclean csv already moved or missing"
mv compliancemetrics.csv data/compliancemetrics.csv 2>/dev/null || echo "  compliancemetrics.csv already moved or missing"
mv "Copy of risk_enrichment.csv" data/risk_enrichment.csv 2>/dev/null || echo "  risk_enrichment.csv already moved or missing"

echo "Moving presentation to docs..."
mv TrialWatch_Final_Presentation.pptx.pdf docs/TrialWatch_Final_Presentation.pdf 2>/dev/null || echo "  Presentation already moved or missing"

echo "Removing venv from repo (should never be committed)..."
rm -rf venv/

echo "Adding .gitkeep to data folder so Git tracks it..."
touch data/.gitkeep

echo ""
echo "Done! Your repo should now look like this:"
echo ""
echo "trialwatch_flask/"
echo "├── app.py"
echo "├── Procfile"
echo "├── requirements.txt"
echo "├── README.md"
echo "├── render.yaml"
echo "├── .gitignore"
echo "├── app/"
echo "│   ├── trialwatch_queries.py"
echo "│   ├── templates/"
echo "│   └── static/"
echo "├── notebooks/"
echo "│   ├── step1_ingestion.ipynb"
echo "│   └── step2_enrichment.ipynb"
echo "├── data/"
echo "│   ├── trialsclean.csv"
echo "│   ├── compliancemetrics.csv"
echo "│   └── risk_enrichment.csv"
echo "└── docs/"
echo "    └── TrialWatch_Final_Presentation.pdf"
echo ""
echo "Next steps:"
echo "  1. Copy README.md, .gitignore, requirements.txt, render.yaml from the files Claude gave you"
echo "  2. Then run:"
echo "     git add ."
echo '     git commit -m "Reorganize repo: clean structure for submission"'
echo "     git push"
