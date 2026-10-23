"""Delete duplicate Salesforce Record Links and add a unique key.

See ``setup/record_links.py``. Local database work only, no Salesforce
calls.
"""

from frappe_salesforce.setup.record_links import ensure_record_link_unique


def execute():
    ensure_record_link_unique()
