"""Educational loan estimate. NOT official SBI lending criteria."""
from typing import Optional

from config import Settings, get_settings

LOAN_DISCLAIMER = (
    "Educational simulation only: this uses a configurable demo debt-to-income rule, "
    "not official SBI lending criteria, and is not a loan approval or credit decision."
)


def calculate_emi(principal: float, annual_rate_pct: float, months: int) -> float:
    """Standard reducing-balance EMI: P*r*(1+r)^n / ((1+r)^n - 1)."""
    if principal <= 0 or months <= 0:
        raise ValueError("principal and months must be positive")
    r = annual_rate_pct / 12 / 100
    if r == 0:
        return principal / months
    growth = (1 + r) ** months
    return principal * r * growth / (growth - 1)


def max_loan_for_emi(emi_capacity: float, annual_rate_pct: float, months: int) -> float:
    """Inverse of calculate_emi: the principal a given EMI can service."""
    if emi_capacity <= 0:
        return 0.0
    r = annual_rate_pct / 12 / 100
    if r == 0:
        return emi_capacity * months
    growth = (1 + r) ** months
    return emi_capacity * (growth - 1) / (r * growth)


def evaluate_loan(monthly_income: float, existing_emi: float, loan_amount: float,
                  tenure_months: Optional[int] = None,
                  settings: Optional[Settings] = None) -> dict:
    s = settings or get_settings()
    months = tenure_months or s.loan_default_tenure_months
    rate = s.loan_annual_interest_pct
    proposed_emi = calculate_emi(loan_amount, rate, months)
    total_emi = existing_emi + proposed_emi
    dti = total_emi / monthly_income
    residual = monthly_income - total_emi
    capacity = max(0.0, monthly_income * s.loan_max_dti - existing_emi)

    conditions = [
        {
            "name": "debt_to_income",
            "rule": f"(existing EMI + proposed EMI) / monthly income <= {s.loan_max_dti:.0%}",
            "met": dti <= s.loan_max_dti,
            "detail": f"Your ratio would be {dti:.1%}.",
        },
        {
            "name": "residual_income",
            "rule": f"Income left after all EMIs >= Rs {s.loan_min_residual_income:,.0f}",
            "met": residual >= s.loan_min_residual_income,
            "detail": f"Income left after all EMIs would be Rs {residual:,.0f}.",
        },
    ]
    eligible = all(c["met"] for c in conditions)
    return {
        "loan_amount": round(loan_amount, 2),
        "tenure_months": months,
        "annual_interest_pct": rate,
        "monthly_income": monthly_income,
        "existing_emi": existing_emi,
        "proposed_emi": round(proposed_emi, 2),
        "dti_ratio": round(dti, 4),
        "residual_income": round(residual, 2),
        "conditions": conditions,
        "eligible": eligible,
        "outcome": "likely_within_demo_limits" if eligible else "likely_outside_demo_limits",
        "estimated_max_loan": round(max_loan_for_emi(capacity, rate, months), 2),
        "disclaimer": LOAN_DISCLAIMER,
    }
