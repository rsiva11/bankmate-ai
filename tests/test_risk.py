"""Fraud-rule behaviour: flagged and non-flagged cases."""
import pytest

from agents import risk_agent
from config import get_settings
from tools.risk_tools import analyze_transactions


def _txns(customer_id):
    from api import store
    return store.find_customer(customer_id)["transactions"]


def test_clean_customer_not_flagged():
    assert analyze_transactions(_txns("CUST1001")) == []
    assert analyze_transactions(_txns("CUST1004")) == []


def test_large_foreign_transfer_flagged():
    alerts = {a["txn_id"]: a for a in analyze_transactions(_txns("CUST1002"))}
    big = alerts["T1002-04"]
    assert {"large_amount", "demo_risk_indicator"} <= set(big["rules"])


def test_rapid_succession_flagged():
    alerts = {a["txn_id"]: a for a in analyze_transactions(_txns("CUST1002"))}
    for tid in ("T1002-05", "T1002-06", "T1002-07", "T1002-08"):
        assert "rapid_succession" in alerts[tid]["rules"]


def test_repeated_identical_amounts_flagged():
    alerts = {a["txn_id"]: a for a in analyze_transactions(_txns("CUST1003"))}
    assert {"T1003-04", "T1003-05", "T1003-06"} <= set(alerts)
    assert all("repeated_amount" in alerts[t]["rules"] for t in ("T1003-04", "T1003-05", "T1003-06"))


def test_alerts_are_never_labelled_fraud():
    for cid in ("CUST1002", "CUST1003"):
        for a in analyze_transactions(_txns(cid)):
            assert a["classification"] == "risk_alert"
            assert "fraud" not in a["explanation"].lower()


def test_credits_are_ignored():
    salary = {"txn_id": "X1", "timestamp": "2026-01-01T09:00:00", "description": "Salary",
              "amount": 900000, "type": "credit", "risk_indicator": "foreign_location"}
    assert analyze_transactions([salary]) == []


def test_thresholds_are_configurable(monkeypatch):
    monkeypatch.setenv("RISK_LARGE_AMOUNT", "1000")
    assert len(analyze_transactions(_txns("CUST1001"), get_settings())) > 0


def test_risk_agent_end_to_end(bank):
    res = risk_agent.check_activity("CUST1002")
    assert res.ok and len(res.data["alerts"]) >= 5
    clean = risk_agent.check_activity("CUST1001")
    assert clean.ok and clean.data["alerts"] == []


def test_risk_agent_unknown_customer(bank):
    assert not risk_agent.check_activity("CUST9999").ok
