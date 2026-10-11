"""Supervisor: intent validation, allowlist routing, multi-agent combination, LLM failures."""
import pytest

import llm
import supervisor
from intents import (Intent, PlanValidationError, extract_loan_amount, extract_transaction_limit,
                     mock_classify, normalize_intents, parse_plan)

CID = "CUST1002"


# ---------- plan validation ----------
def test_parse_plan_valid():
    plan = parse_plan('{"intents": ["account_balance", "Fraud_Check"], "transaction_limit": 3}')
    assert plan.intents == [Intent.account_balance, Intent.fraud_check] and plan.transaction_limit == 3


def test_parse_plan_accepts_code_fences():
    assert parse_plan('```json\n{"intents": ["account_balance"]}\n```').intents == [Intent.account_balance]


@pytest.mark.parametrize("raw", [
    "not json at all",
    '["account_balance"]',
    '{"intents": []}',
    '{"intents": ["delete_all_accounts"]}',
    '{"intents": ["account_balance"], "loan_amount": -5}',
    '{"nothing": 1}',
])
def test_parse_plan_rejects_invalid(raw):
    with pytest.raises(PlanValidationError):
        parse_plan(raw)


def test_normalize_combined_and_unsupported():
    out = normalize_intents([Intent.account_balance, Intent.fraud_check])
    assert out[0] == Intent.combined_banking_request and len(out) == 3
    assert normalize_intents([Intent.unsupported_request]) == [Intent.unsupported_request]
    assert normalize_intents([Intent.unsupported_request, Intent.account_balance]) == [Intent.account_balance]


def test_parameter_extraction():
    assert extract_loan_amount("loan of ₹2,00,000") == 200000
    assert extract_loan_amount("loan of 2.5 lakh") == 250000
    assert extract_loan_amount("show last 5 transactions") is None
    assert extract_transaction_limit("last five transactions") == 5
    assert extract_transaction_limit("last 3 transactions") == 3
    assert extract_transaction_limit("show transactions") == 5


# ---------- the six required use cases (mock mode) ----------
def test_uc1_balance(bank):
    r = supervisor.handle_message("Show my account balance.", "CUST1001")
    assert r.status == "success" and "₹85,420.50" in r.text and r.agents == ["Banking Agent"]


def test_uc2_last_five_transactions(bank):
    r = supervisor.handle_message("Show my last five transactions.", "CUST1001")
    assert r.status == "success" and r.intents == ["transaction_history"]
    assert r.text.count("| debit") + r.text.count("| credit") == 5


def test_uc3_suspicious(bank):
    r = supervisor.handle_message("Check whether any transactions look suspicious.", CID)
    assert r.agents == ["Risk/Fraud Agent"] and "not confirmed fraud" in r.text
    assert "GlobalWire" in r.text
    clean = supervisor.handle_message("Check whether any transactions look suspicious.", "CUST1001")
    assert "no unusual activity" in clean.text


def test_uc4_loan(bank):
    r = supervisor.handle_message("Estimate whether I may qualify for a loan of ₹2,00,000.", "CUST1001")
    assert r.status == "success" and "₹2,00,000.00" in r.text and "simulation" in r.text.lower()
    r3 = supervisor.handle_message("Estimate whether I may qualify for a loan of ₹2,00,000.", "CUST1003")
    assert "outside" in r3.text and "Not met" in r3.text


def test_uc5_multi_agent_combined(bank):
    msg = "Show my transactions, check for suspicious activity and estimate my loan eligibility for Rs 2,00,000."
    r = supervisor.handle_message(msg, CID)
    assert r.intents[0] == "combined_banking_request"
    assert set(r.agents) == {"Banking Agent", "Risk/Fraud Agent", "Credit/Loan Agent"}
    assert r.status == "success"
    # all three real outputs appear in one answer
    assert "Your last" in r.text and "Risk check" in r.text and "Loan estimate" in r.text
    steps = {(t.agent, t.step) for t in r.trace}
    assert ("Banking Agent", "get_transactions") in steps
    assert ("Credit/Loan Agent", "check_loan_eligibility") in steps


# ---------- edge cases and safety ----------
def test_loan_without_amount_asks_for_it(bank):
    r = supervisor.handle_message("Can I qualify for a loan?", "CUST1001")
    assert r.status == "needs_info" and "loan amount" in r.text


def test_unsupported_request(bank):
    r = supervisor.handle_message("Transfer 5000 to my friend", "CUST1001")
    assert r.status == "unsupported" and r.agents == []
    assert supervisor.handle_message("hello", "CUST1001").status == "unsupported"


def test_empty_and_overlong_messages(bank):
    assert supervisor.handle_message("   ", "CUST1001").status == "unsupported"
    assert supervisor.handle_message("x" * 600, "CUST1001").status == "unsupported"


@pytest.mark.parametrize("msg", ["my OTP is 482913, show balance", "here is my password hunter2",
                                 "card 4111111111111111 balance"])
def test_credentials_are_blocked(bank, msg):
    r = supervisor.handle_message(msg, "CUST1001")
    assert r.status == "blocked" and r.agents == []


def test_unknown_and_invalid_customer(bank):
    assert supervisor.handle_message("Show my balance", "CUST9999").status == "error"
    r = supervisor.handle_message("Show my balance", "bogus")
    assert r.status == "error" and "CUST1001" in r.text


def test_partial_success_reports_each_agent(bank, monkeypatch):
    from agents import credit_agent
    from agents.base import AgentResult
    monkeypatch.setitem(supervisor.ROUTES, Intent.loan_eligibility,
                        (credit_agent.NAME, lambda ctx: AgentResult(credit_agent.NAME, ok=False, error="boom"),
                         lambda r: ""))
    r = supervisor.handle_message("Show my balance and check my loan eligibility for 2 lakh", "CUST1001")
    assert r.status == "partial" and "boom" in r.text and "Account balance" in r.text


# ---------- LLM mode: success, bad output, timeout, outage ----------
@pytest.fixture
def llm_mode(monkeypatch):
    monkeypatch.setenv("BANKMATE_MOCK_LLM", "0")


def test_llm_valid_json_is_used(bank, llm_mode, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda s, u: '{"intents": ["account_balance"]}')
    r = supervisor.handle_message("what's in my account?", "CUST1001")
    assert r.status == "success" and "₹85,420.50" in r.text
    assert r.trace[0].status == "ok"


def test_llm_invalid_output_falls_back_visibly(bank, llm_mode, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda s, u: "I think you want your balance!")
    r = supervisor.handle_message("Show my account balance.", "CUST1001")
    assert r.status == "success"
    assert r.trace[0].status == "fallback" and "not valid JSON" in r.trace[0].detail


def test_llm_timeout_and_outage_fall_back(bank, llm_mode, monkeypatch):
    for exc in (llm.LLMTimeout("timed out"), llm.LLMUnavailable("down")):
        def boom(s, u, exc=exc):
            raise exc
        monkeypatch.setattr(llm, "chat_json", boom)
        r = supervisor.handle_message("Show my account balance.", "CUST1001")
        assert r.status == "success" and r.trace[0].status == "fallback"


def test_llm_cannot_invent_loan_amount(bank, llm_mode, monkeypatch):
    monkeypatch.setattr(llm, "chat_json",
                        lambda s, u: '{"intents": ["loan_eligibility"], "loan_amount": 9999999}')
    r = supervisor.handle_message("Can I get a loan?", "CUST1001")
    assert r.status == "needs_info"  # the model's number was ignored


def test_llm_cannot_route_outside_allowlist(bank, llm_mode, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda s, u: '{"intents": ["transfer_funds"]}')
    r = supervisor.handle_message("Show my account balance.", "CUST1001")
    assert r.trace[0].status == "fallback" and r.agents == ["Banking Agent"]
