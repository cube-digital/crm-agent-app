"""Tenant isolation: tenant B must never read tenant A's rows."""
from __future__ import annotations

from tests.conftest import auth, signup


def test_cross_tenant_read_is_forbidden(client):
    a = signup(client)
    b = signup(client)

    # A deal that belongs to tenant A.
    deals_a = client.get("/deals", headers=auth(a["access_token"])).json()["items"]
    assert deals_a, "tenant A should have seeded deals"
    a_deal_id = deals_a[0]["id"]

    # Tenant B fetching A's deal -> 403 (exists, but not yours), not 404.
    res = client.get(f"/deals/{a_deal_id}", headers=auth(b["access_token"]))
    assert res.status_code == 403, res.text

    # B's own deal list never contains A's deal.
    deals_b = client.get("/deals", headers=auth(b["access_token"])).json()["items"]
    assert a_deal_id not in {d["id"] for d in deals_b}


def test_missing_token_is_unauthorized(client):
    res = client.get("/deals")
    assert res.status_code == 401


def test_unknown_row_is_404_within_tenant(client):
    a = signup(client)
    res = client.get("/deals/does-not-exist", headers=auth(a["access_token"]))
    assert res.status_code == 404
