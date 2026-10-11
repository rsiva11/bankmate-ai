"""Supervisor / Orchestrator.

Flow: guard input -> classify intents (LLM -> validated JSON, or rule-based in mock mode)
-> normalise -> ALLOWLIST routing -> run agents -> combine real outputs + trace.

Security properties:
* Model output is parsed as data (JSON) and validated; it is never executed.
* Only intents in ROUTES can reach an agent function.
* Numbers (loan amount, counts) are re-extracted from the user's own text, so a
  hallucinating model cannot invent them.
"""
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

import llm
from agents import banking_agent, credit_agent, privacy_agent, risk_agent
from agents.base import AgentResult, TraceStep
from config import get_settings
from formatting import (render_balance, render_loan, render_privacy, render_risk,
                        render_transactions)
from intents import (Intent, IntentPlan, PlanValidationError, extract_loan_amount,
                     extract_tenure_months, extract_transaction_limit, mock_classify,
                     normalize_intents, parse_plan)
from tools.banking_tools import InvalidCustomerId, validate_customer_id

MAX_MESSAGE_CHARS = 500

CLASSIFIER_PROMPT = """You are an intent classifier for a banking assistant. Reply with ONE JSON object only.
Allowed intents (use these exact strings):
- account_balance: asks for balance
- transaction_history: asks to list/show transactions or statements
- fraud_check: asks about suspicious/unusual/fraud activity
- loan_eligibility: asks about qualifying for a loan
- privacy_policy_question: asks what SBI's public privacy statement/policy says (data collected, cookies, sharing, security, retention, contact)
- combined_banking_request: several banking things in one message
- unsupported_request: anything else (greetings, transfers, payments, general chat)
JSON format: {"intents": ["..."], "transaction_limit": null, "loan_amount": null, "loan_tenure_months": null}
List EVERY intent the message asks for.
Examples:
"Show my balance" -> {"intents": ["account_balance"]}
"Check whether anything looks suspicious" -> {"intents": ["fraud_check"]}
"Show my transactions and check for fraud and see if I qualify for a loan of 2 lakh" -> {"intents": ["combined_banking_request","transaction_history","fraud_check","loan_eligibility"], "loan_amount": 200000}
"What does SBI say about customer information?" -> {"intents": ["privacy_policy_question"]}
"Transfer 500 to Ravi" -> {"intents": ["unsupported_request"]}"""

SENSITIVE_RE = re.compile(r"\b(otp|pin|cvv|password|passcode|passwd)\b|\b\d{12,19}\b", re.I)

HELP_TEXT = ("I can help with: **account balance**, **recent transactions**, **suspicious-activity "
             "checks**, **loan eligibility estimates**, and **questions about SBI's public privacy "
             "information**. Try: \"Show my last five transactions.\"")

SENSITIVE_TEXT = ("For your safety, please don't type passwords, PINs, OTPs, CVVs or full card/account "
                  "numbers here. BankMate AI never needs them. Your message was not processed.")


@dataclass
class SupervisorResponse:
    message: str
    customer_id: str
    status: str                       # success | partial | error | unsupported | needs_info | blocked
    text: str
    intents: list = field(default_factory=list)
    agents: list = field(default_factory=list)
    trace: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    results: dict = field(default_factory=dict)


@dataclass
class Context:
    customer_id: str
    message: str
    plan: IntentPlan
    retriever: Optional[object] = None


# ---- allowlisted routes: intent -> (agent label, function, renderer) ----
def _balance(ctx):      return banking_agent.account_balance(ctx.customer_id)
def _transactions(ctx): return banking_agent.transaction_history(
    ctx.customer_id, ctx.plan.transaction_limit or 5)
def _fraud(ctx):        return risk_agent.check_activity(ctx.customer_id)
def _loan(ctx):         return credit_agent.estimate_loan(
    ctx.customer_id, ctx.plan.loan_amount, ctx.plan.loan_tenure_months)
def _privacy(ctx):      return privacy_agent.answer_question(ctx.message, ctx.retriever)


ROUTES: dict = {
    Intent.account_balance: (banking_agent.NAME, _balance, render_balance),
    Intent.transaction_history: (banking_agent.NAME, _transactions, render_transactions),
    Intent.fraud_check: (risk_agent.NAME, _fraud, render_risk),
    Intent.loan_eligibility: (credit_agent.NAME, _loan, render_loan),
    Intent.privacy_policy_question: (privacy_agent.NAME, _privacy, render_privacy),
}


def classify(message: str) -> tuple:
    """Return (IntentPlan, [TraceStep]). Falls back visibly if the LLM fails."""
    s = get_settings()
    if s.mock_llm:
        return mock_classify(message), [TraceStep("Supervisor", "classify_intent", "info",
                                                  "mock mode: rule-based classifier")]
    try:
        plan = parse_plan(llm.chat_json(CLASSIFIER_PROMPT, message))
        return plan, [TraceStep("Supervisor", "classify_intent", "ok", f"LLM {s.ollama_model}")]
    except (llm.LLMError, PlanValidationError) as exc:
        return mock_classify(message), [TraceStep(
            "Supervisor", "classify_intent", "fallback",
            f"{exc} Used the rule-based classifier instead.")]


def handle_message(message: str, customer_id: str, retriever=None) -> SupervisorResponse:
    message = (message or "").strip()
    resp = SupervisorResponse(message=message, customer_id=customer_id, status="success", text="")

    # 1. input guards
    if not message:
        resp.status, resp.text = "unsupported", "Please type a question. " + HELP_TEXT
        return resp
    if len(message) > MAX_MESSAGE_CHARS:
        resp.status, resp.text = "unsupported", f"Please keep messages under {MAX_MESSAGE_CHARS} characters."
        return resp
    if SENSITIVE_RE.search(message):
        resp.status, resp.text = "blocked", SENSITIVE_TEXT
        resp.trace.append(TraceStep("Supervisor", "input_guard", "error", "credential-like content blocked"))
        return resp

    # 2. classify + validate
    plan, steps = classify(message)
    resp.trace.extend(steps)
    intents = normalize_intents(plan.intents)
    resp.intents = [i.value for i in intents]

    # deterministic parameters (override anything the model suggested)
    plan.loan_amount = extract_loan_amount(message)
    plan.transaction_limit = extract_transaction_limit(message)
    plan.loan_tenure_months = extract_tenure_months(message)

    if intents == [Intent.unsupported_request]:
        resp.status, resp.text = "unsupported", HELP_TEXT
        return resp

    # 3. customer validation (privacy questions don't need an account)
    needs_account = any(i != Intent.privacy_policy_question for i in intents if i in ROUTES)
    if needs_account:
        try:
            validate_customer_id(customer_id)
        except InvalidCustomerId as exc:
            resp.status, resp.text = "error", f"Cannot continue: {exc}"
            resp.trace.append(TraceStep("Supervisor", "validate_customer", "error", str(exc)))
            return resp

    # 4. allowlisted routing
    ctx = Context(customer_id, message, plan, retriever)
    sections, ok_count, run_count, needs_info = [], 0, 0, False
    for intent in intents:
        route = ROUTES.get(intent)
        if route is None:      # combined_banking_request is a label, not an executable route
            continue
        agent_name, fn, renderer = route
        run_count += 1
        result: AgentResult = fn(ctx)
        resp.trace.extend(result.trace)
        resp.results[intent.value] = result
        if agent_name not in resp.agents:
            resp.agents.append(agent_name)
        resp.sources.extend(result.sources)
        if result.ok:
            ok_count += 1
            sections.append(renderer(result))
        else:
            needs_info = needs_info or result.needs_info
            sections.append(f"**{agent_name}:** {result.error}")

    resp.text = "\n\n".join(sections)
    resp.status = ("needs_info" if needs_info and ok_count == 0 else
                   "success" if ok_count == run_count else
                   "partial" if ok_count else "error")
    return resp