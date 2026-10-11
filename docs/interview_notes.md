# Technical interview explanation

**One-liner.** A supervisor agent uses a local LLM to understand a banking request, validates the result, and routes it through a fixed allowlist to specialised agents that call simulated banking APIs or a RAG knowledge base, then combines their real outputs with an audit trail.

**Orchestrator.** `supervisor.handle_message`: guard → `classify` (Ollama JSON) → Pydantic `IntentPlan` → `normalize_intents` → loop over `ROUTES`. Multiple intents run multiple agents; `combined_banking_request` is only a label.

**Agents and tools.** Banking (`get_customer/get_balance/get_transactions`), Risk (rules in `risk_tools.analyze_transactions`: large amount, burst in time window, repeated identical amount, configured indicator), Credit (reducing-balance EMI, DTI ≤ 50% and residual-income rule from config), Privacy (RAG). Tools are plain functions; the LLM cannot add tools or URLs.

**LLM role and hallucination control.** The model classifies intent and phrases the privacy answer from retrieved text. It never produces balances, alerts or loan decisions (templates render real data). Numeric parameters are extracted from the user's text by regex. Invalid output → validation error → visible rule-based fallback.

**RAG.** Fetch/import → extract (HTML headings, PDF pages) → clean → 900/150 overlapping chunks → MiniLM embeddings (local) → ChromaDB (cosine) with metadata (url, title, section, page, date). Query → top-k → distance cut-off → numbered context prompt with strict instructions → answer + citations. No relevant chunks → "insufficient information".

**Privacy.** Synthetic data, local inference, credential-pattern blocking, no secrets committed, telemetry off, no conversation persistence, chat cleared on switch, explicit disclaimers, no compliance claims.

**Testing.** 87 tests; mock mode and a hash embedder make everything deterministic and offline; LLM calls are monkeypatched to test timeouts, outages and bad JSON.

**Limitations to state honestly.** Keyword fallback is crude; 3B model can err; retrieval threshold needs tuning on real documents; demo auth; rules are illustrative; PDF headings heuristic.

**Likely questions.** *Why not let the LLM answer numbers?* Hallucination risk. *Why a separate API?* Service boundary, realistic integration, testable. *How would you scale it?* Real auth, async API, message queue for events, better evals, larger model/hosted private inference, hybrid (BM25 + vector) retrieval. *Why is a rule hit not fraud?* False positives; needs analyst review.
