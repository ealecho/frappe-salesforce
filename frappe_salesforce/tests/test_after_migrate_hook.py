"""The after_migrate hook must stay wired so mappings self-heal on migrate.

Regression guard for the dev-vs-staging incident where a site synced blank
fields because its ``Salesforce Field Mapping`` records were never seeded
(after_install only fires on fresh installs; patches run once). Importing
``hooks`` needs no site, so this runs everywhere.
"""

from frappe_salesforce import hooks


def test_after_migrate_hook_is_wired():
    assert hooks.after_migrate == "frappe_salesforce.setup.install.after_migrate"
