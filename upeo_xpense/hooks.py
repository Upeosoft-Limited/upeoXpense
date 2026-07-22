app_name = "upeo_xpense"
app_title = "UpeoXpense"
app_publisher = "Upeosoft Limited"
app_description = "WhatsApp receipt capture and draft expense claims for a single ERPNext instance"
app_email = "karani@upeosoft.com"
app_license = "mit"

# ERPNext provides Employee; HRMS provides Expense Claim and Expense Claim Type.
required_apps = ["erpnext", "hrms"]

# Installation
# ------------
after_install = "upeo_xpense.install.after_install"
after_migrate = "upeo_xpense.install.after_migrate"

# Scheduled Tasks
# ---------------
# The retry poller re-runs extractions whose backoff window has elapsed. It runs
# every minute so the 1m / 5m / 15m / 1h backoff steps land on time. It is a
# no-op when nothing is due, so it is cheap.
scheduler_events = {
	"cron": {
		"* * * * *": [
			"upeo_xpense.pipeline.retry_due_extractions",
		],
	},
}
