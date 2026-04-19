"""Stub tests for auth module. Full integration tests require a live SF sandbox."""

import pytest

from frappe_salesforce.salesforce.exceptions import (
    SalesforceAuthError,
    SalesforceConfigurationError,
)


def test_exception_hierarchy():
    assert issubclass(SalesforceAuthError, Exception)
    assert issubclass(SalesforceConfigurationError, Exception)


@pytest.mark.skip(reason="Requires a live Salesforce sandbox with credentials")
def test_fetch_new_token_integration():
    """Integration test placeholder."""
    pass
