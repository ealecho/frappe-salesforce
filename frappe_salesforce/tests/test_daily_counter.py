"""The per-day API counter must read back what it counted.

Regression guard: the counter was incremented with ``cache.incr`` (raw key,
raw integer) but read with ``cache.get_value`` (site-prefixed key,
unpickled), so it always read 0 and the per-day budget never tripped.
"""

import pytest

pytest.importorskip("frappe")

import frappe  # noqa: E402
from frappe.utils.redis_wrapper import RedisWrapper  # noqa: E402

from frappe_salesforce.salesforce import client  # noqa: E402


class _FakeRedis:
    """Redis semantics for the calls the counter makes; Frappe's own key scheme."""

    make_key = RedisWrapper.make_key

    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def incr(self, key):
        value = int(self.store.get(key, 0)) + 1
        self.store[key] = str(value).encode()
        return value

    def expire(self, key, seconds):
        pass


@pytest.fixture
def cache(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(frappe, "cache", fake)
    monkeypatch.setattr(frappe.local, "conf", frappe._dict(db_name="site_a"), raising=False)
    return fake


def test_counter_reads_back_what_it_counted(cache):
    assert client._daily_counter_get() == 0
    client._daily_counter_incr()
    client._daily_counter_incr()
    assert client._daily_counter_get() == 2


def test_counter_is_per_site(cache, monkeypatch):
    client._daily_counter_incr()
    monkeypatch.setattr(frappe.local, "conf", frappe._dict(db_name="site_b"))
    assert client._daily_counter_get() == 0
