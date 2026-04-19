from frappe.model.document import Document


class SalesforceFieldMapping(Document):
    def validate(self):
        seen = set()
        for row in self.field_mappings or []:
            key = (row.sf_field or "").lower()
            if not key:
                continue
            if key in seen:
                from frappe import throw, _

                throw(_("Duplicate Salesforce field: {0}").format(row.sf_field))
            seen.add(key)
