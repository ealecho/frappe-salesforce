"""Salesforce integration exceptions."""


class SalesforceError(Exception):
    """Base exception for all Salesforce integration errors."""


class SalesforceAuthError(SalesforceError):
    """Raised when authentication with Salesforce fails."""


class SalesforceAPIError(SalesforceError):
    """Raised when a Salesforce REST/SOQL call fails."""

    def __init__(self, message: str, status_code: int | None = None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class SalesforceRateLimitError(SalesforceAPIError):
    """Raised when Salesforce API daily limit is approaching or exceeded."""


class SalesforceBudgetExceeded(SalesforceError):
    """Raised when an app-level per-tick or per-day call budget is hit.

    Distinct from :class:`SalesforceRateLimitError`, which reflects the
    Salesforce org's actual daily quota. Budgets are a defensive cap we
    impose on ourselves to guarantee we can never blow through a quota.
    """


class SalesforceConfigurationError(SalesforceError):
    """Raised when Salesforce Settings are incomplete or invalid."""
