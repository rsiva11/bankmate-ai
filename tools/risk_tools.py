"""Transparent, configurable risk rules. Pure functions: easy to test and explain.

A triggered rule produces a RISK ALERT for human review. It is never a
confirmed-fraud verdict.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from config import Settings, get_settings

RULE_DESCRIPTIONS = {
    "large_amount": "Debit amount at or above the configured large-transaction threshold",
    "rapid_succession": "Several debits within a short time window",
    "repeated_amount": "The same debit amount repeated several times",
    "demo_risk_indicator": "Transaction carries a configured synthetic risk indicator",
}


def _ts(txn: dict) -> datetime:
    return datetime.fromisoformat(txn["timestamp"])


def _severity(rule_count: int) -> str:
    return "high" if rule_count >= 3 else "medium" if rule_count == 2 else "low"


def analyze_transactions(transactions: list, settings: Optional[Settings] = None) -> list:
    """Return a list of risk alerts (dicts), newest first. Empty list = nothing flagged."""
    s = settings or get_settings()
    debits = [t for t in transactions if t.get("type") == "debit"]
    reasons = defaultdict(dict)  # txn_id -> {rule: explanation}

    # Rule 1: unusually large debit
    for t in debits:
        if t["amount"] >= s.risk_large_amount:
            reasons[t["txn_id"]]["large_amount"] = (
                f"Amount {t['amount']:,.2f} is at or above the {s.risk_large_amount:,.0f} threshold."
            )

    # Rule 2: burst of debits inside a sliding time window
    ordered = sorted(debits, key=_ts)
    window = timedelta(minutes=s.risk_burst_window_minutes)
    left = 0
    for right in range(len(ordered)):
        while _ts(ordered[right]) - _ts(ordered[left]) > window:
            left += 1
        if right - left + 1 >= s.risk_burst_count:
            count = right - left + 1
            for k in range(left, right + 1):
                reasons[ordered[k]["txn_id"]]["rapid_succession"] = (
                    f"Part of a group of {count} debits within {s.risk_burst_window_minutes} minutes "
                    f"(rule: {s.risk_burst_count}+)."
                )

    # Rule 3: identical amounts repeated
    by_amount = defaultdict(list)
    for t in debits:
        by_amount[t["amount"]].append(t)
    for amount, group in by_amount.items():
        if len(group) >= s.risk_repeat_count:
            for t in group:
                reasons[t["txn_id"]]["repeated_amount"] = (
                    f"Amount {amount:,.2f} appears {len(group)} times (rule: {s.risk_repeat_count}+)."
                )

    # Rule 4: configurable demo indicators
    for t in debits:
        if t.get("risk_indicator") and t["risk_indicator"] in s.risk_demo_indicators:
            reasons[t["txn_id"]]["demo_risk_indicator"] = (
                f"Synthetic indicator '{t['risk_indicator']}' is on the configured watch list."
            )

    by_id = {t["txn_id"]: t for t in debits}
    alerts = []
    for txn_id, rules in reasons.items():
        t = by_id[txn_id]
        alerts.append({
            "txn_id": txn_id,
            "timestamp": t["timestamp"],
            "description": t["description"],
            "amount": t["amount"],
            "rules": sorted(rules),
            "severity": _severity(len(rules)),
            "explanation": " ".join(rules[r] for r in sorted(rules)),
            "classification": "risk_alert",  # deliberately NOT "fraud"
        })
    alerts.sort(key=lambda a: a["timestamp"], reverse=True)
    return alerts
