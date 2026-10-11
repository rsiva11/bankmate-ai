# Demo video script (about 8 minutes)

**0:00 Intro (30 s).** "BankMate AI is a privacy-aware multi-agent banking assistant. Everything is synthetic and runs locally on my laptop with a 3B model via Ollama. It is an independent simulation, not an SBI product."

**0:30 Setup tour (60 s).** Show three terminals: API on 8000 (open `/docs`), Streamlit on 8501, `ollama list`. Show sidebar status (Ollama ready, knowledge base chunk count) and the disclaimer.

**1:30 Dashboard (60 s).** Select Aarav: balance card, transactions, no risk alerts, loan estimator (change amount/tenure). Switch to Priya: risk panel shows alerts. Point out "alerts for review, not confirmed fraud". Note chat clears on customer switch.

**2:30 Use cases 1-4 in chat (120 s).** Click the suggested questions one by one. After each, open **Agent activity**: intents, agent, tools, status. Stress that the numbers come from the API and the loan answer carries the educational disclaimer.

**4:30 Multi-agent (90 s).** Use case 5 as Priya. Show three agents invoked, combined answer, trace table with `get_transactions`, `analyze_transactions`, `check_loan_eligibility`. Try Rohan: loan "outside demo limits", failed condition explained.

**6:00 Privacy RAG (90 s).** Use case 6. Show the grounded answer, numbered sources, page/section, clickable URL, retrieval date. Ask an unrelated question ("chocolate cake recipe") → "knowledge base does not contain enough information".

**7:30 Safety + tests (60 s).** Type "my OTP is 123456": blocked. Stop Ollama and ask again: trace shows `fallback`. Run `python -m pytest` → all pass. Close with limitations (synthetic data, demo auth, 3B model, illustrative rules).
