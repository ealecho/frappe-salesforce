"""Add the custom_grant_budget Table field to CRM Deal on existing sites.

The ``CRM Grant Budget`` child doctype itself is shipped as an app DocType
(``doctype/crm_grant_budget``) and is created by model sync, which runs
*before* this post_model_sync patch — so the Table field's ``options``
target already exists by the time ``create_custom_fields`` validates it.
"""

from __future__ import annotations

from frappe_salesforce.setup.custom_fields import ensure_all_custom_fields


def execute() -> None:
    ensure_all_custom_fields()
