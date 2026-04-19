import frappe
from frappe.model.document import Document


class SalesforceSettings(Document):
    def validate(self):
        if self.api_version and not self.api_version.startswith("v"):
            self.api_version = f"v{self.api_version}"
        if self.login_url:
            self.login_url = self.login_url.rstrip("/")
        if self.instance_url:
            self.instance_url = self.instance_url.rstrip("/")
