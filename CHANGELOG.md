# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.2]

### Added
- Six new Salesforce-mirror DocTypes: `SF Campaign`, `SF Recurring Donation`,
  `SF Contact Relationship`, `SF Contact Affiliation`, `SF Opportunity Payment`,
  `SF Event Invitee`. All autoname by `field:custom_salesforce_id`.
- Six new syncers (`campaigns`, `recurring_donations`, `payments`,
  `relationships`, `affiliations`, `event_relations`) wired into the registry
  in dependency order: 15, 55, 58, 65, 68, 75.
- `frappe_salesforce/setup/custom_fields.py` — single source of truth for every
  `custom_sf_*` mirror field, shared by `setup/install.py` and the v0_0_2 patch.
- `frappe_salesforce/sync/addresses.py` — compound SF address blocks
  (`Billing*`, `Shipping*`, `Mailing*`, `Other*`) now upserted as real Frappe
  `Address` docs linked via `Dynamic Link`, idempotent per
  `(parent_doctype, parent_name, address_type)`. Wired in via
  `BaseSyncer.after_upsert` from Account/Contact/Lead.
- Polymorphic reference resolution (`polymorphic_lookup`, `polymorphic_doctype`)
  for SF `WhoId`/`WhatId` and the new Relationship/Affiliation/EventRelation
  references.
- Lead conversion handling: `LeadSyncer` no longer filters converted leads at
  the SOQL level and now propagates `ConvertedAccountId`/`ConvertedContactId`/
  `ConvertedOpportunityId` to the corresponding Frappe records.
- NPSP/Gift Aid rollup fields surfaced as `custom_sf_*` on `CRM Organization`
  and `Contact`.
- Six new high-water-mark fields on `Salesforce Settings`
  (`last_sync_campaign`, `last_sync_recurring_donation`, `last_sync_payment`,
  `last_sync_relationship`, `last_sync_affiliation`, `last_sync_event_relation`).
- `patches/v0_0_2/` patches: `add_custom_fields`, `seed_new_hwm_fields`,
  `extend_default_mappings` — applied in order via `patches.txt`.
- Site-free unit tests: `tests/test_addresses.py` plus expanded
  `tests/test_transforms.py` covering `map_lead_status`,
  `map_deal_lost_reason`, `map_task_status`, and `map_task_priority`.
- Repo-root `pyrightconfig.json` (basic mode, py3.10) and clean pyright run
  (0 errors / 0 warnings).

### Changed
- `setup/install.py` now delegates to `ensure_all_custom_fields()` and seeds
  every HWM (including the six new ones) to install-time `now()` to prevent
  epoch backfill.
- `hooks.py` fixtures filter broadened to
  `[["fieldname", "like", "custom_sf%"]]` plus `custom_salesforce_id` so all
  mirror fields are exported.
- 12 entries in `setup/default_mappings.py` (added Campaign, Recurring
  Donation, Payment, Relationship, Affiliation, EventRelation).

### Fixed
- `patches/v0_0_1/add_custom_salesforce_id_fields.py` previously imported a
  deleted helper. It now calls `ensure_all_custom_fields()` from
  `setup.custom_fields`.
- Pyright issues in `api/sync.py` (possibly-unbound after `frappe.throw`) and
  `salesforce/client.py` (Optional access on `_settings`).

## [0.0.1]

Initial release: User/Account/Contact/Lead/Opportunity/Task/Event syncers,
JWT bearer auth, SOQL pagination, rate-limit abort, scheduler integration,
and `Salesforce Record Link` mapping.
