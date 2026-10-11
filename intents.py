"""Intent plan: schema, validation, deterministic parameter extraction, and the
rule-based classifier used for mock mode and as a visible fallback."""
import json
import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, ValidationError, field_validator


class Intent(str, Enum):
    account_balance = "account_balance"
    transaction_history = "transaction_history"
    fraud_check = "fraud_check"
    loan_eligibility = "loan_eligibility"
    privacy_policy_question = "privacy_policy_question"
    combined_banking_request = "combined_banking_request"
    unsupported_request = "unsupported_request"


CONCRETE = [Intent.account_balance, Intent.transaction_history, Intent.fraud_check,
            Intent.loan_eligibility, Intent.privacy_policy_question]


class PlanValidationError(Exception):
    pass


class IntentPlan(BaseModel):
    intents: list[Intent] = Field(min_length=1, max_length=7)
    transaction_limit: Optional[int] = Field(default=None, ge=1, le=50)
    loan_amount: Optional[float] = Field(default=None, gt=0)
    loan_tenure_months: Optional[int] = Field(default=None, ge=6, le=360)

    @field_validator("intents", mode="before")
    @classmethod
    def _clean_names(cls, v):
        if isinstance(v, list):
            return [x.strip().lower() if isinstance(x, str) else x for x in v]
        return v


def parse_plan(raw: str) -> IntentPlan:
    """Validate raw LLM text as an IntentPlan. Never evaluates anything."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PlanValidationError(f"Model output is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PlanValidationError("Model output must be a JSON object.")
    try:
        return IntentPlan.model_validate(data)
    except ValidationError as exc:
        raise PlanValidationError(f"Model output failed validation: {exc.errors()[0]['msg']}") from exc


def normalize_intents(intents: list) -> list:
    """Ordered, de-duplicated intent list with sensible combined/unsupported handling."""
    found = {i for i in intents}
    concrete = [i for i in CONCRETE if i in found]
    if not concrete and Intent.combined_banking_request in found:
        concrete = [Intent.account_balance, Intent.transaction_history, Intent.fraud_check]
    if not concrete:
        return [Intent.unsupported_request]
    banking_count = len([i for i in concrete if i != Intent.privacy_policy_question])
    if banking_count >= 2 or Intent.combined_banking_request in found:
        return [Intent.combined_banking_request] + concrete
    return concrete


# ---------- deterministic parameter extraction (never trust LLM numbers) ----------
_WORD_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
             "eight": 8, "nine": 9, "ten": 10}
_AMOUNT_RE = re.compile(r"(?:(?<![a-z])(₹|rs\.?|inr))?\s*(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|crores?|k)?\b", re.I)


def extract_loan_amount(text: str) -> Optional[float]:
    for m in _AMOUNT_RE.finditer(text):
        prefix, num, unit = m.group(1), m.group(2), (m.group(3) or "").lower()
        try:
            value = float(num.replace(",", ""))
        except ValueError:
            continue
        if unit.startswith(("lakh", "lac")):
            value *= 100_000
        elif unit.startswith("crore"):
            value *= 10_000_000
        elif unit == "k":
            value *= 1_000
        elif not prefix and value < 10_000:
            continue  # bare small numbers are counts/years, not money
        if value > 0:
            return value
    return None


def extract_transaction_limit(text: str, default: int = 5) -> int:
    low = text.lower()
    m = re.search(r"\b(?:last|latest|recent|past|previous)\s+(\d{1,2}|" + "|".join(_WORD_NUM) + r")\b", low)
    if not m:
        m = re.search(r"\b(\d{1,2}|" + "|".join(_WORD_NUM) + r")\s+(?:recent\s+|latest\s+)?transactions?\b", low)
    if m:
        tok = m.group(1)
        n = int(tok) if tok.isdigit() else _WORD_NUM[tok]
        return max(1, min(n, 20))
    return default


def extract_tenure_months(text: str) -> Optional[int]:
    m = re.search(r"\b(\d{1,2})\s*(months?|years?|yrs?)\b", text.lower())
    if not m:
        return None
    n = int(m.group(1)) * (12 if m.group(2).startswith(("y",)) else 1)
    return n if 6 <= n <= 360 else None


# ---------- rule-based classifier (mock mode + visible fallback) ----------
_KW = {
    Intent.account_balance: ("balance", "how much money", "funds"),
    Intent.transaction_history: ("transaction", "bank statement", "account statement", "history", "spent", "spending", "purchases"),
    Intent.fraud_check: ("suspicious", "fraud", "unusual", "risk", "scam", "anomal", "alert"),
    Intent.loan_eligibility: ("loan", "qualify", "eligib", "borrow"),
    Intent.privacy_policy_question: ("privacy", "personal data", "customer information", "data protection",
                                     "cookie", "consent", "sbi say", "sbi policy", "confidential",
                                     "personal information", "sbi collect", "sbi share", "sbi protect"),
}
_LIST_WORDS = ("show", "list", "display", "history", "last", "recent", "latest", "statement", "view")


def mock_classify(message: str) -> IntentPlan:
    low = message.lower()
    intents = [i for i, kws in _KW.items() if any(k in low for k in kws)]
    # "check whether transactions look suspicious" is a risk request, not a statement request
    if Intent.fraud_check in intents and Intent.transaction_history in intents \
            and not any(w in low for w in _LIST_WORDS):
        intents.remove(Intent.transaction_history)
    if not intents:
        intents = [Intent.unsupported_request]
    return IntentPlan(intents=intents)