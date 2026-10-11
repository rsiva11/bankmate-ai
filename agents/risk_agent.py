"""Risk/Fraud Agent: applies transparent rules to the customer's transactions.

It reports RISK ALERTS for review. It never declares confirmed fraud.
"""
from agents.base import AgentResult, TraceStep, run_tool
from config import get_settings
from tools import banking_tools
from tools.risk_tools import RULE_DESCRIPTIONS, analyze_transactions

NAME = "Risk/Fraud Agent"


def check_activity(customer_id: str) -> AgentResult:
    res = AgentResult(NAME)
    data = run_tool(res, "get_transactions", banking_tools.get_transactions, customer_id, 100)
    if data is None:
        return res
    s = get_settings()
    alerts = analyze_transactions(data["transactions"], s)
    res.trace.append(TraceStep(NAME, "analyze_transactions", "ok", f"{len(alerts)} alert(s)"))
    res.data = {
        "transactions_analyzed": data["count"],
        "alerts": alerts,
        "rules": RULE_DESCRIPTIONS,
        "thresholds": {
            "large_amount": s.risk_large_amount,
            "burst": f"{s.risk_burst_count}+ debits in {s.risk_burst_window_minutes} min",
            "repeat": f"{s.risk_repeat_count}+ identical amounts",
            "indicators": list(s.risk_demo_indicators),
        },
    }
    return res
