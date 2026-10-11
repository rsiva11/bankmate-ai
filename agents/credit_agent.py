"""Credit/Loan Agent: educational loan estimate using the demo DTI rule."""
from typing import Optional

from agents.base import AgentResult, run_tool
from tools import banking_tools

NAME = "Credit/Loan Agent"


def estimate_loan(customer_id: str, loan_amount: Optional[float],
                  tenure_months: Optional[int] = None) -> AgentResult:
    res = AgentResult(NAME)
    if not loan_amount:
        res.ok = False
        res.needs_info = True
        res.error = "Please tell me the loan amount, e.g. \"Can I get a loan of Rs 2,00,000?\""
        return res
    data = run_tool(res, "check_loan_eligibility", banking_tools.check_loan_eligibility,
                    customer_id, loan_amount, tenure_months)
    if data is None:
        return res
    res.data = data
    return res
