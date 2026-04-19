# AGENTS.md

Frappe app providing one-way Salesforce → Frappe CRM sync. Loaded as a `bench` app inside a Frappe v15 site; **cannot run standalone** — `import frappe` is pervasive and requires a site context.

## Layout

- `frappe_salesforce/hooks.py` — Frappe app manifest. Scheduler cron, fixtures, install/uninstall hooks all live here.
- `frappe_salesforce/salesforce/` — outbound API layer (`auth.py` JWT Bearer, `client.py` REST + SOQL pagination + 401 retry + rate-limit abort, `soql.py` query builder).
- `frappe_salesforce/sync/` — per-object syncers. `base.BaseSyncer` is the contract; `registry.SYNCERS` is sorted by `order_in_sync` and **`UserSyncer` must run first** (a test enforces this).
- `frappe_salesforce/tasks/scheduled.py` — entrypoints wired from `hooks.scheduler_events`. Both gate on `Salesforce Settings.enabled`.
- `frappe_salesforce/frappe_salesforce/doctype/` — DocType definitions (note the doubled path; this is standard Frappe layout, not a typo).
- `frappe_salesforce/setup/install.py` — `after_install` creates the `custom_salesforce_id` Data field on the 5 target DocTypes and `custom_sf_activity_type` (Select) on `CRM Task` only.
- `frappe_salesforce/patches/` — referenced from `patches.txt`; run by `bench migrate`.

## Required env

- Frappe `>=15,<16` and the `frappe/crm` app must be installed on the site before this app (`required_apps` in hooks; also declared under `[tool.bench.frappe-dependencies]` in `pyproject.toml`).
- Python `>=3.10`.

## Commands

Install / upgrade in a bench:

```
bench get-app <repo>
bench --site <site> install-app frappe_salesforce
bench --site <site> migrate          # runs patches.txt
bench restart
```

Tests run through bench, not pytest directly (they need a site):

```
bench --site <site> run-tests --app frappe_salesforce
bench --site <site> run-tests --app frappe_salesforce --module frappe_salesforce.tests.test_syncers
```

`test_auth.py` integration test is `@pytest.mark.skip` — needs a real SF sandbox.

There is **no lint, formatter, typecheck, or CI config** in the repo; do not invent commands. `.ruff_cache/` is gitignored but no ruff config exists.

## Conventions / gotchas

- All sync writes use `ignore_permissions=True` and run as the scheduler user.
- Per-record errors in `BaseSyncer.run` are swallowed into `frappe.log_error` and counted in the `Salesforce Sync Log` item; only fatal errors propagate.
- High-water mark is `SystemModstamp` per object, stored on `Salesforce Settings` (one field per syncer — `test_all_syncers_have_unique_hwm_fields` enforces uniqueness). Default epoch on first run is `1970-01-01T00:00:00Z`.
- The `Salesforce Record Link` DocType is the source of truth mapping `(salesforce_id, salesforce_object) -> (frappe_doctype, frappe_name)`. `_upsert_doc` falls back to matching by `custom_salesforce_id` before creating.
- `link_only=True` syncers (e.g. `UserSyncer`) populate `Salesforce Record Link` rows but do **not** create Frappe docs — they exist so other syncers can resolve owner references.
- Salesforce client aborts the whole sync if `Sforce-Limit-Info` shows ≥90% daily API usage (`SalesforceRateLimitError`). Don't remove this without a replacement throttle.
- API version default is `v60.0` (overridable via `Salesforce Settings.api_version`).
- Field mappings are data, not code: edit `Salesforce Field Mapping` records in the site. `setup/default_mappings.py` only seeds them on install. Adding a SOQL field requires a mapping row, not a syncer change.
- Custom fields are managed two ways: programmatically in `setup/install.py` for new sites, and via `fixtures/custom_field.json` for upgrades. Keep both in sync when adding fields.
