"""Banking agent + tools, including API failure handling."""
from agents import banking_agent
from tools import banking_tools


def test_get_customer_success(bank):
    assert banking_tools.get_customer("CUST1001")["name"] == "Aarav Sharma"


def test_balance_via_agent(bank):
    res = banking_agent.account_balance("CUST1001")
    assert res.ok and res.data["balance"]["balance"] == 85420.50
    assert [s.step for s in res.trace] == ["get_customer", "get_balance"]


def test_transaction_history_via_agent(bank):
    res = banking_agent.transaction_history("CUST1001", 5)
    assert res.ok and len(res.data["transactions"]) == 5


def test_unknown_customer_handled(bank):
    res = banking_agent.account_balance("CUST9999")
    assert not res.ok and "not found" in res.error.lower()
    assert res.trace[0].status == "error"


def test_invalid_customer_id_rejected_before_any_request(bank):
    res = banking_agent.account_balance("../etc/passwd")
    assert not res.ok and "CUST1001" in res.error


def test_api_unreachable_reported(monkeypatch):
    monkeypatch.setenv("BANK_API_BASE_URL", "http://127.0.0.1:9")  # nothing listens here
    banking_tools.set_http_client(None)
    res = banking_agent.account_balance("CUST1001")
    assert not res.ok and "not reachable" in res.error
