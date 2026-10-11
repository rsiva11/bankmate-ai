"""Loan EMI and eligibility maths."""
import pytest

from agents import credit_agent
from tools.credit_tools import calculate_emi, evaluate_loan, max_loan_for_emi


def test_emi_known_value():
    # 2,00,000 at 10.5% p.a. for 36 months, standard reducing-balance formula
    assert calculate_emi(200000, 10.5, 36) == pytest.approx(6500.5, abs=1.0)


def test_emi_zero_interest():
    assert calculate_emi(120000, 0, 12) == pytest.approx(10000)


def test_emi_rejects_bad_input():
    with pytest.raises(ValueError):
        calculate_emi(0, 10, 12)
    with pytest.raises(ValueError):
        calculate_emi(1000, 10, 0)


def test_max_loan_is_inverse_of_emi():
    emi = calculate_emi(300000, 10.5, 48)
    assert max_loan_for_emi(emi, 10.5, 48) == pytest.approx(300000, rel=1e-6)


def test_eligible_case():
    r = evaluate_loan(75000, 8000, 200000)
    assert r["eligible"] and all(c["met"] for c in r["conditions"])
    assert r["dti_ratio"] < 0.5


def test_ineligible_case_explains_failed_condition():
    r = evaluate_loan(42000, 16000, 200000)
    assert not r["eligible"]
    failed = [c for c in r["conditions"] if not c["met"]]
    assert failed and failed[0]["name"] == "debt_to_income"
    assert "simulation" in r["disclaimer"].lower()


def test_dti_threshold_configurable(monkeypatch):
    monkeypatch.setenv("LOAN_MAX_DTI", "0.9")
    from config import get_settings
    assert evaluate_loan(42000, 16000, 200000, settings=get_settings())["conditions"][0]["met"]


def test_credit_agent_via_api(bank):
    assert credit_agent.estimate_loan("CUST1001", 200000).data["eligible"] is True
    assert credit_agent.estimate_loan("CUST1003", 200000).data["eligible"] is False


def test_credit_agent_needs_amount(bank):
    res = credit_agent.estimate_loan("CUST1001", None)
    assert not res.ok and res.needs_info
