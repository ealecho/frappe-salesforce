from frappe import _, throw
from frappe.model.document import Document


class SalesforceFieldMapping(Document):
    def validate(self):
        # The natural uniqueness key for a mapping row is the
        # ``(sf_input, frappe_field)`` tuple, NOT the SF field alone.
        # Many legitimate mappings re-use a single SF field to populate
        # multiple Frappe targets — e.g. ``Opportunity.StageName`` maps
        # to both ``status`` (via ``deal_stage``) and ``lost_reason``
        # (via ``deal_lost_reason``). Multi-input rows (where
        # ``sf_fields`` is set instead of ``sf_field``) are keyed by the
        # full sf_fields blob.
        seen: set[tuple[str, str]] = set()
        for row in self.field_mappings or []:
            sf_input = (row.sf_field or "").lower()
            if not sf_input:
                # Multi-input: key by the sf_fields blob (already
                # newline-separated, lowercase to be lenient).
                sf_input = (getattr(row, "sf_fields", "") or "").lower()
            if not sf_input:
                continue
            frappe_field = (row.frappe_field or "").lower()
            key = (sf_input, frappe_field)
            if key in seen:
                throw(
                    _("Duplicate mapping: {0} → {1}").format(
                        row.sf_field or row.sf_fields,
                        row.frappe_field,
                    )
                )
            seen.add(key)
