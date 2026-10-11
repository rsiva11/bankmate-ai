import pandas as pd
import streamlit as st

import llm
import supervisor
from agents import banking_agent, credit_agent, risk_agent
from config import DISCLAIMER, get_settings
from formatting import format_inr
from rag.retriever import Retriever
from tools import banking_tools

st.set_page_config(page_title="BankMate AI", page_icon="🏦", layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 2rem; max-width: 1200px;}
  h1 {color:#0b4f8a; margin-bottom:0;}
  .subtitle {color:#5b6b7c; font-size:1.05rem; margin-bottom:1rem;}
  div[data-testid="stMetric"] {background:#f3f6fa; border:1px solid #e1e8f0; padding:0.8rem 1rem; border-radius:10px;}
  .disclaimer {background:#fff8e6; border-left:4px solid #e0a800; padding:0.6rem 0.9rem; border-radius:6px; font-size:0.9rem;}
</style>
""", unsafe_allow_html=True)

SUGGESTIONS = [
    "Show my account balance.",
    "Show my last five transactions.",
    "Check whether any transactions look suspicious.",
    "Estimate whether I may qualify for a loan of ₹2,00,000.",
    "Show my transactions, check for suspicious activity and estimate my loan eligibility for ₹2,00,000.",
    "What does the public SBI privacy statement say about customer information?",
    "What personal information does SBI collect and how does it protect it?",
]

settings = get_settings()


# ---------------- helpers ----------------
@st.cache_data(ttl=20, show_spinner=False)
def load_customers():
    return banking_tools.list_customers()


def render_sources(sources):
    for s in sources:
        label = f"[{s['id']}] {s['title']}" + (f" · page {s['page']}" if s.get("page") else "")
        with st.expander(label):
            if s.get("section"):
                st.caption(f"Section: {s['section']}")
            st.write(s["excerpt"])
            if str(s["url"]).startswith("http"):
                st.markdown(f"[Open source document]({s['url']})")
            else:
                st.caption(f"Source: {s['url']} (manually imported file)")
            st.caption(f"Retrieved: {s.get('retrieval_date', 'n/a')} · relevance distance {s['distance']} (lower is closer)")


def render_trace(resp):
    with st.expander("🔎 Agent activity", expanded=False):
        st.markdown(f"**Detected intents:** {', '.join(resp.intents) or '—'}")
        st.markdown(f"**Selected agents:** {', '.join(resp.agents) or '—'}")
        st.markdown(f"**Status:** `{resp.status}`")
        if resp.trace:
            st.dataframe(pd.DataFrame([{"agent": t.agent, "tool / step": t.step, "status": t.status,
                                        "detail": t.detail} for t in resp.trace]),
                         hide_index=True, width="stretch")
        errors = [t for t in resp.trace if t.status == "error"]
        if errors:
            st.error("Errors: " + " | ".join(t.detail for t in errors))


def render_response(resp):
    st.markdown(resp.text)
    if resp.sources:
        st.markdown("**Sources**")
        render_sources(resp.sources)
    render_trace(resp)


# ---------------- sidebar ----------------
with st.sidebar:
    st.header("🏦 BankMate AI")
    try:
        customers = load_customers()
    except (banking_tools.BankAPIUnavailable, banking_tools.BankAPIError) as exc:
        st.error(str(exc))
        st.code("uvicorn api.main:app --port 8000", language="bash")
        st.stop()
    options = {f"{c['name']} ({c['customer_id']})": c["customer_id"] for c in customers}
    label = st.selectbox("Synthetic demo customer", list(options))
    customer_id = options[label]
    st.caption("Demo selector only. This is not real authentication.")

    if st.session_state.get("active_customer") != customer_id:
        st.session_state.messages = []          # don't carry one customer's chat to another
        st.session_state.active_customer = customer_id
    if st.button("🧹 Clear chat", width="stretch"):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.subheader("System status")
    if settings.mock_llm:
        st.info("LLM mode: **mock** (deterministic, no Ollama)")
    else:
        status = llm.ollama_status()
        if status["running"] and status["model_ready"]:
            st.success(f"Ollama ready · {status['model']}")
        elif status["running"]:
            st.warning(f"Model missing. Run: ollama pull {status['model']}")
        else:
            st.warning("Ollama not running: using rule-based fallback")
    st.caption(f"Knowledge base: {Retriever(settings).count()} chunks")
    st.divider()
    st.markdown(f'<div class="disclaimer">{DISCLAIMER}</div>', unsafe_allow_html=True)

st.title("BankMate AI")
st.markdown('<div class="subtitle">Privacy-Aware Multi-Agent Banking Assistant</div>', unsafe_allow_html=True)
st.markdown('<div class="disclaimer">Educational simulation · synthetic data only · not an official SBI '
            'or banking service. Never enter real banking credentials.</div>', unsafe_allow_html=True)

tab_dash, tab_chat = st.tabs(["📊 Dashboard", "💬 Assistant chat"])

with tab_dash:
    summary = banking_agent.account_balance(customer_id)
    if not summary.ok:
        st.error(summary.error)
    else:
        c, b = summary.data["customer"], summary.data["balance"]
        cols = st.columns(4)
        cols[0].metric("Account balance", format_inr(b["balance"]))
        cols[1].metric("Account", f"{c['account_type']} · {c['account_masked'][-4:]}")
        cols[2].metric("Monthly income (synthetic)", format_inr(c["monthly_income"]))
        cols[3].metric("Existing monthly EMI", format_inr(c["existing_emi"]))

        left, right = st.columns([3, 2])
        with left:
            st.subheader("Recent transactions")
            tx = banking_agent.transaction_history(customer_id, 10)
            if tx.ok:
                df = pd.DataFrame(tx.data["transactions"])[
                    ["timestamp", "description", "category", "type", "amount", "location"]]
                df["timestamp"] = df["timestamp"].str.replace("T", " ").str[:16]
                st.dataframe(df, hide_index=True, width="stretch")
            else:
                st.error(tx.error)
        with right:
            st.subheader("Risk alerts")
            risk = risk_agent.check_activity(customer_id)
            if not risk.ok:
                st.error(risk.error)
            elif not risk.data["alerts"]:
                st.success(f"No demo risk rules triggered across {risk.data['transactions_analyzed']} transactions.")
            else:
                st.warning(f"{len(risk.data['alerts'])} transaction(s) triggered demo rules. "
                           "These are alerts for review, **not confirmed fraud**.")
                for a in risk.data["alerts"]:
                    with st.expander(f"{a['description']} · {format_inr(a['amount'])} · {a['severity']}"):
                        st.write(a["explanation"])
                        st.caption(f"{a['timestamp'][:16].replace('T', ' ')} · rules: {', '.join(a['rules'])}")

        st.subheader("Loan estimate")
        lc1, lc2 = st.columns(2)
        amount = lc1.number_input("Loan amount (₹)", min_value=10000, max_value=10_000_000,
                                  value=200000, step=10000)
        tenure = lc2.selectbox("Tenure (months)", [12, 24, 36, 48, 60, 84],
                               index=2)
        loan = credit_agent.estimate_loan(customer_id, float(amount), int(tenure))
        if not loan.ok:
            st.error(loan.error)
        else:
            d = loan.data
            m1, m2, m3 = st.columns(3)
            m1.metric("Estimated new EMI", format_inr(d["proposed_emi"]))
            m2.metric("Debt-to-income after loan", f"{d['dti_ratio']:.1%}")
            m3.metric("Demo-rule outcome", "Within limits" if d["eligible"] else "Outside limits")
            for cnd in d["conditions"]:
                (st.success if cnd["met"] else st.error)(f"{cnd['rule']}. {cnd['detail']}")
            st.caption(d["disclaimer"])

with tab_chat:
    st.caption("Try a suggested question or type your own. Banking questions use your synthetic account; "
               "privacy questions are answered from public SBI documents with citations.")
    cols = st.columns(2)
    for i, q in enumerate(SUGGESTIONS):
        if cols[i % 2].button(q, key=f"sg{i}", width="stretch"):
            st.session_state.pending = q

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            if m["role"] == "user":
                st.markdown(m["content"])
            else:
                render_response(m["response"])

    prompt = st.chat_input("Ask about your balance, transactions, risk, loans or SBI privacy info…")
    prompt = st.session_state.pop("pending", None) or prompt
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Agents are working…"):
                response = supervisor.handle_message(prompt, customer_id)
            render_response(response)
        st.session_state.messages.append({"role": "assistant", "response": response})
