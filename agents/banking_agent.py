"""Banking Agent: customer profile, balance, recent transactions."""
from agents.base import AgentResult, run_tool
from tools import banking_tools

NAME = "Banking Agent"


def account_balance(customer_id: str) -> AgentResult:
    res = AgentResult(NAME)
    customer = run_tool(res, "get_customer", banking_tools.get_customer, customer_id)
    if customer is None:
        return res
    balance = run_tool(res, "get_balance", banking_tools.get_balance, customer_id)
    if balance is None:
        return res
    res.data = {"customer": customer, "balance": balance}
    return res


def transaction_history(customer_id: str, limit: int = 5) -> AgentResult:
    res = AgentResult(NAME)
    data = run_tool(res, "get_transactions", banking_tools.get_transactions, customer_id, limit)
    if data is None:
        return res
    res.data = {"transactions": data["transactions"], "count": data["count"], "limit": limit}
    return res
