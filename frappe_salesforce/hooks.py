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
# IMPORTANT: ``custom_sf_*`` fields are NOT exported as fixtures. They are
# created by ``setup/install.py:_ensure_custom_fields()`` on fresh installs
# and by ``patches/v0_1_0/add_custom_fields.py`` on upgrades — both via
# ``create_custom_fields(..., ignore_validate=True)`` which is fast.
#
# Fixture import is *not* fast — it calls ``frappe.db.updatedb(dt)`` after
# each Custom Field insert, triggering a per-field ``ALTER TABLE`` on the
# parent doctype. With ~100 ``custom_sf_*`` fields on Contact (8000+ rows)
# and ~115 on CRM Deal, every migrate would queue 200+ ALTERs that hold
# table-metadata locks for 30-60+ minutes and frequently exceed
# MariaDB's ``max_statement_time``. So we deliberately don't ship them
# as fixtures; the patch handles the create/update path explicitly.
#
# We still ship ``custom_salesforce_id`` as a fixture because (a) it's the
# upsert key, (b) it carries non-default flags (``unique``, ``search_index``)
# that must round-trip cleanly, and (c) it's a single field per doctype so
# ALTER cost is negligible.
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            ["fieldname", "=", "custom_salesforce_id"],
            [
                "dt",
                "in",
                [
                    "CRM Organization",
                    "Contact",
                    "CRM Lead",
                    "CRM Deal",
                    "CRM Task",
                ],
            ],
        ],
    },
]
