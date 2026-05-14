"""One-shot: invalidate the cached Salesforce token.

Up to v0.1.6 the auth layer wrote ``token_expires_at`` using
``frappe.utils.add_to_date(now_datetime(), seconds=expires_in)``. That is
naive *local* time, while the actual SF token expiry (embedded in the
JWT's ``exp`` claim) is absolute UTC. On any non-UTC site this could
produce a stored expiry that disagreed with the token's real expiry —
under some conditions by several hours.

The visible symptom was repeated ``INVALID_AUTH_HEADER /
INVALID_JWT_FORMAT`` 401s: ``_cached_token_valid()`` returned True
because the stored expiry said the token was still good, while SF (which
trusts only its own ``exp``) rejected it as expired.

v0.1.7 fixes the underlying math (UTC throughout) and trusts the JWT's
own ``exp`` first, falling back to the stored value only when the token
isn't a JWT. But sites that deploy 0.1.7 may still have a stale, already-
desynced row in ``Salesforce Settings``. Nulling ``token_expires_at``
forces ``get_access_token()`` on the next scheduler tick to re-fetch a
fresh token, which will be persisted with the corrected UTC math.

Idempotent: setting an already-null field to null is a no-op.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    if not frappe.db.exists("DocType", "Salesforce Settings"):
        # App not installed on this site — nothing to do.
        return
    frappe.db.set_single_value("Salesforce Settings", "token_expires_at", None)
    frappe.db.commit()
