"""Simulated banking API: lookup, balance, transactions, errors."""


def test_customer_lookup_success(client):
    r = client.get("/customers/CUST1001")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Aarav Sharma" and "balance" not in body


def test_balance_is_correct(client):
    r = client.get("/customers/CUST1002/balance")
    assert r.status_code == 200 and r.json()["balance"] == 124300.75


def test_transactions_newest_first_and_limit(client):
    r = client.get("/customers/CUST1001/transactions", params={"limit": 3})
    body = r.json()
    assert body["count"] == 3
    stamps = [t["timestamp"] for t in body["transactions"]]
    assert stamps == sorted(stamps, reverse=True)
    assert body["transactions"][0]["txn_id"] == "T1001-08"


def test_unknown_customer_404(client):
    assert client.get("/customers/CUST9999").status_code == 404
    assert client.get("/customers/CUST9999/balance").status_code == 404


def test_malformed_customer_id_400(client):
    assert client.get("/customers/not-an-id").status_code == 400
    assert client.get("/customers/CUST1001; DROP").status_code in (400, 404)


def test_invalid_limit_422(client):
    assert client.get("/customers/CUST1001/transactions", params={"limit": 0}).status_code == 422
    assert client.get("/customers/CUST1001/transactions", params={"limit": "abc"}).status_code == 422


def test_loan_endpoint_valid_and_invalid(client):
    ok = client.post("/loans/eligibility", json={"customer_id": "CUST1001", "loan_amount": 200000})
    assert ok.status_code == 200 and ok.json()["eligible"] is True
    assert client.post("/loans/eligibility", json={"customer_id": "CUST1001", "loan_amount": -5}).status_code == 422
    assert client.post("/loans/eligibility", json={"customer_id": "bad", "loan_amount": 5000}).status_code == 422
    assert client.post("/loans/eligibility", json={"loan_amount": 5000}).status_code == 422
    assert client.post("/loans/eligibility", json={"customer_id": "CUST9999", "loan_amount": 5000}).status_code == 404


def test_risk_alerts_endpoint(client):
    body = client.get("/customers/CUST1002/risk-alerts").json()
    assert body["alert_count"] > 0 and "NOT confirmed fraud" in body["note"]
    assert client.get("/customers/CUST1001/risk-alerts").json()["alert_count"] == 0


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"
