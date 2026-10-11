"""Tools the agents may call: thin, validated HTTP client for the banking API.

This file is the ONLY place agents reach the bank. Everything here is a
predefined function; the LLM never chooses or builds URLs.
"""
import re
from typing import Optional

import requests

from config import get_settings

_CUSTOMER_ID_RE = re.compile(r"^CUST\d{4}$")
_client = None  # tests inject a FastAPI TestClient here


class InvalidCustomerId(ValueError):
    pass


class BankAPIError(Exception):
    """The API answered with an error status (4xx/5xx)."""

    def __init__(self, status_code: int, message: str):
        super().__init__(f"Bank API error {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class BankAPIUnavailable(Exception):
    """The API could not be reached or timed out."""


def set_http_client(client) -> None:
    global _client
    _client = client


def validate_customer_id(customer_id: str) -> str:
    if not isinstance(customer_id, str) or not _CUSTOMER_ID_RE.match(customer_id):
        raise InvalidCustomerId("Customer ID must look like CUST1001.")
    return customer_id


def _request(method: str, path: str, json_body: Optional[dict] = None, params: Optional[dict] = None):
    s = get_settings()
    try:
        if _client is not None:
            resp = _client.request(method, path, json=json_body, params=params)
        else:
            resp = requests.request(method, s.bank_api_base_url.rstrip("/") + path,
                                    json=json_body, params=params, timeout=s.bank_api_timeout)
    except (requests.ConnectionError, requests.Timeout) as exc:
        raise BankAPIUnavailable(
            "Banking API is not reachable. Start it with: uvicorn api.main:app --port 8000") from exc
    if resp.status_code >= 400:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text
        raise BankAPIError(resp.status_code, str(detail))
    return resp.json()


def list_customers() -> list:
    return _request("GET", "/customers")


def get_customer(customer_id: str) -> dict:
    return _request("GET", f"/customers/{validate_customer_id(customer_id)}")


def get_balance(customer_id: str) -> dict:
    return _request("GET", f"/customers/{validate_customer_id(customer_id)}/balance")


def get_transactions(customer_id: str, limit: int = 10) -> dict:
    return _request("GET", f"/customers/{validate_customer_id(customer_id)}/transactions",
                    params={"limit": int(limit)})


def get_risk_alerts(customer_id: str) -> dict:
    return _request("GET", f"/customers/{validate_customer_id(customer_id)}/risk-alerts")


def check_loan_eligibility(customer_id: str, loan_amount: float, tenure_months: Optional[int] = None) -> dict:
    body = {"customer_id": validate_customer_id(customer_id), "loan_amount": float(loan_amount)}
    if tenure_months:
        body["tenure_months"] = int(tenure_months)
    return _request("POST", "/loans/eligibility", json_body=body)
