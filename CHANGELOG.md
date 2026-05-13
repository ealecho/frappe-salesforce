# Changelog

## [0.1.2]

### Changed
- `hooks.fixtures` filter narrowed: only `custom_salesforce_id` is
  exported as a fixture. The previous `custom_sf%` glob would re-export
  ~290 `custom_sf_*` Custom Field records, each of which would trigger
  a per-field `ALTER TABLE` during `bench migrate`'s `sync_fixtures()`
  pass — easily exceeding MariaDB's `max_statement_time` on tables with
  thousands of rows. The `custom_sf_*` fields are managed code-side via
  `setup/custom_fields.py:ensure_all_custom_fields()` (called from
  `after_install` and `patches/v0_1_0/add_custom_fields`), which uses
  `create_custom_fields()` — that path emits a single per-doctype
  `ALTER` after all fields are created, not 290 separate ones.

### Documentation
- README adds a "Migration timeout on large Contact tables" section
  explaining how to diagnose and recover from a `max_statement_time`
  abort during `sync_fixtures()`.

## [0.1.1]

### Fixed
- Removed `Contact.RecordTypeId → custom_sf_record_type` from default
  mappings. NPSP orgs commonly FLS-restrict this field for the
  integration user, causing `INVALID_FIELD` 400s that abort the entire
  Contact sync before any record is fetched. The field can be re-added
  via the Salesforce Field Mapping UI on orgs that expose it.
- New patch `patches/v0_1_0/prune_problematic_mapping_rows` removes the
  same row from existing sites (mirrors v0.0.2's prune strategy).

### Added
- **FLS-blocked field auto-filter (Strategy B)**: `SalesforceClient`
  gains an `accessible_fields(sobject)` method that returns the case-
  preserved set of fields the integration user can SELECT via SF
  describe (one cached call per object per process).
- `BaseSyncer._soql_fields()` now passes the assembled SOQL field list
  through `_filter_fls_blocked()`, dropping any field absent from
  describe and emitting an `Error Log` entry naming the dropped
  fields. `Id` and `SystemModstamp` are always kept (they're required
  for sync bookkeeping). The filter fails open on describe errors —
  the syncer attempts SOQL with the unfiltered list rather than
  skipping the object entirely.

### Tests
- `test_fls_filter.py` — 5 unit tests covering the filter logic
  (drops blocked, keeps required, fails open on empty / exception,
  preserves order).
- `test_default_mappings_meta.py::test_contact_record_type_id_omitted_by_default`
  — regression test ensuring future PRs don't reintroduce the
  problematic row.

## [0.1.0] — Field coverage rework

### Fixed (mapping bugs from v0.0.x)
- `Opportunity.Amount` now writes to `deal_value` instead of `annual_revenue`
  (the latter is the org's annual revenue, not the deal size).
- `Opportunity.CloseDate` now writes to `expected_closure_date` (an actual
  field on `CRM Deal`) instead of the non-existent `close_date`. A derived
  `closed_date` is populated when `IsClosed=true` via
  `OpportunitySyncer.enrich_values`.
- `Account.NumberOfEmployees` (int) → `no_of_employees` (Select bucket) now
  routed through a new `employee_bucket` transform that maps the SF int to
  CRM Org's "1-10" / "11-50" / ... / "1000+" buckets.
- `Account.Industry` and `Lead.Industry` now resolve to a `CRM Industry`
  Link via the new `industry_link` transform that auto-upserts missing
  industry records (previously failed silently with `LinkValidationError`).
- `Lead.LeadSource` now resolves through a new `lead_source` transform
  that auto-upserts the `CRM Lead Source` record.
- `Task.ActivityDate` (Date) → `due_date` (Datetime) now uses the
  `datetime` transform (was `date`, causing type mismatch).
- `Contact.Email` / `Phone` / `MobilePhone` no longer target the read-only
  flat fields. New multi-input `email_table` and `phone_table` transforms
  populate the `email_ids` / `phone_nos` child tables, also covering
  `npe01__HomeEmail__c`, `npe01__WorkEmail__c`, `npe01__AlternateEmail__c`,
  `HomePhone`, `OtherPhone`, `AssistantPhone`, and `Fax`.

### Added (infrastructure)
- `Salesforce Field Mapping Row` gains an `sf_fields` Long Text column for
  multi-input transforms. When set, the transform receives a
  `dict[str, Any]` of `{sf_field: value}` instead of a scalar.
- `BaseSyncer.extra_soql_fields` class attribute for SF fields needed by
  `enrich_values` / `after_upsert` that aren't represented as mapping rows.
- `BaseSyncer.after_upsert` extension point for linked-record side effects
  (used for `Address` doc upsert).
- `setup/custom_fields.py` — single source of truth for every `custom_sf_*`
  field. Used by `setup/install.py`, the v0.1.0 patch, and exported via
  `hooks.fixtures` (filter broadened to `custom_sf%`).
- `sync/addresses.py` — Frappe `Address` doc upsert keyed by
  `(parent_doctype, parent_name, address_type)`. Wired in via
  `AccountSyncer.after_upsert` (Billing/Shipping) and
  `ContactSyncer.after_upsert` (Mailing/Other).
- `salesforce/soql.py::format_soql_datetime` now coerces space-separated
  datetime strings (`"YYYY-MM-DD HH:MM:SS"`, as returned by
  `frappe.utils.now_datetime()`) to ISO-8601 with a literal `T`. SOQL
  rejects the space form with `MALFORMED_QUERY`.
- New `Reset HWMs to Epoch (Full Backfill)` button in Salesforce Settings
  (Danger Zone), backed by `frappe_salesforce.api.sync.reset_all_high_water_marks`.

### Added (default mappings & custom fields)
- ~50 new mapping rows on Account → CRM Organization (NPSP rollups, PEAS
  custom fields, address block, standard SF mirrors).
- ~80 new mapping rows on Contact → Contact (NPSP rollups, communication
  preferences, address block, household / gift-aid fields, multi-channel
  email + phone).
- ~30 new mapping rows on Lead → CRM Lead (industry, annual revenue,
  employee count, conversion mirrors, NPSP / PEAS custom fields).
- ~80 new mapping rows on Opportunity → CRM Deal (NPSP grant workflow,
  gift aid, payment metadata, capex/opex, fund routing, project dates).
- ~20 new mapping rows on Task → CRM Task and Event → CRM Task
  (call metadata, completion timestamps, NPSP engagement plan refs).
- ~290 new `custom_sf_*` fields across CRM Organization (76), Contact (108),
  CRM Lead (23), CRM Deal (115), CRM Task (23). All marked `no_copy=1`;
  NPSP rollups and SF computed fields marked `read_only=1`.

### Changed
- `LeadSyncer` no longer filters `IsConverted=false` at the SOQL level;
  converted Leads are synced and their `status` forced to `"Converted"`
  via `enrich_values` so historical data is preserved.
- `LeadSyncer.enrich_values` defaults `first_name="-"` when SF FirstName is
  blank (Frappe CRM Lead requires `first_name`; SF only requires `LastName`).
- `ContactSyncer.after_upsert` now ensures Contact ↔ CRM Organization is
  navigable via the `Contact.links` Dynamic Link table (in addition to the
  free-text `company_name` field).
- `Task` and `Event` syncers force `status="Done"` when `IsClosed=true` or
  `CompletedDateTime` is present.

### Migration
- `patches/v0_1_0/add_custom_fields` — creates new `custom_sf_*` fields on
  existing sites.
- `patches/v0_1_0/fix_buggy_mappings` — surgically rewrites the
  `Amount→annual_revenue`, `CloseDate→close_date`, raw-Industry, raw-LeadSource,
  raw-NumberOfEmployees, and `ActivityDate→due_date(date)` rows; deletes
  the read-only Contact email/phone/mobile_no rows.
- `patches/v0_1_0/extend_default_mappings` — additively inserts new
  mapping rows; matches by `(sf_field, frappe_field)`; never overwrites or
  deletes user-customised rows.

### Tests
- `test_default_mappings_meta.py` — asserts every default mapping row
  targets a known native or `custom_sf_*` field, every transform is
  registered, no duplicate rows, no row missing input. Spot regression
  tests for each bug listed under "Fixed".
- `test_custom_fields.py` — asserts no duplicate fieldnames, every
  `custom_sf_*` is `no_copy=1`, every doctype carries `custom_salesforce_id`,
  every mapping target exists in `ALL_CUSTOM_FIELDS`.
- `test_transforms.py` — extended with `employee_bucket`, `address_block`,
  `email_table`, `phone_table` (40+ new assertions).
- `test_addresses.py` — `_extract_block`, `_has_any_value`, `PREFIX_TO_TYPE`.
- `test_soql.py` — regression test for space-separated datetime input.
