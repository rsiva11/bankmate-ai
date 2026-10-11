"""Pydantic request/response models for the simulated banking API."""
from typing import Optional

from pydantic import BaseModel, Field


class CustomerOut(BaseModel):
    customer_id: str
    name: str
    account_type: str
    account_masked: str
    monthly_income: float
    existing_emi: float


class CustomerListItem(BaseModel):
    customer_id: str
    name: str


class BalanceOut(BaseModel):
    customer_id: str
    account_masked: str
    currency: str = "INR"
    balance: float


class TransactionOut(BaseModel):
    txn_id: str
    timestamp: str
    description: str
    amount: float
    type: str
    category: str
    location: str
    risk_indicator: Optional[str] = None


class TransactionsOut(BaseModel):
    customer_id: str
    count: int
    transactions: list[TransactionOut]


class RiskAlertOut(BaseModel):
    txn_id: str
    timestamp: str
    description: str
    amount: float
    rules: list[str]
    severity: str
    explanation: str
    classification: str


class RiskAlertsOut(BaseModel):
    customer_id: str
    transactions_analyzed: int
    alert_count: int
    alerts: list[RiskAlertOut]
    note: str


class LoanRequest(BaseModel):
    customer_id: str = Field(pattern=r"^CUST\d{4}$")
    loan_amount: float = Field(gt=0, le=100_000_000)
    tenure_months: Optional[int] = Field(default=None, ge=6, le=360)


class LoanConditionOut(BaseModel):
    name: str
    rule: str
    met: bool
    detail: str


class LoanResponse(BaseModel):
    customer_id: str
    loan_amount: float
    tenure_months: int
    annual_interest_pct: float
    monthly_income: float
    existing_emi: float
    proposed_emi: float
    dti_ratio: float
    residual_income: float
    conditions: list[LoanConditionOut]
    eligible: bool
    outcome: str
    estimated_max_loan: float
    disclaimer: str
