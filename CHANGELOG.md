# Changelog

## [0.1.8]

### Fixed
- `Token persist verification failed: wrote len=N but read back len=N`
  raised by `test_connection` and scheduler runs on v0.1.7. Root cause:
  Frappe's `get_decrypted_password` is memoised in
  `frappe.local.request_cache` for the lifetime of a request; the
  v0.1.7 write-verify readback inside the same request returned the
  token cached *before* the write, not the value just persisted to
  `__Auth`. Lengths matched (both real SF tokens cluster around the
  same size) so the symptom was misleading. Frappe's shared Redis
  password cache can cause the same shadowing across workers.

### Changed (auth.py)
- Removed the v0.1.7 atomic write-verify block. It was generating
  false positives against an in-process cache rather than catching a
  real `__Auth` write failure. The remaining v0.1.7 protections (JWT
  exp as source of truth, UTC math, naive-UTC persistence, token
  `.strip()`) are sufficient.
- New helper `_invalidate_password_cache(doctype, fieldname)`. Called
  after every successful token write and from
  `invalidate_cached_token`. Drops:
  1. The in-process `frappe.local.request_cache` bucket for
     `get_decrypted_password` (the actual culprit behind v0.1.7's
     false positives).
  2. The shared Redis cache entries under all known hash names
     (`__password`, `passwords`, `frappe.utils.password`) and key
     shapes — best-effort, swallowing errors.

### Changed (patch)
- `patches/v0_1_0/clear_desynced_sf_token.py` additionally evicts the
  Redis password-cache entry for `Salesforce Settings.access_token`
  so the first post-migrate read isn't shadowed by a pre-deploy stale
  entry. Still idempotent.

## [0.1.7]

### Fixed
- Persistent `INVALID_AUTH_HEADER` / `INVALID_JWT_FORMAT` 401s on
  non-UTC sites. Root cause confirmed by decoding the cached token's
  JWT payload on a staging site (`Europe/London`):
  - SF embedded `exp` in the JWT (UTC absolute time): ~14:20 UTC.
  - Our persisted `token_expires_at`: ~19:01 local naive (=18:01 UTC),
    written via `frappe.utils.add_to_date(now_datetime(), seconds=…)`,
    which adds to *local naive* time. The result was a stored expiry
    nearly 4 hours after the token's true SF-side expiry. The cache
    happily served an expired token; SF correctly rejected it.
  - Plus: the persisted `(access_token, token_expires_at)` pair can
    desync if one Frappe `set_single_value` lands but the other
    doesn't, with no detection.

### Changed (auth.py)
- `_cached_token_valid()` now decodes the JWT's own `exp` claim and
  compares to UTC `datetime.now(timezone.utc)`. The JWT IS the source
  of truth; stored `token_expires_at` is advisory only and consulted
  only for non-JWT (legacy opaque) session IDs.
- `_do_fetch_new_token()` stores `token_expires_at` as **naive UTC**
  (consistent with the JWT-derived expiry it reads), not naive local.
  Prefers the JWT's `exp` claim; falls back to `expires_in` only when
  the token isn't a JWT.
- `_do_fetch_new_token()` sanitises the returned `access_token` via
  `.strip()` before persisting (defense against any whitespace SF
  might emit in edge cases).
- `_do_fetch_new_token()` performs an atomic write-verify after
  `frappe.db.commit()`: reads the encrypted `access_token` back and
  raises `SalesforceAuthError` if it doesn't match what was just
  written. Catches silent `__Auth` write failures at the source
  instead of caching a desynced pair.
- New helper `_decode_jwt_exp(token)` parses the JWT payload
  (signature unverified — we trust the token's own self-describing
  metadata for expiry only).

### Migration
- `patches/v0_1_0/clear_desynced_sf_token` — nulls the current
  `token_expires_at` once so the first post-deploy scheduler tick
  re-fetches a fresh token under the corrected UTC math. Idempotent.

## [0.1.6]

### Fixed
- Intermittent `INVALID_AUTH_HEADER` / `INVALID_JWT_FORMAT` 401s during
  scheduled sync. Root causes:
  1. `_cached_token_valid()` read `token_expires_at` from a snapshot
     taken in `SalesforceAuth.__init__`. A concurrent worker that just
     refreshed (or invalidated) the token left this caller working off
     a stale expiry.
  2. `invalidate_cached_token()` wrote an empty string to the
     encrypted `access_token` field, creating an intermediate state
     where a concurrent reader could fetch `""` and assemble a
     malformed `Authorization: Bearer ` header.
  3. No cross-process mutex around `_fetch_new_token()`. Two scheduler
     workers waking simultaneously could both POST to the token
     endpoint and race their cached-token writes.
  4. Cached token shape was never validated — a truncated / corrupted
     blob would round-trip through `get_access_token` and immediately
     fail at Salesforce.

### Changed
- `auth._cached_token_valid()` now reads `token_expires_at` live via
  `frappe.db.get_single_value` instead of `self.settings`.
- `auth.get_access_token()` validates the cached token has at least
  `MIN_PLAUSIBLE_TOKEN_LEN` chars before returning it; otherwise
  refreshes.
- `auth.invalidate_cached_token()` nulls `token_expires_at` only;
  never writes an empty `access_token`.
- `auth._fetch_new_token()` wraps the actual fetch in
  `frappe.utils.synchronization.filelock("sf_token_refresh",
  timeout=30)` with a double-checked-locking guard so a contending
  worker reuses the freshly-cached token rather than re-fetching.
- `client._get()` emits a one-shot diagnostic `log_error` on the first
  401 per client instance, capturing token length (never the value),
  snapshot-vs-live expiry, and the SF response body.
- `BaseSyncer.run()` catches `SalesforceAPIError(status_code=401)`
  inside the SOQL pagination loop, increments a local counter, and
  aborts the syncer after 3 consecutive auth failures (allowing the
  orchestrator to continue with the next object). Single failures are
  logged but tolerated.

### Migration
- None. Pure code-level fix.

## [0.1.5]

### Fixed
- Hotfix for 0.1.4 migration: Frappe rejects `Data → Long Text`
  fieldtype change (`ALLOWED_FIELDTYPE_CHANGE` only permits
  `Data <-> Small Text` and `Data <-> Text`). Switched
  `custom_sf_file_location` to `Small Text` and updated the
  `widen_file_location` patch accordingly. Added a `_small_text` helper
  in `setup/custom_fields.py` to make the intent explicit for any
  future Data-overflow fixes.

## [0.1.4]

### Fixed
- `CharacterLengthExceededError` on `CRM Deal.custom_sf_file_location`
  during Opportunity sync. SF stores long network-share paths wrapped
  in `<strong>` HTML; the original 140-char `Data` field overflowed.
  Symptom: `'<strong>File Location</strong>' (C:\...) will get
  truncated, as max characters allowed is 140`.
- The `File_location__c → custom_sf_file_location` mapping row gains
  the `html_strip` transform so HTML wrappers don't leak into Frappe.

### Added
- `BaseSyncer._truncate_to_max_length()` — generic safety net that
  silently truncates scalar string values to the target field's max
  length (cached per syncer via `frappe.get_meta`). Logs once per
  `(doctype, field)` per run with a sample of the offending value, so
  oversized fields are surfaced for widening rather than aborting the
  whole record. Applies to `Data` / `Link` / `Select` (which enforce
  the cap); Long/Small/Markdown text are untouched.

### Migration
- `patches/v0_1_0/widen_file_location` — converts
  `CRM Deal.custom_sf_file_location` from `Data` to `Small Text` on
  existing sites. We use Small Text (not Long Text) because Frappe's
  `ALLOWED_FIELDTYPE_CHANGE` only permits `Data <-> Small Text` /
  `Data <-> Text`. Idempotent.
- `patches/v0_1_0/set_file_location_html_strip` — backfills the
  `html_strip` transform on the existing mapping row. Idempotent.

## [0.1.3]

### Fixed
- `LinkValidationError` on clean installs when SF picklist values land in
  Frappe CRM Link fields. The bare `deal_stage` / `lead_status` /
  `task_status` / `task_priority` / `deal_lost_reason` transforms only
  mapped values; they didn't ensure the target Link parent existed.
  Symptom on staging: `Could not find Status: Proposal/Quotation` during
  `OpportunitySyncer` upsert. Same class as the v0.1.0 `lead_source` fix
  but for the other picklists.

### Added
- `_ensure_link(doctype, value, *name_field_candidates)` shared helper in
  `sync/transforms.py` — idempotent upsert of a Link parent by name.
  Tolerates missing DocType (returns the bare string) so the same
  transform works against installs whose CRM still uses Select fields.
- New transforms registered in the dispatcher:
  - `deal_stage_link` — `map_deal_stage` + `CRM Deal Status` upsert
  - `lead_status_link` — `map_lead_status` + `CRM Lead Status` upsert
  - `task_status_link` — `map_task_status` + `CRM Task Status` upsert
  - `task_priority_link` — `map_task_priority` + `CRM Task Priority` upsert
  - `deal_lost_reason_link` — `map_deal_lost_reason` + `CRM Lost Reason` upsert
- `industry_link`, `lead_source_link`, `lost_reason_link` refactored to
  delegate to `_ensure_link` (behaviour preserved; less duplication).
- `Salesforce Field Mapping Row.transform` Select options extended with
  the five new `_link` variants.

### Migration
- `patches/v0_1_0/safen_link_transforms` — rewrites mapping rows on
  existing sites from each bare picklist transform to its `_link`
  variant. Idempotent; only touches rows still using the old names.

### Tests
- `test_transforms.py` — 10 new asserts exercising each `_link` wrapper
  via stubbed `frappe.db` / `frappe.get_doc` (no site required).
- `test_default_mappings_meta.py` — five regression tests asserting
  `Lead.Status`, `Opportunity.StageName→status`,
  `Opportunity.StageName→lost_reason`, `Task.Status`, `Task.Priority`
  default to their `_link` transforms.

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
