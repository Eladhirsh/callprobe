"""didyoureally: catch AI agents that misreport what they did."""

from .adapters import from_openai_messages, load_trace
from .extract import GivenClaims, LLMExtractor
from .matcher import Finding, Verdict, check, problems
from .schema import Claim, ToolCall, ToolSpec, Trace

__version__ = "0.1.0"

__all__ = [
    "Claim",
    "Finding",
    "GivenClaims",
    "LLMExtractor",
    "ToolCall",
    "ToolSpec",
    "Trace",
    "Verdict",
    "check",
    "from_openai_messages",
    "load_trace",
    "problems",
]
