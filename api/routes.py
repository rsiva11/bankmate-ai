"""REST endpoints of the simulated bank. Synthetic data only."""
from fastapi import APIRouter, HTTPException, Query

from api import store
from api.schemas import (BalanceOut, CustomerListItem, CustomerOut, LoanRequest,
                         LoanResponse, RiskAlertsOut, TransactionsOut)
from tools.credit_tools import evaluate_loan
from tools.risk_tools import analyze_transactions

router = APIRouter()


def _customer_or_error(customer_id: str) -> dict:
    if not store.CUSTOMER_ID_RE.match(customer_id):
        raise HTTPException(status_code=400, detail="Invalid customer ID format. Expected e.g. CUST1001.")
    customer = store.find_customer(customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found.")
    return customer


@router.get("/customers", response_model=list[CustomerListItem])
def list_customers():
    return [{"customer_id": c["customer_id"], "name": c["name"]} for c in store.all_customers()]


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: str):
    return _customer_or_error(customer_id)


@router.get("/customers/{customer_id}/balance", response_model=BalanceOut)
def get_balance(customer_id: str):
    c = _customer_or_error(customer_id)
    return {"customer_id": c["customer_id"], "account_masked": c["account_masked"], "balance": c["balance"]}


@router.get("/customers/{customer_id}/transactions", response_model=TransactionsOut)
def get_transactions(customer_id: str, limit: int = Query(default=10, ge=1, le=100)):
    c = _customer_or_error(customer_id)
    newest_first = sorted(c["transactions"], key=lambda t: t["timestamp"], reverse=True)[:limit]
    return {"customer_id": c["customer_id"], "count": len(newest_first), "transactions": newest_first}


@router.get("/customers/{customer_id}/risk-alerts", response_model=RiskAlertsOut)
def get_risk_alerts(customer_id: str):
    c = _customer_or_error(customer_id)
    alerts = analyze_transactions(c["transactions"])
    return {
        "customer_id": c["customer_id"],
        "transactions_analyzed": len(c["transactions"]),
        "alert_count": len(alerts),
        "alerts": alerts,
        "note": "Alerts come from demo rules and are NOT confirmed fraud.",
    }


@router.post("/loans/eligibility", response_model=LoanResponse)
def loan_eligibility(req: LoanRequest):
    c = _customer_or_error(req.customer_id)
    result = evaluate_loan(c["monthly_income"], c["existing_emi"], req.loan_amount, req.tenure_months)
    return {"customer_id": c["customer_id"], **result}
