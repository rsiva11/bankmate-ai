"""Shared result types for all agents."""
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from tools.banking_tools import BankAPIError, BankAPIUnavailable, InvalidCustomerId

# Errors an agent tool is allowed to turn into a friendly message. Anything else
# is a real bug and is deliberately NOT swallowed.
EXPECTED_TOOL_ERRORS = (BankAPIError, BankAPIUnavailable, InvalidCustomerId)


@dataclass
class TraceStep:
    agent: str
    step: str
    status: str  # "ok" | "error" | "fallback" | "info"
    detail: str = ""


@dataclass
class AgentResult:
    agent: str
    ok: bool = True
    data: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)
    error: Optional[str] = None
    sources: list = field(default_factory=list)
    needs_info: bool = False


def run_tool(result: AgentResult, name: str, fn: Callable, *args, **kwargs) -> Any:
    """Call one allowlisted tool, record a trace step, return its value (or None on failure)."""
    try:
        value = fn(*args, **kwargs)
    except EXPECTED_TOOL_ERRORS as exc:
        result.ok = False
        result.error = str(exc)
        result.trace.append(TraceStep(result.agent, name, "error", str(exc)))
        return None
    result.trace.append(TraceStep(result.agent, name, "ok"))
    return value
