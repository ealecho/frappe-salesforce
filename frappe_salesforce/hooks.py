app_name = "frappe_salesforce"
app_title = "Frappe Salesforce"
app_publisher = "Your Name"
app_description = "Salesforce (SOQL) integration for Frappe CRM"
app_email = "you@example.com"
app_license = "MIT"

required_apps = ["frappe/crm"]

# Installation hooks
after_install = "frappe_salesforce.setup.install.after_install"
before_uninstall = "frappe_salesforce.setup.uninstall.before_uninstall"

# Scheduler
scheduler_events = {
    "cron": {
        # Incremental sync every 15 minutes
        "*/15 * * * *": [
            "frappe_salesforce.tasks.scheduled.run_incremental_sync",
        ],
        # Deletion sweep daily at 03:00
        "0 3 * * *": [
            "frappe_salesforce.tasks.scheduled.run_deletion_sync",
        ],
    },
}

# Fixtures
#
# Export every SF mirror custom field — they all share the ``custom_sf_*``
# prefix (plus the legacy ``custom_salesforce_id``). Install/patch creates
# the fields programmatically; this fixture ensures they're tracked in
# version control as well.
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            ["fieldname", "like", "custom_sf%"],
        ],
    },
    {
        "dt": "Custom Field",
        "filters": [
            ["fieldname", "=", "custom_salesforce_id"],
        ],
    },
]
