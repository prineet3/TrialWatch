from trialwatch_queries import (
    connect,
    get_compliance_overview,
    get_top_overdue_sponsors
)

MONGO_URI = "mongodb+srv://gb3013:EswRpPsIS7bPgTB4@trialwatch.zrkdkfu.mongodb.net/?appName=TrialWatch"
db = connect(MONGO_URI)

print(get_compliance_overview(db))
print(get_top_overdue_sponsors(db, 3))