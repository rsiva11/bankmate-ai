"""Turn real agent data into user-facing markdown. Numbers come from data, never from the LLM."""
import re

from agents.base import AgentResult
from tools.credit_tools import LOAN_DISCLAIMER


def format_inr(value: float) -> str:
    sign = "-" if value < 0 else ""
    whole, frac = f"{abs(value):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        whole = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head) + "," + tail
    return f"{sign}₹{whole}.{frac}"


def render_balance(res: AgentResult) -> str:
    c, b = res.data["customer"], res.data["balance"]
    return (f"**Account balance** for {c['name']} ({b['account_masked']}): "
            f"**{format_inr(b['balance'])}**")


def render_transactions(res: AgentResult) -> str:
    txns = res.data["transactions"]
    rows = ["| Date | Description | Type | Amount |", "|---|---|---|---:|"]
    for t in txns:
        sign = "+" if t["type"] == "credit" else "-"
        rows.append(f"| {t['timestamp'][:16].replace('T', ' ')} | {t['description']} | {t['type']} | "
                    f"{sign}{format_inr(t['amount'])} |")
    return f"**Your last {len(txns)} transaction(s):**\n\n" + "\n".join(rows)


def render_risk(res: AgentResult) -> str:
    alerts, n = res.data["alerts"], res.data["transactions_analyzed"]
    if not alerts:
        return (f"**Risk check:** I reviewed {n} transactions against the demo rules and found "
                "**no unusual activity**.")
    lines = [f"**Risk check:** {len(alerts)} of {n} transactions triggered demo risk rules. "
             "These are **alerts for review, not confirmed fraud**."]
    for a in alerts:
        lines.append(f"- {a['timestamp'][:16].replace('T', ' ')} · {a['description']} · "
                     f"{format_inr(a['amount'])} · severity **{a['severity']}** — {a['explanation']}")
    return "\n".join(lines)


def render_loan(res: AgentResult) -> str:
    d = res.data
    verdict = ("**likely within** the demo limits" if d["eligible"] else "**likely outside** the demo limits")
    lines = [
        f"**Loan estimate** for {format_inr(d['loan_amount'])} over {d['tenure_months']} months at "
        f"{d['annual_interest_pct']}% p.a.: this is {verdict}.",
        f"- Estimated new EMI: {format_inr(d['proposed_emi'])} (existing EMI: {format_inr(d['existing_emi'])}, "
        f"monthly income: {format_inr(d['monthly_income'])})",
    ]
    for c in d["conditions"]:
        lines.append(f"- {'✅ Met' if c['met'] else '❌ Not met'}: {c['rule']}. {c['detail']}")
    lines.append(f"- Rough maximum loan under the debt-to-income rule: {format_inr(d['estimated_max_loan'])}")
    lines.append(f"\n*{LOAN_DISCLAIMER}*")
    return "\n".join(lines)


def render_privacy(res: AgentResult) -> str:
    text = res.data["answer"]
    if res.sources:
        refs = "; ".join(f"[{s['id']}] {s['title']}" + (f", p.{s['page']}" if s.get("page") else "")
                         for s in res.sources)
        text += f"\n\n*Sources: {refs}.* (Public SBI documents; not your synthetic account data.)"
    return text
