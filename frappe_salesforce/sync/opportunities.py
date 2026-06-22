"""Opportunity → CRM Deal syncer."""

from __future__ import annotations

from datetime import date
from typing import Any

import frappe
from frappe.utils import get_datetime, now_datetime

from .base import BaseSyncer
from .transforms import map_contact

#: Salesforce ``Income_year__c`` fields pulled to populate the CRM Deal
#: ``custom_income_years`` grid (CRM Grant Income Year). The lookup back to
#: the parent Opportunity is ``Grant_Or_Donation__c``.
INCOME_YEAR_FIELDS = (
    "Id",
    "Income_year__c",
    "IY_Amount__c",
    "IY_TotalOpex__c",
    "IY_TotalCapex__c",
    "IY_ConfirmedOpex__c",
    "IY_ConfirmedCapex__c",
)

#: Salesforce ``npe01__OppPayment__c`` (NPSP Payment) fields pulled to
#: populate the CRM Deal ``custom_payment_schedule`` grid (CRM Grant
#: Payment). The lookup back to the parent Opportunity is
#: ``npe01__Opportunity__c`` (NOT the quirky ``Probability__c`` lookup).
PAYMENT_FIELDS = (
    "Id",
    "npe01__Scheduled_Date__c",
    "npe01__Payment_Amount__c",
    "npe01__Payment_Date__c",
    "npe01__Paid__c",
    "npe01__Written_Off__c",
)


class OpportunitySyncer(BaseSyncer):
    salesforce_object = "Opportunity"
    frappe_doctype = "CRM Deal"
    high_water_field = "last_sync_opportunity"
    order_in_sync = 50
    extra_soql_fields = ("IsClosed", "CloseDate")

    def enrich_values(
        self, rec: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        # Derive ``closed_date`` from ``IsClosed=true`` + ``CloseDate``;
        # mapping rows already populate ``expected_closure_date``.
        if rec.get("IsClosed") and rec.get("CloseDate"):
            try:
                values["closed_date"] = str(get_datetime(rec["CloseDate"]).date())
            except (TypeError, ValueError) as e:
                frappe.log_error(
                    title="OpportunitySyncer.enrich_values",
                    message=(
                        f"Unparseable CloseDate for SF Opportunity "
                        f"{rec.get('Id') or '?'}: {rec.get('CloseDate')!r}\n{e}"
                    ),
                )

        # Fallback contact resolution: if ContactId was empty, try the
        # NPSP primary-contact link.
        if not values.get("contact"):
            primary = rec.get("npsp__Primary_Contact__c")
            if primary:
                resolved = map_contact(primary)
                if resolved:
                    values["contact"] = resolved

        return values

    # ------------------------------------------------------------------
    # Child related lists → CRM Deal child tables
    # ------------------------------------------------------------------
    def after_upsert(self, rec: dict[str, Any], doc) -> None:
        """Rebuild the Income Year Breakdown and Payment Schedule grids.

        Salesforce is treated as the source of truth: each grid is cleared
        and repopulated from the related ``Income_year__c`` /
        ``npe01__OppPayment__c`` records. Any rows added manually in Frappe
        are therefore overwritten on the next sync.

        NOTE: editing only a child record in Salesforce does not bump the
        parent Opportunity's ``SystemModstamp``, so the incremental sync
        will not re-pull an Opportunity solely because one of its payments
        or income-year rows changed. Use the backfill command
        (``frappe_salesforce.api.sync.backfill_deal_child_tables``) or a
        periodic full refresh to reconcile.
        """
        opp_id = rec.get("Id")
        if not opp_id:
            return
        has_income_years, has_payments = self._grant_child_tables_present()
        # Benches without the PEAS grant child tables (these doctypes/fields
        # are owned by a separate app, not frappe_salesforce) get a clean
        # no-op — and crucially we skip the SF queries so we don't burn API
        # calls fetching child records there's nowhere to store.
        if not (has_income_years or has_payments):
            return
        changed = False
        if has_income_years:
            changed |= self._sync_income_years(opp_id, doc)
        if has_payments:
            changed |= self._sync_payments(opp_id, doc)
        if changed:
            doc.save(ignore_permissions=True)

    def _grant_child_tables_present(self) -> tuple[bool, bool]:
        """Whether the CRM Deal grant child tables exist on this bench.

        Cached per syncer instance; one ``get_meta`` for the whole run.
        """
        cached = getattr(self, "_grant_child_tables_cache", None)
        if cached is None:
            meta = frappe.get_meta(self.frappe_doctype)
            cached = (
                bool(meta.get_field("custom_income_years")),
                bool(meta.get_field("custom_payment_schedule")),
            )
            self._grant_child_tables_cache = cached
        return cached

    def _sync_income_years(self, opp_id: str, doc) -> bool:
        soql = (
            f"SELECT {', '.join(INCOME_YEAR_FIELDS)} FROM Income_year__c "
            f"WHERE Grant_Or_Donation__c = '{opp_id}'"
        )
        rows = [build_income_year_row(r) for r in self.client.query(soql)]
        doc.set("custom_income_years", rows)
        return True

    def _sync_payments(self, opp_id: str, doc) -> bool:
        today = now_datetime().date()
        soql = (
            f"SELECT {', '.join(PAYMENT_FIELDS)} FROM npe01__OppPayment__c "
            f"WHERE npe01__Opportunity__c = '{opp_id}'"
        )
        rows = [build_payment_row(r, today) for r in self.client.query(soql)]
        doc.set("custom_payment_schedule", [r for r in rows if r is not None])
        return True


# ----------------------------------------------------------------------
# Pure row builders (no Frappe / network deps — unit-testable)
# ----------------------------------------------------------------------
def build_income_year_row(rec: dict[str, Any]) -> dict[str, Any]:
    """Map one ``Income_year__c`` record to a CRM Grant Income Year row.

    ``opex_percentage`` is derived (SF has no direct field): the OpEx
    share of the income-year amount. ``cost_type``, ``country_allocation``
    and ``confirmation_date`` have no Salesforce source on this object and
    are left blank.
    """
    amount = rec.get("IY_Amount__c")
    opex = rec.get("IY_TotalOpex__c")
    return {
        "income_year": rec.get("Income_year__c"),
        "iy_amount": amount,
        "opex_percentage": _opex_percentage(amount, opex),
        "iy_opex": opex,
        "iy_capex": rec.get("IY_TotalCapex__c"),
        "iy_confirmed_opex": rec.get("IY_ConfirmedOpex__c"),
        "iy_confirmed_capex": rec.get("IY_ConfirmedCapex__c"),
    }


def build_payment_row(
    rec: dict[str, Any], today: date | None = None
) -> dict[str, Any] | None:
    """Map one ``npe01__OppPayment__c`` record to a CRM Grant Payment row.

    ``expected_payment_date`` is mandatory on CRM Grant Payment. Salesforce
    payments don't always carry ``npe01__Scheduled_Date__c`` (e.g. a payment
    logged after the fact), so we fall back to the actual payment date
    (``npe01__Payment_Date__c``). If *neither* date exists we return
    ``None`` to signal "skip this row" — emitting a row without the
    mandatory field raises ``MandatoryError`` and fails the whole CRM Deal
    save, which would drop every other (valid) grid row too.

    ``amount_received`` / ``payment_received_date`` are only populated once
    the payment is marked paid in Salesforce. ``fx_difference`` and
    ``notes`` have no Salesforce source and are left blank.
    """
    paid = bool(rec.get("npe01__Paid__c"))
    written_off = bool(rec.get("npe01__Written_Off__c"))
    scheduled = rec.get("npe01__Scheduled_Date__c")
    payment_date = rec.get("npe01__Payment_Date__c")
    amount = rec.get("npe01__Payment_Amount__c")
    expected_date = scheduled or payment_date
    if not expected_date:
        return None
    return {
        "expected_payment_date": expected_date,
        "amount_expected": amount,
        "payment_received_date": payment_date if paid else None,
        "amount_received": amount if paid else None,
        "payment_status": derive_payment_status(paid, written_off, scheduled, today),
    }


def derive_payment_status(
    paid: bool,
    written_off: bool,
    scheduled_date: Any,
    today: date | None,
) -> str:
    """Collapse SF payment booleans into the CRM Grant Payment picklist.

    Picklist options are Pending / Received / Overdue / Partially Received.
    Salesforce's "Written Off" has no equivalent option, so it is folded
    into Overdue.
    """
    if paid:
        return "Received"
    if written_off:
        return "Overdue"
    sched = _coerce_date(scheduled_date)
    if sched and today and sched < today:
        return "Overdue"
    return "Pending"


def _opex_percentage(amount: Any, opex: Any) -> float | None:
    if amount in (None, "", 0) or opex is None:
        return None
    try:
        return round(float(opex) / float(amount) * 100, 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _coerce_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
