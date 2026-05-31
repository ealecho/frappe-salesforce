"""One-shot: invalidate the cached Salesforce token + password cache.

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

v0.1.7 fixed the math (UTC throughout, prefers the JWT's own ``exp``).
v0.1.8 additionally invalidates Frappe's Redis password cache after
every token write — without this, ``get_decrypted_password`` can keep
returning a stale prior token for the cache TTL even though
``__Auth`` has been updated.

This patch:
1. Nulls ``token_expires_at`` so the next scheduler tick re-fetches.
2. Drops the Redis password cache entry for ``access_token`` so the
   next read after the fetch isn't shadowed by a pre-deploy stale entry.

Idempotent.
"""

from __future__ import annotations

import frappe


def execute() -> None:
    if not frappe.db.exists("DocType", "Salesforce Settings"):
        # App not installed on this site — nothing to do.
        return
    frappe.db.set_single_value("Salesforce Settings", "token_expires_at", None)
    frappe.db.commit()

    # Best-effort Redis password-cache invalidation. The cache-key shape
    # varies across Frappe versions; try every known variant. Failures
    # are non-fatal — the next token write will overwrite the cache
    # eventually anyway, this just speeds it up.
    try:
        cache = frappe.cache()
    except Exception:
        return
    for key in (
        "Salesforce Settings.Salesforce Settings.access_token",
        "Salesforce Settings|Salesforce Settings|access_token",
        "Salesforce SettingsSalesforce Settingsaccess_token",
    ):
        for hash_name in ("__password", "passwords", "frappe.utils.password"):
            try:
                cache.hdel(hash_name, key)
            except Exception:
                pass
