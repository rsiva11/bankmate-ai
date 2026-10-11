# Architecture

## Components
| Layer | File(s) | Responsibility |
|---|---|---|
| UI | `app.py` | Streamlit dashboard, chat, privacy Q&A, trace display |
| Orchestrator | `supervisor.py`, `intents.py` | Guards, intent classification, validation, allowlist routing, combining results |
| LLM | `llm.py` | Ollama HTTP client; typed errors (unavailable / timeout / invalid output) |
| Agents | `agents/*.py` | One responsibility each; return `AgentResult` (data, trace, sources, error) |
| Tools | `tools/*.py` | Predefined functions: HTTP client to bank API, pure risk rules, pure loan maths |
| Bank API | `api/*.py` | FastAPI + Pydantic over `data/demo_data.json` |
| RAG | `rag/*.py` | Load, clean, chunk, embed, store (ChromaDB), retrieve |

## Request flow (combined request)
1. **Guard**: length limit; credential-like content blocked.
2. **Classify**: Ollama (`format=json`, temperature 0) returns `{"intents": [...]}`.
3. **Validate**: Pydantic `IntentPlan` (enum of allowed intents). Failure → rule-based fallback, logged in trace.
4. **Parameters**: loan amount / tenure / count re-extracted from the user's text with regex (model numbers ignored).
5. **Route**: `ROUTES[intent]` is a fixed dict of Python functions. No dynamic dispatch from model text.
6. **Execute**: each agent calls tools; tools call the REST API; results carry trace steps.
7. **Combine**: renderers format real data into markdown; sources and trace are attached.

## Why these choices
- **LLM for language, code for facts**: avoids hallucinated money or policy.
- **Separate API process**: demonstrates a service boundary like a real bank integration; agents never read the JSON file.
- **Rules as pure functions with config**: auditable and testable.
- **Visible fallback**: reliability without hiding failures.
- **Distance cut-off in retrieval**: the mechanism that lets the Privacy agent say "not enough information".
- **Embedding backend recorded in the Chroma collection**: prevents mixing incompatible vectors.

## Trust boundaries
LLM output (untrusted data) → validated → allowlist. User text → guarded. Retrieved text → used only as quoted context, shown with source. Bank API → synthetic only.
